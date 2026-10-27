# -*- coding: utf-8 -*-
"""TANDERA V2 — "os nossos olhos e ouvidos" (fase 1, 20/10/2026). Um comando que analisa vídeo e áudio. O motor é a RÉGUA
(regua.py: calibrar, cortes, separação, fala, entonação, batida, pacote por corte); as medidas novas estão em tandera_medir.py e
os olhos (Qwen local / Gemini grátis, imagens, prompts) em tandera_olhos.py. Receitas: skill /analise-de-video
(references\\plexus.md, cinematico.md). NÃO usa nada do Tandera V1 (apps\\TANDERA).

  python tandera.py <video> --estilo plexus|cinematico|camera-parada|vlog --estagio A|B|C
                    [--modo rapido|completo] [--roteiro <arquivo> [--shots-roteiro 64-69]] [--elenco <pasta>] [--prompt <arquivo>]
                    [--de S --ate S] [--saida PASTA] [--refazer medida,medida|tudo] [--gemini] [--gemini-shots 48,52] [--sem-placa]

- rápido: cortes + 1 quadro por shot + descrição leve (Qwen), pra decidir como analisar.
- completo: o que a receita do estilo e do estágio pedir (RECEITA abaixo).
- Medida guardada por arquivo (cache\\<nome>_<assinatura>\\: tamanho + data + 1 MB do começo e do fim): rodar de novo reaproveita;
  reanalisar a ficha (mesmos quadros e mesmo prompt) não chama o modelo de novo. --refazer força.
- --de/--ate: só um trecho do vídeo (os cortes e os números de shot são do vídeo inteiro; o tempo escrito é o do vídeo inteiro).
- Saída: <pasta>\\DOSSIE.md (legível) · dados.json (tudo) · folhas\\ (quadros pro olho) · ficha_elenco.jpg.
- T4: o andamento vai pra estado\\<id>.json (tandera_estado.py) e aparece na tela do app (apps\\TANDERA), venha da tela ou do terminal.
  --projeto EP03 dá o nome do projeto na tela (sem ele, sai do caminho do arquivo).
- T5: o motor pode ser morto a qualquer hora ("pausar e liberar a placa" na tela) e o RETOMAR roda o mesmo comando: tudo que o cache
  confere por existência é gravado ao lado e trocado no fim, e as etapas longas guardam em pedaços (Pedacos; lista em
  tandera_estado.PEDACOS). As de uma vez só recomeçam do zero ao retomar."""
import argparse, hashlib, json, os, re, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
PY_VENV = os.path.join(AQUI, ".venv", "Scripts", "python.exe")
if not os.environ.get("TANDERA_NO_VENV") and os.path.exists(PY_VENV) and \
        os.path.normcase(os.path.realpath(sys.prefix)) != os.path.normcase(os.path.realpath(os.path.join(AQUI, ".venv"))):
    _env = dict(os.environ); _env["PYTHONIOENCODING"] = "utf-8"; _env["TANDERA_NO_VENV"] = "1"
    sys.exit(subprocess.run([PY_VENV, os.path.abspath(__file__), *sys.argv[1:]], env=_env).returncode)

sys.path.insert(0, AQUI)


def _config_da_fly():
    """pacote da Fly (27/10): o config.json da pasta (o instalar.py escreve a partir do PC check) vira variável de ambiente ANTES dos
    imports (regua, tandera_medir e tandera_olhos leem algumas na hora do import). "minhas" vence "variaveis"; variável que já veio do
    terminal vence as duas. {pasta} = esta pasta."""
    try:
        with open(os.path.join(AQUI, "config.json"), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return {}
    for k, v in dict(c.get("variaveis") or {}, **(c.get("minhas") or {})).items():
        if v not in (None, "") and k not in os.environ:
            os.environ[k] = str(v).replace("{pasta}", AQUI)
    return c


CONFIG_FLY = _config_da_fly()
import numpy as np  # noqa: E402
import regua as R  # noqa: E402
import tandera_medir as TM  # noqa: E402
import tandera_olhos as TO  # noqa: E402
import tandera_estado as TE  # noqa: E402

CACHE = os.path.join(AQUI, "cache")
TRAVA = os.path.join(AQUI, "GPU_EM_USO.txt")   # NOTEBOOK: a trava fica na própria pasta
log = R.log

# ---------------------------------------------------------------- receitas (references\plexus.md e cinematico.md)
RECEITA = {
    ("plexus", "A"): ["cortes", "cortes2", "camera", "texto", "ficha", "tracado"],                                   # etapas 0 e 2 + traçado; sem som
    ("plexus", "B"): ["cortes", "cortes2", "separacao", "fala", "batida", "camera", "texto", "ficha", "roteiro_previsto"],  # 0, 1 (prevista), 2
    ("plexus", "C"): ["cortes", "cortes2", "separacao", "fala", "batida", "grade", "musica", "camera", "texto", "efeitos",
                      "ficha", "tiras", "visao"],                                                                        # 0 a 4 (4 = eu, com o dossiê)
    "cinematico": ["cortes", "cortes2", "separacao", "batida", "grade", "musica", "camera", "corpo", "cor", "descricao"],
    "camera-parada": ["cortes", "separacao", "fala", "entonacao", "rosto", "descricao_leve"],
    "vlog": ["cortes", "cortes2", "separacao", "fala", "entonacao", "batida", "musica", "camera", "rosto", "texto", "efeitos", "descricao"],
}
RAPIDO = ["cortes", "descricao_leve"]
LOTE_OCR = 16           # T5: quadros por chamada ao OCR (cada lote guardado ao voltar)
SOM = {"separacao", "fala", "entonacao", "batida", "grade", "musica", "efeitos", "tiras"}
PLACA = {"cortes2", "separacao", "fala", "batida", "musica", "camera", "corpo", "rosto", "efeitos"}   # torch na placa
OLHOS = {"ficha", "descricao", "descricao_leve", "tiras", "tracado", "roteiro_previsto"}       # Qwen no Ollama (placa também)
NOMES = {"cortes": "cortes (AutoShot)", "cortes2": "2ª opinião de corte (TransNetV2)", "cortes3": "3ª opinião de corte (diferença de pixel)",
         "rosto": "rosto / boca × fala (OpenFace 3.0, WSL)", "separacao": "separação (Roformer → BandIt Plus)",
         "fala": "fala no ms (Whisper 8178 + MMS + onda)", "entonacao": "entonação (Praat)", "batida": "batida (Beat This + ataque)",
         "grade": "grade fechada na onda", "musica": "medidor de música", "camera": "câmera (CoTracker3: a curva)", "corpo": "corpo / fase da rep (Sapiens2-1B)",
         "texto": "texto na tela (PP-OCRv6)", "efeitos": "qual efeito (encaixe na onda)", "cor": "cor por take", "ficha": "ficha do shot (olho local)",
         "descricao": "descrição do shot (olho local)", "descricao_leve": "descrição leve (olho local, 1 quadro)", "tiras": "tira de momento (13 quadros, olho local)",
         "tracado": "traçado ficha × roteiro × prompt (olho local)", "roteiro_previsto": "partes previstas pelo roteiro (olho local)",
         "visao": "visão geral (medida; Gemini só com --gemini)"}
TEMPOS = []


def para_json(o):
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, np.ndarray): return o.tolist()
    if hasattr(o, "__dict__"): return o.__dict__
    return str(o)


def salvar(arq, v):
    """T5: grava ao lado e troca no fim — o motor pode ser morto a qualquer hora (pausar e liberar a placa, cancelar) e um JSON pela
    metade no cache quebraria a rodada seguinte"""
    tmp = arq + f".{os.getpid()}.parcial"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(v, f, ensure_ascii=False, indent=1, default=para_json)
    os.replace(tmp, arq)


# ---------------------------------------------------------------- medida guardada por arquivo
def assinatura(p):
    st = os.stat(p); h = hashlib.sha1(f"{st.st_size}|{int(st.st_mtime)}".encode())
    with open(p, "rb") as f:
        h.update(f.read(1 << 20)); f.seek(max(0, st.st_size - (1 << 20))); h.update(f.read(1 << 20))
    return h.hexdigest()[:12]


