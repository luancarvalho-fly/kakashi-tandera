# EXEMPLO de receita completa: o PLEXUS (a receita do Luan, V1 de 20/10/2026)

Esta é a receita que o Luan montou pro Plexus (a série de animação gerada por IA da Fly). Está aqui como EXEMPLO do que uma receita
pronta tem: pra quê, quando usar cada parte, o que medir, o que perguntar ao vídeo, o que conferir no olho. A sua vai ser diferente;
monte com o `MODELO-DA-RECEITA.md`. Ela foi debatida com ele no chat e no Kakashi (20/10) e provada em testes com gabarito. Plexus é
FICÇÃO: tudo é gerado, então o vídeo segue o roteiro à risca («Plexus é ficção, Luan é vida real»).

## Regra que vale pra tudo: o ROTEIRO é a bússola
«Sempre com o roteiro na mão.» Toda leitura é conferida contra ele. **Provado (teste T2):** com o trecho do roteiro junto, o modelo dá
nome a quem só o roteiro nomeia, MAS só quando a imagem confirma, e aponta onde o vídeo DIFERE do roteiro, sem copiar.

## Antes de rodar: o briefing (1 linha) = estágio + pra quê
| estágio | pergunta | o que roda (`--estilo plexus --estagio ...`) |
|---|---|---|
| **A. Geração solta** (um shot que saiu do gerador) | "Deu certo? Se não, o que mudar: no PROMPT, no ROTEIRO ou nos dois?" | etapas 0 e 2 + o traçado ficha × roteiro × prompt. Sem som |
| **B. Montando** | montagem e storytelling | etapas 0, 1 (prevista pelo roteiro) e 2 |
| **C. Montado** | sonoplastia e sound design | 0 a 4. A ficha sonora SÓ aqui: «o entre-cenas conta muito» |

Estágio A, nas palavras dele: «fazer a ficha do shot e um traçado comparativo com o roteiro e o prompt, porque dependendo da alteração
você vai ter que alterar alguma coisa no prompt, ou no roteiro, ou nos dois». É assim que o aprendizado de longo prazo acontece. "Refaz
ou segue" se testa em shot com erro de verdade, nunca em material já escolhido.

Comando do estágio A (um shot com o trecho do roteiro, o prompt e o elenco):
```
"<pasta>\.venv\Scripts\python.exe" "<pasta>\tandera.py" "<shot.mp4>" --estilo plexus --estagio A --roteiro "<roteiro.md>"
      --shots-roteiro 64-69 --prompt "<prompt.txt>" --elenco "<pasta com as imagens do elenco>" --nome-shot "G1 · roteiro 64–69"
```
O elenco: uma imagem por personagem/objeto, com o NOME no nome do arquivo e a ALTURA entre parênteses: `PLEXUS (1 metro de altura).jpg`,
`PEDALEIRA (1,90 m de altura).jpg`. Subpasta `shot48\` = só daquele shot.

## Etapa 0 — medir (a régua). Roda UMA vez por arquivo e fica guardado
Cortes (AutoShot) · fala no ms (MMS) · separação voz/música/efeito · batida · câmera (CoTracker3: a CURVA do movimento) · texto na
tela (PP-OCRv6). Vídeo montado com shots já medidos: reaproveita. Reanalisar = reler a ficha pronta, não rodar o modelo de novo.

## Etapa 1 — visão geral
- B: partes / tensão / clímax PREVISTOS pelo roteiro. C: medidos no vídeo e conferidos contra o roteiro.
- Olho: um modelo que vê o vídeo INTEIRO com som (pela ARDI, `view_file` com o vídeo 480p). No teste T1 acertou 10/10 partes do EP01 a
  ±2 s e a tensão; o clímax é proposta. Nenhum modelo local aguenta o vídeo inteiro.

## Etapa 2 — ficha do shot
- Vai junto:
  - **quadros POR PLANO** (cortes medidos, 2–3 quadros em cada plano, inclusive nos curtos), com o **tempo escrito em cada quadro**. No
    teste T2, os quadros espaçados por igual pularam um plano de 1 s e geraram "falta" falso;
  - cabeçalho "shot N · de X a Y · vídeo de Z";
  - **ficha do elenco**: TODOS os assets ligados àquele shot na geração (todo shot do Fly Studio é feito com assets), com foto + nome +
    altura, numa imagem só. Provado (T1): com a ficha, a nave Feriado sai pelo nome;
  - o trecho do roteiro (T2).
- O que sai: quem (pelo nome), ação, lugar, efeito visual, troca de lugar/mundo, e o que DIFERE do roteiro.
- Olho: **gemma4:12b local** quando o PC aguenta (8 GB de placa; 8/10 no teste de 23/10, think DESLIGADO: pensando ele trava no que é
  ambíguo); senão, **pela ARDI** (`view_file` com a folha do shot + a ficha do elenco + o trecho do roteiro). Shot complexo ou
  momento-chave: o melhor modelo que a pessoa tiver (no teste T1, o Gemini Flash foi 9/10, o 1º lugar).
- **Sempre conferir no olho:** todo "FALTA" (pode ser só a amostragem) e todo "boca aberta = fala" (o roteiro empurra pra "falando").
- **Câmera:** nenhum modelo acerta sempre → vale a curva do CoTracker3.

## Etapa 3 — tira de momento (só C)
- No pacote da Fly a tira AUTOMÁTICA não roda (ela parte dos efeitos achados na biblioteca de sons do Luan, que não vem no pacote). Dá
  pra fazer na mão: os 13 quadros em volta do momento (os quadros saem pelo número; ver `quadros\` da análise) e a mesma pergunta.
- 13 quadros seguidos, com o número e o tempo, e a pergunta "em qual quadro exato acontece X".
- Resultado: os modelos acertam a ±1 quadro o que é NÍTIDO (fogo, clarão). Em movimento contínuo (porta) erram de 1 a 5 quadros. Aí: 2
  leitores + o olho.
- **O quadro devolvido é o PICO do som.** O clipe entra antes, pelo "até o pico" do arquivo de som, pra nunca ficar fora de sincronia.

## Etapa 4 — quem analisa (só C)
Junta tudo com o roteiro e o jeito de quem edita → a ficha sonora completa, olhando o ENTRE-CENAS:
- música de fundo da geração que precisa sair;
- mesmo lugar = mesma cama;
- J-cut e reverb de quem está no mesmo lugar;
- fala que acaba antes da imagem e precisa de costura.
