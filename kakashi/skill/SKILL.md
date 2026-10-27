---
name: kakashi
description: Lê a última gravação do KAKASHI (o gravador de correção que pega a voz, o som do PC, a tela, o mouse, a janela da frente, os links do Chrome, os prints do "aqui" e, no Premiere, cada ação da timeline) e transforma em pedidos, erros e decisões com o minuto. Use SEMPRE que a pessoa digitar /kakashi, ou disser "vê a gravação", "olha o que eu gravei no Kakashi", "gravei a correção", "passei o feedback pelo Kakashi".
---

# /kakashi — ler a gravação

A pessoa grava falando (o atalho dela começa e conclui; o padrão é Ctrl+Page Down, e cada um escolhe o seu) e digita /kakashi.
**O pedido dela está FALADO dentro da gravação: ela não vai repetir no chat.** Ler tudo antes de responder.
Pasta do Kakashi: `%LOCALAPPDATA%\Programs\Kakashi-Fly\` (abaixo, "a pasta"). Python dele: `.venv\Scripts\python.exe` da pasta.

## 0. JÁ LIDAS — antes de tudo, em TODO chat
0. **Versão nova?** `python atualizar.py --checar` (na pasta). Se disser `NOVA`, avise a pessoa numa linha no fim da resposta: "tem
   versão nova do Kakashi: botão ATUALIZAR na janelinha (atalho KAKASHI na área de trabalho)". Não atualize no meio da leitura.
1. `python kakashi_lidas.py novas` (na pasta) → só existe pra ler o que ele listar, da mais nova pra mais velha. Sessão com `LIDA.json`
   na pasta, ou `LEITURA-CLAUDE.md`, = OUTRO chat já leu: NÃO ler de novo, NÃO refazer o pedido dela.
2. Ao começar a trabalhar numa sessão: `python kakashi_lidas.py marcar "<pasta da sessão>" --chat <id deste chat> --nota "<o que virou>"`.
   Marcar LOGO, antes de fazer os pedidos: outro chat aberto pode estar olhando.

## 1. Achar a gravação (a MAIS NOVA que a lista deu)
- **PC** (qualquer janela: Chrome, ARDI, Fly Studio...): `sessoes\<AAAA-MM-DD_HHMMSS>_pc\`.
- **Premiere** (o painel do KAKASHI aberto): `premiere\sessoes\<AAAA-MM-DD_HHMM_SEQUÊNCIA>\` — `resumo.md` (cada ação da timeline),
  `audio.wav` (só a voz), `pc.wav` (só o som do PC), `tela.mp4`; e a pasta `_olho\` = o que a pessoa fez FORA da timeline enquanto o
  painel gravava (janela, mouse, elemento debaixo do mouse, print do "aqui", cópias, links), no MESMO relógio da sessão.
- **CONTINUA NO PREMIERE**: se a sessão de PC diz `"continua_em": "premiere"` (o `LEITURA.md` dela escreve "CONTINUA NO PREMIERE em
  m:ss" e o nome da sessão), a pessoa começou no PC e entrou no Premiere: é UMA correção só. Ler AS DUAS, na ordem PC → Premiere.
- Pular `_descartadas` e `sessao.json` com `"descartada": true` (a pessoa cancelou).
- Antes de reiniciar o Kakashi: `GET http://127.0.0.1:7816/status` (PC) e `GET http://127.0.0.1:7815/status` (Premiere) → `estado`
  tem que ser `parado`. Nunca reiniciar nem reinstalar no meio de uma gravação.

## 2. Transcrever (o motor está no `config.json` da pasta → `"transcricao"`)
- `"ardi"` (padrão de quem é da Fly): pelas ferramentas da ARDI. `upload_file` com o `fala.wav` da sessão de PC (no Premiere, o
  `_olho\fala.wav`) → rode o comando que ela devolve (curl) → `view_file` com o `assetId` (sem pergunta: é só transcrever). Salve o
  texto num .txt e rode `python importar_transcricao.py "<pasta da sessão ou _olho>" "<arquivo.txt>"`. Fica guardado.
  Sem as ferramentas da ARDI nesta sessão do Claude: diga isso e ofereça trocar pra `"local"`.
- `"local"`: o próprio resumo transcreve com o faster-whisper (o `perfil.json` do PC check diz se o PC aguenta).

## 3. Ler
- PC: `python resumo_pc.py "<pasta da sessão>" --quadros` → ler o `LEITURA.md` INTEIRO.
- Premiere: `python resumo_pc.py "<sessão>\_olho" --quadros` → ler o `_olho\LEITURA.md` INTEIRO junto com o `resumo.md` da sessão,
  pelo minuto (o print nativo do "aqui" vence o quadro do `tela.mp4`).
