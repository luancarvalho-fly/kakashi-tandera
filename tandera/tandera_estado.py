# -*- coding: utf-8 -*-
"""TANDERA V2 — o andamento de cada trabalho num arquivo (T4, 20/10/2026).

Cada rodada do tandera.py (pela tela do app ou pelo terminal) escreve estado\\<id>.json:
arquivo, projeto, estilo/estágio/modo, quem pediu, as etapas (feitas, a atual, as que faltam),
o andamento dentro da etapa, as últimas linhas do log e o PID. A tela do app (apps\\TANDERA)
só LÊ esses arquivos — por isso o que o Claude roda pelo terminal aparece lá do mesmo jeito.

- estado\\<id>.controle.json é escrito pela TELA (pausas). Daqui só se lê, pra descontar o tempo pausado.
- estado\\_tempos.json guarda quanto cada etapa levou por minuto de vídeo: a estimativa aprende a cada rodada.
- Nada aqui pode derrubar o motor: todo erro de escrita é engolido.
- T5 (21/10): "pausar e liberar a placa" mata o motor e a tela guarda o comando exato (argv + pasta). O RETOMAR roda o MESMO
  comando com TANDERA_RETOMAR=1 e o mesmo TANDERA_ID: aqui o estado continua o de antes (mesmo começo, mesmas pausas) e diz
  "retomando: N de M etapas já prontas". PEDACOS diz quais etapas guardam em pedaços (o resto recomeça do zero ao retomar)."""
import json, os, re, sys, threading, time

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "estado")
HIST = os.path.join(PASTA, "_tempos.json")

# a ordem em que o tandera.py RODA as etapas (não a ordem da receita)
ORDEM = ["cortes", "cortes2", "separacao", "fala", "entonacao", "batida", "grade", "musica", "efeitos", "camera", "corpo", "rosto",
         "quadros", "texto", "cor", "descricao_leve", "ficha", "descricao", "tiras", "tracado", "roteiro_previsto", "gemini_shots",
         "visao", "dossie"]
CURTO = {"cortes": "cortes", "cortes2": "2ª e 3ª opinião de corte", "separacao": "separação", "fala": "fala", "entonacao": "entonação",
         "batida": "batida", "grade": "grade", "musica": "música", "efeitos": "efeitos", "camera": "câmera", "corpo": "corpo",
         "rosto": "rosto", "quadros": "quadros", "texto": "texto na tela", "cor": "cor", "descricao_leve": "descrição leve",
         "ficha": "fichas", "descricao": "descrição", "tiras": "tira", "tracado": "traçado", "roteiro_previsto": "roteiro previsto",
         "gemini_shots": "Gemini (shots)", "visao": "visão geral", "dossie": "dossiê"}
PLACA = {"cortes", "cortes2", "separacao", "fala", "batida", "musica", "camera", "corpo", "rosto", "efeitos",
         "descricao_leve", "ficha", "descricao", "tiras", "tracado", "roteiro_previsto"}
# chute inicial, em segundos por MINUTO de trecho (cortes: por minuto do vídeo inteiro), tirado dos tempos do T3; depois aprende
CHUTE = {"cortes": 7, "cortes2": 8, "separacao": 46, "fala": 8, "entonacao": 5, "batida": 4, "grade": 2, "musica": 4, "efeitos": 183,
         "camera": 70, "corpo": 950, "rosto": 340, "quadros": 10, "texto": 50, "cor": 2, "descricao_leve": 60, "ficha": 350,
         "descricao": 470, "tiras": 140, "tracado": 220, "roteiro_previsto": 20, "gemini_shots": 15, "visao": 36, "dossie": 2}
