# PIT — Starfighter: Frontline Protocol

## Roteiro de slides

### Slide 1 — A missão começa

**Starfighter: Frontline Protocol**  
Jogo de nave 2D com rolagem horizontal, inspirado em clássicos como R-Type.
A missão combina combate espacial com os conceitos de Sistemas Operacionais
estudados em sala.

### Slide 2 — O problema e a ideia

Como demonstrar concorrência durante uma partida? A simulação atualiza a fase
continuamente enquanto outra thread prepara as ondas de inimigos. Semáforos
coordenam essas duas atividades.

### Slide 3 — O desafio do jogador

Pilote a nave, desvie dos disparos e planeje quando usar o escudo e o tiro
carregado. Atravesse cinco ondas e derrote o chefe antes de perder os três
pontos de casco.

### Slide 4 — Uma missão em funcionamento

- Mova a nave com as setas ou `W`, `A`, `S`, `D`.
- Aperte `Espaço` para disparar ou segure e solte para lançar um tiro carregado.
- Segure `Shift` para ativar o escudo e acompanhe o consumo de energia no painel.
- Destrua inimigos para somar pontos. A derrota ocorre quando o casco chega a
  zero. A vitória ocorre ao derrotar o chefe.

### Slide 5 — Sistemas Operacionais em ação

- **Thread de simulação.** Calcula movimento, projéteis e colisões em passos de
  tempo fixos.
- **Thread de ondas.** Prepara as formações de inimigos pedidas pela simulação.
- **Semáforos.** Sinalizam quando a simulação deve acordar, quando há um pedido
  de onda e quando a formação fica pronta.
- **Lock.** Protege o estado que o navegador recebe enquanto o motor atualiza
  a partida.

### Slide 6 — Motor e interface

O motor Python calcula as regras e o resultado da partida. O navegador envia
os controles ao servidor local e desenha em Canvas os dados que recebe. O
projeto usa a biblioteca padrão do Python.

### Slide 7 — Demonstração

1. Execute `python web_app.py`, abra `http://127.0.0.1:8000` e inicie a missão.
2. Mova a nave na vertical e na horizontal enquanto o cenário passa.
3. Mostre um disparo normal, um disparo carregado e o consumo de energia do
   escudo.
4. Em `flight.py`, mostre a solicitação de uma onda e o semáforo que sinaliza
   quando os inimigos estão prontos.
5. Execute `python -m unittest discover -s tests -v`.

### Slide 8 — Encerramento

Relembre o que acontece durante uma onda. O motor mantém a fase em movimento,
recebe a formação da outra thread e incorpora os novos inimigos à partida.

## Fala de venda (PIT)

“Você pilota uma nave de patrulha e precisa atravessar cinco ondas de inimigos
para alcançar o chefe. Em tempo real, você decide quando desviar, carregar um
tiro ou gastar energia com o escudo. Enquanto isso, duas threads Python
mantêm a missão em andamento. Uma move a nave e resolve as colisões. A outra
prepara os inimigos. Os semáforos sincronizam a chegada de cada onda. Na
demonstração, vamos jogar uma missão e acompanhar no código como essas duas
threads cooperam.”

## Divisão sugerida para o grupo

Distribuam entre os participantes a apresentação do conceito e do objetivo,
a demonstração, a explicação de threads e semáforos e a explicação dos testes.
