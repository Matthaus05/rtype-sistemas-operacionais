# PIT — Starfighter: Frontline Protocol

## Roteiro de slides

### Slide 1 — A missão começa

**Starfighter: Frontline Protocol**  
Um combate espacial de terminal inspirado em clássicos como R-Type — feito para transformar conceitos de Sistemas Operacionais em uma missão jogável.

### Slide 2 — O problema e a ideia

Como mostrar concorrência e sincronização de um jeito prático e fácil de entender? Em nosso jogo, a simulação e a chegada de inimigos acontecem em threads separadas, coordenadas por semáforos.

### Slide 3 — O desafio do jogador

Sobreviva a 18 turnos, destrua inimigos e proteja o casco. Cada decisão importa: disparar para marcar pontos, ativar o escudo no momento certo ou aguardar.

### Slide 4 — Uma missão em funcionamento

- Ondas chegam a cada três turnos.
- Ataques acontecem a cada quatro turnos.
- O escudo bloqueia um ataque no turno em que é ativado.
- Vitória: completar a missão; derrota: perder todo o casco.

### Slide 5 — Sistemas Operacionais em ação

- **Threads:** interface do jogador, simulação e produtor de ondas.
- **Semáforos:** liberam ações, solicitam ondas e confirmam que uma onda foi criada antes de a simulação continuar.
- **Lock:** protege os dados compartilhados contra atualizações concorrentes.
- **Filas:** transportam comandos e resultados sem misturar responsabilidades.

### Slide 6 — O que torna o projeto interessante?

É leve, roda no terminal, não precisa de bibliotecas externas e deixa visível o papel de cada mecanismo de sincronização. A prioridade é o funcionamento do sistema concorrente — não gráficos ou processamento de imagens.

### Slide 7 — Demonstração

1. Execute `python game.py`.
2. Use `f` para destruir inimigos e marcar pontos.
3. Use `s` no turno de ataque para demonstrar o escudo.
4. Mostre o código e a sincronização em `game.py`.
5. Execute `python -m unittest discover -s tests -v`.

### Slide 8 — Encerramento

**Starfighter transforma threads e semáforos em parte da missão.**  
Pronto para jogar, estudar e apresentar.

## Fala de venda (PIT)

"Imagine defender a fronteira espacial enquanto ondas de inimigos se aproximam. Em Starfighter: Frontline Protocol, cada turno conta: você escolhe quando atirar, proteger a nave ou esperar. Mas o jogo também tem uma missão por trás da tela: mostrar Sistemas Operacionais funcionando de verdade. A simulação e a chegada das ondas rodam em threads diferentes; semáforos coordenam cada ação e lock protege os dados compartilhados. Tudo roda no terminal, sem instalar bibliotecas extras, para que o foco fique no que importa: entender concorrência jogando. Você consegue sobreviver aos 18 turnos?"

## Divisão sugerida para o grupo

Cada participante deve apresentar uma parte da venda do jogo, conforme a orientação da disciplina. Uma divisão possível é: conceito e objetivo; regras e demonstração; threads e semáforos; explicação do código e testes.