# nas etapas que andam shot a shot, o tempo depende do número de shots, não da duração (T4: 16 shots em 21 s levaram 99 s
# na descrição leve; por minuto o chute dava 21 s). Segundos por shot; depois aprende.
POR_SHOT = {"quadros": 0.3, "descricao_leve": 6.2, "ficha": 13, "descricao": 10}
# T5: as etapas que GUARDAM EM PEDAÇOS (parar no meio perde só o pedaço da vez) e como. Todas as outras são de uma vez só:
# parar no meio = a etapa recomeça do zero ao retomar (as de antes dela vêm do cache).
PEDACOS = {"cortes2": "em 2 partes (TransNetV2 → pixel)", "separacao": "em 2 partes (Roformer → BandIt)",
           "camera": "shot a shot", "corpo": "take a take", "rosto": "em lotes de 150 quadros", "quadros": "quadro a quadro",
           "texto": "em lotes de 16 quadros", "descricao_leve": "shot a shot", "ficha": "shot a shot", "descricao": "shot a shot",
           "tiras": "efeito a efeito", "tracado": "plano a plano"}
# por que as outras não: o modelo olha o arquivo INTEIRO de uma vez (cortar em trechos muda o resultado na emenda) — e quase
# todas levam segundos. As longas de uma vez só: efeitos (encaixe contra a biblioteca, ~3 min no EP01) e a parte em andamento da separação.
POR_QUE_INTEIRA = {"cortes": "o AutoShot olha o vídeo inteiro em janelas que se cruzam", "fala": "o Whisper e o alinhador olham a fala inteira",
                   "entonacao": "segundos", "batida": "o Beat This olha a música inteira", "grade": "segundos", "musica": "segundos",
                   "efeitos": "o encaixe procura cada efeito na onda inteira", "cor": "segundos", "roteiro_previsto": "uma chamada só",
                   "gemini_shots": "um pedido só", "visao": "um pedido só", "dossie": "segundos"}


def _ler(arq, padrao):
    try:
        return json.load(open(arq, encoding="utf-8"))
    except Exception:
        return padrao


def _gravar(arq, v):
    tmp = arq + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(v, f, ensure_ascii=False, indent=1)
    for _ in range(20):                  # a tela pode estar lendo bem nessa hora (Windows trava o replace)
        try:
            os.replace(tmp, arq); return
        except PermissionError:
            time.sleep(0.05)
    os.remove(tmp)


def projeto_do_caminho(caminho):
    """EP03 pelo caminho ou pelo nome (PX_EP03_..., ep_3_youtube...); senão a pasta, pulando as genéricas."""
    m = re.search(r"(?i)(?:^|[\\/_\s-])ep[_\s-]?0*(\d{1,3})(?=[_\s\-.\\/]|$)", caminho)
    if m:
        return f"EP{int(m.group(1)):02d}"
    genericas = {"1_bruto", "2_audio", "97_temp", "99_exports", "trabalho", "v2", "desktop", "downloads", "videos", "vídeos", "temp", "tmp"}
    for p in reversed(os.path.normpath(caminho).split(os.sep)[:-1]):
        if p and p.lower() not in genericas and not re.fullmatch(r"[0-9a-f]{12}", p) and ":" not in p:
            return p
    return "—"


class _Tee:
    """o que o motor imprime continua indo pro terminal e também vira 'mensagem' na tela"""
    def __init__(self, orig, estado):
        self.orig, self.e, self.buf = orig, estado, ""

    def write(self, s):
        try:
            self.orig.write(s)
        except Exception:
            pass
        try:
            self.buf += s
            while "\n" in self.buf:
                linha, self.buf = self.buf.split("\n", 1)
                self.e._linha(linha)
        except Exception:
            pass
        return len(s)

    def flush(self):
        try:
            self.orig.flush()
        except Exception:
            pass

    def __getattr__(self, k):
        return getattr(self.orig, k)


