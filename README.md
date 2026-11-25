# Starfighter: Frontline Protocol

Jogo de nave 2D com rolagem horizontal e combate em tempo real. A missão e os
elementos visuais são originais, com inspiração em clássicos do gênero como
**R-Type**. O jogo roda no navegador e usa um motor em Python com threads e
semáforos.

## Como jogar

Atravesse cinco ondas de inimigos e derrote o chefe. A nave tem três pontos de
casco. Desvie dos inimigos e dos projéteis, use o escudo quando necessário e
carregue o canhão para causar mais dano.

| Controle | Ação |
| --- | --- |
| Setas ou `W`, `A`, `S`, `D` | Mover a nave em quatro direções |
| `Espaço` | Disparar. Segure para carregar e solte para lançar um tiro mais forte. |
| `Shift` | Ativar o escudo enquanto houver energia |

Em telas sensíveis ao toque, use os botões na parte inferior da página.

## Executar

Na pasta do projeto, com Python 3.10 ou superior, inicie o servidor local.
O projeto usa apenas a biblioteca padrão do Python.

```powershell
python web_app.py
```

Abra `http://127.0.0.1:8000` no navegador e inicie a missão. Para fechar o
servidor, volte ao terminal e pressione `Ctrl+C`.

Se o Windows abrir a Microsoft Store ao chamar `python`, execute o
`python.exe` da sua instalação pelo caminho completo. Em uma instalação
local padrão do Python 3.12, o comando é o seguinte.

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" web_app.py
```

## Threads e semáforos

O navegador desenha a fase em Canvas, envia o estado dos controles e recebe
cópias do estado da partida. `web_app.py` recebe essas requisições HTTP locais.
Em `flight.py`, o `FlightController` coordena duas threads de trabalho.

- **Simulação.** Atualiza movimento, rolagem, projéteis, colisões, pontuação e
  resultado da missão em passos fixos de 60 Hz.
- **Produção de ondas.** Aguarda um pedido da simulação, prepara a formação de
  inimigos e sinaliza que a onda está pronta.

Os semáforos acordam a simulação e coordenam os pedidos e as respostas entre
as duas threads. Um lock protege o estado compartilhado enquanto ele é
atualizado ou copiado para o navegador.

## Testes e protótipo de terminal

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem a simulação 2D, a comunicação HTTP e o protótipo de turnos.
Esse protótipo pode ser executado com `python game.py`.

## Git

Use `git status --short --branch` na pasta do projeto para conferir a branch
e as mudanças locais. Se você recebeu uma cópia em ZIP e quer conservar o
histórico do grupo, clone o repositório do grupo e copie para ele as mudanças
que precisa manter.

## Apresentação PIT

Veja o roteiro de slides, a fala de venda e a demonstração ao vivo.
[Apresentação PIT](docs/apresentacao-pit.md)
