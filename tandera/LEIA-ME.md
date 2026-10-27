# TANDERA — a análise de vídeo (Windows) · Fly

Feito pelo Luan Carvalho com o Claude Code, pro time da Fly. O Tandera **mede** o vídeo quadro a quadro (em que quadro corta, em que
milissegundo cada palavra começa, onde cai a batida, o que está escrito na tela, como a câmera anda) e entrega um dossiê pro Claude
entender o vídeo do jeito certo. Quem diz o que olhar é **você**: a régua é igual pra todo mundo, a receita é sua (o Claude monta com
você; o Plexus vem de exemplo).

## Instalar (dois cliques)
Extraia o zip e dê dois cliques no **`Instalar.bat`** da raiz. Ele põe o que faltar (Python, ffmpeg), mostra o que o seu PC aguenta (o
**PC check**), diz quantos GB o Tandera vai baixar e instala só o que o seu PC roda. Sem senha de administrador.
Prefere pelo Claude? Solte o zip no Claude Code e peça **"instala o Tandera"**: ele segue o `INSTALAR-COM-CLAUDE.md`.

## Usar
No Claude Code: **/tandera**, o caminho do vídeo e o que você quer saber dele ("os cortes caem na batida?", "a geração seguiu o
roteiro?", "o que tem escrito na tela?").

## O que o seu PC roda (medido em 26–27/10)
| PC | roda no PC | vai pela sua conta ARDI | não roda |
|---|---|---|---|
| **leve** (sem placa NVIDIA de 4 GB, ou menos de 16 GB de RAM) | cortes, quadros, texto na tela, cor | fala (o texto com o tempo da frase), o olho (a ficha do shot), a visão geral | separação, fala no ms, batida, câmera |
| **médio** (NVIDIA 4 GB+ e 16 GB+ de RAM) | + separação de voz/música/efeitos, fala no milissegundo, entonação, batida e música, 2ª opinião de corte | o olho e a visão geral | câmera |
| **forte** (NVIDIA 12 GB+ e 24 GB+ de RAM) | + câmera (a curva do movimento) e o olho no PC (com o Ollama) | a visão geral | — |

Corpo, rosto/boca e "qual efeito da biblioteca" ficam no PC do Luan (não vêm no pacote). Placa NVIDIA de 4 GB com pouca RAM roda a
separação e a fala **no limite**: o instalador não liga sozinho (dá pra ligar com o Claude, se você quiser).

## Licença dos modelos
Alguns modelos são **não comerciais** (CoTracker3 e MMS: CC BY-NC 4.0): uso interno da Fly, que não é comercial. A lista completa (de
onde cada um vem, tamanho e licença) está em `MODELOS.md`; o que vem dentro do zip, em `LICENCAS-TERCEIROS.md`.

## O que ainda não tem
- **Mac**: está com o Piloto.
- Testado (27/10) no PC do Luan: a instalação no nível leve numa pasta de teste e a análise de 3 vídeos curtos, que bateu com a do PC
  dele. Os níveis médio e forte ainda NÃO foram instalados do zero em outro PC. Deu erro? Grave com o Kakashi (ou mande o print) pro Luan.

## Privacidade
Tudo fica no seu PC (`%LOCALAPPDATA%\Programs\Tandera-Fly`). Só sobe pra sua conta ARDI o que o seu PC não roda, quando o Claude
pergunta antes.