class Estado:
    def __init__(self, video, comando):
        self.ok = True
        self.antes, self.s_antes = None, {}
        try:
            os.makedirs(PASTA, exist_ok=True)
            nome = os.path.basename(video)
            quem = os.environ.get("TANDERA_QUEM", "")
            if quem not in ("tela", "claude", "terminal"):      # T5: o RETOMAR da tela passa adiante quem pediu da 1ª vez
                quem = "claude" if os.environ.get("CLAUDECODE") else "terminal"
            self.id = os.environ.get("TANDERA_ID") or time.strftime("%Y%m%d-%H%M%S") + "_" + re.sub(r"[^A-Za-z0-9_-]", "_", os.path.splitext(nome)[0])[:32]
            self.arq = os.path.join(PASTA, self.id + ".json")
            agora = time.time()
            # T5: argv + pasta = o comando EXATO, pro RETOMAR rodar de novo igual (caminho relativo, --refazer, tudo)
            self.d = {"id": self.id, "pid": os.getpid(), "pid_inicio": agora, "quem": quem, "comando": comando, "argv": sys.argv[1:],
                      "pasta": os.getcwd(), "video": video, "arquivo": nome,
                      "projeto": projeto_do_caminho(video), "estilo": "", "estagio": "", "modo": "", "situacao": "rodando",
                      "mensagem": "calibrando o arquivo…", "linhas": [], "inicio": agora, "fim": None, "atualizado": agora,
                      "etapas": [], "atual": None, "saida": "", "dossie": "", "minutos": 0}
            if os.environ.get("TANDERA_RETOMAR"):
                self.antes = _ler(self.arq, None)
            if self.antes:     # retomando depois de "pausar e liberar a placa": o mesmo trabalho continua (mesmo começo, quem pediu e histórico)
                for k in ("inicio", "quem", "projeto", "liberacoes", "retomadas"):
                    if self.antes.get(k):
                        self.d[k] = self.antes[k]
                self.d["mensagem"] = "retomando: relendo o que já foi feito…"
                # o tempo de cada etapa soma o de antes da pausa (a feita antes volta do cache em ~0 s)
                for e in self.antes.get("etapas", []):
                    s = e.get("s") if e.get("estado") == "feita" else e.get("s_antes")
                    if s:
                        self.s_antes[e["chave"]] = float(s)
            self._sujo, self._trava = True, threading.Lock()
            self.gravar()
            threading.Thread(target=self._laco, daemon=True).start()
            sys.stdout = _Tee(sys.stdout, self)
        except Exception:
            self.ok = False

    # ---------------------------------------------------------------- escrita (no máximo 1x por segundo; o fim grava na hora)
    def _laco(self):
        while self.ok:
            time.sleep(1.0)
            if self._sujo:
                self.gravar()

    def gravar(self):
        try:
            with self._trava:
                self.d["atualizado"] = time.time(); self._sujo = False
                _gravar(self.arq, self.d)
        except Exception:
            pass

    def _linha(self, linha):
        linha = linha.rstrip()
        if not linha.strip():
            return
        self.d["linhas"] = (self.d["linhas"] + [linha])[-40:]
        self.d["mensagem"] = re.sub(r"^\[\d\d:\d\d:\d\d\]\s*", "", linha)[:300]
        self._sujo = True

    # ---------------------------------------------------------------- pausas (quem escreve é a tela)
    def _pausado(self, a, b):
        c = _ler(os.path.join(PASTA, self.id + ".controle.json"), {})
        tot = 0.0
        for x, y in c.get("pausas", []):
            tot += max(0.0, min(b, y) - max(a, x))
        return tot

    # ---------------------------------------------------------------- plano, etapas, andamento
    def plano(self, receita, estilo, estagio, modo, minutos_trecho, minutos_video, projeto=None, extra=()):
        try:
            hist = _ler(HIST, {})
            chaves = [k for k in ORDEM if k in receita or k in ("quadros", "dossie") or k in extra]
            et = []
            for k in chaves:
                ritmo = hist.get(k, {}).get("ritmo") or CHUTE.get(k, 10)
                mins = minutos_video if k in ("cortes", "cortes2") else minutos_trecho
                et.append({"chave": k, "nome": CURTO.get(k, k), "estado": "falta", "placa": k in PLACA, "est_s": round(max(1.0, ritmo * mins), 1),
                           "ini": None, "fim": None, "s": None, "sub": None, "como": ""})
            self.d.update(etapas=et, estilo=estilo, estagio=estagio if estilo == "plexus" else "", modo=modo, minutos=round(minutos_trecho, 2),
                          minutos_video=round(minutos_video, 2))
            if projeto:
                self.d["projeto"] = projeto
            if self.antes:
                self._anunciar_retomada()
            self._sujo = True
        except Exception:
            pass

    def _anunciar_retomada(self):
        """T5: 'retomando: N de M etapas já prontas' + o pedaço da etapa que parou (ou 'recomeça do zero')"""
        ant = {e["chave"]: e for e in self.antes.get("etapas", [])}
        chaves = [e["chave"] for e in self.d["etapas"]]
        prontas = [k for k in chaves if ant.get(k, {}).get("estado") == "feita"]
        parou = next((ant[k] for k in chaves if ant.get(k, {}).get("estado") in ("agora", "parou")), None)
        r = {"quando": time.time(), "prontas": len(prontas), "total": len(chaves), "etapa": None, "pedacos": None, "recomeca": False}
        txt = f"retomando: {len(prontas)} de {len(chaves)} etapas já prontas (vêm do cache)"
        if parou:
            k = parou["chave"]; r["etapa"] = k
            sub = parou.get("sub")
            if k in PEDACOS and sub and sub[1]:
                r["pedacos"] = [int(sub[0]), int(sub[1]), sub[2] if len(sub) > 2 else ""]
                txt += f" · {CURTO.get(k, k)}: {sub[0]} de {sub[1]} {(sub[2] if len(sub) > 2 else '').split(' (')[0]} já guardados"
            elif k in PEDACOS:
                txt += f" · {CURTO.get(k, k)}: guarda {PEDACOS[k]} — continua do pedaço em que parou"
            else:
                r["recomeca"] = True
                txt += f" · {CURTO.get(k, k)}: esta etapa recomeça do zero"
        self.d["retomadas"] = (self.d.get("retomadas") or []) + [r]
        self.d["mensagem"] = txt
        print(time.strftime("[%H:%M:%S]"), txt, flush=True)

    def shots(self, n):
        """com os cortes medidos: refaz a estimativa das etapas que andam shot a shot"""
        try:
            hist = _ler(HIST, {})
            self.d["shots"] = int(n)
            for e in self.d["etapas"]:
                k = e["chave"]
                if self._geracao_inteira(k):
                    continue
                if k in POR_SHOT and e["estado"] in ("falta", "agora"):
                    e["est_s"] = round(max(1.0, (hist.get(k, {}).get("por_shot") or POR_SHOT[k]) * n), 1)
            self._sujo = True
        except Exception:
            pass

    def _geracao_inteira(self, k):
        """Plexus A completo: a ficha é UMA unidade com todos os planos (T3: 83 s) — aí vale o tempo por minuto"""
        return k == "ficha" and self.d.get("estagio") == "A" and self.d.get("modo") == "completo"

    def _fechar(self, e, como="feita"):
        agora = time.time()
        e["estado"], e["fim"] = como, agora
        e["s"] = round(agora - e["ini"] - self._pausado(e["ini"], agora) + self.s_antes.get(e["chave"], 0.0), 1)

    def etapa(self, chave):
        try:
            idx = next((i for i, e in enumerate(self.d["etapas"]) if e["chave"] == chave), None)
            if idx is None:
                return
            for i, e in enumerate(self.d["etapas"]):
                if e["estado"] == "agora":
                    self._fechar(e)
                elif e["estado"] == "falta" and i < idx:
                    e["estado"] = "pulada"
            e = self.d["etapas"][idx]
            e.update(estado="agora", ini=time.time(), sub=None, s_antes=self.s_antes.get(chave))   # T5: s_antes = o que ela já andou antes da pausa
            self.d["atual"] = chave
            self.gravar()
        except Exception:
            pass

    def sub(self, feito, total, txt=""):
        """andamento dentro da etapa: 3 de 16 shots"""
        try:
            for e in self.d["etapas"]:
                if e["estado"] == "agora":
                    e["sub"] = [int(feito), int(total), txt]
            self._sujo = True
        except Exception:
            pass

    def fim(self, situacao, mensagem="", saida="", tempos=None):
        try:
            if self.antes and situacao == "parado":
                # T5: retomado e parou antes de chegar onde estava (Premiere aberto, placa em uso): volta a pausado com a placa
                # livre, com as etapas como estavam na pausa — não vira "parado" no histórico e o próximo RETOMAR conta certo
                situacao = "pausado-livre"
                mensagem = "não conseguiu retomar: " + (mensagem or self.d.get("mensagem", ""))
                for k in ("etapas", "liberada", "atual"):
                    if k in self.antes:
                        self.d[k] = self.antes[k]
                self.d["retomadas"] = (self.d.get("retomadas") or [])[:-1]
            else:
                for e in self.d["etapas"]:
                    if e["estado"] == "agora":
                        self._fechar(e, "feita" if situacao == "pronto" else "parou")
                    elif e["estado"] == "falta":
                        e["estado"] = "pulada" if situacao == "pronto" else "falta"
            if situacao == "pausado-livre":
                self.d.update(situacao=situacao, fim=None)
            else:
                self.d.update(situacao=situacao, fim=time.time(), atual=None)
            if mensagem and self.antes and situacao == "pronto":     # T5: o tempo do motor é só desde a última retomada
                n = len(self.d.get("retomadas") or [])
                mensagem = f"{mensagem} desde a última retomada ({n} retomada{'s' if n > 1 else ''}; o tempo do trabalho todo está na barra)"
            if mensagem:
                self.d["mensagem"] = mensagem
            if saida:
                self.d["saida"] = saida
                if situacao == "pronto" and os.path.exists(os.path.join(saida, "DOSSIE.md")):
                    self.d["dossie"] = os.path.join(saida, "DOSSIE.md")
            if situacao == "pronto" and not self.antes:      # retomada: parte veio do cache no meio da etapa — estragaria a média
                self._aprender(tempos or [])
            self.gravar()
            self.ok = False
            if isinstance(sys.stdout, _Tee):
                sys.stdout = sys.stdout.orig
        except Exception:
            pass

    def _aprender(self, tempos):
        """só aprende com etapa que MEDIU de verdade (reaproveitar do cache leva 0 s e estragaria a média)"""
        mins = max(0.05, self.d.get("minutos") or 0)
        medidas = {}      # etapa -> quantas unidades foram feitas DE VERDADE agora (None = a etapa toda)
        for t in tempos:
            como = str(t.get("como", ""))
            m = re.match(r"Qwen: (\d+) chamada\(s\) agora, (\d+)", como)
            if como == "medido":
                medidas[t.get("etapa")] = None
            elif m and int(m.group(1)) > 0:     # parte veio do cache: o tempo é só das chamadas feitas agora
                medidas[t.get("etapa")] = (int(m.group(1)), int(m.group(1)) + int(m.group(2)))
        hist = _ler(HIST, {})
        for e in self.d["etapas"]:
            k = e["chave"]
            if e["estado"] != "feita" or not e.get("s"):
                continue
            real = k in medidas or (k == "cortes2" and "cortes3" in medidas) or (k in ("quadros", "dossie") and e["s"] > 0.5)
            if not real:
                continue
            feitas, total = medidas.get(k) or (None, None)
            s_inteira = e["s"] * total / feitas if feitas else e["s"]       # quanto levaria sem nada guardado
            ritmo = s_inteira / (max(0.05, self.d.get("minutos_video") or mins) if k in ("cortes", "cortes2") else mins)
            h = hist.setdefault(k, {"ultimos": []})
            h["ultimos"] = (h.get("ultimos", []) + [round(ritmo, 2)])[-5:]
            h["ritmo"] = round(sorted(h["ultimos"])[len(h["ultimos"]) // 2], 2)
            if k in POR_SHOT and self.d.get("shots") and not self._geracao_inteira(k):
                h["ultimos_por_shot"] = (h.get("ultimos_por_shot", []) + [round(e["s"] / (feitas or self.d["shots"]), 2)])[-5:]
                h["por_shot"] = round(sorted(h["ultimos_por_shot"])[len(h["ultimos_por_shot"]) // 2], 2)
        try:
            _gravar(HIST, hist)
        except Exception:
            pass
