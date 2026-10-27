# Pro Claude Code: como instalar o TANDERA neste PC (Windows)

> **⚠ ANTES DE INSTALAR: RODE O PC CHECK E MOSTRE PRA PESSOA.** Rode `py -3 pc_check.py` (desta pasta; ele só LÊ o PC, não instala
> nada) e explique pra pessoa, em palavras simples:
> - o **nível** do PC dela (N0 leve · N1 médio · N2 forte) e por quê (a placa de vídeo NVIDIA e a memória RAM);
> - **o que roda onde** no Tandera: **no PC dela** (LOCAL), **pela conta ARDI dela** (ARDI: o Claude faz pelas ferramentas da ARDI),
>   **no limite** (LIMITE: roda, mas sem folga; só com tudo fechado e se ela quiser) ou **não roda** (NÃO, com o motivo).
>
> Depois rode `py -3 instalar.py --so-tamanho`, diga **quantos GB vai baixar** e quanto de disco precisa, e **peça o OK** dela. Só
> depois instale, e só o que o PC aguenta (é o que o instalador faz sozinho).

1. **Sistema:** Windows 10/11. No Mac, pare: a versão do Mac está com o Piloto.
2. **Python 3.10+** (`py -3 --version`) e **ffmpeg** (`ffmpeg -version`). Faltando: o jeito mais fácil é o `Instalar.bat` da raiz do
   zip (ele põe os dois sozinho, sem administrador). Na mão: `winget install -e --id Python.Python.3.12 --scope user` e
   `winget install -e --id Gyan.FFmpeg` (peça o OK antes; depois feche e abra o terminal).
3. **PC check + tamanho + OK** (o aviso lá de cima).
4. **Pergunte uma coisa:** "Você tem conta na ARDI (é da Fly)?" Não tem: acrescente `--sem-ardi` (o que só ia pela ARDI fica de fora).
   Se o PC check marcou algo como **LIMITE** (placa NVIDIA de 4 GB com pouca RAM), diga o que é e pergunte se ela quer arriscar:
   só com o "sim" dela, acrescente `--com-limite` (e avise: na hora de analisar, fechar tudo o que pesa).
5. **Instale**, de dentro desta pasta (extraída do zip): `py -3 instalar.py --sem-perguntas` (+ `--sem-ardi` / `--com-limite`).
   - Demora de 2 min (PC leve, ~1 GB) a uns 20–40 min (PC forte, ~9 GB, conforme a internet). Ele mostra o que está baixando.
   - Se já existir uma skill `/tandera` que NÃO veio deste pacote, o instalador não troca e avisa: pergunte antes de rodar com
     `--trocar-skill` (a antiga é guardada, não apagada).
   - Se cair a internet: rode de novo, ele continua de onde parou.
6. **Mostre o resumo** que o instalador escreve no fim (o que ficou instalado e o que o PC não aguenta) e diga como usar: no Claude
   Code, **/tandera** + o caminho do vídeo + o que ela quer saber dele.

Atualizar = rodar o `instalar.py` da versão nova (o cache, as análises, as receitas dela e o config ficam; o que já foi baixado não baixa
de novo). Desinstalar: `py -3 "%LOCALAPPDATA%\Programs\Tandera-Fly\instalar.py" --desinstalar` (tira a skill, os programas e os
modelos; as análises e as receitas ficam).
