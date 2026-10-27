---
name: tandera
description: Análise de vídeo do time da Fly com o TANDERA (a RÉGUA que mede o vídeo quadro a quadro: cortes, fala no milissegundo, batida, música, texto na tela, câmera, cor) + a RECEITA de cada pessoa (o que olhar em cada estilo) + a ARDI pro que o PC não roda. Use SEMPRE que a pessoa digitar /tandera, ou pedir pra analisar um vídeo, "ver os cortes", "medir a fala", "ver se a geração deu certo", "comparar com o roteiro", "o que tem escrito na tela", "a batida casa com o corte?", "faz a ficha dos shots", ou quiser montar a receita de análise dela.
---

# /tandera — analisar um vídeo com a régua

**A régua é universal; a receita é de cada um.** A régua (o Tandera) MEDE: em que quadro corta, em que milissegundo cada palavra
começa, onde cai a batida, o que está escrito na tela, como a câmera anda. A receita diz o que olhar, em que ordem e pra quê, e é da
PESSOA: cada um tem a sua (o Plexus é um exemplo completo em `receitas\plexus.md`).

**A EXPLICAÇÃO DA PESSOA VEM PRIMEIRO; a medida confere.** O que ela diz que o vídeo é e o que ela quer saber é o centro. A medida
serve pra conferir, achar o que ninguém viu e dar o número exato; nunca substitui o contexto. (Fala do Luan, 27/10, sobre o mesmo erro
em outra ferramenta: «não adianta nada você só comparar um projeto com outro... você tem que levar tudo em consideração... e ver a minha
explicação». E do estudo da régua: medida sem contexto pergunta errado: «o contexto é o parâmetro mais importante».)

## 0. Antes de tudo (todo chat)
1. **A pasta do Tandera:** `%LOCALAPPDATA%\Programs\Tandera-Fly\` (abaixo, "a pasta"). Se esta skill tem o arquivo `.tandera-fly`, o
   caminho escrito nele vale. O Python dele: `<pasta>\.venv\Scripts\python.exe` (nunca o Python do sistema).
2. **Versão nova?** Se existir `<pasta>\atualizar.py`: rode `"<pasta>\.venv\Scripts\python.exe" "<pasta>\atualizar.py" --checar`. Se
   disser `NOVA`, avise numa linha no fim da resposta: "tem versão nova do Tandera: rode o Instalar.bat da versão nova (ou o botão
   ATUALIZAR da janelinha do Kakashi)". Não atualize no meio de uma análise.
3. **O que este PC roda:** leia `<pasta>\config.json` (`etapas_no_pc`, `nivel`, `sem_placa`) e `<pasta>\perfil.json` (o PC check:
   `etapas[]` com `onde` = LOCAL · ARDI · LIMITE · NÃO, e o `obs` de cada uma). Diga pra pessoa, em palavras simples, o que vai medir no
   PC dela, o que vai pela ARDI e o que fica de fora, ANTES de rodar. Etapa fora do PC nunca é "preenchida no chute".
4. **ffmpeg** no caminho (`ffmpeg -version`); se não achar, peça pra ela rodar o Instalar.bat de novo.

## 1. Entender o pedido (a explicação dela)
Se ela ainda não disse, pergunte (curto, uma coisa de cada vez, com opções):
- **O que é o vídeo** (dela? de referência? uma geração solta? o montado?) e **pra que ela quer a análise** (decidir o quê?).
- **O estilo** (ver o §2) e, se tiver: o **roteiro**, o **prompt** da geração, as **imagens do elenco**, o **trecho** (de/até).
O que ela explicar entra na resposta como o norte; a medida vem depois, pra confirmar, contradizer ou detalhar.

## 2. A receita (de quem pediu)
1. Ela já tem receita? Procure em `<pasta>\minhas-receitas\` (um `.md` por receita). Tem: leia inteira e siga.
2. Não tem: comece pela **receita-base do estilo** (`receitas\estilos-base.md`, nesta skill) e mostre o **exemplo completo do Plexus**
   (`receitas\plexus.md`) como modelo do que uma receita pronta tem. Monte a dela COM ela, no molde `receitas\MODELO-DA-RECEITA.md`:
   o que ela quer saber, o que medir, o que olhar, a ordem. Grave em `<pasta>\minhas-receitas\<nome>.md` só com o OK dela.
3. **Nada vira regra sem ela dizer.** O que ela corrigir numa análise é CASO (com a data e a fala dela); vira regra da receita quando ela
   disser que é sempre. Escolha que foi do momento não vira "sempre".

## 3. Medir (rodar o Tandera)
```
"<pasta>\.venv\Scripts\python.exe" "<pasta>\tandera.py" "<vídeo>" --estilo plexus|cinematico|camera-parada|vlog [--estagio A|B|C]
      [--modo rapido] [--roteiro ARQ [--shots-roteiro 64-69]] [--elenco PASTA] [--prompt ARQ] [--de S --ate S] [--idioma pt]
      [--saida PASTA] [--refazer tudo|etapa,etapa] [--projeto NOME]
