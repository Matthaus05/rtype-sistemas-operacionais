# Starfighter: Frontline Protocol

Jogo acadêmico de nave 2D com rolagem horizontal e combate em tempo real,
inspirado em clássicos como **R-Type**. Desenvolvido para a disciplina de
Sistemas Operacionais, o jogo usa threads e semáforos no motor Python e
renderiza a partida em Canvas no navegador.

A interface fica separada em arquivos HTML, CSS e JavaScript; o motor e a
concorrência do jogo continuam em Python.

![Nave do jogador, dois inimigos e chefe do Starfighter](web/ships.png)

## Executar o jogo

Você precisa de **Python 3.10 ou superior** e um navegador. O jogo usa apenas a
biblioteca padrão do Python.

Para baixar o projeto pela primeira vez, clone o repositório.

```bash
git clone https://github.com/Matthaus05/rtype-sistemas-operacionais.git
cd rtype-sistemas-operacionais
```

Na pasta do projeto, inicie o servidor local.

```powershell
python web_app.py
```

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000) e clique em **Iniciar
missão**. Para encerrar o servidor, pressione `Ctrl+C` no terminal.
Se já houver uma instância do jogo na porta `8000`, encerre-a antes de
iniciar a nova.

Se o Windows abrir a Microsoft Store ao chamar `python`, execute o
`python.exe` da sua instalação pelo caminho completo. Para a instalação
padrão do Python 3.12 no perfil do usuário, use este comando.

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" web_app.py
```

## Como jogar

Você começa com três pontos de casco. Desvie dos inimigos e dos projéteis,
use o escudo e carregue o canhão para causar mais dano.

### Fases

1. **Órbita da Fronteira.** A **Nave de Comando** patrulha a órbita e dispara
   projéteis em leque.
2. **Cinturão de Gelo.** A **Sentinela Glacial** protege o cinturão de
   asteroides com salvas direcionadas à sua nave.
3. **Fenda Rubra.** O **Devastador Rubro** avança pelo campo de batalha e
   varia a abertura de suas rajadas.

O chefe aparece na quinta onda de cada fase. Ao derrotar um dos dois
primeiros chefes, você avança com a pontuação, o casco, a arma equipada e
todos os níveis de tiros obtidos. Derrote o Devastador Rubro para vencer a
campanha.

| Controle | Ação |
| --- | --- |
| Setas ou `W`, `A`, `S`, `D` | Mover a nave em quatro direções |
| `Espaço` | Atirar. Segure e solte para disparar um tiro carregado. |
| `Shift` | Ativar o escudo enquanto houver energia |

Em telas sensíveis ao toque, use os botões abaixo do campo de jogo.

### Upgrades

Quando você abate um inimigo marcado, ele solta uma cápsula. Passe com a nave
sobre ela para coletá-la. A primeira cápsula de leque ou plasma libera
a arma no nível I. As próximas cápsulas daquela arma aumentam seu nível,
até o III. O tiro padrão e o carregado já começam no nível I.

| Tiro | Nível I | Nível II | Nível III |
| --- | --- | --- | --- |
| Padrão | 1 de dano | 2 de dano | 3 de dano |
| Leque | 3 projéteis | 5 projéteis | 7 projéteis |
| Plasma | 2 de dano | 3 de dano | 4 de dano |
| Carregado | 8 de dano | 11 de dano | 14 de dano |

Quanto maior o nível do plasma, maior o projétil. A cápsula de uma arma a
equipa e os níveis das demais ficam guardados. A cápsula de carga melhora
o tiro carregado sem trocar a arma equipada. Para usar o carregado com
qualquer arma, segure e solte `Espaço`.

Cada cápsula de vida soma um ponto de casco, mesmo com o casco cheio, até o
limite de cinco pontos. Uma nova campanha começa com três pontos de casco,
tiro padrão equipado e os níveis iniciais.

## Threads e semáforos

O servidor HTTP leva os comandos do navegador ao motor da partida e devolve
uma cópia do estado para o Canvas. O `FlightController` coordena duas threads
de trabalho.

- **Simulação.** Atualiza movimento, rolagem, projéteis, colisões, pontuação e
  resultado da missão em passos fixos de 60 Hz.
- **Produção de ondas.** Aguarda um pedido da simulação, prepara a formação de
  inimigos e sinaliza que a onda está pronta.

O semáforo `_wake` acorda a simulação ao iniciar a missão ou encerrar o
servidor. O par `_wave_requested` e `_wave_created` sincroniza o pedido da
onda e a entrega da formação. Um lock protege o estado compartilhado
enquanto ele é atualizado ou copiado para o navegador.

## Arquivos do projeto

| Arquivo | Função |
| --- | --- |
| [`flight.py`](flight.py) | Motor da missão em tempo real |
| [`web_app.py`](web_app.py) | Servidor local e comunicação com o navegador |
| [`web/index.html`](web/index.html) | Estrutura da interface do navegador |
| [`web/styles.css`](web/styles.css) | Estilos da interface |
| [`web/app.js`](web/app.js) | Controles, comunicação com o servidor e renderização em Canvas |
| [`web/ships.png`](web/ships.png) | Sprites originais do jogador, dos inimigos e da Nave de Comando |
| [`web/bosses.png`](web/bosses.png) | Sprites da Sentinela Glacial e do Devastador Rubro |
| [`game.py`](game.py) | Protótipo de turnos, executável com `python game.py` |

## Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem a simulação 2D, a progressão entre fases, os chefes, os
controles, os níveis dos tiros, o carregamento dos sprites pelo servidor
HTTP e o protótipo de turnos.
