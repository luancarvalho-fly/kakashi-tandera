# -*- coding: utf-8 -*-
"""Resumo de uma correção do KAKASHI do PC → LEITURA.md na pasta (19/10; "olho de Deus" P3 em 21/10).

  python resumo_pc.py [pasta | ultima] [--quadros] [--sem-refs]

Por trecho de 15 s: fala (Whisper do OpenWhispr, porta 8178, sem placa) + janela da frente + link aberto no Chrome (endereço exato,
do histórico) + elemento debaixo do mouse (UI Automation, na pausa e no clique) + card do Luluka + o que ele copiou + o print NATIVO
do "aqui / isso / esse / ó / olha" (marcado pelo tempo da fala). No fim: pré-triagem (pedidos, bugs, ideias) e SUGESTÕES de
fechamento das perguntas abertas do quiz (fala literal; quem fecha é o Claude, depois de conferir).
--quadros: onde não houver print nativo perto do "aqui", tira o quadro do tela.mp4 (_quadros\\mmss.jpg, 1920 de largura).
--sem-refs: não baixa imagem de pin (só lista os links).
A transcrição fica em fala_transcricao.json (rodar de novo não retranscreve).
"""
import datetime, glob, json, os, re, subprocess, sys, tempfile, unicodedata, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import olho  # noqa: E402

WHISPER = "http://127.0.0.1:8178/inference"
RASTRO_LULUKA = os.path.join(AQUI, "_sem_luluka.jsonl")   # pacote da Fly: sem Luluka
PENDENCIAS = "http://127.0.0.1:7798/api/luluka/pendencias"
TRECHO = 15
APONTA = re.compile(r"\b(aqui|isso|esse|essa|este|esta|ó|olha)\b", re.I)


def mmss(t):
    t = max(0, t)
    return "%d:%02d" % (int(t) // 60, int(t) % 60)


def sessao_premiere_da_troca(meta):
    """a sessão do Premiere (CORRETOR) que começou na troca: a de "inicio" mais perto do pedido da troca (até 30 s depois)"""
    t = meta.get("troca_pedida_epoch") or meta.get("troca_epoch")
    base = os.path.join(AQUI, "premiere", "sessoes")   # pacote da Fly: o servidor do painel mora em premiere\
    melhor = None
    for sj in glob.glob(os.path.join(glob.escape(base), "20*", "sessao.json")):
        try:
            ini = json.load(open(sj, encoding="utf-8")).get("inicio")
        except (OSError, ValueError):
            continue
        if t and ini and -5 <= ini - t <= 30 and (melhor is None or abs(ini - t) < melhor[0]):
            melhor = (abs(ini - t), os.path.basename(os.path.dirname(sj)))
    return "`%s`" % melhor[1] if melhor else "(não achei a pasta em premiere\\sessoes: procurar a que começou na mesma hora)"


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


# ------------------------------------------------------------------ fala
def transcrever(wav, dur):
    segs = []
    tmp = os.path.join(tempfile.gettempdir(), "kakashi_pedaco_%d.wav" % os.getpid())
    t = 0.0
    while t < dur:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-t", "25", "-i", wav, "-ac", "1", "-ar", "16000", tmp], check=False)
        bnd = "----k"
        corpo = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n" % bnd).encode()
                 + open(tmp, "rb").read()
                 + ("\r\n--%s\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\nverbose_json\r\n--%s\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\npt\r\n--%s--\r\n" % (bnd, bnd, bnd)).encode())
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(WHISPER, data=corpo, headers={"Content-Type": "multipart/form-data; boundary=" + bnd}), timeout=120))
            for s in r.get("segments", []):
                tx = s["text"].strip()
                if tx and not re.fullmatch(r"(Tchau\.?|Obrigad[oa]\.?|.*Amara\.org.*)", tx):
                    segs.append([round(t + s["start"], 2), round(t + s.get("end", s["start"] + 2), 2), tx])
        except Exception as e:
            segs.append([t, t, "[whisper falhou: %s]" % e])
        t += 25
    try:
        os.remove(tmp)
    except OSError:
        pass
    return segs


def motor_transcricao():
    """pacote da Fly: config.json → "transcricao": "ardi" (padrão) | "local" (faster-whisper no PC) | "8178" (whisper-server)"""
    try:
        return json.load(open(os.path.join(AQUI, "config.json"), encoding="utf-8")).get("transcricao", "ardi")
    except (OSError, ValueError):
        return "ardi"


