# -*- coding: utf-8 -*-
"""TANDERA V2 (20/10/2026) — os OLHOS: quem descreve o shot e as imagens que vão pra ele.
  - OLHO LOCAL no Ollama = PADRÃO (local, grátis). Mesmos parâmetros do T1b: think falso, temperatura 0,15. Desde 23/10 o gemma4:12b
    (era o Qwen3-VL 8B instruct): no teste dos modelos (saidas\\t5_modelos\\RELATORIO-MODELOS-23-10.md) descreveu melhor (8 × 7 de 10), acertou a linha do tempo
    da ficha e viu a câmera fechar, mais rápido (6–13 s × 11–23 s por shot), mesma placa no pico (11,2 GB). Voltar = trocar QWEN abaixo.
  - Gemini 3.8 Flash GRÁTIS só quando pedido (--gemini): visão geral do vídeo inteiro e shot complexo. Cota de 20 pedidos/dia por
    modelo: agrupa shots num pedido e, no 429, passa pro próximo modelo Flash. Pago NUNCA (só modelo "flash", sem cartão).
    A chave (~\\.gemini\\chave-api.txt, de quem usa) é lida só na hora da chamada e nunca vai pra tela nem pra arquivo.
  - Imagens: quadro pelo número, com o tempo ESCRITO no quadro; ficha do elenco numa imagem só (foto + nome + altura);
    folha do shot com o cabeçalho "shot N · de X a Y · vídeo de Z"; tira de 13 quadros seguidos.
Prompts: os do T2 (saidas\\t2\\t2_rodar.py), com os quadros POR PLANO e a câmera tirada do modelo (quem diz a câmera é a CURVA)."""
import base64, glob, hashlib, json, os, re, time, urllib.error, urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OLLAMA = "http://localhost:11434/api"
QWEN = os.environ.get("TANDERA_OLHO") or "gemma4:12b"   # NOTEBOOK: o gemma4:12b (8 GB) não cabe aqui; TANDERA_OLHO escolhe outro                 # 23/10 (T5); antes: "qwen3-vl:8b-instruct" (o nome QWEN ficou: o resto da régua chama TO.QWEN)
QWEN_DO_OPENWHISPR = "qwen2.5:7b"
SEMENTE = 20261021
FONTE = r"C:\Windows\Fonts\arialbd.ttf"
CHAVE_GEMINI = os.path.join(os.path.expanduser("~"), ".gemini", "chave-api.txt")   # NOTEBOOK
API_G = "https://generativelanguage.googleapis.com"


