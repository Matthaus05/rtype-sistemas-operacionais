# Starfighter: Frontline Protocol

Um jogo didático de combate espacial em terminal, inspirado em jogos clássicos
de nave de rolagem horizontal, como **R-Type**. O protótipo usa somente a
biblioteca padrão do Python e demonstra concorrência com threads, semáforos e
um lock. Não usa código, personagens, imagens, músicas ou outros recursos do
jogo original.

## Tema e objetivo

Você pilota uma nave de defesa na fronteira espacial. Sobreviva a 18 turnos,
derrube inimigos e administre o escudo para proteger o casco. O objetivo da
missão é terminar os 18 turnos sem perder os três pontos de casco.

## Como funciona

- Uma onda inimiga chega a cada três turnos.
- Um ataque inimigo ocorre a cada quatro turnos se ainda houver inimigos.
- `f` dispara: elimina um inimigo e soma 100 pontos; sem alvo, o disparo erra.
- `s` ativa o escudo naquele turno e bloqueia um ataque.
- `w` aguarda e não ataca.
- `q` encerra a missão.
- O jogo termina em vitória ao completar 18 turnos ou em derrota quando o casco
  chega a zero.

## Requisitos

- Python 3.10 ou superior.
- Nenhuma dependência externa, instalação ou conexão com a internet.

## Executar

No terminal, a partir da pasta do projeto:

```powershell
python game.py
```

Para executar os testes:

```powershell
python -m unittest discover -s tests -v
```

## Concorrência: threads e semáforos

`GameController` coordena três fluxos de execução:

1. **Thread principal:** apresenta o estado e lê os comandos do jogador.
2. **Thread `simulation`:** avança os turnos, processa ações e ataques.
3. **Thread `enemy-waves`:** produz ondas inimigas independentemente da thread
   de simulação.

Os semáforos sincronizam eventos sem busy waiting:

- `_action_ready` libera a simulação somente quando há uma ação do jogador.
- `_wave_requested` sinaliza à thread de ondas que uma onda deve ser produzida.
- `_wave_created` confirma à simulação que a onda foi adicionada antes de
  resolver a ação daquele turno.

Os dados compartilhados (`GameState`) são protegidos por `_lock`, evitando
leituras ou atualizações simultâneas inconsistentes. As filas transportam
comandos e resultados entre a interface e a simulação.

## Explicação do código-fonte

- **`GameState`** reúne turno, casco, pontuação, inimigos, ondas e resultado.
- **`GameController.__init__`** cria o estado, as filas, o lock, os semáforos e
  as duas threads de trabalho.
- **`start()`** inicia o produtor de ondas e a simulação.
- **`submit()`** valida a entrada, envia um comando e libera `_action_ready`;
  depois espera a resposta da simulação.
- **`_run_simulation()`** aguarda cada comando com `_action_ready.acquire()`.
  Quando é hora de uma nova onda, libera `_wave_requested` e espera
  `_wave_created`. Em seguida processa disparo/escudo/espera e atualiza o estado
  sob o lock.
- **`_produce_waves()`** espera `_wave_requested`, adiciona inimigos sob o lock
  e libera `_wave_created` para sinalizar conclusão.
- **`snapshot()`** fornece uma cópia consistente do estado para a interface.
- **`stop()`** sinaliza encerramento, acorda as threads bloqueadas e aguarda
  seu término.
- **`play()`** implementa a interface de terminal; os testes automatizados
  estão em `tests/test_game.py`.

## Apresentação PIT

Veja [docs/apresentacao-pit.md](docs/apresentacao-pit.md) para o roteiro de
slides, fala de venda e demonstração ao vivo.

## Nota

Projeto acadêmico original, sem afiliação ou endosso dos criadores ou
detentores dos direitos de R-Type. O nome é citado apenas para indicar a
inspiração geral.