class Cache:
    def __init__(self, pasta, refazer):
        self.pasta = pasta; self.refazer = set(refazer); os.makedirs(pasta, exist_ok=True)
        # T5: o RETOMAR roda o MESMO comando, com o mesmo --refazer. O que esta rodada já refez antes da pausa (gravado depois do
        # começo dela, TANDERA_DESDE) vale — senão retomar refaria tudo de novo.
        self.desde = float(os.environ.get("TANDERA_DESDE") or time.time())

    def arq(self, nome, chave=""):
        return os.path.join(self.pasta, nome + (("_" + hashlib.sha1(chave.encode()).hexdigest()[:10]) if chave else "") + ".json")

    def tem(self, nome, chave=""):
        a = self.arq(nome, chave)
        if not os.path.exists(a):
            return False
        if {"tudo", nome, nome.split("__")[0]} & self.refazer:     # camera__pedaco é refeito pelo --refazer camera
            return os.path.getmtime(a) >= self.desde
        return True

    def ler(self, nome, chave=""):
        with open(self.arq(nome, chave), encoding="utf-8") as f:
            return json.load(f)["valor"]

    def guardar(self, nome, v, chave="", s=0.0):
        salvar(self.arq(nome, chave), {"valor": v, "_s": s, "_quando": time.strftime("%Y-%m-%d %H:%M")})

    def get(self, nome, func, chave="", registrar=True):
        a = self.arq(nome, chave)
        d = None
        if self.tem(nome, chave):
            try:
                with open(a, encoding="utf-8") as f:
                    d = json.load(f)
            except ValueError:          # quebrado (escrito pela metade antes do T5): mede de novo
                d = None
        if d is not None:
            if registrar: TEMPOS.append({"etapa": nome, "s": 0.0, "como": "reaproveitado", "s_quando_mediu": round(d.get("_s", 0), 1)})
            return d["valor"]
        t = time.time(); v = func(); s = time.time() - t
        if isinstance(v, dict) and v.get("erro"):        # erro (cota do Gemini, servidor) não fica guardado: a próxima rodada tenta de novo
            if registrar: TEMPOS.append({"etapa": nome, "s": round(s, 1), "como": f"falhou: {v.get('erro')}"})
            return v
        self.guardar(nome, v, chave, s)
        if registrar: TEMPOS.append({"etapa": nome, "s": round(s, 1), "como": "medido"})
        return v


class Pedacos:
    """T5 (pausar e liberar a placa): uma etapa longa guardada POR PEDAÇO (shot, take, lote de quadros) assim que cada um fica pronto.
    Parar no meio perde só o pedaço da vez; rodar de novo pula os guardados. Só onde cada pedaço é medido sozinho (o resultado de um
    não depende dos outros) — aí o resultado é o mesmo de uma rodada direta. Mostra o andamento na tela ("6/16 takes (5 do cache)")."""
    def __init__(self, C, etapa, chave, total, unidade, andamento=None):
        self.C, self.nome, self.chave, self.total, self.unidade, self.andamento = C, etapa + "__pedaco", chave, total, unidade, andamento
        self.feitos = self.do_cache = 0

    def tem(self, x):
        return self.C.tem(self.nome, self.chave(x))

    def ler(self, x):
        self.do_cache += 1
        return self._andou(self.C.ler(self.nome, self.chave(x)))

    def guardar(self, x, v):
        self.C.guardar(self.nome, v, self.chave(x))
        return self._andou(v)

    def _andou(self, v):
        self.feitos += 1
        if self.andamento:
            self.andamento(min(self.feitos, self.total), self.total, self.unidade + (f" ({self.do_cache} do cache)" if self.do_cache else ""))
        return v


# ---------------------------------------------------------------- placa: Premiere fechado, trava, um modelo por vez
class Placa:
    def __init__(self, usar, video):
        self.usar, self.video, self.minha = usar, video, False

    @staticmethod
    def premiere_aberto():
        o = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, encoding="cp850", errors="replace").stdout
        return any("premiere" in l.split(",")[0].lower() for l in o.splitlines() if l)

    def antes(self, etapa):
        if not self.usar:
            return False
        if self.premiere_aberto():
            log(f"PREMIERE ABERTO — não uso a placa ({etapa}). Feche o Premiere e rode de novo (o que já foi medido fica guardado).")
            raise SystemExit(3)
        if not self.minha:
            if os.path.exists(TRAVA):
                log("A PLACA ESTÁ EM USO por outro trabalho:", open(TRAVA, encoding="utf-8", errors="replace").read().strip()[:200]); raise SystemExit(4)
            open(TRAVA, "w", encoding="utf-8").write(f"Tandera V2 usando a placa (pid {os.getpid()}) desde {time.strftime('%d/%m %H:%M')} — {self.video}\n"
                                                      "Apaga sozinho no fim. Se ficar aqui depois que o Tandera parou, pode apagar.\n")
            self.minha = True
        TO.descarregar(TO.QWEN_DO_OPENWHISPR)          # o OpenWhispr usa esse; sai da placa antes
        if etapa not in OLHOS:
            TO.descarregar(TO.QWEN)                      # um modelo por vez
        return True

    def fim(self):
        if self.minha and os.path.exists(TRAVA) and f"pid {os.getpid()}" in open(TRAVA, encoding="utf-8", errors="replace").read():
            os.remove(TRAVA)


# ---------------------------------------------------------------- roteiro
RE_SHOT = re.compile(r"(?i)\bSHOT\s+(\d+(?:\.\d+)?)")


def norm(t):
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", t).split()


def blocos_roteiro(texto):
    """o roteiro em blocos de SHOT (cada um com a cena em que está e as falas/efeitos até o próximo SHOT)"""
    bl, cena, cur = [], "", None
    for l in texto.splitlines():
        if re.match(r"^\s*#+\s*CENA", l, re.I):
            cena = l.strip().lstrip("#").strip(); cur = None; continue
        m = RE_SHOT.search(l)
        if m:
            cur = {"shot": m.group(1), "cena": cena, "linhas": [l.strip()]}; bl.append(cur)
        elif cur is not None and l.strip():
            cur["linhas"].append(l.strip())
    return bl


def trecho_por_shots(texto, sel):
    """--shots-roteiro 64-69 → a cena + os SHOTs 64 a 69 (com 64.1 etc.)"""
    a, b = [float(x) for x in (sel.split("-") + sel.split("-"))[:2]] if "-" in sel else (float(sel), float(sel))
    bl = [x for x in blocos_roteiro(texto) if a <= float(x["shot"]) < int(b) + 1]
    if not bl:
        return None
    out, cena = [], None
    for x in bl:
        if x["cena"] != cena:
            cena = x["cena"]; out.append(f"## {cena}")
        out += x["linhas"]
    return "\n".join(out)


def trecho_pela_fala(blocos, palavras):
    """liga o shot ao roteiro pela FALA medida: o bloco cujas falas mais casam com as palavras ditas no shot"""
    import difflib
    alvo = " ".join(norm(" ".join(w["p"] for w in palavras)))
    if len(alvo) < 8:
        return None, 0.0
    melhor, nota = None, 0.0
    for b in blocos:
        falas = " ".join(norm(" ".join(l.split(":", 1)[1] for l in b["linhas"][1:] if ":" in l)))
        if not falas:
            continue
        sm = difflib.SequenceMatcher(None, alvo, falas, autojunk=False)
        n = sum(m.size for m in sm.get_matching_blocks()) / max(1, min(len(alvo), len(falas)))
        if n > nota:
            melhor, nota = b, n
    if melhor and nota >= 0.55:
        return f"## {melhor['cena']}\n" + "\n".join(melhor["linhas"]), round(nota, 2)
    return None, round(nota, 2)


