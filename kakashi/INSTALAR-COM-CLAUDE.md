# Pro Claude Code: como instalar o KAKASHI neste PC (Windows)

> **⚠ ANTES DE TUDO: RODE O PC CHECK.** Antes de instalar qualquer coisa, rode `py -3 pc_check.py` (desta pasta; só LÊ o PC, não
> instala nada) e mostre pra pessoa, em palavras simples, o nível do PC dela (N0 leve, N1 médio, N2 forte) e a tabela "onde roda o
> quê": o que roda no PC dela, o que vai pela ARDI e o que não roda. Só depois siga os passos abaixo. O gravador é leve em qualquer
> PC; o que muda com o nível é a transcrição (e, no Tandera, a análise).

1. **Sistema:** precisa ser **Windows 10/11**. No Mac, pare: o gravador do Mac ainda não existe (o Piloto está terminando).
2. **Python 3.10+** (`py -3 --version`) e **ffmpeg** (`ffmpeg -version`). Faltando: ofereça instalar com
   `winget install Python.Python.3.12` / `winget install Gyan.FFmpeg` (peça o OK da pessoa antes; depois feche e abra o terminal).
3. **PC check** (o aviso lá de cima): `py -3 pc_check.py` → explique o resultado.
4. **Pergunte duas coisas, uma de cada vez:**
   - **O atalho.** "Qual atalho você quer pra começar e concluir a gravação? O do Luan é Ctrl+Page Down; pode ser qualquer um, tipo
     Ctrl+Alt+K ou F9." O de cancelar vira o mesmo + Shift (Ctrl+Shift+Page Down). Confira antes com
     `py -3 atalho.py --conferir "<o que ela escolheu>"` (diz se vale e se outro programa já usa).
   - **A conta da ARDI.** "Você tem conta na ARDI (é da Fly)?" Sim → a fala é transcrita pela ARDI (padrão). Não → transcrição no
     próprio PC (`--transcricao local`; o PC check diz se fica rápido ou lento).
5. **Instale**, de dentro desta pasta (extraída do zip):
   `py -3 instalar.py --atalho "<o atalho dela>"` (+ `--transcricao local` se ela não tem ARDI).
   - Se ela não usa o Premiere: `--sem-premiere`. Com o Premiere instalado, o instalador põe o painel KAKASHI nele (fechar e abrir o
     Premiere depois).
   - Se já existir uma skill `/kakashi` que não veio deste pacote, o instalador NÃO troca e avisa: pergunte antes de rodar com
     `--trocar-skill` (a antiga é guardada, não apagada).
6. **Mostre o resumo** que o instalador escreve e diga como usar: o atalho começa e conclui, o de cancelar cancela (vai pra
   `_descartadas`, nunca apaga), e depois de gravar é só digitar **/kakashi** aqui no Claude Code. O atalho dá pra trocar quando quiser:
   atalho **KAKASHI** na área de trabalho → **TROCAR O ATALHO**.
7. Se o Windows avisar "O Windows protegeu o computador" num atalho: "Mais informações" → "Executar assim mesmo".

Atualizar = rodar o `instalar.py` da versão nova (as gravações, o config e o atalho ficam).
Desinstalar: `py -3 "%LOCALAPPDATA%\Programs\Kakashi-Fly\instalar.py" --desinstalar` (as gravações ficam).
