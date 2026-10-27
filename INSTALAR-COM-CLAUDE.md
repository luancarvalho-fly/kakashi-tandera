# Pro Claude Code: como instalar o KAKASHI + TANDERA neste PC (Windows)

> **⚠ ANTES DE TUDO: RODE O PC CHECK.** Antes de instalar qualquer coisa, rode `py -3 kakashi\pc_check.py` (desta pasta; só LÊ o PC,
> não instala nada) e mostre pra pessoa, em palavras simples, o nível do PC dela (N0 leve, N1 médio, N2 forte) e a tabela "onde roda
> o quê": o que roda no PC dela, o que vai pela ARDI e o que não roda. Só depois siga os passos abaixo.

1. **Sistema:** Windows 10/11. No Mac, pare: a versão do Mac está com o Piloto.
2. **Python 3.10+** (`py -3 --version`). Faltando: ofereça `winget install -e --id Python.Python.3.12 --scope user` (peça o OK antes;
   depois feche e abra o terminal). O ffmpeg o instalador põe sozinho se faltar.
3. **PC check** (o aviso lá de cima): `py -3 kakashi\pc_check.py` → explique o resultado.
4. **Pergunte o atalho do Kakashi:** "Qual atalho você quer pra começar e concluir a gravação? O do Luan é Ctrl+Page Down; pode ser
   qualquer um, tipo Ctrl+Alt+K ou F9." Confira com `py -3 kakashi\atalho.py --conferir "<o que ela escolheu>"` (diz se vale e se
   outro programa já usa). O de cancelar vira o mesmo + Shift.
5. **Tamanho do Tandera:** `py -3 tandera\instalar.py --so-tamanho` → diga quantos GB vai baixar e pergunte se pode.
6. **Instale tudo** de dentro desta pasta (extraída do zip):
   `py -3 instalar_tudo.py --sim --atalho "<o atalho dela>"` (+ `--sem-tandera` se ela não quiser o Tandera agora; + `--sem-premiere`
   se ela não usa o Premiere). Com o Premiere instalado, o plugin KAKASHI entra nele (fechar e abrir o Premiere depois).
   Se já existir uma skill `/kakashi` ou `/tandera` que não veio deste pacote, o instalador NÃO troca e avisa: pergunte antes de rodar
   o instalador daquela parte com `--trocar-skill`.
7. **Mostre o resumo** e diga como usar: o atalho começa e conclui, o + Shift cancela (vai pra `_descartadas`, nunca apaga); depois de
   gravar, **/kakashi** aqui no Claude Code; vídeo pra analisar, **/tandera**. Trocar o atalho ou procurar atualização: atalho
   **KAKASHI** na área de trabalho.
8. Se o Windows avisar "O Windows protegeu o computador": "Mais informações" → "Executar assim mesmo".

Atualizar: o botão ATUALIZAR da janelinha, ou `python atualizar.py --instalar` dentro de `%LOCALAPPDATA%\Programs\Kakashi-Fly`.
Desinstalar: `py -3 "%LOCALAPPDATA%\Programs\Kakashi-Fly\instalar.py" --desinstalar` (e o mesmo no `Tandera-Fly`). As gravações ficam.
