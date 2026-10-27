# -*- coding: utf-8 -*-
"""Fonte pixel 5x7 do KAKASHI — a MESMA do painel do Premiere (CORRETOR_v0.2_dev\\_icone_novo\\gerar_pixel.py), com as letras que
faltavam pro Kakashi único (19/10: K, W, X, Y, '-', '/', Ó). Ele: "o Kakashi todo é pra tá na estética do plugin do Premiere, todo 8 bits".
render(texto, escala, cor) → imagem PIL (RGBA). Escala 2 = letra miúda do painel; 3 = rótulo de botão; 5 = relógio."""
from PIL import Image

G = {
 '0': [".XXX.", "X...X", "X..XX", "X.X.X", "XX..X", "X...X", ".XXX."],
 '1': ["..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", ".XXX."],
 '2': [".XXX.", "X...X", "....X", "...X.", "..X..", ".X...", "XXXXX"],
 '3': ["XXXX.", "....X", "....X", ".XXX.", "....X", "....X", "XXXX."],
 '4': ["...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."],
 '5': ["XXXXX", "X....", "XXXX.", "....X", "....X", "X...X", ".XXX."],
 '6': [".XXX.", "X....", "X....", "XXXX.", "X...X", "X...X", ".XXX."],
 '7': ["XXXXX", "....X", "...X.", "..X..", ".X...", ".X...", ".X..."],
 '8': [".XXX.", "X...X", "X...X", ".XXX.", "X...X", "X...X", ".XXX."],
 '9': [".XXX.", "X...X", "X...X", ".XXXX", "....X", "....X", ".XXX."],
 'A': [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
 'B': ["XXXX.", "X...X", "X...X", "XXXX.", "X...X", "X...X", "XXXX."],
 'C': [".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX"],
 'D': ["XXXX.", "X...X", "X...X", "X...X", "X...X", "X...X", "XXXX."],
 'E': ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "XXXXX"],
 'F': ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."],
 'G': [".XXXX", "X....", "X....", "X.XXX", "X...X", "X...X", ".XXXX"],
 'H': ["X...X", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
 'I': ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "XXXXX"],
 'J': ["..XXX", "...X.", "...X.", "...X.", "...X.", "X..X.", ".XX.."],
 'K': ["X...X", "X..X.", "X.X..", "XX...", "X.X..", "X..X.", "X...X"],
 'L': ["X....", "X....", "X....", "X....", "X....", "X....", "XXXXX"],
 'M': ["X...X", "XX.XX", "X.X.X", "X.X.X", "X...X", "X...X", "X...X"],
 'N': ["X...X", "XX..X", "X.X.X", "X..XX", "X...X", "X...X", "X...X"],
 'O': [".XXX.", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
 'P': ["XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."],
 'Q': [".XXX.", "X...X", "X...X", "X...X", "X.X.X", "X..X.", ".XX.X"],
 'R': ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"],
 'S': [".XXXX", "X....", "X....", ".XXX.", "....X", "....X", "XXXX."],
 'T': ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."],
 'U': ["X...X", "X...X", "X...X", "X...X", "X...X", "X...X", ".XXX."],
 'V': ["X...X", "X...X", "X...X", "X...X", "X...X", ".X.X.", "..X.."],
 'W': ["X...X", "X...X", "X...X", "X.X.X", "X.X.X", "XX.XX", "X...X"],
 'X': ["X...X", "X...X", ".X.X.", "..X..", ".X.X.", "X...X", "X...X"],
 'Y': ["X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."],
 'Z': ["XXXXX", "....X", "...X.", "..X..", ".X...", "X....", "XXXXX"],
 'Ç': [".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX", "...X."],
 '?': [".XXX.", "X...X", "....X", "...X.", "..X..", ".....", "..X.."],
 '.': [".....", ".....", ".....", ".....", ".....", ".....", "..X.."],
 ':': ["...", ".X.", ".X.", "...", ".X.", ".X.", "..."],
 '-': ["....", "....", "....", "XXXX", "....", "....", "...."],
 '+': [".....", "..X..", "..X..", "XXXXX", "..X..", "..X..", "....."],
 '/': ["....X", "....X", "...X.", "..X..", ".X...", "X....", "X...."],
 ' ': ["...", "...", "...", "...", "...", "...", "..."],
 '·': ["...", "...", "...", ".X.", "...", "...", "..."],
 '●': [".....", ".XXX.", "XXXXX", "XXXXX", "XXXXX", ".XXX.", "....."],
}
CORES = {
 'vermelho': ((255, 92, 92), (232, 16, 30), (150, 0, 18), (40, 0, 6)),
 'branco':   ((255, 255, 255), (238, 238, 238), (190, 190, 196), (70, 0, 10)),
 'amarelo':  ((255, 244, 160), (255, 214, 10), (196, 160, 0), (10, 10, 13)),
 'cinza':    ((150, 150, 160), (120, 120, 132), (96, 96, 106), (8, 8, 10)),
 'apagado':  ((96, 96, 106), (78, 78, 88), (60, 60, 70), (8, 8, 10)),
}
SEM = {'Á': 'A', 'À': 'A', 'Ã': 'A', 'Â': 'A', 'É': 'E', 'Ê': 'E', 'Í': 'I', 'Ó': 'O', 'Õ': 'O', 'Ô': 'O', 'Ú': 'U'}


def render(txt, E=2, cor='branco'):
    txt = ''.join(SEM.get(c, c) for c in str(txt).upper())
    txt = ''.join(c if c in G else ' ' for c in txt)
    cl, cm, ce, sb = [c + (255,) for c in CORES[cor]]
    larg = sum(len(G[ch][0]) + (1 if ch != ':' else 0) for ch in txt) or 1
    img = Image.new('RGBA', (larg * E, 8 * E), (0, 0, 0, 0))
    px = img.load()

    def ponto(x, y, c):
        for yy in range(y * E, y * E + E):
            for xx in range(x * E, x * E + E):
                if xx < img.width and yy < img.height:
                    px[xx, yy] = c
    for camada in (0, 1):
        x0 = 0
        for ch in txt:
            g = G[ch]
            for y, lin in enumerate(g):
                for x, v in enumerate(lin):
                    if v == 'X':
                        if camada == 0:
                            ponto(x0 + x + 1, y + 1, sb)
                        else:
                            ponto(x0 + x, y, cl if y <= 1 else (ce if y >= 6 else cm))
            x0 += len(g[0]) + (1 if ch != ':' else 0)
    return img
