# KAKASHI + TANDERA (Fly) — Windows

Feitos pelo Luan Carvalho com o Claude Code, pro time da Fly.

- **KAKASHI** — o gravador de correção. Você aperta o seu atalho, fala e mexe à vontade (Chrome, Fly Studio, Premiere, qualquer
  janela), aperta de novo e digita **/kakashi** no Claude Code. O Claude lê a sua fala junto com o que estava na tela, onde o mouse
  estava, o link aberto, o que você copiou, um print com zoom de cada "olha aqui" e, no Premiere, cada ação na timeline. Acabou o
  "ficar mandando áudio, print e gravação de tela pro Claude".
- **TANDERA** — a análise de vídeo: mede cortes, fala, música, texto na tela, câmera... e devolve um dossiê pro Claude entender o vídeo
  do jeito certo. No Claude Code: **/tandera** e o caminho do vídeo.

## Instalar (dois cliques)
1. Extraia o zip numa pasta qualquer.
2. Dois cliques no **`Instalar.bat`**.
   - Se faltar o Python ou o ffmpeg, ele instala sozinho, só pra você, sem senha de administrador.
   - Ele mostra o que o seu PC aguenta (o **PC check**), instala o Kakashi e o plugin do Premiere (se você tem Premiere), e pergunta
     uma vez só se pode baixar o Tandera (diz quantos GB).
3. Pronto. O atalho do Kakashi é **Ctrl+Page Down** (o mesmo + Shift cancela). Pra trocar: atalho **KAKASHI** na área de trabalho →
   **TROCAR O ATALHO** → aperte o novo.

Prefere pelo Claude? Solte o zip no Claude Code e peça **"instala o Kakashi e o Tandera"**: ele segue o `INSTALAR-COM-CLAUDE.md`.

## Atualização
O Kakashi confere sozinho, duas vezes por dia, se tem versão nova aqui no GitHub. Quando tem, a janelinha do KAKASHI abre com o botão
**ATUALIZAR**: um clique e ele baixa e instala (o seu atalho, a sua configuração e as suas gravações ficam). O `/kakashi` e o
`/tandera` também avisam no Claude Code. Não precisa de conta no GitHub.

## O que roda no seu PC
O gravador do Kakashi é leve em qualquer PC. A transcrição da fala vai pela sua conta **ARDI**. O Tandera roda no seu PC o que ele
aguenta (o PC check diz o quê); o mais pesado (corpo, rosto, câmera) precisa de placa NVIDIA de 12 GB.

## O que ainda não tem
- **Mac**: está com o Piloto.
- Testado no PC do Luan; ainda não rodou no PC de outra pessoa. Deu erro? Grave com o próprio Kakashi (ou mande o print) pro Luan.

## Privacidade
Tudo fica no seu PC. Só o áudio da sua voz sobe pra ARDI quando o Claude transcreve. Senha nunca é gravada (campo de senha,
gerenciador de senha e janela com "senha/password" no título são pulados).
