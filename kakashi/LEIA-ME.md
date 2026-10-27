# KAKASHI — o gravador de correção (Windows) · versão de 27/10/2026

Feito pelo Luan Carvalho. Ele resolve o "ficar mandando áudio, print e gravação de tela pro Claude": você aperta **o seu atalho**,
fala e mexe à vontade (no Chrome, no Fly Studio, no Premiere, em qualquer janela), aperta de novo e digita **/kakashi** no Claude Code.
O Claude lê a sua fala junto com o que estava na tela, onde o mouse estava, o link aberto, o que você copiou, um print com zoom de
cada "olha aqui" e, no Premiere, cada ação na timeline.

## Instalar (o jeito mais fácil)
Solte este zip no Claude Code e peça: **"instala o Kakashi"**. Ele segue o `INSTALAR-COM-CLAUDE.md`: primeiro roda o **PC check**
(mostra o que o seu PC aguenta), pergunta qual atalho você quer e se você tem conta na ARDI, e instala.
Na mão: extraia o zip e dê dois cliques no `Instalar.bat`.

## Usar
- **O atalho** (o do Luan é Ctrl+Page Down; você escolhe o seu na instalação) = começa / conclui. O mesmo + **Shift** = cancela (vai
  pra `sessoes\_descartadas`, nunca apaga).
- **Trocar o atalho** quando quiser: atalho **KAKASHI** na área de trabalho → **TROCAR O ATALHO** → aperte o novo (Esc cancela).
- O olho do Kakashi aparece no canto da tela só enquanto grava. A janelinha (atalho KAKASHI) lista as últimas gravações (abrir,
  descartar).
- **Premiere**: com o painel KAKASHI aberto no Premiere, o atalho grava pelo painel (com a timeline). Se você começa a gravar em outra
  janela e entra no Premiere, ele passa sozinho pro Premiere: é uma gravação só.
- **Replay**: ele guarda os últimos 2 minutos o tempo todo; quando você aperta o atalho, esses 2 min entram no começo (pra quando você
  lembra de gravar depois que já falou). Desligar: `config.json` → `"replay": false`. Enquanto o replay roda, o ícone de microfone em
  uso do Windows fica aceso.
- Depois de gravar: **/kakashi** no Claude Code.

## Onde roda o quê (PC check)
O instalador roda o `pc_check.py`, que olha o seu PC e diz o nível (N0 leve, N1 médio, N2 forte). O **gravador é leve em qualquer PC**
(medido: 0,1–1% do processador; ~1,2 GB por hora de disco no replay, apagado sozinho; no Premiere a tela grava na resolução do seu
monitor). A **transcrição** vai pela sua conta **ARDI** por padrão (centavos por gravação); sem ARDI, ela roda no próprio PC.

## O que esta versão NÃO tem
- **Mac**: o gravador é feito pro Windows; a versão do Mac está com o Piloto.
- O que foi testado (27/10): o gravador no PC do Luan (é o mesmo código que ele usa todo dia); a instalação limpa, o atalho escolhível,
  a janelinha e a leitura (PC, PC → Premiere, já lidas) numa pasta de teste no PC dele. Ainda NÃO rodou no PC de outra pessoa, e o
  painel do Premiere desta versão não foi instalado em nenhum Premiere. Se der erro, grave com o próprio Kakashi (ou mande o print)
  pro Luan.

## Privacidade
Tudo fica no seu PC (`%LOCALAPPDATA%\Programs\Kakashi-Fly\sessoes`). Só o áudio da sua voz sobe pra ARDI quando o Claude transcreve.
Senha nunca é gravada: campo de senha, gerenciador de senha e janela com "senha/password" no título são pulados.
