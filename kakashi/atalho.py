# -*- coding: utf-8 -*-
"""ATALHO ESCOLHÍVEL do KAKASHI (pacote da Fly, 27/10/2026). Só existe no pacote: o Kakashi do Luan continua com o dele fixo.

Ele (21/10): «esse atalho Ctrl e Page Down... É atalho do meu PC, pode ser qualquer atalho... o atalho que a pessoa quiser»
e (27/10): «coloca pra pessoa customizar o atalho do Kakashi... se ela quiser usar outro, ela pode trocar».

config.json → "atalho": "ctrl+pagedown" (começa / conclui; o padrão é o do Luan) e, se quiser, "atalho_cancelar"
(sem ele: o mesmo + shift; se o atalho já tem shift, o mesmo + alt). Texto livre: ctrl, alt, shift, win + UMA tecla
(letra, número, f1–f24, pagedown, pageup, home, end, insert, delete, pause, scrolllock, espaco, setas, numpad0–9).
Trocar: janelinha do KAKASHI → TROCAR O ATALHO (vale na hora, sem reiniciar) ou o config.json + reiniciar o Kakashi.

  python atalho.py --conferir "ctrl+alt+k"   → diz se o texto vale e se o atalho está livre (o instalador usa)
"""
import ctypes, sys, time

user32 = ctypes.windll.user32
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
WM_APP = 0x8000
WM_RECARREGAR = WM_APP + 1      # a thread do atalho relê o config.json e registra de novo
WM_SOLTAR = WM_APP + 2          # a thread solta os atalhos (enquanto a pessoa aperta o novo na janelinha)
PADRAO = "ctrl+pagedown"

TECLAS = {"pagedown": 0x22, "pageup": 0x21, "end": 0x23, "home": 0x24, "insert": 0x2D, "delete": 0x2E, "pause": 0x13,
          "scrolllock": 0x91, "espaco": 0x20, "esquerda": 0x25, "cima": 0x26, "direita": 0x27, "baixo": 0x28}
TECLAS.update({chr(c).lower(): c for c in range(0x41, 0x5B)})                    # a–z
TECLAS.update({str(n): 0x30 + n for n in range(10)})                             # 0–9
TECLAS.update({"f%d" % n: 0x6F + n for n in range(1, 25)})                       # f1–f24
TECLAS.update({"numpad%d" % n: 0x60 + n for n in range(10)})
APELIDOS = {"control": "ctrl", "pgdn": "pagedown", "page down": "pagedown", "pgup": "pageup", "page up": "pageup",
            "windows": "win", "space": "espaco", "espaço": "espaco", "del": "delete", "ins": "insert", "scroll lock": "scrolllock",
            "left": "esquerda", "up": "cima", "right": "direita", "down": "baixo"}
MODS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
NOME = {"pagedown": "PAGE DOWN", "pageup": "PAGE UP", "scrolllock": "SCROLL LOCK", "espaco": "ESPACO"}
SOZINHA_PODE = {0x13, 0x91} | set(range(0x70, 0x88))       # sem modificador só vale pause, scroll lock e f1–f24
VK_NOME = {v: k for k, v in TECLAS.items()}

THREAD_ID = None        # a thread do atalho (kakashi.pyw) escreve aqui o id dela
ATIVO = None            # {"gravar": {...}, "cancelar": {...}} registrado agora


def ler(txt):
    """'ctrl+alt+k' → {"mods", "vk", "texto", "nome"}; texto que não vale → ValueError com o motivo (em palavras simples)."""
    partes = [APELIDOS.get(p.strip().lower(), p.strip().lower()) for p in str(txt or "").split("+") if p.strip()]
    mods, tecla = 0, None
    for p in partes:
        if p in MODS:
            mods |= MODS[p]
        elif p in TECLAS:
            if tecla:
                raise ValueError("só pode UMA tecla além de ctrl/alt/shift/win (veio %s e %s)" % (tecla, p))
            tecla = p
        else:
            raise ValueError("não conheço a tecla «%s»" % p)
    if not tecla:
        raise ValueError("falta a tecla (ex.: ctrl+alt+k)")
    a = montar(mods, TECLAS[tecla])
    erro = validar(a)
    if erro:
        raise ValueError(erro)
    return a


def montar(mods, vk):
    tecla = VK_NOME.get(vk, "vk%d" % vk)
    ordem = [m for m in ("ctrl", "alt", "shift", "win") if mods & MODS[m]]
    return {"mods": mods, "vk": vk, "texto": "+".join(ordem + [tecla]),
            "nome": "+".join([m.upper() for m in ordem] + [NOME.get(tecla, tecla.upper())])}


def validar(a):
    if a["vk"] == 0x1B:
        return "o Esc não pode (ele cancela a troca)"
    so_shift = a["mods"] in (0, MOD_SHIFT)
    if so_shift and a["vk"] not in SOZINHA_PODE:
        return "use ctrl, alt ou win junto (senão o atalho dispara enquanto você digita)"
    return ""


