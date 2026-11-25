    const canvas = document.querySelector("canvas");
    const ctx = canvas.getContext("2d");
    const menu = document.getElementById("menu");
    const missionTitle = document.getElementById("mission-title");
    const missionCopy = document.getElementById("mission-copy");
    const levelProgress = document.getElementById("level-progress");
    const startButton = document.getElementById("start");
    const touchControls = document.getElementById("touch-controls");
    const notice = document.getElementById("notice");
    const score = document.getElementById("score");
    const wave = document.getElementById("wave");
    const levelNumber = document.getElementById("level-number");
    const levelName = document.getElementById("level-name");
    const hull = document.getElementById("hull");
    const weaponLabel = document.getElementById("weapon");
    const pickupNotice = document.getElementById("pickup-notice");
    const charge = document.getElementById("charge");
    const chargeTierLabel = document.getElementById("charge-tier");
    const shieldEnergy = document.getElementById("shield-energy");
    const weaponNames = {standard: "Padrão", spread: "Triplo", plasma: "Plasma"};
    const tierNames = {1: "I", 2: "II", 3: "III"};
    const pickupStyles = {
      standard: {color: "#89eaff", message: "Tiro padrão"},
      spread: {color: "#ffe284", message: "Disparo triplo"},
      plasma: {color: "#79f5bd", message: "Canhão de plasma"},
      charge: {color: "#bdb0ff", message: "Tiro carregado"},
      life: {color: "#ffa7d1", message: "Vida +1"}
    };
    const actions = ["up", "down", "left", "right", "fire", "shield"];
    const bindings = {
      ArrowUp: "up", KeyW: "up", ArrowDown: "down", KeyS: "down",
      ArrowLeft: "left", KeyA: "left", ArrowRight: "right", KeyD: "right",
      Space: "fire", ShiftLeft: "shield", ShiftRight: "shield"
    };
    const keys = new Set();
    const pointers = new Map();
    const connectionIssues = new Map();
    const pendingInputs = [];
    let lastInput = "";
    let inputRequest = null;
    let state = null;
    let starting = false;
    let missionRevision = 0;
    let pollTimer;
    let polling = false;
    let pickupTimer;
    let lastDamage = -1000;

    function connectionNotice(source, message = "") {
      if (message) connectionIssues.set(source, message);
      else connectionIssues.delete(source);
      const latest = [...connectionIssues.values()].at(-1) ?? "";
      if (notice.textContent !== latest) notice.textContent = latest;
      notice.hidden = !latest;
    }

    async function request(path, options, timeout = 1800) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      try {
        const response = await fetch(path, {...options, signal: controller.signal});
        if (!response.ok) throw new Error("Falha na comunicação com a missão.");
        return response.status === 204 ? null : await response.json();
      } finally {
        clearTimeout(timer);
      }
    }

    function hidePickupNotice() {
      clearTimeout(pickupTimer);
      pickupNotice.hidden = true;
    }

    function updateUpgrades(previous, next) {
      const weapon = next.player.weapon ?? "standard";
      const levels = next.player.weapon_levels ?? {};
      const weaponText = (weaponNames[weapon] ?? weaponNames.standard) + " " + (tierNames[levels[weapon]] ?? "I");
      if (weaponLabel.dataset.weapon !== weapon || weaponLabel.textContent !== weaponText) {
        weaponLabel.dataset.weapon = weapon;
        weaponLabel.textContent = weaponText;
      }
      const chargedTier = tierNames[levels.charge] ?? "I";
      if (chargeTierLabel.textContent !== chargedTier) {
        chargeTierLabel.textContent = chargedTier;
        charge.setAttribute("aria-label", "Carga do tiro, nível " + chargedTier);
      }

      const before = previous?.pickups_collected ?? 0;
      const after = next.pickups_collected ?? 0;
      if (next.status !== "playing" || after < before) {
        hidePickupNotice();
      } else if (previous?.status === "playing" && after > before && pickupStyles[next.last_pickup]) {
        const {color, message} = pickupStyles[next.last_pickup];
        const tier = tierNames[levels[next.last_pickup]];
        clearTimeout(pickupTimer);
        pickupNotice.style.color = color;
        pickupNotice.hidden = false;
        pickupNotice.textContent = tier ? message + " · Nível " + tier : message;
        pickupTimer = setTimeout(hidePickupNotice, 1650);
      }
    }

    function updateLevel(previous, next) {
      if (previous?.level !== next.level || previous?.level_total !== next.level_total || !previous) {
        levelNumber.textContent = (next.level ?? 1) + " / " + (next.level_total ?? 1);
      }
      if (previous?.level_name !== next.level_name || !previous) {
        levelName.textContent = next.level_name ?? "Órbita da Fronteira";
      }
      if (previous?.wave !== next.wave || previous?.wave_total !== next.wave_total) {
        wave.textContent = (next.wave || "–") + " / " + (next.wave_total ?? 5);
      }

      if (next.status === "transition") {
        const remaining = next.transition_remaining ?? 0;
        if (previous?.status !== "transition") levelProgress.max = Math.max(remaining, .1);
        levelProgress.value = levelProgress.max - remaining;
      }
    }

    function updateGame(next) {
      const previous = state;
      state = next;
      if (previous?.status === "playing" && next.hull < previous.hull) {
        lastDamage = performance.now();
      }
      if (previous?.score !== next.score) {
        score.textContent = String(next.score).padStart(6, "0");
      }
      updateLevel(previous, next);
      if (previous?.max_hull !== next.max_hull || previous?.hull !== next.hull) {
        hull.setAttribute("aria-label", next.hull + " de " + next.max_hull);
        if (hull.children.length !== next.max_hull) {
          const segments = Array.from({length: next.max_hull}, () => {
            const segment = document.createElement("span");
            segment.className = "hull-segment";
            segment.setAttribute("aria-hidden", "true");
            return segment;
          });
          hull.replaceChildren(...segments);
        }
        [...hull.children].forEach((segment, index) => {
          segment.classList.toggle("filled", index < next.hull);
        });
      }
      updateUpgrades(previous, next);
      if (previous?.player.charge !== next.player.charge) charge.value = next.player.charge;
      if (previous?.player.energy !== next.player.energy) shieldEnergy.value = next.player.energy;

      if (previous?.status === next.status) return;
      menu.hidden = next.status === "playing";
      touchControls.hidden = !menu.hidden;
      const transitioning = next.status === "transition";
      startButton.hidden = transitioning;
      levelProgress.hidden = !transitioning;
      if (next.status === "playing") {
        lastDamage = -1000;
        connectionNotice("start");
        return;
      }

      clearInput(false);
      connectionNotice("input");
      if (transitioning) {
        missionTitle.textContent = next.next_level_name ?? "Próxima fase";
        missionCopy.textContent = "Fase " + next.level + " concluída. Você avança automaticamente.";
        return;
      }

      const outcomes = {
        ready: ["Defenda a fronteira", (next.level_total ?? 1) > 1
          ? "Supere três fases e derrube as naves de comando."
          : "Enfrente cinco ondas e derrube a nave de comando.", "Iniciar missão"],
        won: ["Fronteira segura", "Missão concluída. Você marcou " + next.score + " pontos.", "Jogar de novo"],
        lost: ["Nave destruída", "Você marcou " + next.score + " pontos. Prepare-se para outra tentativa.", "Jogar de novo"]
      };
      const [title, copy, button] = outcomes[next.status];
      missionTitle.textContent = title;
      missionCopy.textContent = copy;
      startButton.textContent = button;
      if ((next.status === "won" || next.status === "lost") && !document.hidden) startButton.focus();
    }

    async function pollState() {
      if (polling) return;
      clearTimeout(pollTimer);
      polling = true;
      const revision = missionRevision;
      if (!starting) {
        try {
          const next = await request("/api/flight");
          if (revision === missionRevision && !starting) {
            updateGame(next);
            connectionNotice("state");
          }
        } catch {
          if (revision === missionRevision && !starting) {
            connectionNotice("state", "Conexão interrompida. Reconectando…");
          }
        }
      }
      polling = false;
      const delay = {playing: 33, transition: 100}[state?.status] ?? 450;
      pollTimer = setTimeout(pollState, document.hidden ? 450 : delay);
    }

    function sendInputs() {
      if (inputRequest || pendingInputs.length === 0) return;
      inputRequest = request("/api/flight/input", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: pendingInputs.shift()
      }).then(() => connectionNotice("input")).catch(() => {
        if (state?.status === "playing" && !starting) {
          connectionNotice("input", "Comandos interrompidos. Reconectando…");
          pendingInputs.length = 0;
        }
      }).finally(() => {
        inputRequest = null;
        sendInputs();
      });
    }

    function queueInput(keepalive = false) {
      if (state?.status !== "playing" || starting) return;
      const held = new Set([...keys].map(key => bindings[key]));
      for (const button of pointers.values()) held.add(button.dataset.command);
      const payload = JSON.stringify(Object.fromEntries(actions.map(action => [action, held.has(action)])));
      if (!keepalive && payload === lastInput) return;
      lastInput = payload;
      pendingInputs.push(payload);
      sendInputs();
    }

    function clearInput(send = true) {
      keys.clear();
      for (const button of pointers.values()) button.classList.remove("pressed");
      pointers.clear();
      pendingInputs.length = 0;
      lastInput = "";
      if (send) queueInput();
    }

    async function startMission() {
      if (starting || state?.status === "transition") return;
      starting = true;
      missionRevision += 1;
      startButton.disabled = true;
      clearInput(false);
      connectionNotice("start");

      try {
        await inputRequest;
        const next = await request("/api/flight/start", {method: "POST"});
        updateGame(next);
        connectionNotice("state");
      } catch {
        connectionNotice("start", "Não foi possível iniciar a missão. Tente outra vez.");
      } finally {
        starting = false;
        startButton.disabled = false;
        pollState();
      }
    }

    window.addEventListener("keydown", event => {
      if (!Object.hasOwn(bindings, event.code) || state?.status !== "playing") return;
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      event.preventDefault();
      if (event.repeat) return;
      keys.add(event.code);
      queueInput();
    });

    window.addEventListener("keyup", event => {
      if (!keys.delete(event.code)) return;
      event.preventDefault();
      queueInput();
    });

    window.addEventListener("blur", () => clearInput());
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) clearInput();
    });

    for (const button of touchControls.querySelectorAll("button")) {
      button.addEventListener("pointerdown", event => {
        if (event.button !== 0 || state?.status !== "playing") return;
        event.preventDefault();
        button.setPointerCapture(event.pointerId);
        button.classList.add("pressed");
        pointers.set(event.pointerId, button);
        queueInput();
      });

      function releasePointer(event) {
        if (!pointers.delete(event.pointerId)) return;
        if (![...pointers.values()].includes(button)) button.classList.remove("pressed");
        queueInput();
      }

      for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
        button.addEventListener(type, releasePointer);
      }
    }

    startButton.addEventListener("click", startMission);
    setInterval(() => {
      if (!inputRequest && pendingInputs.length === 0 && !document.hidden) queueInput(true);
    }, 190);
    pollState();

    const {width, height} = canvas;
    const shipAtlas = new Image();
    shipAtlas.src = "/assets/ships.png";
    const bossAtlas = new Image();
    bossAtlas.src = "/assets/bosses.png";
    // Source rectangles enclose each ship with a few pixels for its rim lighting.
    const shipSprites = {
      player: [78, 114, 603, 284],
      scout: [869, 54, 474, 375],
      gunner: [64, 600, 596, 377],
      boss: [756, 505, 650, 544]
    };
    const bossSprites = {
      frost: [61, 170, 510, 685],
      rift: [708, 299, 770, 425]
    };

    let seed = 27123;
    function random() {
      seed = (1664525 * seed + 1013904223) >>> 0;
      return seed / 4294967296;
    }

    const stars = Array.from({length: 154}, () => ({
      x: random() * width,
      y: random() * height,
      size: .65 + random() * 2.1,
      depth: .1 + random() * .9,
      light: .16 + random() * .65
    }));

    function polygon(points, fill, stroke) {
      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      for (const [x, y] of points.slice(1)) ctx.lineTo(x, y);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      if (stroke) {
        ctx.strokeStyle = stroke;
        ctx.stroke();
      }
    }

    function ellipse(x, y, rx, ry, fill) {
      ctx.beginPath();
      ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = fill;
      ctx.fill();
    }

    function glow(x, y, color, radius) {
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
      gradient.addColorStop(0, color);
      gradient.addColorStop(1, "transparent");
      ellipse(x, y, radius, radius, gradient);
    }

    function drawSky() {
      ctx.fillStyle = "#050a17";
      ctx.fillRect(0, 0, width, height);
      glow(755, 271, "#283f6a", 465);
      glow(385, 450, "#2c1a3d", 403);
      glow(228, 50, "#162747", 333);

      ctx.save();
      ctx.translate(766, 211);
      ctx.rotate(-.23);
      ctx.strokeStyle = "#6880b436";
      ctx.lineWidth = 2;
      for (const index of [0, 1, 2, 3, 4, 5]) {
        ctx.beginPath();
        ctx.ellipse(0, 0, 166 + index * 13, 53 + index * 4.2, 0, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.rotate(.23);
      glow(-31, -35, "#476ca9", 125);
      const planet = ctx.createRadialGradient(-60, -58, 12, -1, 3, 133);
      planet.addColorStop(0, "#7788ae");
      planet.addColorStop(.52, "#374c73");
      planet.addColorStop(.82, "#172741");
      planet.addColorStop(1, "#0c1528");
      ellipse(0, 0, 112, 112, planet);

      ctx.save();
      ctx.beginPath();
      ctx.arc(0, 0, 111, 0, Math.PI * 2);
      ctx.clip();
      ctx.lineWidth = 6;
      for (const y of [-81, -53, -23, 8, 43, 70]) {
        ctx.beginPath();
        ctx.moveTo(-117, y + 31);
        ctx.bezierCurveTo(-64, y - 12, 38, y + 1, 120, y - 24);
        ctx.strokeStyle = "#b6c5e317";
        ctx.stroke();
      }
      ctx.restore();

      ctx.rotate(-.23);
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#9bb3d953";
      for (const index of [0, 1, 2, 3, 4, 5]) {
        ctx.beginPath();
        ctx.ellipse(0, 0, 166 + index * 13, 53 + index * 4.2, 0, .12, 3.02);
        ctx.stroke();
      }
      ctx.restore();

      ctx.fillStyle = "#101829";
      ctx.fillRect(0, height - 5, width, 5);
    }

    function drawAsteroid(x, y, scale, angle, colors) {
      const [rock, face, shadow, edge] = colors;
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(scale, scale);
      ctx.rotate(angle);
      ctx.lineWidth = 1.2;
      polygon([[-62, 12], [-38, -30], [6, -42], [42, -21], [63, 8], [33, 34], [-20, 39]], rock, edge);
      polygon([[-38, -30], [6, -42], [42, -21], [11, 1], [-17, -6], [-62, 12]], face);
      polygon([[-20, 39], [11, 1], [42, -21], [63, 8], [33, 34]], shadow);
      polygon([[-38, -30], [6, -42], [11, 1], [-17, -6]], edge);
      ctx.restore();
    }

    function drawIceBelt() {
      ctx.fillStyle = "#040e1d";
      ctx.fillRect(0, 0, width, height);
      glow(695, 78, "#21466e", 385);
      glow(834, 433, "#164550", 332);
      glow(144, 224, "#102638", 242);

      ctx.save();
      ctx.translate(758, 151);
      glow(-24, -26, "#53a9d449", 128);
      const moon = ctx.createRadialGradient(-29, -43, 5, 4, 4, 119);
      moon.addColorStop(0, "#b3d5e0");
      moon.addColorStop(.44, "#5992ad");
      moon.addColorStop(.77, "#234762");
      moon.addColorStop(1, "#102739");
      ellipse(0, 0, 108, 108, moon);
      ctx.beginPath();
      ctx.arc(0, 0, 108, 0, Math.PI * 2);
      ctx.clip();
      for (const offset of [-54, 6, 63]) {
        polygon([
          [-105, offset - 30], [-50, offset - 9], [-23, offset - 24], [20, offset + 11],
          [67, offset - 2], [110, offset + 18], [67, offset + 14], [23, offset + 19],
          [-25, offset - 16], [-54, offset + 1]
        ], "#c1effe3b");
      }
      ctx.restore();

      const ice = ["#16374c", "#2b5970", "#102537", "#458096"];
      for (const [x, y, size, angle] of [
        [21, 50, 1.04, -.21], [124, 76, .43, .46], [235, 40, .62, .16],
        [488, 84, .41, -.54], [896, 49, .78, .23], [944, 391, .68, .53],
        [937, 511, 1.55, .17], [796, 481, .51, -.38], [675, 548, 1.21, -.2],
        [366, 498, .46, .36], [172, 471, .58, -.22], [30, 531, 1.54, .04]
      ]) {
        drawAsteroid(x, y, size, angle, ice);
      }
    }

    function drawCrimsonRift() {
      ctx.fillStyle = "#140c17";
      ctx.fillRect(0, 0, width, height);
      glow(811, 263, "#66302d", 378);
      glow(536, 119, "#382333", 318);
      glow(240, 438, "#372026", 288);

      ctx.save();
      ctx.translate(770, 246);
      ctx.rotate(-.37);
      glow(14, -8, "#994c34b3", 166);
      ellipse(8, -3, 142, 51, "#230f22bb");
      ctx.lineCap = "round";
      for (const [radius, strokeWidth, tint] of [
        [221, 44, "#ac514e12"], [185, 18, "#c4604029"],
        [158, 5, "#f592575a"], [143, 2, "#ffb38d90"]
      ]) {
        ctx.beginPath();
        ctx.ellipse(1, 0, radius, radius * .34, 0, -.3, 3.9);
        ctx.lineWidth = strokeWidth;
        ctx.strokeStyle = tint;
        ctx.stroke();
      }
      glow(122, -22, "#f89b5788", 56);
      ctx.restore();

      ctx.save();
      const dust = ctx.createLinearGradient(70, 380, 960, 177);
      dust.addColorStop(0, "#78413d00");
      dust.addColorStop(.53, "#ba60502a");
      dust.addColorStop(1, "#fda15138");
      ctx.lineWidth = 26;
      ctx.strokeStyle = dust;
      ctx.beginPath();
      ctx.moveTo(25, 462);
      ctx.bezierCurveTo(251, 333, 340, 426, 528, 269);
      ctx.bezierCurveTo(677, 143, 868, 259, 994, 79);
      ctx.stroke();
      ctx.restore();

      const embers = ["#35212d", "#623638", "#241826", "#8f4946"];
      for (const [x, y, size, angle] of [
        [98, 23, .84, -.39], [282, 69, .36, .32], [536, 56, .55, .33],
        [930, 85, .66, .69], [888, 517, 1.45, -.29], [747, 449, .39, .47],
        [592, 510, .63, .32], [274, 537, .74, -.19], [27, 490, 1.1, .53]
      ]) {
        drawAsteroid(x, y, size, angle, embers);
      }
    }

    const stageThemes = [
      {paint: drawSky, starColors: ["#e6f6ff", "#9bb7d6"], bossStyle: "command"},
      {paint: drawIceBelt, starColors: ["#dbffff", "#81b4cf"], bossStyle: "frost"},
      {paint: drawCrimsonRift, starColors: ["#ffebd0", "#d6968e"], bossStyle: "rift"}
    ];
    const bossLooks = {
      command: {name: "Nave de Comando", glow: "#ff6797"},
      frost: {
        name: "Sentinela Glacial", glow: "#75d8ff", armor: "#23465f",
        projectile: ["#6d86ff", "#807be6", "#e5ebff"],
        silhouette: [[-.45, -.2], [-.27, -.2], [-.12, -.48], [.3, -.48], [.48, -.28],
          [.34, -.2], [.34, .2], [.48, .28], [.3, .48], [-.12, .48], [-.27, .2], [-.45, .2], [-.36, 0]]
      },
      rift: {
        name: "Devastador Rubro", glow: "#ff935e", armor: "#532a3b",
        projectile: ["#ff6148", "#ef732c", "#fff0c2"],
        silhouette: [[-.49, 0], [-.31, -.14], [-.4, -.44], [-.12, -.29], [.19, -.3],
          [.39, -.47], [.49, -.22], [.32, 0], [.49, .22], [.39, .47], [.19, .3], [-.12, .29],
          [-.4, .44], [-.31, .14]]
      }
    };
    const skyCache = new Map();

    function skyFor(theme) {
      if (!skyCache.has(theme)) {
        const background = document.createElement("canvas");
        background.width = width;
        background.height = height;
        theme.paint();
        background.getContext("2d").drawImage(canvas, 0, 0);
        skyCache.set(theme, background);
      }
      return skyCache.get(theme);
    }

    function drawStars(distance, colors) {
      for (const star of stars) {
        const period = width + 20;
        const x = ((star.x - distance * star.depth) % period + period) % period - 10;
        ctx.globalAlpha = star.light;
        ctx.fillStyle = star.depth > .78 ? colors[0] : colors[1];
        ctx.fillRect(x, star.y, star.size * (1 + star.depth * 1.8), star.size * .65);
      }
      ctx.globalAlpha = 1;
    }

    function drawSprite(atlas, sprite, w, h) {
      if (!atlas.naturalWidth) return false;
      const [sx, sy, sw, sh] = sprite;
      const scale = Math.min(w / sw, h / sh);
      const dw = sw * scale;
      const dh = sh * scale;
      ctx.drawImage(atlas, sx, sy, sw, sh, -dw / 2, -dh / 2, dw, dh);
      return true;
    }

    function drawHull(kind, w, h) {
      if (drawSprite(shipAtlas, shipSprites[kind], w, h)) return;
      const tip = kind === "player" ? w / 2 : -w / 2;
      const edge = kind === "player" ? "#94eaff" : "#ff9a81";
      polygon([[tip, 0], [-tip, -h / 2], [-tip * .72, 0], [-tip, h / 2]], "#273a52", edge);
    }

    function getBossStyle(boss, theme) {
      return Object.hasOwn(bossLooks, boss.boss_style) ? boss.boss_style : theme.bossStyle;
    }

    function drawBoss(enemy, style, now) {
      const {w, h} = enemy;
      const look = bossLooks[style];
      ctx.globalAlpha = .42 + Math.sin(now * .02 + enemy.y) * .19;
      glow(w * .47, -h * .16, look.glow, w * .17);
      glow(w * .47, h * .16, look.glow, w * .17);
      ctx.globalAlpha = 1;
      if (style === "command") {
        drawHull("boss", w, h);
      } else if (!drawSprite(bossAtlas, bossSprites[style], w, h)) {
        ctx.lineWidth = 2;
        polygon(look.silhouette.map(([x, y]) => [x * w, y * h]), look.armor, look.glow);
        glow(-w * .16, 0, look.glow, h * .24);
        ellipse(-w * .16, 0, w * .08, h * .11, "#f7f9ff");
      }
    }

    function drawPlayer(player, now) {
      ctx.save();
      ctx.translate(player.x, player.y);
      if (player.invulnerable) ctx.globalAlpha = .65;
      const nozzle = -.47 * player.w;
      const plumeWidth = .042 * player.w;
      const nozzleOffset = .065 * player.w;
      for (const y of [-nozzleOffset, nozzleOffset]) {
        const flame = player.w * (.27 + Math.sin(now * .041 + y) * .1);
        const jet = ctx.createLinearGradient(nozzle - flame, 0, nozzle, 0);
        jet.addColorStop(0, "#54acf500");
        jet.addColorStop(.58, "#43bfff");
        jet.addColorStop(1, "#d1faff");
        polygon([
          [nozzle - flame, y],
          [nozzle, y - plumeWidth],
          [nozzle + 2, y],
          [nozzle, y + plumeWidth]
        ], jet);
      }
      drawHull("player", player.w, player.h);

      if (player.charge > .05) {
        const tip = player.w / 2 + 3;
        const spark = 1 + player.charge * 4;
        const aura = (player.weapon_levels?.charge ?? 1) >= 2 ? "#b2a0ff" : "#8cd4ff";
        glow(tip, 0, aura, 8 + player.charge * 13);
        ellipse(tip, 0, spark, spark, "#fff");
      }
      if (player.shield) {
        ctx.globalAlpha = 1;
        ellipse(0, 0, 35, 26, "#91d7ff22");
        ctx.strokeStyle = "#a8deff";
        ctx.lineWidth = 1.7;
        ctx.stroke();
        ctx.beginPath();
        ctx.ellipse(0, 0, 38, 29, 0, -.75, .75);
        ctx.strokeStyle = "#edfaff";
        ctx.stroke();
      }
      ctx.restore();
    }

    function drawEnemy(enemy, now, theme = stageThemes[0]) {
      ctx.save();
      ctx.translate(enemy.x, enemy.y);
      if (enemy.kind === "boss") {
        drawBoss(enemy, getBossStyle(enemy, theme), now);
      } else {
        ctx.globalAlpha = .42 + Math.sin(now * .02 + enemy.y) * .19;
        glow(enemy.w * .4, 0, "#ff9067", enemy.w * .22);
        ctx.globalAlpha = 1;
        drawHull(enemy.kind, enemy.w, enemy.h);
      }
      ctx.restore();
      if (pickupStyles[enemy.drop]) {
        drawPickupBadge(enemy.drop, enemy.x, enemy.y - enemy.h / 2 - 10, .53);
      }
    }

    function drawPickupBadge(kind, x, y, scale) {
      const {color} = pickupStyles[kind];
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(scale, scale);
      ctx.lineWidth = 1.6;
      polygon([
        [-8, -12], [8, -12], [13, -7], [13, 7], [8, 12],
        [-8, 12], [-13, 7], [-13, -7]
      ], "#101c30", color);

      if (kind === "life") {
        ctx.fillStyle = color;
        ctx.fillRect(-2, -7, 4, 14);
        ctx.fillRect(-7, -2, 14, 4);
      } else if (kind === "spread") {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.2;
        ctx.lineCap = "round";
        ctx.beginPath();
        for (const offset of [-6, 0, 6]) {
          ctx.moveTo(-6, offset * .3);
          ctx.lineTo(6, offset);
        }
        ctx.stroke();
      } else if (kind === "standard") {
        polygon([[-6, -3], [3, -3], [8, 0], [3, 3], [-6, 3]], color);
      } else if (kind === "charge") {
        polygon([[0, -8], [8, 0], [0, 8], [-8, 0]], "#382e62", color);
        ellipse(0, 0, 2.5, 2.5, "#fff");
      } else {
        polygon([[-1, -8], [6, -8], [2, -2], [7, -2], [-3, 9], [-1, 2], [-6, 2]], color);
      }
      ctx.restore();
    }

    function drawPickup(pickup, now) {
      const style = pickupStyles[pickup.kind];
      if (!style) return;
      const pulse = .85 + .16 * Math.sin(now * .009);
      glow(pickup.x, pickup.y, style.color + "78", Math.max(pickup.w, pickup.h) * pulse);
      drawPickupBadge(pickup.kind, pickup.x, pickup.y, Math.min(pickup.w, pickup.h) / 26);
    }

    function drawShot(shot) {
      const enemy = shot.kind === "enemy";
      const strong = shot.kind === "charged";
      const radius = Math.max(7, shot.h);
      const rx = shot.w / 2;
      const ry = shot.h / 2;
      const tier = shot.tier ?? 1;
      const luminous = 1 + (tier - 1) * .14;
      const bossColors = enemy ? bossLooks[shot.boss_style]?.projectile : null;
      if (bossColors) {
        const [halo, rim, core] = bossColors;
        glow(shot.x + rx * .35, shot.y, halo, radius * 1.55);
        ellipse(shot.x, shot.y, rx, ry, rim);
        ellipse(shot.x - rx * .24, shot.y, rx * .48, ry * .59, core);
        return;
      }
      if (shot.kind === "plasma") {
        glow(shot.x, shot.y, "#4cf8b8", radius * 1.6 * luminous);
        ellipse(shot.x, shot.y, rx, ry, tier >= 3 ? "#8bffd7" : "#37dfa2");
        ellipse(shot.x + rx * .15, shot.y, rx * .72, ry * .52, "#e8fff4");
        return;
      }
      if (shot.kind === "spread") {
        glow(shot.x, shot.y, "#ffd569", radius * 1.4 * luminous);
        ellipse(shot.x, shot.y, rx, ry, "#fff1aa");
        return;
      }
      const core = enemy ? "#ffcf9c" : "#e8ffff";
      const aura = strong && tier >= 2 ? "#a48bff" : "#4bd8ff";
      glow(shot.x, shot.y, enemy ? "#ff6378" : aura, radius * 1.35 * luminous);
      if (strong) {
        ellipse(shot.x, shot.y, rx + 4, ry + 2, tier >= 2 ? "#b2a0ff" : "#5ce9ff");
      }
      ellipse(shot.x, shot.y, rx, ry, core);
    }

    function showBossHealth(boss, theme) {
      const look = bossLooks[getBossStyle(boss, theme)];
      ctx.fillStyle = "#0a101dcc";
      ctx.fillRect(width / 2 - 142, 12, 284, 37);
      ctx.fillStyle = "#f5f8ff";
      ctx.textAlign = "center";
      ctx.font = "700 13px Segoe UI, sans-serif";
      ctx.fillText((boss.boss_name ?? look.name).toLocaleUpperCase("pt-BR"), width / 2, 28);
      ctx.fillStyle = "#442c45";
      ctx.fillRect(width / 2 - 132, 35, 264, 5);
      ctx.fillStyle = look.glow;
      ctx.fillRect(width / 2 - 132, 35, 264 * (boss.hull / boss.max_hull), 5);
    }

    function drawFrame(now) {
      const theme = stageThemes[(state?.level ?? 1) - 1] ?? stageThemes[0];
      ctx.drawImage(skyFor(theme), 0, 0);
      const ready = !state || state.status === "ready";
      const playing = state?.status === "playing";
      drawStars(ready ? now * .024 : state.distance, theme.starColors);

      if (ready) {
        const drift = Math.sin(now * .0015) * 10;
        drawPlayer({x: 672, y: 307 + drift, w: 236, h: 132}, now);
        drawEnemy({x: 837, y: 112, w: 58, h: 42, kind: "scout"}, now);
        drawEnemy({x: 888, y: 180, w: 76, h: 53, kind: "gunner"}, now);
      } else {
        for (const enemy of state.enemies) drawEnemy(enemy, now, theme);
        for (const pickup of state.pickups ?? []) drawPickup(pickup, now);
        for (const shot of state.shots) drawShot(shot);
        for (const shot of state.enemy_shots) drawShot(shot);
        if (state.hull > 0) drawPlayer(state.player, now);
        const boss = state.enemies.find(enemy => enemy.kind === "boss");
        if (boss && playing) showBossHealth(boss, theme);
        const pulse = 1 - (now - lastDamage) / 280;
        if (playing && pulse > 0) {
          ctx.strokeStyle = "rgba(255, 96, 121, " + (pulse * .7) + ")";
          ctx.lineWidth = 8;
          ctx.strokeRect(0, 0, width, height);
        }
      }
      requestAnimationFrame(drawFrame);
    }

    requestAnimationFrame(drawFrame);