# ---------------------------------------------------------------- quadros por plano
def quadros_do_plano(a, b):
    """2–3 quadros por plano, inclusive nos curtos (T2: os espaçados por igual pularam um plano de 1 s)"""
    n = b - a
    if n <= 1: return [a]
    if n <= 4: return [a, b - 1]
    if n <= 12: return [a + 1, b - 2]
    return [a + 2, (a + b) // 2, b - 3]


# ---------------------------------------------------------------- estágio A: traçado ficha × roteiro × prompt
def palavras_chave(t):
    pare = set("para pela pelo com sem uma umas uns que como mais muito entre sobre depois antes onde quando tipo seu sua dele dela deixando outro outra cada esta este isso".split())
    return [w for w in norm(t) if len(w) > 3 and w not in pare]


def tracar(u, fps, src, pasta_q, out, olhar, prompt_txt, andamento=None):
    """1) cada PLANO medido → qual SHOT do roteiro ele mostra, o que tem e o que falta (Qwen, poucos quadros, pergunta fechada);
    2) o código monta a ORDEM, os shots que não saíram, e diz ONDE MEXER pelas medidas e pelo texto do prompt."""
    mm = TO.mmss
    bl = blocos_roteiro(u.get("roteiro") or "")
    shots_r = [(b["shot"], re.sub(r"^[-\s\[\]]*\**\s*SHOT\s+[\d.]+\s*:?\**\s*:?", "", b["linhas"][0], flags=re.I).strip(" *")) for b in bl]
    if not shots_r:
        return {"erro": "sem trecho do roteiro com SHOTs: o traçado precisa do --roteiro (e do --shots-roteiro se o arquivo for o episódio inteiro)"}
    planos = []
    for i, (x, y) in enumerate(u["planos"], 1):
        if andamento: andamento(i - 1, len(u["planos"]) + 1, "planos")
        arqs = []
        for k, f in enumerate(quadros_do_plano(x, y), 1):
            cru = os.path.join(pasta_q, f"q{f}.jpg")
            arqs.append(TO.quadro_com_tempo(cru, os.path.join(out, "quadros", f"u{u['n']:03d}_plano{i:02d}_{k}_q{f}.jpg"), f"{k} · {mm(f / fps)} · q{f}", 512))
        cab = f"{u['rotulo']} · plano {i} de {len(u['planos'])} · de {mm(x / fps)} a {mm(y / fps)} ({(y - x) / fps:.2f} s)"
        ims = ([u["ficha_elenco"]] if u.get("ficha_elenco") else []) + arqs
        r = olhar("tracado_plano", TO.prompt_plano_ver(cab, len(arqs), bool(u.get("ficha_elenco"))), ims, 200, temperatura=0)
        planos.append({"plano": i, "de_q": x, "ate_q": y, "vejo": " ".join(r.get("texto", "").split()), "shot": None, "shots": [], "falta": "", "s": r.get("s")})
    if andamento: andamento(len(u["planos"]), len(u["planos"]) + 1, "planos (casando com o roteiro)")
    r = olhar("tracado_plano", TO.prompt_plano_casar([(p["plano"], p["vejo"]) for p in planos], shots_r), [], 400, temperatura=0)
    validos = {s for s, _ in shots_r}
    for p in planos:
        m = re.search(rf"(?im)PLANO\s*{p['plano']}\s*=\s*((?:SHOT[^|\n]*)|NENHUM)\s*\|?\s*(?:FALTA\s*:\s*(.*))?$", r.get("texto", ""))
        if m:
            p["shots"] = list(dict.fromkeys(s.rstrip(".") for s in re.findall(r"\d+(?:\.\d+)?", m.group(1) or "") if s.rstrip(".") in validos))
            p["shot"] = "+".join(p["shots"]) or None
            p["falta"] = (m.group(2) or "").strip()
    casar = r.get("texto", "")
    ordem_r = [s for s, _ in shots_r]
    vistos = [s for p in planos for s in p["shots"]]
    seq = [s for i, s in enumerate(vistos) if i == 0 or s != vistos[i - 1]]
    pos = {s: k for k, s in enumerate(ordem_r)}
    fora = [s for i, s in enumerate(seq) if s in pos and any(pos.get(s2, -1) > pos[s] for s2 in seq[:i])]
    nao_saiu = [s for s in ordem_r if s not in vistos]
    curtos = [p for p in planos if (p["ate_q"] - p["de_q"]) / fps < 1.0]
    pr = {w[:5] for w in palavras_chave(prompt_txt or "")}     # pelo começo da palavra: grita × gritando
    def no_prompt(texto, sem_prompt):
        if not prompt_txt:
            return sem_prompt
        kw = list(dict.fromkeys(palavras_chave(texto)))
        falta_p = [w for w in kw if w[:5] not in pr]
        if not falta_p:
            return "o prompt pede tudo isso e o gerador não entregou → PROMPT: reforçar esse plano (ou gerar de novo)"
        return f"o prompt não tem: {', '.join(falta_p[:6])} → PROMPT: acrescentar"
    mexer = []
    for s in nao_saiu:
        pedido = dict(shots_r)[s]
        mexer.append(f"SHOT {s} não saiu ({pedido[:80]}) — " + no_prompt(pedido, "sem prompt: não dá pra dizer se faltou no prompt ou se o gerador errou"))
    for p in planos:
        if p["shot"] and p["falta"] and not re.match(r"(?i)^\s*nada", p["falta"]):
            mexer.append(f"SHOT {p['shot']} (plano {p['plano']}, {mm(p['de_q'] / fps)}): falta {p['falta']} — " + no_prompt(p["falta"], "sem prompt pra comparar") + "  ⚠ conferir no olho")
    if fora:
        mexer.append(f"ORDEM: o vídeo entrega {', '.join(seq)}; o roteiro pede {', '.join(ordem_r)} → PROMPT: numerar os planos na ordem do roteiro "
                     "(ou, se a ordem nova ficou melhor, ROTEIRO: trocar a ordem — decisão de quem dirige)")
    if len(ordem_r) >= 4 and (u["ate_q"] - u["de_q"]) / fps < 2.5 * len(ordem_r):
        mexer.append(f"ROTEIRO/divisão: {len(ordem_r)} shots do roteiro numa geração de {(u['ate_q'] - u['de_q']) / fps:.1f} s; {len(curtos)} plano(s) com menos de 1 s → "
                     "OS DOIS: dividir em mais gerações ou juntar shots no roteiro")
    return {"planos": planos, "casamento": casar, "ordem_roteiro": ordem_r, "ordem_video": seq, "fora_de_ordem": fora, "nao_saiu": nao_saiu, "onde_mexer": mexer,
            "tem_prompt": bool(prompt_txt)}


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description="Tandera V2 — análise de vídeo e áudio (fase 1)")
    ap.add_argument("video")
    ap.add_argument("--estilo", choices=["plexus", "cinematico", "camera-parada", "vlog"])
    ap.add_argument("--estagio", choices=["A", "B", "C"], default="C")
    ap.add_argument("--modo", choices=["rapido", "completo"], default="completo")
    ap.add_argument("--roteiro"); ap.add_argument("--shots-roteiro"); ap.add_argument("--elenco"); ap.add_argument("--prompt")
    ap.add_argument("--de", type=float); ap.add_argument("--ate", type=float)
    ap.add_argument("--saida"); ap.add_argument("--refazer", default="")
    ap.add_argument("--nome-shot", help="rótulo do shot no estágio A (ex.: 'G1 · roteiro 64–69')")
    ap.add_argument("--idioma", default="auto", help="idioma da fala pro Whisper (auto, pt, en...)")
    ap.add_argument("--gemini", action="store_true", help="visão geral com o Gemini Flash GRÁTIS (vídeo 480p com som)")
    ap.add_argument("--gemini-shots", default="", help="shots complexos pro Gemini Flash grátis, num pedido só (ex.: 48,52)")
    ap.add_argument("--sem-placa", action="store_true")
    ap.add_argument("--projeto", help="nome do projeto na tela do app (ex.: EP03); sem ele, sai do caminho do arquivo")
    a = ap.parse_args()
    if CONFIG_FLY.get("sem_placa") and not a.sem_placa:   # pacote da Fly: o PC check disse que este PC roda sem a placa
        a.sem_placa = True; log("config.json: este PC roda sem a placa (--sem-placa automático)")
    T0 = time.time()
    src = os.path.abspath(a.video); nome = os.path.splitext(os.path.basename(src))[0]
    E = TE.Estado(src, "python tandera.py " + subprocess.list2cmdline(sys.argv[1:]))     # T4: o andamento na tela do app
    placa_ok = not a.sem_placa
    if placa_ok and os.environ.get("REGUA_PLACA_FRACAO"):   # NOTEBOOK (4 GB): o torch DESTE processo para com erro em vez de transbordar
        try:                                                # pra RAM (no Windows, placa cheia vaza pra RAM e trava a máquina)
            import torch
            if torch.cuda.is_available():
                torch.cuda.set_per_process_memory_fraction(float(os.environ["REGUA_PLACA_FRACAO"]))
                log(f"NOTEBOOK: placa limitada a {float(os.environ['REGUA_PLACA_FRACAO']):.0%} neste processo")
        except Exception as ex:
            log(f"NOTEBOOK: não consegui limitar a placa: {ex}")
    refazer = [x.strip() for x in a.refazer.split(",") if x.strip()]

    # ---- 0. calibrar (o arquivo inteiro), cache e trecho
    C = Cache(os.path.join(CACHE, f"{re.sub(r'[^A-Za-z0-9_-]', '_', nome)[:40]}_{assinatura(src)}"), refazer)
    cal = C.get("calibracao", lambda: R.calibrar(src))
    dur_total = float(R.ffprobe(src, "-show_entries", "format=duration", "-of", "csv=p=0") or 0)
    fps = cal["fps"]; larg, alt = TM.dimensoes(cal)
    estilo = a.estilo
    if not estilo:
        log("sem --estilo: uso 'vlog' (o reconhecedor do regua.py precisa da fala; diga o estilo pra receita certa)"); estilo = "vlog"
    receita = RAPIDO if a.modo == "rapido" else list(RECEITA[(estilo, a.estagio)] if estilo == "plexus" else RECEITA[estilo])
    if not cal["audio"]:
        receita = [e for e in receita if e not in SOM]
    if not a.roteiro:
        receita = [e for e in receita if e != "roteiro_previsto"]
    PULAR = {x.strip() for x in os.environ.get("TANDERA_PULAR", "").split(",") if x.strip()}   # NOTEBOOK: etapa que não cabe aqui
    if PULAR:
        log("NOTEBOOK: pulando " + ", ".join(e for e in receita if e in PULAR)); receita = [e for e in receita if e not in PULAR]
    tag = f"{estilo}_{a.estagio if estilo == 'plexus' else ''}_{a.modo}".replace("__", "_")
    out = os.path.abspath(a.saida or os.path.join(AQUI, "analises", "tandera", f"{nome}_{tag}"))
    for d in ("folhas", "quadros"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    placa = Placa(placa_ok, src)
    E.plano(receita, estilo, a.estagio, a.modo, ((a.ate if a.ate is not None else dur_total) - (a.de or 0)) / 60, dur_total / 60, a.projeto,
            extra=("gemini_shots",) if a.gemini_shots else ())
    D = {"video": src, "quando": time.strftime("%Y-%m-%d %H:%M"), "estilo": estilo, "estagio": a.estagio, "modo": a.modo, "receita": receita,
         "calibracao": cal, "duracao_video_s": dur_total, "cache": C.pasta}
    try:
        # ---- cortes (vídeo inteiro: o número do shot é o do vídeo inteiro)
        E.etapa("cortes")
        if not C.tem("cortes"):
            placa.antes("cortes")       # T4: o AutoShot usa a placa — antes dele, Premiere fechado e trava escrita (como as outras etapas)
        log("cortes (AutoShot)")
        Cc = C.get("cortes", lambda: R.cortes(src))
        N = Cc["quadros"]
        qa = int(round(a.de * fps)) if a.de is not None else 0
        qb = min(N, int(round(a.ate * fps))) if a.ate is not None else N
        base_t = qa / fps
        cortes_todos = Cc["cortes"]
        bordas = [0] + cortes_todos + [N]
        shots_todos = [(bordas[i], bordas[i + 1]) for i in range(len(bordas) - 1) if bordas[i + 1] > bordas[i]]
        shots = [(max(x, qa), min(y, qb), i + 1) for i, (x, y) in enumerate(shots_todos) if y > qa and x < qb]
        cortes = [c for c in cortes_todos if qa < c < qb]
        D["trecho"] = {"de_q": qa, "ate_q": qb, "de_s": round(base_t, 3), "ate_s": round(qb / fps, 3)}
        D["cortes"] = {"autoshot": cortes, "n_shots": len(shots)}
        if "cortes2" in receita and placa.antes("cortes2"):
            E.etapa("cortes2"); log("2ª opinião de corte (TransNetV2)"); E.sub(0, 2, "partes")
            c2 = C.get("cortes2", lambda: TM.cortes_transnet(src, placa_ok))
            D["cortes"]["transnet"] = [c for c in c2["cortes"] if qa < c < qb]
            D["cortes"]["discordam"] = TM.comparar_cortes(cortes, D["cortes"]["transnet"])
            log("3ª opinião de corte (diferença de pixel: jump cut)"); E.sub(1, 2, "partes")
            c3 = C.get("cortes3", lambda: TM.cortes_pixel(src, Cc["cortes"] + c2["cortes"]))
            D["cortes"]["possiveis_pixel"] = [x for x in c3 if qa < x["q"] < qb]

        # ---- som (só o trecho): separação → fala → entonação → batida → grade → música → efeitos
        stems = None; pal = []; ent = None; bat = None
        trecho_id = f"trecho_{qa}-{qb}" if (qa, qb) != (0, N) else "inteiro"
        if any(e in receita for e in ("separacao", "fala", "batida", "musica", "efeitos")):
            E.etapa("separacao")
            pasta_st = os.path.join(C.pasta, trecho_id, "stems"); os.makedirs(pasta_st, exist_ok=True)
            mix = os.path.join(pasta_st, "mix_48k.wav")
            if not os.path.exists(mix):      # T5: grava ao lado e troca (motor morto no meio não deixa wav pela metade)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-map", "0:a:0", "-af", f"atrim=start={base_t:.6f}:end={qb / fps:.6f},asetpts=PTS-STARTPTS",
                                "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", mix[:-4] + ".parcial.wav"], check=True)
                os.replace(mix[:-4] + ".parcial.wav", mix)
            placa.antes("separacao"); log("separando o som (Roformer → BandIt Plus)"); E.sub(0, 2, "partes")
            stems = C.get("separacao", lambda: R.separar(src, pasta_st, placa_ok, andou=lambda k: E.sub(k, 2, "partes")), chave=trecho_id)
        folga = cal["folga_aac_s"]
        if "fala" in receita and stems:
            E.etapa("fala"); placa.antes("fala"); log("fala (texto do whisper-server 8178 → MMS + onda)")
            def _fala():
                try:
                    segs, lingua, fora = TM.segmentos_8178(stems["voz"], a.idioma)
                except Exception as ex:      # NOTEBOOK: sem whisper-server na 8178 → o faster-whisper do regua.fala transcreve
                    log(f"NOTEBOOK: whisper-server fora ({str(ex)[:80]}) → faster-whisper aqui"); segs, lingua, fora = None, a.idioma, []
                    if a.idioma not in ("", "auto"): os.environ["REGUA_IDIOMA"] = a.idioma   # pacote da Fly: o --idioma vale pro faster-whisper
                ws = R.fala(stems["voz"], placa_ok, segs=segs)
                return {"idioma": lingua, "descartados_do_whisper": fora, "palavras": [{"p": w["p"], "ini": round(w["ini"] + base_t, 3), "fim": round(w["fim"] + base_t, 3)} for w in ws]}
            F = C.get("fala", _fala, chave=trecho_id + a.idioma); pal = F["palavras"]; D["fala"] = F
        if "entonacao" in receita and stems and pal:
            E.etapa("entonacao"); log("entonação")
            ent = C.get("entonacao", lambda: [dict(e, ini=round(e["ini"] + base_t, 3), fim=round(e["fim"] + base_t, 3)) for e in
                                              R.entonacao(stems["voz"], [dict(w, ini=w["ini"] - base_t, fim=w["fim"] - base_t) for w in pal])], chave=trecho_id)
            D["entonacao"] = ent
        if "batida" in receita and stems:
            E.etapa("batida"); placa.antes("batida"); log("batida (Beat This + ataque, no stem de música)")
            b0 = C.get("batida", lambda: R.batida(stems["musica"], placa_ok), chave=trecho_id)
            bat = {"batidas": [round(t + base_t, 4) for t in b0["batidas"]], "tempos_fortes": [round(t + base_t, 4) for t in b0["tempos_fortes"]]}
            D["batida"] = bat
            if "grade" in receita:
                E.etapa("grade"); log("grade fechada na onda")
                g = C.get("grade", lambda: TM.grade_na_onda(stems["musica"], b0["batidas"]), chave=trecho_id)
                g = dict(g, grade=[round(t + base_t, 4) for t in g.get("grade", [])]); D["grade"] = g
            usar = D.get("grade", {}).get("grade") or bat["batidas"]
            D["corte_x_batida"] = TM.corte_x_batida(cortes, fps, usar, folga, meias=bool(D.get("grade", {}).get("grade")))
            D["corte_x_batida"]["fonte"] = "grade fechada na onda" if D.get("grade", {}).get("grade") else "lista crua do Beat This"
        if "musica" in receita and stems:
            E.etapa("musica"); placa.antes("musica"); log("medidor de música")
            sys.path.insert(0, os.path.join(AQUI, "scripts")); from musica import medir
            D["musica"] = C.get("musica", lambda: {k: v for k, v in medir(stems["musica"], dispositivo="cuda" if placa_ok else "cpu").items() if k != "curvas_0_1s"}, chave=trecho_id)
            D["musica"]["_obs"] = f"tempos contados do começo do trecho ({base_t:.3f} s)"
        if "efeitos" in receita and stems:
            E.etapa("efeitos"); placa.antes("efeitos"); log("qual efeito (encaixe na onda contra a biblioteca)")
            ef = C.get("efeitos", lambda: TM.efeitos(stems["efeitos"], os.path.join(C.pasta, trecho_id), folga, placa_ok), chave=trecho_id)
            for e in ef:
                for k in ("inicio_do_arquivo_s", "toca_de_s", "toca_ate_s", "pico_no_video_s"):
                    if e.get(k) is not None: e[k] = round(e[k] + base_t, 4)
            D["efeitos"] = ef
        if pal or bat:
            D["pacotes"] = R.pacotes(cortes, fps, pal, ent, bat, folga)

        # ---- imagem: câmera, corpo
        planos = [(x, y) for x, y, _ in shots]
        por_shot = lambda ab: f"{ab[0]}-{ab[1]}"         # T5: a chave do pedaço é o shot (quadro de começo e de fim)
        if "camera" in receita:
            E.etapa("camera"); placa.antes("camera"); log("câmera (CoTracker3 + geometria)")
            cam = C.get("camera", lambda: TM.camera(src, planos, fps, larg, alt, placa_ok, pedacos=Pedacos(C, "camera", por_shot, len(planos), "shots", E.sub)),
                        chave=str(planos))
            D["camera"] = cam
        if "corpo" in receita:
            E.etapa("corpo")
            if cal.get("deitado_suspeito") and estilo == "cinematico":
                log("ATENÇÃO: take possivelmente DEITADO (largura > altura sem rotação) — conferir antes de ler o corpo")
            placa.antes("corpo"); log("corpo (Sapiens2-1B): fase da rep")
            D["corpo"] = C.get("corpo", lambda: TM.corpo(src, planos, fps, larg, alt, placa_ok, pedacos=Pedacos(C, "corpo", por_shot, len(planos), "takes", E.sub)),
                               chave=str(planos))
        if "rosto" in receita:
            E.etapa("rosto"); placa.antes("rosto"); log("rosto (OpenFace 3.0 no WSL): boca × fala")
            n_lotes = max(1, -(-sum(len(range(0, y - x, 2)) for x, y in planos) // TM.LOTE_ROSTO))
            por_lote = lambda lote: ",".join(str(q) for q, _ in lote)
            D["rosto"] = C.get("rosto", lambda: TM.rosto(src, planos, fps, larg, alt, pal, folga, os.path.join(C.pasta, "rosto"),
                                                         pedacos=Pedacos(C, "rosto", por_lote, n_lotes, "lotes de quadros", E.sub)), chave=str(planos) + str(len(pal)))
        try:
            import torch; torch.cuda.empty_cache()
        except Exception:
            pass

        # ---- quadros por plano (com o tempo escrito) e unidades de ficha
        unidades = []
        if estilo == "plexus" and a.estagio == "A" and a.modo == "completo":
            unidades.append({"n": 1, "rotulo": a.nome_shot or "shot 1", "de_q": qa, "ate_q": qb, "planos": planos})
        else:
            for x, y, n in shots:
                unidades.append({"n": n, "rotulo": f"shot {n}", "de_q": x, "ate_q": y, "planos": [(x, y)]})
        pasta_q = os.path.join(C.pasta, "quadros")
        E.shots(len(unidades))
        E.etapa("quadros")
        for iu, u in enumerate(unidades):
            E.sub(iu, len(unidades), "shots")
            # T3: mais de 12 quadros não cabe em 16k no Qwen (130 s × 44 s). O quadro do MEIO sai primeiro dos planos mais LONGOS
            # (o começo e o fim já mostram o movimento); plano curto fica com os 3 — na G1 a moto passa justo no meio de um plano de 1 s.
            por_plano = [quadros_do_plano(*p) if a.modo == "completo" else [(p[0] + p[1]) // 2] for p in u["planos"]]
            for i in sorted(range(len(por_plano)), key=lambda i: -(u["planos"][i][1] - u["planos"][i][0])):
                if sum(len(x) for x in por_plano) <= 12: break
                if len(por_plano[i]) > 2: por_plano[i] = [por_plano[i][0], por_plano[i][-1]]
            qs = [f for x in por_plano for f in x]
            u["quadros"] = qs
            u["quadros_arq"] = []
            for k, f in enumerate(qs, 1):
                cru = TM.quadro_arq(src, f, fps, os.path.join(pasta_q, f"q{f}.jpg"))
                if not cru: continue
                larg_q = 512     # T3: diminuir a imagem não economiza token no Ollama (~1.100 por imagem); só perde detalhe
                lab =os.path.join(out, "quadros", f"u{u['n']:03d}_{k:02d}_q{f}_{larg_q}.jpg")
                u["quadros_arq"].append(TO.quadro_com_tempo(cru, lab, f"{k} · {TO.mmss(f / fps)} · q{f}", larg_q))
            u["cab"] = f"{u['rotulo']} · de {TO.mmss(u['de_q'] / fps)} a {TO.mmss(u['ate_q'] / fps)} · vídeo de {TO.mmss(dur_total)}"
            u["palavras"] = [w for w in pal if u["de_q"] / fps <= w["ini"] - folga < u["ate_q"] / fps]

        if "texto" in receita:
            E.etapa("texto"); log("texto na tela (PP-OCRv6, processador)")
            todas = sorted({os.path.join(pasta_q, f"q{f}.jpg") for u in unidades for f in u["quadros"]})
            faltam = [i for i in todas if not C.tem("ocr", i + str(os.path.getsize(i)))]
            ja = len(todas) - len(faltam)
            # T5: em lotes de 16 quadros, cada lote guardado assim que volta (o OCR lê cada quadro sozinho: o lote não muda a leitura).
            # Antes era um lote só — parar no meio perdia a etapa inteira.
            for k in range(0, len(faltam), LOTE_OCR):
                E.sub(ja + k, len(todas), "quadros" + (f" ({ja} do cache)" if ja else ""))
                lote = faltam[k:k + LOTE_OCR]
                res = TM.texto_na_tela(lote, os.path.join(C.pasta, "ocr_tmp"))
                for i in lote:
                    C.guardar("ocr", res[i], chave=i + str(os.path.getsize(i)))   # pacote da Fly: o texto_na_tela conferiu que todas voltaram
            TEMPOS.append({"etapa": "texto", "s": 0, "como": f"{len(faltam)} quadros lidos, {len(todas) - len(faltam)} reaproveitados"})
            for u in unidades:
                import difflib
                txt = []
                for f in u["quadros"]:
                    i = os.path.join(pasta_q, f"q{f}.jpg")
                    # pacote da Fly (27/10, defeito (b)): aqui era C.get(..., lambda: {"linhas": []}): quando o cache não "tinha" a
                    # entrada (com --refazer, o Cache de 20/10 não via nem a que acabou de ser gravada), ele "media" com o vazio e
                    # GRAVAVA "linhas: []" por cima da leitura certa (o «POLÍCIA» do G1 sumiu assim). Agora só lê o que está gravado.
                    ch = i + str(os.path.getsize(i))
                    for l in (C.ler("ocr", ch)["linhas"] if os.path.exists(C.arq("ocr", ch)) else []):
                        t = l["texto"].strip()
                        if l["nota"] < 0.8 or len(re.sub(r"\W", "", t)) < 3:
                            continue
                        par = [x for x in txt if difflib.SequenceMatcher(None, " ".join(norm(x["texto"])), " ".join(norm(t))).ratio() > 0.6]
                        if par:      # mesma palavra lida de novo (ex.: o POLÍCIA da viatura em 5 quadros): fica a leitura de nota maior
                            p = par[0]; p["vezes"] = p.get("vezes", 1) + 1
                            if l["nota"] > p["nota"]: p.update(texto=t, nota=l["nota"])
                        else:
                            txt.append({"texto": t, "q": f, "nota": l["nota"], "vezes": 1})
                u["texto_na_tela"] = txt
        if "cor" in receita:
            E.etapa("cor")
            for u in unidades:
                u["cor"] = TM.cor([os.path.join(pasta_q, f"q{f}.jpg") for f in u["quadros"]])

        # ---- elenco e roteiro
        elenco = TO.ler_elenco(a.elenco)
        rot_txt = open(a.roteiro, encoding="utf-8").read() if a.roteiro else None
        blocos = blocos_roteiro(rot_txt) if rot_txt else []
        prompt_txt = open(a.prompt, encoding="utf-8").read().strip() if a.prompt else None
        for u in unidades:
            assets = elenco.get(u["n"], []) + elenco.get("todos", []) if elenco else []
            u["elenco"] = [{"nome": x["nome"], "altura": x["altura"], "arquivo": x["arquivo"]} for x in assets]
            u["ficha_elenco"] = TO.ficha_elenco(assets, os.path.join(out, "folhas", f"ficha_elenco_u{u['n']:03d}.jpg")) if assets else None
            if rot_txt:
                if a.estagio == "A" or estilo != "plexus":
                    u["roteiro"] = (trecho_por_shots(rot_txt, a.shots_roteiro) if a.shots_roteiro else rot_txt.strip()[:6000]); u["roteiro_como"] = "dado no comando"
                else:
                    u["roteiro"], nota = trecho_pela_fala(blocos, u["palavras"]); u["roteiro_como"] = f"ligado pela fala (casamento {nota}) — conferir"
        fichas_unicas = sorted({u["ficha_elenco"] for u in unidades if u.get("ficha_elenco")})
        if len(fichas_unicas) == 1:   # uma só pra todos: guarda com o nome simples
            import shutil; shutil.copy2(fichas_unicas[0], os.path.join(out, "ficha_elenco.jpg"))

        # ---- olhos (Qwen local): torch já saiu da placa
        conta = {}
        def olhar(nome_etapa, texto, imagens, num_predict=700, temperatura=0.15):
            chave = TO.hash_arqs(imagens, texto + TO.QWEN + str(temperatura))
            c = conta.setdefault(nome_etapa, [0, 0]); c[0 if not C.tem("olho_" + nome_etapa, chave) else 1] += 1
            return C.get("olho_" + nome_etapa, lambda: TO.qwen(texto, imagens, num_predict, temperatura=temperatura), chave=chave, registrar=False)
        def do_cache(nome_etapa):        # T5: "5/16 shots (4 do cache)" — ao retomar, os que já tinham resposta voltam na hora
            c = conta.get(nome_etapa, [0, 0])
            return f" ({c[1]} do cache)" if c[1] else ""
        t_olhos = {}
        if "descricao_leve" in receita:
            E.etapa("descricao_leve"); placa.antes("descricao_leve"); log(f"descrição leve ({TO.QWEN}), {len(unidades)} shots"); t = time.time()
            for iu, u in enumerate(unidades):
                E.sub(iu, len(unidades), "shots" + do_cache("leve"))
                ims = ([u["ficha_elenco"]] if u.get("ficha_elenco") else []) + u["quadros_arq"][:1]
                u["descricao_leve"] = olhar("leve", TO.prompt_leve(u["cab"], bool(u.get("ficha_elenco"))), ims, 120)
            t_olhos["descricao_leve"] = time.time() - t
        if "ficha" in receita or "descricao" in receita:
            et = "ficha" if "ficha" in receita else "descricao"
            E.etapa(et); placa.antes(et); log(f"{NOMES[et]}: {len(unidades)} unidade(s)"); t = time.time()
            for iu, u in enumerate(unidades):
                E.sub(iu, len(unidades), "shots" + do_cache(et))
                ims = ([u["ficha_elenco"]] if u.get("ficha_elenco") else []) + u["quadros_arq"]
                falas = None
                if u["palavras"]:
                    falas = " ".join(f"[{TO.mmss(w['ini'] - folga)}] {w['p']}" if i == 0 or w["ini"] - u["palavras"][i - 1]["fim"] > 0.4 else w["p"] for i, w in enumerate(u["palavras"]))
                txt = TO.prompt_ficha(u["cab"], len(u["quadros_arq"]), bool(u.get("ficha_elenco")), u.get("roteiro"), falas, um_shot_montado=len(u["planos"]) == 1)
                r = olhar(et, txt, ims, 1600)
                r["texto_marcado"] = TO.marcar_conferir(r.get("texto", "")); u["ficha"] = r
            t_olhos[et] = time.time() - t
        if "tiras" in receita and D.get("efeitos"):
            E.etapa("tiras"); placa.antes("tiras"); t = time.time()
            musical = re.compile(r"(?i)\d+\s*bpm|\b(major|minor|maior|menor)\b|\([A-G](#|b)?(_[A-G](#|b)?)?\)|\bloop\b|drums?\b|piano|violin|guitar")
            conf = sorted([e for e in D["efeitos"] if e.get("confiavel") and e.get("pico_no_video_s") is not None and qa / fps <= e["pico_no_video_s"] < qb / fps
                           and not musical.search(e["nome"])], key=lambda e: -e["nota"])[:6]   # T3: som musical (bateria 77 bpm, piano em Lá#) não marca acontecimento na imagem
            log(f"tira de momento: {len(conf)} efeitos confiáveis")
            D["tiras"] = []
            for ie, e in enumerate(conf):
                E.sub(ie, len(conf), "efeitos")
                fp = int(round(e["pico_no_video_s"] * fps)); q13 = [f for f in range(fp - 6, fp + 7) if 0 <= f < N]
                arqs = []
                for k, f in enumerate(q13, 1):
                    cru = TM.quadro_arq(src, f, fps, os.path.join(pasta_q, f"q{f}.jpg"))
                    arqs.append(TO.quadro_com_tempo(cru, os.path.join(out, "quadros", f"tira_q{fp}_{k:02d}_512.jpg"), f"{k} · {TO.mmss(f / fps)} · q{f}", 512))
                cab = f"tira · de {TO.mmss(q13[0] / fps)} a {TO.mmss((q13[-1] + 1) / fps)} · vídeo de {TO.mmss(dur_total)}"
                r = olhar("tira", TO.prompt_tira(cab, len(arqs), e["nome"]), arqs, 120)
                m = re.search(r"QUADRO\s*(\d+)", r.get("texto", ""), re.I)
                q_img = q13[int(m.group(1)) - 1] if m and 1 <= int(m.group(1)) <= len(q13) else None
                fl = TO.folha(cab + f" · som: {e['nome'][:50]}", arqs, os.path.join(out, "folhas", f"tira_q{fp}.jpg"), colunas=7, largura=300,
                              rodape=[f"pico do som no quadro {fp} · Qwen: {r.get('texto', '').splitlines()[0] if r.get('texto') else '?'}"])
                D["tiras"].append({"efeito": e["nome"], "pico_do_som_q": fp, "ate_o_pico_ms": e.get("ate_o_pico_ms"), "resposta": r, "quadro_da_imagem": q_img,
                                   "clipe_entra_q": (None if q_img is None or e.get("ate_o_pico_ms") is None else round(q_img - e["ate_o_pico_ms"] / 1000 * fps, 1)),
                                   "folha": fl})
            t_olhos["tiras"] = time.time() - t
        if "tracado" in receita:
            E.etapa("tracado"); placa.antes("tracado"); log("traçado ficha × roteiro × prompt (por plano)"); t = time.time()
            for u in unidades:
                u["tracado"] = tracar(u, fps, src, pasta_q, out, olhar, prompt_txt, andamento=E.sub)
            t_olhos["tracado"] = time.time() - t
        if "roteiro_previsto" in receita and rot_txt:
            E.etapa("roteiro_previsto"); placa.antes("roteiro_previsto")
            D["roteiro_previsto"] = olhar("roteiro_previsto", "Leia este roteiro de um episódio de animação e responda em português: 1. PARTES (nome curto e o que acontece, na ordem); "
                                          "2. onde a TENSÃO sobe; 3. o CLÍMAX previsto. Só o que está escrito.\n\n" + rot_txt[:20000], [], 900)
        TO.descarregar(TO.QWEN)
        for k, v in t_olhos.items():
            c = conta.get({"descricao_leve": "leve", "tiras": "tira", "tracado": "tracado_plano"}.get(k, k), [0, 0])
            TEMPOS.append({"etapa": k, "s": round(v, 1), "como": f"Qwen: {c[0]} chamada(s) agora, {c[1]} reaproveitada(s)"})

        # ---- Gemini grátis, só quando pedido
        if a.gemini_shots:
            alvo = {int(x) for x in a.gemini_shots.split(",") if x.strip()}
            us = [u for u in unidades if u["n"] in alvo]
            if us:
                E.etapa("gemini_shots"); log(f"Gemini Flash grátis: {len(us)} shot(s) num pedido só")
                partes = []
                for u in us:
                    partes.append({"text": f"=== {u['cab']} ==="})
                    for i in ([u["ficha_elenco"]] if u.get("ficha_elenco") else []) + u["quadros_arq"]:
                        partes.append({"inline_data": {"mime_type": "image/jpeg", "data": TO.b64(i)}})
                    partes.append({"text": TO.prompt_ficha(u["cab"], len(u["quadros_arq"]), bool(u.get("ficha_elenco")), u.get("roteiro"), None, len(u["planos"]) == 1)})
                partes.append({"text": "Responda cada shot separado, começando cada um por '=== shot N ==='."})
                ch = TO.hash_arqs([i for u in us for i in u["quadros_arq"]], a.gemini_shots)
                D["gemini_shots"] = C.get("gemini_shots", lambda: TO.gemini(partes), chave=ch)
        if "visao" in receita:
            E.etapa("visao"); jan = 10.0; vis = []
            for t in np.arange(qa / fps, qb / fps, jan):
                c_ = [c for c in cortes if t <= c / fps < t + jan]
                f_ = sum(max(0, min(w["fim"], t + jan) - max(w["ini"], t)) for w in pal)
                e_ = [x["nome"][:40] for x in D.get("efeitos", []) if x.get("confiavel") and t <= (x.get("pico_no_video_s") or -1) < t + jan]
                vis.append({"de": TO.mmss(t, 1), "cortes": len(c_), "fala_pct": round(100 * f_ / jan), "efeitos_confiaveis": e_})
            D["visao_medida"] = vis
            if a.gemini:
                log("visão geral: Gemini Flash grátis com o vídeo (480p, com som)")
                v480 = os.path.join(C.pasta, trecho_id, "video_480p.mp4")
                if not os.path.exists(v480):
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{base_t:.4f}", "-i", src, "-t", f"{(qb - qa) / fps:.4f}", "-vf", "scale=-2:480", "-c:v", "libx264",
                                    "-crf", "28", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", v480[:-4] + ".parcial.mp4"], check=True)
                    os.replace(v480[:-4] + ".parcial.mp4", v480)
                perg = ("Este vídeo é um trecho de uma série brasileira de animação 3D (Plexus), com som. Assista e ouça tudo e responda em português: "
                        "1. PARTES (início e fim m:ss, nome curto, o que acontece); 2. onde a TENSÃO SOBE (m:ss e o que faz subir); 3. CLÍMAX (m:ss e por quê). "
                        f"Os tempos são do trecho (0:00 = {TO.mmss(base_t)} do episódio). Só o que está no vídeo.")
                D["visao_gemini"] = C.get("visao_gemini", lambda: TO.gemini_video(v480, perg), chave=trecho_id)

        # ---- folhas por unidade
        E.etapa("dossie")
        cam_por_q = {c["de_q"]: c for c in D.get("camera", [])}
        corpo_por_q = {c["de_q"]: c for c in D.get("corpo", [])}
        corpo_por_q.update({("rosto", r["de_q"]): r for r in D.get("rosto", [])})
        for u in unidades:
            rod = []
            cs = [cam_por_q[x] for x, _ in u["planos"] if x in cam_por_q]
            if cs: rod.append("câmera: " + " | ".join(f"{TO.mmss(c['de_q'] / fps)} {c['classe']}" for c in cs)[:150])
            if u.get("texto_na_tela"): rod.append("texto na tela: " + " · ".join(x["texto"] for x in u["texto_na_tela"])[:150])
            curva = cs[0]["curva"] if len(cs) == 1 and cs[0].get("curva") else None
            u["folha"] = TO.folha(u["cab"], u["quadros_arq"], os.path.join(out, "folhas", f"shot_{u['n']:03d}.jpg"), colunas=min(6, max(3, len(u["quadros_arq"]))), rodape=rod, curva=curva)
        if a.modo == "rapido":
            for i in range(0, len(unidades), 16):
                TO.folha(f"visão rápida · shots {unidades[i]['n']}–{unidades[min(i + 15, len(unidades) - 1)]['n']} · vídeo de {TO.mmss(dur_total)}",
                         [u["quadros_arq"][0] for u in unidades[i:i + 16] if u["quadros_arq"]], os.path.join(out, "folhas", f"visao_rapida_{i // 16 + 1:02d}.jpg"), colunas=4, largura=360)

        D["unidades"] = [{k: v for k, v in u.items()} for u in unidades]
        D["tempos"] = TEMPOS; D["tempo_total_s"] = round(time.time() - T0, 1)
        salvar(os.path.join(out, "dados.json"), D)
        escrever_dossie(out, D, unidades, cam_por_q, corpo_por_q, fps, folga, a, prompt_txt)
        log(f"pronto em {time.time() - T0:.0f} s:", out)
        E.fim("pronto", f"pronto em {time.time() - T0:.0f} s", saida=out, tempos=TEMPOS)
    except SystemExit:          # 3 = Premiere aberto · 4 = placa em uso: a mensagem já saiu no log
        E.fim("parado", saida=out); raise
    except KeyboardInterrupt:
        E.fim("parado", "interrompido (Ctrl+C)", saida=out); raise
    except BaseException as x:
        E.fim("erro", f"{type(x).__name__}: {x}"[:300], saida=out); raise
    finally:
        placa.fim()


# ---------------------------------------------------------------- DOSSIÊ
def escrever_dossie(out, D, unidades, cam_por_q, corpo_por_q, fps, folga, a, prompt_txt):
    mm = TO.mmss
    rel = lambda p: os.path.relpath(p, out).replace("\\", "/") if p else "—"
    L = [f"# DOSSIÊ — {os.path.basename(D['video'])}", "",
         f"- **estilo:** {D['estilo']} · **estágio:** {D['estagio'] if D['estilo'] == 'plexus' else '—'} · **modo:** {D['modo']}",
         f"- **trecho:** {mm(D['trecho']['de_s'])} a {mm(D['trecho']['ate_s'])} (quadros {D['trecho']['de_q']}–{D['trecho']['ate_q']}) · vídeo de {mm(D['duracao_video_s'])}",
         f"- **calibração:** {D['calibracao']['fps']:.3f} q/s · {D['calibracao']['largura']}×{D['calibracao']['altura']} · folga do AAC {D['calibracao']['folga_aac_s'] * 1000:.2f} ms descontada"
         + (" · ⚠ TAKE POSSIVELMENTE DEITADO" if D['calibracao'].get('deitado_suspeito') and D['estilo'] == 'cinematico' else ""),
         f"- **tempo total:** {D['tempo_total_s']:.0f} s · medidas guardadas em `{D['cache']}`", ""]
    L += ["## O que rodou", "| etapa | como | tempo |", "|---|---|---|"]
    for t in D["tempos"]:
        if t["etapa"] in ("calibracao",) or t["etapa"].startswith("olho_"): continue
        L.append(f"| {NOMES.get(t['etapa'], t['etapa'])} | {t['como']} | {t['s']:.1f} s" + (f" (medido antes em {t['s_quando_mediu']} s)" if t.get("s_quando_mediu") else "") + " |")
    L.append("")
    cc = D["cortes"]
    L += ["## Cortes", f"- {len(cc['autoshot'])} cortes no trecho (AutoShot) · {cc['n_shots']} shots"]
    if "discordam" in cc:
        d = cc["discordam"]
        if d["so_autoshot"] or d["so_transnet"]:
            L.append(f"- ⚠ conferir no olho — só o AutoShot viu: {d['so_autoshot'] or 'nenhum'} · só o TransNetV2 viu: {d['so_transnet'] or 'nenhum'}")
        else:
            L.append("- TransNetV2 concorda com todos (±1 quadro)")
    if cc.get("possiveis_pixel"):
        L.append("- ⚠ conferir no olho — POSSÍVEIS cortes que os dois detectores não marcaram (salto de diferença de pixel; jump cut ou clarão): "
                 + ", ".join(f"q{x['q']} ({mm(x['q'] / fps)}, {x['dif']:.0f} × {x['vizinhos']:.0f})" for x in cc["possiveis_pixel"]))
    if D.get("corte_x_batida", {}).get("lista"):
        r = D["corte_x_batida"]["resumo"]
        L += ["", f"### Corte × batida ({D['corte_x_batida']['fonte']})",
              f"- {r['no_quadro_da_batida']} de {r['cortes']} cortes no quadro da batida · {r['a_1_quadro']} a ±1 quadro (o acaso dá ~{r['acaso_a_1_quadro_pct']}%) · mediana {r['mediana_ms']:+.0f} ms",
              "| corte | batida | quadro da batida | desvio |", "|---|---|---|---|"]
        for o in D["corte_x_batida"]["lista"]:
            L.append(f"| q{o['corte_q']} ({mm(o['corte_q'] / fps)}) | {o['batida_s']:.4f} s{' (meia batida)' if o.get('tipo') == 'meia batida' else ''} | q{o['batida_q']} | {o['desvio_q']:+d} q ({o['desvio_ms']:+.0f} ms) |")
    g = D.get("grade")
    if g:
        L.append(f"- grade: {'FECHADA' if g.get('fechada') else 'não fechou'} · {g.get('bpm', g.get('bpm_cru', '?'))} BPM · {g.get('golpes_usados', '?')} golpes · resíduo mediano {g.get('residuo_mediano_ms', '?')} ms"
                 + (" · o Beat This marcou em meio tempo (corrigido)" if g.get("meio_tempo_corrigido") else "") + (f" · {g['motivo']}" if g.get("motivo") else ""))
    L.append("")
    if D.get("visao_medida"):
        L += ["## Visão geral (medida, por 10 s)", "| de | cortes | fala | efeitos confiáveis |", "|---|---|---|---|"]
        for v in D["visao_medida"]:
            L.append(f"| {v['de']} | {v['cortes']} | {v['fala_pct']}% | {', '.join(v['efeitos_confiaveis']) or '—'} |")
        L.append("")
    if D.get("visao_gemini"):
        vg = D["visao_gemini"]
        L += ["## Visão geral (Gemini Flash grátis)", vg.get("texto") or f"(não veio: {vg.get('erro')} {vg.get('erros_antes')})", ""]
    if D.get("roteiro_previsto"):
        L += ["## Previsto pelo roteiro (Qwen, só lendo o roteiro)", D["roteiro_previsto"].get("texto", ""), ""]
    L += ["## Shots" if not (D["estilo"] == "plexus" and D["estagio"] == "A") else "## Ficha do shot (geração solta)", ""]
    for u in unidades:
        L += [f"### {u['cab']}", f"- folha: `{rel(u.get('folha'))}`" + (f" · ficha do elenco: `{rel(u['ficha_elenco'])}`" if u.get("ficha_elenco") else "")]
        if len(u["planos"]) > 1:
            L.append(f"- planos medidos: " + " · ".join(f"{mm(x / fps)}–{mm(y / fps)} ({(y - x) / fps:.2f} s)" for x, y in u["planos"]))
        if u.get("elenco"):
            L.append("- elenco (assets do shot): " + " · ".join(f"{e['nome']} ({e['altura']})" for e in u["elenco"]))
        for x, y in u["planos"]:
            c = cam_por_q.get(x)
            if c:
                L.append(f"- câmera {mm(x / fps)}–{mm(y / fps)}: **{c['classe']}**" + (f" (x {c['dx']:+.2f} · y {c['dy']:+.2f} · escala {c['log_escala']:+.2f}; pico de velocidade em q{c['pico_de_velocidade_q']})" if 'dx' in c else ""))
            b = corpo_por_q.get(x)
            if b and b.get("articulacao"):
                L.append(f"- corpo: {b['articulacao']} {b['faixa_graus'][0]:.0f}–{b['faixa_graus'][1]:.0f}° · {b['reps_contadas']} rep(s) · entra {b['entrada']['movimento']} ({b['entrada']['ponto']}, {b['entrada']['angulo']:.0f}°)"
                         f" · sai {b['saida']['movimento']} ({b['saida']['ponto']}, {b['saida']['angulo']:.0f}°)" + (" · termina num extremo do movimento" if b["termina_num_extremo"] else ""))
            elif b:
                L.append(f"- corpo: pessoa em {b['com_pessoa']} de {b['quadros_medidos']} quadros (pouco pra medir)")
            ro = corpo_por_q.get(("rosto", x))
            if ro:
                txt = f"- rosto: {ro['rosto_pct']:.0f}% do tempo com rosto"
                if "fala_pct" in ro:
                    txt += f" · fala em {ro['fala_pct']:.0f}%" + (f" · a boca mexe {ro['boca_mexe_na_fala_x_fora']}× mais na fala que fora" if ro.get("boca_mexe_na_fala_x_fora") else "")
                    if ro.get("boca_mexe_sem_fala"): txt += " · ⚠ boca mexendo sem fala medida (conferir no olho)"
                    if ro.get("fala_sem_boca"): txt += " · ⚠ fala sem a boca mexer (outra pessoa? off? conferir no olho)"
                L.append(txt)
        if u.get("cor"):
            L.append(f"- cor: brilho {u['cor']['brilho']} · saturação {u['cor']['saturacao']} · quente−frio {u['cor']['quente_menos_frio']:+.0f}")
        if u.get("texto_na_tela"):
            L.append("- texto na tela (PP-OCRv6): " + " · ".join(f"\"{x['texto']}\" (q{x['q']})" for x in u["texto_na_tela"]))
        if u.get("palavras"):
            L.append("- fala medida: " + " ".join(w["p"] for w in u["palavras"])[:300])
        if u.get("roteiro"):
            L += [f"- trecho do roteiro ({u.get('roteiro_como')}):", "```", u["roteiro"][:1500], "```"]
        if u.get("descricao_leve"):
            L.append(f"- descrição leve (Qwen): {u['descricao_leve'].get('texto', '')}")
        if u.get("ficha"):
            L += [f"- ficha ({u['ficha'].get('modelo', TO.QWEN)}, {u['ficha'].get('s', 0):.0f} s):", "", u["ficha"].get("texto_marcado", ""), ""]
        tr = u.get("tracado")
        if tr and tr.get("erro"):
            L += ["#### Traçado ficha × roteiro × prompt", f"- não rodou: {tr['erro']}", ""]
        elif tr:
            L += ["#### Traçado ficha × roteiro × prompt" + ("" if tr["tem_prompt"] else " · SEM PROMPT (só ficha × roteiro)"),
                  "Passo 1: cada plano MEDIDO (2–3 quadros) foi descrito pelo Qwen SEM o roteiro na frente. Passo 2: o Qwen casou as descrições com os SHOTs "
                  "(só texto). A ordem, o que não saiu e o 'onde mexer' são conta do código.", "",
                  "| plano | de–até | o Qwen vê (sem roteiro) | é o SHOT | falta |", "|---|---|---|---|---|"]
            for p in tr["planos"]:
                L.append(f"| {p['plano']} | {mm(p['de_q'] / fps)}–{mm(p['ate_q'] / fps)} | {p.get('vejo', '')[:220]} | {p['shot'] or 'nenhum'} | {p['falta'][:100]}"
                         + ("  ⚠ conferir no olho" if p["falta"] and not p["falta"].lower().startswith("nada") else "") + " |")
            L += ["", f"- ordem do roteiro: {', '.join(tr['ordem_roteiro'])} · ordem no vídeo: {', '.join(tr['ordem_video']) or '—'}"
                  + (f" · **fora de ordem: {', '.join(tr['fora_de_ordem'])}**" if tr["fora_de_ordem"] else ""),
                  f"- SHOTs do roteiro que não saíram em nenhum plano: {', '.join(tr['nao_saiu']) or 'nenhum'}" + ("  ⚠ conferir no olho" if tr["nao_saiu"] else ""),
                  "", "**Onde mexer:**"] + [f"- {x}" for x in tr["onde_mexer"] or ["nada a mexer pelo que os quadros mostram"]] + [""]
        L.append("")
    if D.get("gemini_shots"):
        L += ["## Shots complexos (Gemini Flash grátis)", D["gemini_shots"].get("texto") or f"(não veio: {D['gemini_shots'].get('erro')} {D['gemini_shots'].get('erros_antes')})", ""]
    if D.get("efeitos") is not None:
        L += ["## Efeitos achados (encaixe na onda contra a biblioteca)", "Só os ★ confiáveis (repetem ≥ 1 s) valem como fato; o resto é pista.", "",
              "| | arquivo | o arquivo começa | toca | até o pico | nota |", "|---|---|---|---|---|---|"]
        for e in D["efeitos"]:
            L.append(f"| {'★' if e.get('confiavel') else ''} | {e['nome'][:60]} | {mm(e['inicio_do_arquivo_s'])} | {mm(e['toca_de_s'])}–{mm(e['toca_ate_s'])} | {e.get('ate_o_pico_ms', '?')} ms | {e['nota']} |")
        if not D["efeitos"]:
            L.append("| | (nada achado na biblioteca) | | | | |")
        L.append("")
    if D.get("tiras"):
        L += ["## Tira de momento (o quadro devolvido = o PICO do som; o clipe entra antes pelo 'até o pico')", "| efeito | pico do som | Qwen: quadro da imagem | o clipe entraria em | folha |", "|---|---|---|---|---|"]
        for t in D["tiras"]:
            borda = t["quadro_da_imagem"] is not None and abs(t["quadro_da_imagem"] - t["pico_do_som_q"]) >= 6
            L.append(f"| {t['efeito'][:45]} | q{t['pico_do_som_q']} | {('q' + str(t['quadro_da_imagem'])) if t['quadro_da_imagem'] is not None else 'NENHUM'}"
                     f"{' ⚠ na borda da tira: provavelmente nada na imagem (conferir)' if borda else ''} | "
                     f"{('q' + str(t['clipe_entra_q'])) if t['clipe_entra_q'] is not None else '—'} | `{rel(t['folha'])}` |")
        L += ["Movimento contínuo (porta, braço) erra de 1 a 5 quadros: aí, 2 leitores + o olho.", ""]
    if D.get("pacotes"):
        L += ["## Pacote de cada corte (fala e batida em volta)", "| corte | fala antes (4 s) | fim da palavra antes | começo da palavra depois | batida |", "|---|---|---|---|---|"]
        for p in D["pacotes"]:
            L.append(f"| q{p['quadro']} ({mm(p['s'])}) | …{p.get('falas_antes_4s', '')[-50:]} | '{p.get('palavra_antes', '')}' {p.get('fim_da_palavra_antes_ms', '–')} ms antes | "
                     f"'{p.get('palavra_depois', '')}' {p.get('inicio_da_palavra_depois_ms', '–')} ms depois | {p.get('batida_ms', '–')} ms |")
        L.append("")
    L += ["## Conferir no olho", "- todo **FALTA** e todo **boca aberta = fala** (marcados ⚠ acima): pode ser só a amostragem ou o roteiro empurrando;",
          "- a câmera vale pela CURVA do CoTracker3, não pelo que o modelo de imagem diz;"]
    if D.get("estilo") == "plexus" and D.get("estagio") == "C":
        L.append("- etapa 4 (a ficha sonora do entre-cenas) é minha, com este dossiê + o roteiro + a skill /sonoplastia.")
    open(os.path.join(out, "DOSSIE.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
