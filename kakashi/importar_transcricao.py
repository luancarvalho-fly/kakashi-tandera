# -*- coding: utf-8 -*-
"""Grava a transcrição que o Claude trouxe da ARDI (view_file) no formato que o resumo_pc.py lê.

  python importar_transcricao.py <pasta da sessão> <arquivo.txt com o texto do view_file>

O view_file devolve uma linha por trecho com o tempo: "[1:23] texto" (ou "[1:23–1:30] texto", "[0:01:23] texto").
Isto vira fala_transcricao.json na pasta da sessão, com a marca do fala.wav (o resumo não transcreve de novo).
"""
import json, os, re, sys

TEMPO = re.compile(r"^\s*\[?\s*(\d+):(\d\d)(?::(\d\d))?(?:[.,]\d+)?\s*(?:[-–—]\s*(\d+):(\d\d)(?::(\d\d))?(?:[.,]\d+)?)?\s*\]?\s*[-–:]?\s*(.*)$")


def seg(h_or_m, m_or_s, s):
    return int(h_or_m) * 3600 + int(m_or_s) * 60 + int(s) if s is not None else int(h_or_m) * 60 + int(m_or_s)


def main():
    pasta, txt = sys.argv[1], sys.argv[2]
    wav = os.path.join(pasta, "fala.wav")
    linhas = []
    for l in open(txt, encoding="utf-8"):
        m = TEMPO.match(l)
        if not m or not m.group(7).strip():
            continue
        ini = seg(m.group(1), m.group(2), m.group(3))
        fim = seg(m.group(4), m.group(5), m.group(6)) if m.group(4) else None
        linhas.append([ini, fim, m.group(7).strip()])
    if not linhas:
        sys.exit("não achei nenhuma linha com tempo ([m:ss] texto) no arquivo")
    segs = []
    for i, (a, b, t) in enumerate(linhas):
        if b is None:
            b = linhas[i + 1][0] if i + 1 < len(linhas) else a + 5
        segs.append([float(a), float(max(b, a + 0.5)), t])
    marca = [os.path.getsize(wav), int(os.path.getmtime(wav))]
    json.dump({"marca": marca, "segmentos": segs, "fonte": "ARDI view_file"},
              open(os.path.join(pasta, "fala_transcricao.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"ok: {len(segs)} trechos gravados em {os.path.join(pasta, 'fala_transcricao.json')}")


if __name__ == "__main__":
    main()