def mmss(seg, casas=2):
    m = int(seg // 60); s = seg - 60 * m
    return f"{m}:{s:0{3 + casas}.{casas}f}"


def fonte(tam):
    return ImageFont.truetype(FONTE, tam)


def escrever(img, linhas, tam=20, onde=(6, 6)):
    d = ImageDraw.Draw(img); f = fonte(tam); x, y = onde
    for txt in linhas:
        l, t, r, b = d.textbbox((x, y), txt, font=f)
        d.rectangle([l - 4, t - 3, r + 4, b + 3], fill=(0, 0, 0)); d.text((x, y), txt, font=f, fill=(255, 255, 255)); y = b + 8
    return img


def b64(p):
    return base64.b64encode(open(p, "rb").read()).decode()


def hash_arqs(arqs, extra=""):
    h = hashlib.sha1(extra.encode("utf-8"))
    for a in arqs:
        h.update(open(a, "rb").read())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- imagens
def quadro_com_tempo(src, dst, rotulo, largura=512):
    """cópia do quadro na largura pedida, com o rótulo (número · tempo · quadro) escrito no canto"""
    if os.path.exists(dst):
        return dst
    im = Image.open(src).convert("RGB")
    im = im.resize((largura, max(2, int(round(im.size[1] * largura / im.size[0])))), Image.LANCZOS)
    tmp = dst[:-4] + f".parcial{os.getpid()}.jpg"        # T5: grava ao lado e troca — processo morto no meio não deixa jpg pela metade
    escrever(im, [rotulo], tam=max(14, largura // 26)).save(tmp, format="JPEG", quality=90)
    os.replace(tmp, dst)
    return dst


def ler_elenco(pasta):
    """--elenco <pasta>: cada imagem é um asset; o NOME vem do nome do arquivo e a ALTURA, se tiver, entre parênteses.
    Ex.: 'PLEXUS (1 m).jpg' · 'FERIADO a nave (10 m).png' · 'POLICIAL 1 - BARBOSA (1,60 m).jpg'. Sem parênteses = altura não escrita.
    Subpasta 'shot48' (ou 'shot_48') = assets só daquele shot; as imagens soltas valem pra todos."""
    if not pasta:
        return {}
    def ler(d):
        out = []
        for a in sorted(glob.glob(os.path.join(d, "*"))):
            if os.path.splitext(a)[1].lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            base = os.path.splitext(os.path.basename(a))[0].replace("_", " ").strip()
            m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", base)
            nome, alt = (m.group(1).strip(), m.group(2).strip()) if m else (base, "altura não escrita no asset")
            out.append({"arquivo": a, "nome": nome, "altura": alt})
        return out
    el = {"todos": ler(pasta)}
    for d in glob.glob(os.path.join(pasta, "*")):
        m = re.match(r"(?i)^shot[_ ]?(\d+)$", os.path.basename(d))
        if os.path.isdir(d) and m:
            el[int(m.group(1))] = ler(d)
    return el


def ficha_elenco(assets, dst, titulo="FICHA DO ELENCO — assets do shot (nome e altura)"):
    """TODOS os assets do shot numa imagem só: foto + nome + altura (como no T2)"""
    if not assets:
        return None
    alt_cel, leg = 300, 70
    ims = [(Image.open(a["arquivo"]).convert("RGB"), a["nome"], a["altura"]) for a in assets]
    cels = [im.resize((max(220, int(alt_cel * im.size[0] / im.size[1])), alt_cel), Image.LANCZOS) for im, _, _ in ims]
    largura = sum(c.size[0] for c in cels) + 10 * (len(cels) - 1)
    ficha = Image.new("RGB", (max(largura, 700), 40 + alt_cel + leg), (20, 20, 20)); d = ImageDraw.Draw(ficha)
    d.text((10, 8), titulo, font=fonte(22), fill=(255, 255, 255)); x = 0
    for c, (_, n, h) in zip(cels, ims):
        ficha.paste(c, (x, 40))
        d.text((x + 8, 40 + alt_cel + 6), n, font=fonte(22 if len(n) < 26 else 15), fill=(255, 220, 80))
        d.text((x + 8, 40 + alt_cel + 38), h, font=fonte(18), fill=(255, 255, 255)); x += c.size[0] + 10
    if ficha.size[0] > 1800:
        ficha = ficha.resize((1800, int(ficha.size[1] * 1800 / ficha.size[0])), Image.LANCZOS)
    os.makedirs(os.path.dirname(dst), exist_ok=True); ficha.save(dst, quality=90)
    return dst


def folha(cabecalho, quadros, dst, colunas=4, largura=392, rodape=None, curva=None):
    """folha pro olho: cabeçalho + quadros (já com o tempo escrito) em grade; embaixo, a curva da câmera (se tiver)"""
    ims = [Image.open(q).convert("RGB") for q in quadros if q and os.path.exists(q)]
    if not ims:
        return None
    ims = [i.resize((largura, max(2, int(i.size[1] * largura / i.size[0]))), Image.LANCZOS) for i in ims]
    h = max(i.size[1] for i in ims); cols = min(colunas, len(ims)); lin = (len(ims) + cols - 1) // cols
    alt_curva = 110 if curva else 0; alt_rod = 26 * len(rodape or [])
    W = cols * largura + (cols - 1) * 6; H = 44 + lin * (h + 6) + alt_curva + alt_rod + 6
    f = Image.new("RGB", (max(W, 600), H), (15, 15, 15)); d = ImageDraw.Draw(f)
    d.text((8, 8), cabecalho, font=fonte(24), fill=(255, 220, 80))
    for k, im in enumerate(ims):
        f.paste(im, ((k % cols) * (largura + 6), 44 + (k // cols) * (h + 6)))
    y = 44 + lin * (h + 6)
    if curva:
        _desenhar_curva(d, curva, 8, y + 4, max(W, 600) - 16, alt_curva - 10); y += alt_curva
    for r in rodape or []:
        d.text((8, y + 2), r, font=fonte(18), fill=(230, 230, 230)); y += 26
    os.makedirs(os.path.dirname(dst), exist_ok=True); f.save(dst, quality=88)
    return dst


def _desenhar_curva(d, curva, x0, y0, w, h):
    """a CURVA da câmera: deslocamento x (azul), y (verde) e escala (laranja), acumulados, no tempo do shot"""
    d.rectangle([x0, y0, x0 + w, y0 + h], outline=(80, 80, 80))
    d.text((x0 + 4, y0 + 2), "câmera (CoTracker3): x azul · y verde · escala laranja", font=fonte(14), fill=(200, 200, 200))
    qs = [c["q"] for c in curva]
    if len(qs) < 2:
        return
    q0, q1 = min(qs), max(qs)
    vals = np.array([[c["dx"], c["dy"], c["escala"]] for c in curva]); m = max(0.05, float(np.abs(vals).max()))
    for j, cor in enumerate([(90, 160, 255), (90, 220, 120), (255, 160, 60)]):
        pts = [(x0 + (c["q"] - q0) / max(1, q1 - q0) * w, y0 + h / 2 - vals[i, j] / m * (h / 2 - 8)) for i, c in enumerate(curva)]
        d.line(pts, fill=cor, width=2)


# ---------------------------------------------------------------- Ollama (Qwen3-VL)
def _post(rota, corpo, timeout=900):
    req = urllib.request.Request(f"{OLLAMA}/{rota}", data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def descarregar(modelo):
    try:
        _post("generate", {"model": modelo, "keep_alive": 0}, timeout=60)
        return True
    except Exception:
        return False


def carregados():
    try:
        with urllib.request.urlopen(f"{OLLAMA}/ps", timeout=20) as r:
            return [{"modelo": m["name"], "total_mib": m["size"] // 2 ** 20, "na_placa_mib": m.get("size_vram", 0) // 2 ** 20} for m in json.loads(r.read())["models"]]
    except Exception:
        return []


def sem_repeticao(texto):
    """o 8B às vezes entra em laço (T3: a linha ORDEM repetida 12 vezes): frase igual a uma já dita na mesma linha sai"""
    out = []
    for l in texto.splitlines():
        vistas, frases = set(), []
        for f in re.split(r"(?<=[.!?])\s+", l):
            k = re.sub(r"\W+", " ", f.lower()).strip()
            if k and k in vistas: continue
            vistas.add(k); frases.append(f)
        out.append(" ".join(frases))
    return "\n".join(out)


def qwen(texto, imagens=(), num_predict=700, num_ctx=None, temperatura=0.15):
    """uma chamada ao Qwen3-VL. Descarrega o qwen2.5:7b (o OpenWhispr usa ele) antes, pra ficar UM modelo só na placa."""
    descarregar(QWEN_DO_OPENWHISPR)
    if num_ctx is None:   # T3: o Ollama gasta ~1.100 tokens por imagem, qualquer tamanho; passar de 16k transborda da placa (13 quadros = 16k, 13 s no T1b)
        num_ctx = int(min(32768, max(8192, 4096 * np.ceil((len(texto) // 3 + 1100 * len(imagens) + num_predict + 200) / 4096))))
    t0 = time.time()
    # T5: semente fixa — com temperatura > 0 e sem semente, duas rodadas iguais já davam textos diferentes; com ela, a mesma entrada
    # dá a mesma resposta (pausar, liberar a placa e retomar não muda o que o Qwen escreve). Fora isso, os mesmos parâmetros do T1b.
    r = _post("generate", {"model": QWEN, "prompt": texto, "images": [b64(a) for a in imagens], "stream": False, "keep_alive": "5m", "think": False,
                           "options": {"temperature": temperatura, "num_predict": num_predict, "num_ctx": num_ctx, "repeat_penalty": 1.12, "seed": SEMENTE}},
              timeout=1800)
    return {"texto": sem_repeticao(r.get("response", "").strip()), "s": round(time.time() - t0, 1), "tokens_entrada": r.get("prompt_eval_count"),
            "tokens_saida": r.get("eval_count"), "num_ctx": num_ctx, "modelo": QWEN, "fim": r.get("done_reason")}


# ---------------------------------------------------------------- Gemini Flash GRÁTIS (só quando pedido)
def _chave():
    return open(CHAVE_GEMINI, encoding="utf-8").read().strip()


def modelos_flash():
    """os modelos Flash que a conta enxerga (pra revezar a cota de 20/dia por modelo). Nunca 'pro'."""
    try:
        req = urllib.request.Request(f"{API_G}/v1beta/models?pageSize=200", headers={"x-goog-api-key": _chave()})
        ms = json.load(urllib.request.urlopen(req, timeout=60)).get("models", [])
        nomes = [m["name"].split("/")[-1] for m in ms if "generateContent" in m.get("supportedGenerationMethods", [])]
        fl = [n for n in nomes if "flash" in n and "pro" not in n and "image" not in n and "tts" not in n and "live" not in n]
        return sorted(fl, key=lambda n: (n != "gemini-3.8-flash", n))
    except Exception:
        return ["gemini-3.8-flash"]


def gemini(partes, modelos=None, temperatura=0.15):
    """generateContent no Flash grátis. 503/500: tenta de novo. 429 (cota do dia do modelo): passa pro próximo Flash."""
    modelos = modelos or modelos_flash()
    corpo = json.dumps({"contents": [{"role": "user", "parts": partes}], "generationConfig": {"temperature": temperatura}}).encode()
    hist, t0 = [], time.time()
    for mod in modelos:
        for tent in range(4):
            req = urllib.request.Request(f"{API_G}/v1beta/models/{mod}:generateContent", data=corpo,
                                         headers={"Content-Type": "application/json", "x-goog-api-key": _chave()})
            try:
                j = json.load(urllib.request.urlopen(req, timeout=600))
                txt = "".join(p.get("text", "") for c in j.get("candidates", []) for p in c.get("content", {}).get("parts", []))
                return {"texto": txt.strip(), "s": round(time.time() - t0, 1), "uso": j.get("usageMetadata"), "modelo": mod, "erros_antes": hist}
            except urllib.error.HTTPError as e:
                hist.append(f"{mod}:{e.code}")
                if e.code in (429, 404, 400, 403): break      # cota do dia (429) ou modelo que não atende essa conta (404/400/403) → próximo modelo
                if e.code in (500, 503): time.sleep(20); continue
                return {"erro": e.code, "modelo": mod, "erros_antes": hist}
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                hist.append(f"{mod}:rede"); time.sleep(10)
    return {"erro": "cota/servidor", "erros_antes": hist}


def gemini_video(arq_mp4, pergunta):
    """sobe o vídeo (480p) na Files API, pergunta, e apaga o arquivo de lá no fim (como no T1, teste 2)"""
    def chamar(metodo, url, dados=None, cab=None):
        cab = dict(cab or {}); cab["x-goog-api-key"] = _chave()
        return urllib.request.urlopen(urllib.request.Request(url, data=dados, headers=cab, method=metodo), timeout=900)
    tam = os.path.getsize(arq_mp4)
    r = chamar("POST", f"{API_G}/upload/v1beta/files", json.dumps({"file": {"display_name": os.path.basename(arq_mp4)}}).encode(),
               {"X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "X-Goog-Upload-Header-Content-Length": str(tam),
                "X-Goog-Upload-Header-Content-Type": "video/mp4", "Content-Type": "application/json"})
    f = json.load(chamar("POST", r.headers["x-goog-upload-url"], open(arq_mp4, "rb").read(),
                         {"Content-Length": str(tam), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"}))["file"]
    try:
        while f.get("state") == "PROCESSING":
            time.sleep(10); f = json.load(chamar("GET", f"{API_G}/v1beta/{f['name']}"))
        return gemini([{"file_data": {"mime_type": "video/mp4", "file_uri": f["uri"]}}, {"text": pergunta}])
    finally:
        try: chamar("DELETE", f"{API_G}/v1beta/{f['name']}")
        except Exception: pass


# ---------------------------------------------------------------- prompts
def prompt_ficha(cab, n_quadros, tem_ficha, trecho=None, falas=None, um_shot_montado=False):
    """o prompt do T2 (mesma ordem e regras), com os quadros POR PLANO e sem a câmera (quem diz a câmera é a curva medida)"""
    rot = (f"\n\nTRECHO DO ROTEIRO (o que o diretor pediu; o vídeo pode cobrir só parte dele):\n\"\"\"\n{trecho}\n\"\"\"") if trecho else ""
    fal = (f"\n\nFALA MEDIDA NO ÁUDIO deste trecho (Whisper + MMS; serve só pra saber QUANDO alguém fala, não QUEM):\n{falas}") if falas else ""
    if tem_ficha:
        nomes = ("Use o NOME de quem está na ficha. Quem não está na ficha: se o roteiro dá o nome e o traço bate, use o nome do roteiro; "
                 "senão descreva a aparência sem inventar nome.") if trecho else "Use o NOME de quem está na ficha. Quem não está na ficha: descreva a aparência, sem inventar nome."
        abre = "A 1ª imagem é a FICHA DO ELENCO: foto, NOME e ALTURA dos assets ligados a este shot.\n"
        resto = f"As {n_quadros} imagens seguintes"
    else:
        nomes = "Quem não for reconhecível: descreva a aparência, sem inventar nome."
        abre = ""; resto = f"As {n_quadros} imagens"
    checa = ("\n5. ROTEIRO × VÍDEO — SHOT por SHOT do trecho do roteiro: o que o vídeo entrega (com o tempo), o que FALTA e o que veio "
             "DIFERENTE do pedido. Só escreva 'entrega' do que você VÊ nos quadros; cada parte do pedido conta (ex.: 'gato pula a cerca' "
             "sem cerca = FALTA a cerca). Ignore falas e efeitos sonoros do roteiro: você não ouve o som.") if trecho else ""
    plano = ("todas do mesmo plano (do começo ao fim dele)" if um_shot_montado else
             "tiradas POR PLANO: 2 ou 3 de cada plano (o começo, o meio e o fim de cada um), inclusive dos planos curtos")
    return f"""{cab}

{abre}{resto} são QUADROS EM ORDEM deste shot, {plano}. Cada quadro tem o número, o tempo e o quadro escritos no canto
(ex.: "3 · 0:02.29 · q55" = imagem 3, aos 2,29 s, quadro 55).{rot}{fal}

Responda em português, nesta ordem, com estes títulos (seja curto: cada seção uma vez só, sem repetir):
1. DESCRIÇÃO — UM parágrafo de 3 a 5 frases: enquadramento (e se muda), QUEM está no quadro, a ação do começo ao fim, efeitos visuais, lugar e luz.
2. QUEM ESTÁ ONDE — uma linha por personagem: nome, posição no quadro (esquerda/centro/direita, frente/fundo) e de que tempo a que tempo aparece.
3. QUEM FALA — quem parece estar falando (boca aberta ou mexendo) e em que tempo. Você não ouve o som: diga só o que dá para ver.
4. LINHA DO TEMPO — os planos, um por linha: "de X a Y — o que é", com os tempos escritos nos quadros.{checa}

Regras: {nomes} Descreva SÓ o que está nos quadros, não invente. Não fale do movimento de câmera (ele é medido à parte). Cite os tempos como estão escritos nos quadros."""


def prompt_leve(cab, tem_ficha):
    f = "A 1ª imagem é a FICHA DO ELENCO (foto, nome e altura). A 2ª é " if tem_ficha else "A imagem é "
    return (f"{cab}\n{f}um quadro do meio deste shot. Em UMA frase, em português: enquadramento, QUEM está (pelo nome, se estiver na ficha), "
            "a ação, o lugar e a luz. Não invente. Não fale de câmera.")


def prompt_tira(cab, n, o_que):
    return (f"{cab}\nAs {n} imagens são {n} QUADROS SEGUIDOS (sem pular nenhum), cada um com o número (1 a {n}), o tempo e o quadro escritos no canto.\n"
            f"No som, neste trecho, entra: {o_que}. Em qual quadro exato acontece, NA IMAGEM, o acontecimento que esse som marca (impacto, clarão, "
            "batida, explosão, o objeto encostando)? Se nada na imagem combina, responda 'NENHUM'.\n"
            "Responda assim, em português: 'QUADRO <número> · <tempo>' na 1ª linha; na 2ª, uma frase curta dizendo o que muda nesse quadro.")


def prompt_plano_ver(cab_plano, n_quadros, tem_ficha):
    """traçado, passo 1 (T3): só OLHAR um plano — sem o roteiro na frente, pra não copiar"""
    abre = "A 1ª imagem é a FICHA DO ELENCO (foto, nome e altura). " if tem_ficha else ""
    return (f"{cab_plano}\n{abre}As {n_quadros} imagens {'seguintes ' if tem_ficha else ''}são quadros de UM plano só (começo, meio e fim), com o tempo escrito no canto.\n"
            "Em português, em 2 frases: o enquadramento no começo e no fim (aberto, médio, close), QUEM está (pelo nome da ficha), o que cada um faz e o que "
            "passa pelo quadro — inclusive coisas borradas ou rápidas (veículo passando, objeto voando). Não fale de câmera. Não invente.")


def prompt_plano_casar(planos_txt, shots_roteiro):
    """traçado, passo 2 (T3): casar o que foi visto com os SHOTs do roteiro — só texto, pergunta fechada"""
    lista = "\n".join(f"SHOT {s}: {t}" for s, t in shots_roteiro)
    vis = "\n".join(f"PLANO {i}: {t}" for i, t in planos_txt)
    return f"""Uma geração de vídeo de IA foi cortada em planos. Abaixo, o que se VÊ em cada plano e os SHOTS que o roteiro pedia.

O QUE SE VÊ:
{vis}

O ROTEIRO PEDIA (na ordem):
{lista}

Para CADA plano, uma linha exatamente assim: PLANO <n> = SHOT <número> | FALTA: <parte do pedido desse shot que não está no que se vê, ou nada>
Se o plano mostra dois shots seguidos (ex.: começa aberto e termina num close pedido por outro shot), escreva os dois: PLANO <n> = SHOT <a>+<b> | FALTA: ...
Se o plano não corresponde a nenhum shot: PLANO <n> = NENHUM | FALTA: nada
Regras: compare o enquadramento (close × aberto), quem está e a ação. Um shot pode não aparecer em plano nenhum. Não invente."""


def marcar_conferir(texto):
    """todo 'FALTA' e todo 'boca aberta = fala' sai marcado (receita do Plexus, T2)"""
    out = []; em_quem_fala = False
    for l in texto.splitlines():
        if re.match(r"^\s*(\*\*)?\s*\d\.\s*", l):
            em_quem_fala = bool(re.search(r"(?i)quem fala", l))
        alvo = re.search(r"(?i)\bfalta|não aparece|nao aparece|ausente|boca|falando|fala\b|falar|articul", l) or (em_quem_fala and l.strip() and not re.match(r"^\s*(\*\*)?\s*\d\.", l))
        out.append(l + ("  ⚠ conferir no olho" if alvo and "conferir no olho" not in l else ""))
    return "\n".join(out)