- Por trecho de 15 s: a fala literal, a janela da frente, o link exato do Chrome, o elemento debaixo do mouse, o que foi copiado
  (`_copias\`) e o print do "aqui / isso / esse / ó / olha" (`_prints\mmss_*_perto.jpg` = recorte em volta do cursor marcado de
  vermelho; abrir o recorte primeiro). Sem print perto: `_quadros\mmss.jpg`. **REPLAY**: se o topo disser REPLAY, 0:00–2:00 é o que
  aconteceu ANTES do atalho e conta como parte da gravação. Trechos de "voz muda" (`sessao.json` → `voz_muda`) entram como "não
  ouvido", nunca somem.

## 4. Entender — a gravação é pra NIVELAR o Claude, não só pra cumprir pedido
**A EXPLICAÇÃO VEM PRIMEIRO.** O que a pessoa FALA, do começo ao fim, junto do que ela fazia em cada minuto, é o centro. Comparar o
projeto/timeline de antes com o de depois serve pra conferir os números e achar o que ela fez calada; NUNCA substitui a fala.
(Erro de verdade que gerou esta regra: o Claude só comparou o projeto antigo com o novo e ignorou a explicação. Fala do Luan, 27/10:
«toda correção que eu fizer, ela vale pra nivelar o seu conhecimento, então não adianta nada você só comparar um projeto com outro,
que aí você tira toda a proposta do Kakashi... você tem que levar tudo em consideração, o projeto anterior com projeto novo, e ver a
minha explicação sobre isso».)
- **O MAIS NOVO VENCE.** Antes de guardar um ensinamento, conferir nas gravações MAIS NOVAS e na última versão que a PESSOA salvou se
  ela fez ou disse diferente depois. O caso velho fica marcado «MUDOU em <data>», não some. O que foi do momento (um lugar, um estado do
  projeto, frase de passagem) não vira «sempre»: «Não dá pra tu ficar levando tudo ao pé da letra».
- **Cruzar com o que já existe:** procurar nas instruções e skills da pessoa (CLAUDE.md, skills dela) o que briga com o ensinamento novo
  e PROPOR o ajuste. Ajuste dela = caso; vira regra só quando ela disser que é sempre.
- **Catar o que ela mostra:** arquivo, link ou referência que ela abre na gravação = guardar já na leitura (o caminho exato, o link do
  `links.json`). Nunca dizer "não achei" sem olhar o `links.json`, as `_copias\` e os prints daquele minuto.
- Dúvida sobre o que ela mostrou = caçar antes de perguntar (cliques no `eventos.jsonl`, quadros, links). Pergunta que sobrar = no chat,
  com o minuto, curta, com opções.

## 5. Responder e fazer — NADA DE FORA
- Escrever o `LEITURA-CLAUDE.md` na pasta da sessão: Pedidos diretos · Erros do Claude (fala dela) · Respostas a perguntas · Critérios
  dela (casos) · Ordens de "não fazer". Sempre a fala LITERAL curta entre aspas + `[mm:ss]`.
- Cada pedido falado vira uma linha de checklist (fala + minuto + onde foi feito). Pedido que vale pra mais de um lugar ("a roxa tem que
  ser verde") vale em TODOS os lugares. Gravação longa ou várias gravações do mesmo projeto: checklist de TODAS, não só da última.
- Responder em português simples, lista numerada: o que entendeu, o que vai fazer, o que ficou ambíguo. Pedido claro = fazer. Decisão
  nova = propor e esperar o OK. Antes de dizer "feito": reler a fala inteira e riscar item por item.

## Trocar o atalho
A pessoa pode trocar quando quiser: janelinha do KAKASHI (atalho KAKASHI na área de trabalho) → **TROCAR O ATALHO** → apertar o novo
(Esc cancela); vale na hora. Se ela pedir pra você: conferir com `python atalho.py --conferir "ctrl+alt+k"` (diz se vale e se está
livre), gravar em `config.json` → `"atalho"` e pedir pra ela usar o botão TROCAR O ATALHO, ou reiniciar o Kakashi com ele `parado`.

## Cuidados
- Só lê: o Kakashi nunca toca som e não usa a placa de vídeo.
- Senha nunca é lida (o gravador pula campo de senha e gerenciador de senha).
- A gravação é da pessoa: não mande pra lugar nenhum além da transcrição (ARDI dela).
- A tela pode ser 4K: recortar só a região que importa antes de olhar.