def cancelar_de(g):
    """o atalho de cancelar quando o config não diz: o mesmo + shift (o do Luan: Ctrl+Shift+Page Down); já tem shift → + alt."""
    for extra in (MOD_SHIFT, MOD_ALT):
        if not g["mods"] & extra:
            return montar(g["mods"] | extra, g["vk"])
    return None


def do_config(c):
    """{"gravar", "cancelar", "erro"}: texto do config que não vale cai no padrão (e o erro vai pro aviso do olho)."""
    erro = ""
    try:
        g = ler(c.get("atalho") or PADRAO)
    except ValueError as e:
        erro = "atalho do config.json não vale (%s): voltei pro Ctrl+Page Down" % e
        g = ler(PADRAO)
    cn = None
    if c.get("atalho_cancelar"):
        try:
            cn = ler(c["atalho_cancelar"])
        except ValueError as e:
            erro = erro or "atalho_cancelar do config.json não vale (%s)" % e
    if cn is None or (cn["mods"], cn["vk"]) == (g["mods"], g["vk"]):
        cn = cancelar_de(g)
    return {"gravar": g, "cancelar": cn, "erro": erro}


def legenda(c):
    """texto da janelinha: «CTRL+PAGE DOWN GRAVA · +SHIFT CANCELA» (igual ao do Luan quando é o padrão)."""
    a = do_config(c); g, cn = a["gravar"], a["cancelar"]
    if not cn:
        return "%s GRAVA · BOTAO DIREITO NO OLHO CANCELA" % g["nome"]
    extra = cn["mods"] & ~g["mods"]
    if cn["vk"] == g["vk"] and extra in (MOD_SHIFT, MOD_ALT) and (cn["mods"] & g["mods"]) == g["mods"]:
        return "%s GRAVA · +%s CANCELA" % (g["nome"], "SHIFT" if extra == MOD_SHIFT else "ALT")
    return "%s GRAVA · %s CANCELA" % (g["nome"], cn["nome"])


def teclas_soltar():
    """as teclas do atalho de agora (pra esperar soltar antes do Ctrl+V do «/kakashi»)."""
    vks = [0x11, 0x10, 0x12, 0x5B, 0x5C]
    for a in ((ATIVO or {}).get("gravar"), (ATIVO or {}).get("cancelar")):
        if a:
            vks.append(a["vk"])
    return vks or [0x11, 0x10, 0x12, 0x22]


def _postar(m):
    if THREAD_ID:
        user32.PostThreadMessageW(THREAD_ID, m, 0, 0)


def recarregar():
    _postar(WM_RECARREGAR)


def soltar():
    _postar(WM_SOLTAR)


def livre(a):
    """o Windows deixa registrar? (testa e solta na hora; o atalho de agora tem que estar solto antes)"""
    ok = bool(user32.RegisterHotKey(None, 0x7FF0, a["mods"], a["vk"]))
    if ok:
        user32.UnregisterHotKey(None, 0x7FF0)
    return ok


def _baixo(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def capturar(limite=15.0):
    """espera a pessoa apertar o atalho novo (Esc cancela). Volta {"ok", "texto", "msg"}; msg = texto curto pra janelinha."""
    fim = time.time() + limite
    while time.time() < fim and any(_baixo(v) for v in (0x01, 0x02)):      # solta o clique do botão primeiro
        time.sleep(0.02)
    candidatas = sorted(set(TECLAS.values()))
    while time.time() < fim:
        if _baixo(0x1B):
            return {"ok": False, "msg": "TROCA CANCELADA"}
        for vk in candidatas:
            if not _baixo(vk):
                continue
            mods = ((MOD_CONTROL if _baixo(0x11) else 0) | (MOD_SHIFT if _baixo(0x10) else 0) |
                    (MOD_ALT if _baixo(0x12) else 0) | (MOD_WIN if (_baixo(0x5B) or _baixo(0x5C)) else 0))
            a = montar(mods, vk)
            fim_solta = time.time() + 3
            while time.time() < fim_solta and any(_baixo(v) for v in (vk, 0x11, 0x10, 0x12, 0x5B, 0x5C)):
                time.sleep(0.02)
            erro = validar(a)
            if erro:
                return {"ok": False, "msg": "NAO VALE · USE CTRL ALT OU WIN JUNTO"}     # a fonte pixel não tem vírgula
            if not livre(a):
                return {"ok": False, "msg": "%s JA E DE OUTRO PROGRAMA" % a["nome"]}
            return {"ok": True, "texto": a["texto"], "msg": "NOVO ATALHO: " + a["nome"]}
        time.sleep(0.015)
    return {"ok": False, "msg": "NAO APERTOU NADA"}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 3 and sys.argv[1] == "--conferir":
        try:
            a = ler(sys.argv[2])
        except ValueError as e:
            print("NÃO VALE: %s" % e); sys.exit(1)
        if not livre(a):
            print("OCUPADO: %s já é de outro programa neste PC; escolha outro" % a["nome"]); sys.exit(2)
        c = cancelar_de(a)
        print("OK: %s (texto pro config: %s) · cancelar = %s" % (a["nome"], a["texto"], c["nome"] if c else "botão direito no olho"))
        sys.exit(0)
    print(__doc__)
