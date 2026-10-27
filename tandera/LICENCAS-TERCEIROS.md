# Licenças do que vem DENTRO deste pacote (de terceiros)

## AutoShot — `modelos/autoshot.onnx`
Origem: github.com/wentaozhu/AutoShot (artigo: "AutoShot: A Short Video Dataset and State-of-the-Art Shot Boundary Detection", CVPR
2023 Workshops). Peso `ckpt_0_200_0.pth` (o dos autores; cópia do espelho huggingface.co/backseollgi/AutoShot), convertido pra ONNX
(mesma saída do PyTorch até 0,000003) por Luan Carvalho, sem treinar nem mudar nada.

```
MIT License

Copyright (c) 2023 Wentao Zhu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Beat This! — `modelos/torch/hub/checkpoints/beat_this-final0.ckpt`
Origem: github.com/CPJKU/beat_this (o checkpoint `final0`, da nuvem da JKU: cloud.cp.jku.at/index.php/s/7ik4RrBKTS273gp). O README do
projeto: "The code and the published model weights are released under the MIT license".

```
MIT License

Copyright (c) 2024 Institute of Computational Perception, JKU Linz, Austria

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

O resto (código de terceiros e modelos maiores) NÃO vem no zip: o `instalar.py` baixa das fontes oficiais. Lista e licenças: `MODELOS.md`.