```
- `--estilo` escolhe a receita de medidas (§2). `--estagio` só no Plexus (A geração solta · B montando · C montado).
- `--modo rapido` = só cortes + 1 quadro por shot (triagem). `--de/--ate` = só um trecho (os números de shot e o tempo continuam os do
  vídeo inteiro). `--idioma pt` quando ela disser que a fala é em português (sem isso, descobre sozinho).
- O que este PC não aguenta já sai sozinho (o `config.json` desliga; com `sem_placa` o `--sem-placa` entra sozinho). Não force etapa
  desligada.
- **Tempo** (medido em 26/10 num notebook fraco, no processador): ~1 min pra um vídeo de 15–25 s (cortes, quadros, texto na tela).
  Com separação e fala na placa, alguns minutos a mais. Vídeo longo: rode em segundo plano e avise.
- **A placa:** se o Tandera usa a placa neste PC e o Premiere está aberto, ele PARA de propósito (código 3: "feche o Premiere e rode de
  novo; o que já foi medido fica guardado"). Avise a pessoa; nunca rode dois trabalhos na placa ao mesmo tempo (`<pasta>\GPU_EM_USO.txt`
  = outro trabalho usando).
- **Saída:** `<pasta>\analises\tandera\<vídeo>_<estilo>...\` (ou `--saida`): `DOSSIE.md` (o legível), `dados.json` (tudo), `folhas\`
  (os quadros de cada shot numa imagem, com o tempo escrito), `quadros\`. A medida fica guardada em `<pasta>\cache\`: rodar de novo
  reaproveita (`--refazer` mede de novo).

## 4. O que o PC não roda: pela ARDI (se a pessoa tem conta; `perfil.json` → `tem_ardi`)
As ferramentas da ARDI no Claude Code: arquivo do PC = `upload_file` → rodar o comando que ela devolve → `view_file` com a pergunta da
pessoa, nas palavras dela. Custa centavos e fica registrado na conta dela: diga antes.
- **Fala** (quando a separação/fala não roda no PC): tire o som com `ffmpeg -i "<vídeo>" -vn -ac 1 -ar 16000 "<pasta da análise>\fala.wav"`,
  suba e peça "transcreva com o tempo de cada frase". Vem o texto com [m:ss]: é o tempo da FRASE, não o milissegundo da palavra (isso
  só a régua local mede). Escreva isso junto.
- **Olho / ficha do shot** (sem o olho local): suba a folha do shot (`folhas\shot_NNN.jpg`, já com o tempo escrito em cada quadro) e,
  se tiver, a ficha do elenco e o trecho do roteiro, com a pergunta da pessoa. Câmera NÃO vale pelo que o modelo diz (vale a curva do
  CoTracker3, quando o PC mede).
- **Visão geral do vídeo inteiro:** suba o vídeo (se for grande, uma cópia 480p: `ffmpeg -i "<vídeo>" -vf scale=-2:480 -c:v libx264 -crf 28
  -c:a aac "<pasta da análise>\video_480p.mp4"`) e pergunte as partes, onde a tensão sobe, o clímax.
- Sem ARDI: diga o que ficou de fora e siga só com o que foi medido.

## 5. Ler o DOSSIÊ e o dados.json (o que é universal)
- **Calibração** (topo): fps, tamanho, a folga do AAC (o som de vídeo exportado em AAC vem ~21 ms atrasado; já descontada), take
  possivelmente deitado (conferir antes de ler corpo/rosto). Todo quadro citado é o NÚMERO do quadro no vídeo (`q123`), com o tempo.
- **Cortes:** AutoShot (o escolhido por teste, ~97% no quadro exato). Com a 2ª opinião: o que só um dos dois viu e os "possíveis cortes"
  da diferença de pixel (jump cut, clarão) vêm marcados ⚠ conferir no olho.
- **Fala** (`dados.json` → `fala.palavras`: `p`, `ini`, `fim` em segundos): o início da palavra a ~8 ms (a régua acerta 74% a 1 quadro);
  o fim tem a cauda de eco. **Entonação:** altura no começo/fim de cada trecho, final sobe/desce/plano, sílabas por segundo.
- **Batida:** Beat This! no som da música separado; **grade** fechada na onda quando a música é de tempo fixo; **corte × batida**: quantos
  cortes caem no quadro da batida, e quanto o acaso daria. **Música:** partes, subidas, drop, viradas, respiros (medida, sem modelo).
- **Pacote de cada corte:** a fala dos 4 s antes, quanto antes acabou a palavra, quanto depois começa a próxima, a batida mais perto.
- **Texto na tela** (PP-OCRv6): só leitura com nota ≥ 0,8; "vezes" = em quantos quadros a mesma palavra apareceu.
- **Câmera:** vale a CURVA medida (deslocamento e escala); "pouca confiança" quando poucos pontos foram seguidos (fogo, explosão).
- **Cor:** brilho, saturação, quente − frio por shot.
- **Ficha do shot / tira** (olho local): todo **FALTA** e todo "boca aberta = fala" vêm ⚠: conferir no olho antes de afirmar.
- **O que não está no dossiê não foi medido.** Nunca preencha: diga "não medido neste PC" (e, se der, ofereça a ARDI).

## 6. Responder
- Comece pelo que ELA perguntou, com a explicação dela como norte; depois a medida que confirma ou contradiz (diga qual).
- Cite o quadro e o tempo (`q186 · 0:07.75`). Antes de afirmar algo visual, ABRA a folha ou o quadro (o dossiê aponta o arquivo).
- Separe: **MEDIDO** (número da régua) · **LEITURA** (a sua interpretação, marcada assim) · **PERGUNTA** (o que só ela sabe).
- Disputa (duas medidas brigando, ou medida × o que ela disse): mostre os quadros em volta (F−2…F+1) e deixe ela decidir.
- No fim: o que ficou de fora neste PC e, se ela quiser, o que aprendemos que pode entrar na receita dela (só com o OK).

## Cuidados
- O Tandera só LÊ o vídeo: não mexe no vídeo nem no projeto da pessoa.
- O vídeo é dela: sobe pra ARDI só o necessário e só quando o PC não roda (diga antes).
- Licença: alguns modelos são NÃO COMERCIAIS (CoTracker3, MMS): uso interno da Fly. Lista em `<pasta>\MODELOS.md`.
- Tela grande (4K): recorte a região que importa antes de olhar um quadro.
