# -*- coding: utf-8 -*-
"""Tandera V2 — texto na tela com PP-OCRv6 medium (onnx) dentro do RapidOCR 1.2.3, no processador (o venv-ler da pasta).
Igual ao testes\\ler\\rodar_rapidocr.py (PLACAR-LER, 20/10: 0 erro e 7/7 acentos no Plexus): os 2 onnx + o dicionário do v6,
com o mesmo remendo de 3 linhas (o RapidOCR 1.2.3 não aceita dicionário por parâmetro).
Uso: <python do venv-ler> tandera_ocr.py entrada.json saida.json   (entrada = {"imagens": [...], "det", "rec", "dic"})"""
import json, os, sys, time

ent = json.load(open(sys.argv[1], encoding="utf-8"))
from rapidocr_onnxruntime import RapidOCR  # noqa: E402
import ch_ppocr_v3_rec.utils as ru  # noqa: E402  (o RapidOCR importa como módulo de topo)
_orig = ru.CTCLabelDecode.__init__
ru.CTCLabelDecode.__init__ = lambda self, _p, _d=ent["dic"]: _orig(self, _d)

eng = RapidOCR(det_model_path=ent["det"], rec_model_path=ent["rec"])
res = {}
for f in ent["imagens"]:
    if not f or not os.path.exists(f):
        continue
    t = time.perf_counter()
    r, _ = eng(f)
    res[f] = {"s": round(time.perf_counter() - t, 2),
              "linhas": [{"texto": b[1], "nota": round(float(b[2]), 3),
                          "y": [round(float(min(p[1] for p in b[0]))), round(float(max(p[1] for p in b[0])))]} for b in (r or [])]}
json.dump(res, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ocr:", len(res), "imagens")