def transcrever_pelo_motor(wav):
    motor = motor_transcricao()
    if motor == "8178":
        return transcrever(wav, olho.duracao(wav))
    if motor == "local":
        from faster_whisper import WhisperModel   # pip install faster-whisper (o pc_check diz se o PC aguenta)
        modelo = os.environ.get("KAKASHI_WHISPER", "small")
        try:
            m = WhisperModel(modelo, device="cuda", compute_type="float16")
        except Exception:
            m = WhisperModel(modelo, device="cpu", compute_type="int8")
        segs, _ = m.transcribe(wav, language="pt", vad_filter=True)
        return [[round(s.start, 2), round(s.end, 2), s.text.strip()] for s in segs if s.text.strip()]
    # "ardi": quem transcreve é o Claude, pelo ARDI (upload_file + view_file), e grava com importar_transcricao.py
    raise SystemExit("PRECISA TRANSCREVER PELA ARDI: suba o fala.wav (upload_file), leia com view_file e rode\n"
                     "  python importar_transcricao.py <pasta da sessao> <texto do view_file.txt>\n"
                     "depois rode este resumo de novo.")


def fala_da_sessao(pasta, desloc):
    """[(inicio, fim, texto)] no relógio da sessão. Cache em fala_transcricao.json (refaz se o fala.wav mudou)."""
    wav = os.path.join(pasta, "fala.wav")
    if not os.path.isfile(wav):
        return []
    cache = os.path.join(pasta, "fala_transcricao.json")
    marca = [os.path.getsize(wav), int(os.path.getmtime(wav))]
    try:
        c = json.load(open(cache, encoding="utf-8"))
        if c.get("marca") == marca:
            segs = c["segmentos"]
        else:
            raise ValueError
    except (OSError, ValueError, KeyError):
        segs = transcrever_pelo_motor(wav)
        json.dump({"marca": marca, "segmentos": segs}, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    # 4º campo: o pedaço começa num corte de 25 s (só ali o Whisper parte palavra no meio: 'pequ' / 'ena')
    return [(a + desloc, b + desloc, tx, (a % 25) < 0.6) for a, b, tx in segs]


def frases(fala):
    """junta os pedaços do Whisper em frases; cada frase com o tempo do 1º pedaço"""
    out, atual, t_ini = [], "", None
    for a, b, tx, corte in fala:
        if tx.startswith("[whisper"):
            continue
        if t_ini is None:
            t_ini = a
        cola = corte and re.match(r"^[a-zà-ú]", tx) and re.search(r"[a-zà-ú]$", atual)
        atual = (atual + ("" if cola else " ") + tx).strip()
        partes = re.split(r"(?<=[.?!])\s+", atual)
        for p in partes[:-1]:
            out.append((t_ini, p.strip())); t_ini = a
        atual = partes[-1]
        if re.search(r"[.?!]$", atual):
            out.append((t_ini, atual.strip())); atual, t_ini = "", None
    if atual.strip():
        out.append((t_ini or 0, atual.strip()))
    return [(t, f) for t, f in out if len(f) > 1]


def momentos_aqui(fala):
    """[(t estimado da palavra, palavra, frase)] — o tempo da palavra é proporcional à posição dela dentro do pedaço"""
    out = []
    for a, b, tx, _ in fala:
        for m in APONTA.finditer(tx):
            t = a + (max(b, a + 0.5) - a) * (m.start() / max(1, len(tx)))
            if out and t - out[-1][0] < 1.5:
                continue
            out.append((round(t, 2), m.group(0), tx))
    return out


FORTE = re.compile(r"^(aqui|ó|olha)$", re.I)


# ------------------------------------------------------------------ outras fontes
def rastro_luluka(ini_epoch, fim_epoch, meta=None):
    """cliques no Luluka que o próprio Luluka já grava (luluka-rastro.jsonl, hora UTC) — serve também pras sessões antigas.
    meta: o relógio da sessão (olho do Premiere = relógio do painel, sem pausas; olho.t_da_sessao)"""
    out = []
    try:
        with open(RASTRO_LULUKA, encoding="utf-8") as f:
            for l in f:
                try:
                    e = json.loads(l)
                    q = datetime.datetime.fromisoformat(e["em"].replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                if ini_epoch <= q <= fim_epoch and e.get("id") and e.get("tipo") in ("clique", "passou", "selecionou"):
                    out.append({"tipo": "luluka", "acao": e["tipo"], "id": e["id"], "k": e.get("k"), "titulo": e.get("titulo"),
                                "aba": e.get("aba"), "t": round(olho.t_da_sessao(q, meta) if meta else q - ini_epoch, 2),
                                "fonte": "rastro do Luluka"})
    except OSError:
        pass
    return out


def pendencias_abertas():
    """só PERGUNTAS abertas do quiz (tarefa aberta não se 'responde' falando; e muitas nasceram da própria correção)"""
    try:
        return [i for i in json.load(urllib.request.urlopen(PENDENCIAS, timeout=5)).get("itens", [])
                if i.get("estado") == "aberta" and i.get("tipo") != "tarefa"]
    except Exception:
        return None


PARADAS = set(sem_acento("""a o e é de da do das dos que pra para por com sem um uma uns umas no na nos nas em ao aos à às se
seu sua seus suas meu minha eu você voce ele ela isso esse essa aqui ali lá la tá ta né ne tipo mano cara porque mais menos muito
muita como quando onde qual quais quem ser ter tem foi vai vou fazer faz fica ficar está esta estão estou já ja só so também tambem
mas ou então entao assim coisa coisas sei não nao sim pode pô po aí ai ó olha ver vê ve dar dá da aquele aquela isso tudo nada
cada porque gente ainda sobre entre depois antes outro outra algum alguma bem bom""").split())


def palavras(s):
    return {w for w in re.findall(r"[a-z0-9]{4,}", sem_acento(s)) if w not in PARADAS}


def sugerir_fechamentos(frs, abertas):
    """resposta falada que bate com pergunta aberta do quiz: palavras raras em comum numa janela de ~30 s de fala"""
    import math
    if not abertas:
        return []
    docs = {p["id"]: palavras(p.get("titulo", "") + " " + p.get("pergunta", "")) for p in abertas}
    df = {}
    for ws in docs.values():
        for w in ws:
            df[w] = df.get(w, 0) + 1
    n = len(docs)
    out = []
    for i, (t, f) in enumerate(frs):
        janela = [x for x in frs[i:i + 6] if x[0] - t <= 30]
        texto = " ".join(x[1] for x in janela)
        ws = palavras(texto)
        for p in abertas:
            comum = ws & docs[p["id"]]
            if len(comum) < 3:
                continue
            peso = sum(math.log(1 + n / df[w]) for w in comum)
            cobre = len(comum) / max(1, len(docs[p["id"]]))
            if peso >= 6 and cobre >= 0.2:
                out.append((peso, p, t, texto, sorted(comum)))
    melhores = {}
    for peso, p, t, texto, comum in sorted(out, key=lambda x: -x[0]):
        if p["id"] not in melhores:
            melhores[p["id"]] = (peso, p, t, texto, comum)
    return sorted(melhores.values(), key=lambda x: -x[0])[:10]


BUG = re.compile(r"\b(bug\w*|quebrad\w*|quebrou|zoad\w*|errad\w*|erro|n[aã]o (funciona|t[aá] funcionando|aparece|abre|carrega)|"
                 r"travou|travando|sumiu|cortad\w*|comid\w*|desalinhad\w*|feio|bizarro|estranho)\b", re.I)
PEDIDO = re.compile(r"\b(quero|queria|gostaria|tem que|tinha que|precisa|preciso|faça|coloca|colocar|bota|botar|tira|tirar|"
                    r"muda|mudar|troca|trocar|dá uma|repagina\w*|arruma|corrige|ajusta|cria|criar|adiciona|baixar|transcrever|"
                    r"analisar|separa)\b", re.I)
IDEIA = re.compile(r"\b(ideia|e se|talvez|poderia|seria (legal|bom|irado)|acho que|vale a pena|imagina|pensei|pensando|n[aã]o sei se)\b", re.I)


def triagem(frs):
    cats = {"Pedidos": [], "Bugs": [], "Ideias": []}
    for t, f in frs:
        if len(f) < 12:
            continue
        if BUG.search(f):
            cats["Bugs"].append((t, f))
        elif PEDIDO.search(f):
            cats["Pedidos"].append((t, f))
        elif IDEIA.search(f):
            cats["Ideias"].append((t, f))
    return cats


# ------------------------------------------------------------------ montar
def descrever_elemento(e):
    nome = e.get("nome") or ""
    txt = "«%s»" % nome[:80] if nome else "(sem nome)"
    txt += " (%s · %s)" % (e.get("controle") or "?", e.get("app") or "?")
    if e.get("dentro_de"):
        txt += " dentro de «%s»" % e["dentro_de"]["nome"][:60]
    if e.get("ret"):
        txt += " [%d,%d %dx%d]" % (e["ret"][0], e["ret"][1], e["ret"][2] - e["ret"][0], e["ret"][3] - e["ret"][1])
    return txt


def linha_evento(x, uia_por_clique):
    tp = x.get("tipo"); tt = mmss(x.get("t", 0))
    if tp == "janela":
        return "- %s janela: %s — %s" % (tt, x.get("app"), (x.get("titulo") or "")[:90])
    if tp in ("clique", "clique_direito"):
        u = next((ue for (ut, ux, uy), ue in uia_por_clique.items()
                  if abs(ut - x["t"]) <= 0.3 and ux == x.get("x") and uy == x.get("y")), None)
        alvo = descrever_elemento(u) if u else "%s — %s" % (x.get("app"), (x.get("titulo") or "")[:60])
        return "- %s %s em (%s, %s) · %s" % (tt, tp.replace("_", " "), x.get("x"), x.get("y"), alvo)
    if tp == "sob_mouse" and x.get("motivo") == "parou":
        return "- %s mouse parou em (%s, %s) · %s" % (tt, x.get("x"), x.get("y"), descrever_elemento(x))
    if tp == "luluka":
        return "- %s card do Luluka (%s): %s · %s%s" % (tt, x.get("acao"), x.get("id"), (x.get("titulo") or "")[:70],
                                                       " [%s]" % x["fonte"] if x.get("fonte") else "")
    if tp == "copiou":
        o = x.get("o_que")
        if o in ("texto", "link"):
            det = "«%s»" % x.get("texto", "")[:300].replace("\n", " ⏎ ")
        elif o == "arquivos":
            det = ", ".join(x.get("arquivos", [])[:5])
        else:
            det = x.get("arquivo", "") + (" (de %s)" % x["url_imagem"] if x.get("url_imagem") else "")
        return "- %s copiou %s: %s · %s%s" % (tt, o, det, x.get("app", ""), (" · de %s" % x["de"]) if x.get("de") else "")
    if tp == "print" and x.get("motivo") == "pagina":
        return "- %s print da página: %s" % (tt, x.get("perto"))
    return None


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a or a[0] == "ultima":
        ps = sorted(glob.glob(os.path.join(AQUI, "sessoes", "*_pc")))
        if not ps:
            sys.exit("nenhuma sessão")
        pasta = ps[-1]
    else:
        pasta = a[0]
    meta = json.load(open(os.path.join(pasta, "sessao.json"), encoding="utf-8"))
    ini = meta.get("inicio_epoch") or 0
    dur = meta.get("duracao_s") or 0
    rep = meta.get("replay_s") or 0
    juntos = meta.get("replay_juntado") or []
    desloc_fala = rep if (rep and "fala" not in juntos) else 0        # replay que não juntou: o fala.wav começa no atalho
    desloc_tela = rep if (rep and "tela" not in juntos) else 0
    evs = [json.loads(l) for l in open(os.path.join(pasta, "eventos.jsonl"), encoding="utf-8") if l.strip()]
    if not any(e.get("tipo") == "luluka" for e in evs):
        evs += rastro_luluka(ini, olho.fim_da_sessao(meta), meta)
    evs.sort(key=lambda e: e.get("t", 0))
    # links do Chrome
    try:
        links = json.load(open(os.path.join(pasta, "links.json"), encoding="utf-8"))["links"]
    except (OSError, ValueError, KeyError):
        try:
            links = olho.links_da_sessao(pasta, meta, baixar="--sem-refs" not in sys.argv)
        except Exception as e:
            links = []; print("links do Chrome: %s" % e)
    fala = fala_da_sessao(pasta, desloc_fala)
    frs = frases(fala)
    prints = [e for e in evs if e.get("tipo") == "print"]
    aqui = momentos_aqui(fala)

    # print do "aqui": o nativo mais perto (de 1 s antes a 2 s depois; senão ±3 s). Sem nativo → quadro do vídeo (--quadros),
    # no máximo 3 por trecho, 1 a cada 3 s, "aqui/ó/olha" antes de "isso/esse"
    aponta = []
    for ta, palavra, tx in aqui:
        cand = [p for p in prints if -1.0 <= p["t"] - ta <= 2.0] or [p for p in prints if abs(p["t"] - ta) <= 3.0]
        aponta.append((ta, palavra, min(cand, key=lambda p: abs(p["t"] - ta)) if cand else None))
    quadros = []
    for t_tr in range(0, int(max(dur, 1)) + TRECHO, TRECHO):
        cands = sorted([x for x in aponta if x[2] is None and t_tr <= x[0] < t_tr + TRECHO], key=lambda x: (not FORTE.match(x[1]), x[0]))
        pegos = []
        for c in cands:
            if len(pegos) < 3 and all(abs(c[0] - p[0]) >= 3 for p in pegos):
                pegos.append(c)
        quadros += [int(c[0]) for c in pegos]
    quadros = sorted(set(quadros))
    if "--quadros" in sys.argv and os.path.isfile(os.path.join(pasta, "tela.mp4")):
        os.makedirs(os.path.join(pasta, "_quadros"), exist_ok=True)
        for tt in quadros[:60]:
            ts = tt - desloc_tela
            if ts < 0:
                continue
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(ts), "-i", os.path.join(pasta, "tela.mp4"), "-frames:v", "1",
                            "-vf", "scale='min(1920,iw)':-2",       # a tela do painel do Premiere é 4K: quadro em 1920 igual ao do PC
                            os.path.join(pasta, "_quadros", "%02d%02d.jpg" % (tt // 60, tt % 60))], check=False)

    j0 = meta.get("janela_inicial") or {}
    n_cop = sum(1 for e in evs if e.get("tipo") == "copiou")
    linhas = ["# Correção KAKASHI (PC) · %s" % meta.get("inicio_local", ""), "",
              "duração %s · microfone: %s · janela no atalho: %s — %s" % (mmss(dur), meta.get("microfone"), j0.get("app"), j0.get("titulo")),
              "arquivos: fala.wav (voz) · pc.wav (som do PC) · tela.mp4 (5 q/s, 1920) · eventos.jsonl (inclui o caminho do mouse) · "
              "_prints\\ (nativos, *_perto = recorte 800x500) · _copias\\ · _refs\\ · links.json",
              "contagem: %d prints nativos · %d elementos sob o mouse · %d links · %d cópias · %d cards do Luluka" % (
                  len(prints), sum(1 for e in evs if e.get("tipo") == "sob_mouse"), len(links), n_cop,
                  sum(1 for e in evs if e.get("tipo") == "luluka"))]
    if rep:
        linhas.append("REPLAY: 0:00–%s = os %d s ANTES do atalho (buffer); o atalho foi em %s. Juntado no arquivo: %s." % (
            mmss(rep), rep, mmss(rep), ", ".join(juntos) or "nada (ver erros)"))
    if meta.get("olho_premiere"):                    # 23/10: o olho do PC dentro da sessão do Premiere (kakashi.pyw OlhoPremiere)
        linhas.append("**OLHO DO PREMIERE** da sessão `%s`: mesmo relógio do painel (pausas e pedaços apagados tirados). O que ele fez na "
                      "timeline está no resumo.md da sessão (a pasta de cima); aqui é o resto da tela: janela, mouse, elemento sob o mouse, "
                      "prints, cópias, links. Ler os dois juntos pelo minuto." % meta.get("sessao_premiere", "?"))
    if meta.get("continua_em") == "premiere":        # 23/10: troca sozinha PC → Premiere (kakashi.pyw _vigiar_troca)
        linhas.append("**CONTINUA NO PREMIERE em %s** (ele entrou no Premiere e o Kakashi trocou sozinho): esta é só a 1ª parte; a correção "
                      "segue na sessão do Premiere %s — LER AS DUAS, nessa ordem." % (mmss(meta.get("troca_s") or dur), sessao_premiere_da_troca(meta)))
    if meta.get("erros"):
        linhas.append("erros: " + " · ".join(meta["erros"]))
    linhas.append("")

    uia_por_clique = {}
    for e in evs:
        if e.get("tipo") == "sob_mouse" and e.get("motivo") == "clique":
            uia_por_clique[(round(e["t"], 1), e.get("x"), e.get("y"))] = e

    t = 0.0
    fim_tl = max([dur, 1] + [e.get("t", 0) for e in evs[-1:]])
    while t < fim_tl:
        f = [x for x in fala if t <= x[0] < t + TRECHO]
        e = [x for x in evs if t <= x.get("t", 0) < t + TRECHO and x.get("tipo") not in ("mouse", "parou")]
        ln = [x for x in links if t <= x.get("t", 0) < t + TRECHO]
        ap = [x for x in aponta if t <= x[0] < t + TRECHO]
        if f or e or ln:
            marca = " (replay, antes do atalho)" if rep and t + TRECHO <= rep else (" (atalho em %s)" % mmss(rep) if rep and t < rep else "")
            linhas.append("## [%s–%s]%s" % (mmss(t), mmss(t + TRECHO), marca))
            for x in f:
                linhas.append("> %s" % x[2])
            itens = []          # (t, linha) — links e eventos em ordem de tempo
            for x in ln:
                ref = (" · imagem: %s" % x["ref"]) if x.get("ref") else (" · (%s: vale o print da página)" % x["ref_erro"] if x.get("ref_erro") else "")
                itens.append((x["t"], "- %s link: %s — %s%s" % (mmss(x["t"]), (x.get("titulo") or "")[:70], x["url"], ref)))
            for x in e:
                s = linha_evento(x, uia_por_clique)
                if s:
                    itens.append((x.get("t", 0), s))
            linhas += [s for _, s in sorted(itens, key=lambda i: i[0])]
            # o "aqui": um print nativo por linha (com as palavras que caem nele); sem nativo, uma linha só pro trecho
            nat = {}
            for ta, palavra, p in ap:
                if p:
                    nat.setdefault(p["perto"], (p, []))[1].append("«%s» %s" % (palavra, mmss(ta)))
            for perto, (p, ditos) in nat.items():
                linhas.append("- %s → print nativo %s (inteiro: %s)" % (", ".join(ditos), perto, p["arquivo"]))
            sem = [x for x in ap if not x[2]]
            if sem:
                qs = [q for q in quadros if t <= q < t + TRECHO]
                linhas.append("- %s → sem print nativo perto; %s" % (
                    ", ".join("«%s» %s" % (x[1], mmss(x[0])) for x in sem),
                    ("quadros do vídeo (1920): " + ", ".join("_quadros\\%02d%02d.jpg" % (q // 60, q % 60) for q in qs))
                    if "--quadros" in sys.argv else "rodar com --quadros pro quadro do vídeo"))
            linhas.append("")
        t += TRECHO

    # triagem
    linhas += ["---", "", "# Triagem (pré-triagem por palavra — o Claude confere com a fala acima)", ""]
    for cat, itens in triagem(frs).items():
        linhas.append("## %s" % cat)
        linhas += ["- [%s] «%s»" % (mmss(t), f) for t, f in itens] or ["- (nada)"]
        linhas.append("")
    linhas.append("## Respostas → perguntas abertas do quiz (SUGESTÃO; não fechar sozinho, o Claude confere e fecha)")
    abertas = pendencias_abertas()
    if abertas is None:
        linhas.append("- (Luluka fora do ar: não deu pra ler as pendências)")
    else:
        sug = sugerir_fechamentos(frs, abertas)
        for peso, p, tt, texto, comum in sug:
            linhas.append("- `%s` «%s» ← [%s] «%s» (em comum: %s)" % (p["id"], p.get("titulo", ""), mmss(tt), texto[:400], ", ".join(comum[:8])))
        if not sug:
            linhas.append("- (nenhuma fala bateu com as %d perguntas abertas)" % len(abertas))
    linhas.append("")
    open(os.path.join(pasta, "LEITURA.md"), "w", encoding="utf-8").write("\n".join(linhas))
    print(os.path.join(pasta, "LEITURA.md"))


if __name__ == "__main__":
    main()
