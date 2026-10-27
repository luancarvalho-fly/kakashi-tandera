# Os modelos do Tandera: de onde vêm, tamanho, licença (conferido em 27/10/2026)

O pacote vai num GitHub PÚBLICO. Por isso só entra DENTRO do zip modelo com menos de 95 MB e licença que deixa redistribuir; o resto o
`instalar.py` baixa da fonte OFICIAL, num ponto fixo (o commit/versão que foi testado), e confere o tamanho (e o sha256 quando a fonte
publica). Ele só baixa o que o nível do PC usa.

| modelo | pra quê | quando baixa | fonte oficial | tamanho | licença | no zip? |
|---|---|---|---|---|---|---|
| **AutoShot** (`autoshot.onnx`) | cortes | sempre | código e peso dos autores: github.com/wentaozhu/AutoShot (o peso original fica no Baidu; o usado veio do espelho huggingface.co/backseollgi/AutoShot, `ckpt_0_200_0.pth`, 57,2 MB, mesmo tamanho do original) → convertido pra ONNX pelo Luan (CUTX, 01/10) | 34,0 MB | MIT | **sim** (não existe ONNX oficial) |
| **PP-OCRv6 medium** (det + rec + dicionário) | texto na tela | sempre | huggingface.co/PaddlePaddle/PP-OCRv6_medium_det_onnx (commit 6132380) e .../PP-OCRv6_medium_rec_onnx (commit 50c7eac); o dicionário sai do `inference.yml` do rec | 62,0 + 76,6 MB | Apache-2.0 | não (baixa) |
| **TransNetV2** (pesos dentro do pacote pip `transnetv2-pytorch` 1.0.5) | 2ª opinião de corte | nível médio+ (vem com os pacotes) | pypi.org/project/transnetv2-pytorch | 32,7 MB | MIT | não (pip) |
| **Roformer** `model_bs_roformer_ep_317_sdr_12.9755.ckpt` | separação: a voz | médio+ | github.com/TRvlvr/model_repo (repositório de modelos do UVR), baixado pelo `audio-separator` | 639,3 MB | não declarada pelo repositório | não (baixa) |
| **BandIt Plus** `model_bandit_plus_dnr_sdr_11.47.chpt` | separação: música × efeitos | médio+ | github.com/ZFTurbo/Music-Source-Separation-Training, release v.1.0.3 (código do MSST no commit 2ba884c) | 148,9 MB | MSST: MIT · BandIt original (kwatcharasupat/bandit): Apache-2.0 | não (baixa) |
| **faster-whisper large-v3** | fala (o texto) | médio+ | huggingface.co/Systran/faster-whisper-large-v3 (commit edaa852) | 3,09 GB | MIT | não (baixa) |
| **MMS** (alinhamento, `MMS_FA` do torchaudio) | fala (o milissegundo da palavra) | médio+ | dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt (Meta) | 1,26 GB | **CC BY-NC 4.0 (não comercial)** | não (baixa) |
| **Beat This!** `final0.ckpt` | batida | sempre (vem no zip) | github.com/CPJKU/beat_this (o peso fica na nuvem da JKU, cloud.cp.jku.at; código no commit b95c8ab) | 81,1 MB | MIT (código e pesos, diz o README) | **sim** (o servidor oficial deu erro 500 em 27/10) |
| **CoTracker3** `scaled_offline.pth` | câmera | forte | huggingface.co/facebook/cotracker3 (commit bf55ea5) + código github.com/facebookresearch/co-tracker (commit 82e02e8) | 101,9 MB | **CC BY-NC 4.0 (não comercial)** (peso e código) | não (baixa) |
| **gemma4:12b** (Ollama) | olho local (ficha do shot) | forte, se o Ollama já está instalado | ollama.com/library/gemma4 | 8,02 GB | Apache-2.0 | não (o Ollama baixa) |

Ficam no PC do Luan (não vêm no pacote): **Sapiens2-1B** (corpo; huggingface.co/facebook/sapiens2-pose-1b, 6,08 GB, licença própria
"sapiens2-license") + o detector DETR (Apache-2.0); **OpenFace 3.0** (rosto; precisa de WSL); a **biblioteca de efeitos** dele.

**Não comercial (CC BY-NC 4.0):** CoTracker3 e MMS. Uso interno da Fly, que não é comercial (o Luan liberou pro time em 21/10).
