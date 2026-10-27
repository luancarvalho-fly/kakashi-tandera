# -*- coding: utf-8 -*-
"""TANDERA da Fly (Windows): a análise de vídeo. Instala pra ESTE usuário, sem administrador. Rodar de novo = atualiza (o que já foi
baixado não baixa de novo; o cache, as análises, as suas receitas e o config ficam).

  py -3 instalar.py                     → mostra o PC check, diz quantos GB vai baixar e pergunta antes de começar
  py -3 instalar.py --sem-perguntas     → instala o que o PC aguenta, sem perguntar nada (é o que o Instalar.bat usa)
  py -3 instalar.py --so-tamanho        → só diz quantos GB vai baixar neste PC, e sai
  py -3 instalar.py --sem-ardi          → pra quem não tem conta na ARDI (o PC check marca o que fica de fora)
  py -3 instalar.py --com-limite        → NVIDIA de 4 GB com pouca RAM: instala também a separação e a fala (rodam NO LIMITE)
  py -3 instalar.py --nivel N0|N1       → instala como se o PC fosse mais fraco (baixa menos; serve pra teste)
  py -3 instalar.py --trocar-skill      → troca uma /tandera que NÃO veio deste pacote (a antiga é guardada, não apagada)
  py -3 instalar.py --desinstalar       → tira a skill, os programas e os modelos; as análises, as suas receitas e o cache ficam
Teste (não mexe na skill): py -3 instalar.py --destino <pasta de teste> --sem-perguntas --sem-skill

O que faz: copia pra %LOCALAPPDATA%\\Programs\\Tandera-Fly; roda o PC check (perfil.json); instala o uv (pip, num ambiente de apoio) e,
com ele, o Python 3.12 e os 3 ambientes (.venv principal, .venv-sep da separação, venv-ler do texto na tela) com o torch certo pro PC
(NVIDIA com etapa na placa → cu128; senão → o do processador, 3 GB a menos); baixa SÓ os modelos que o nível do PC usa, das fontes
oficiais (MODELOS.md); escreve o config.json (o que fica desligado neste PC); instala a skill /tandera no Claude Code. É Python, não
.ps1: o PowerShell com "-ExecutionPolicy Bypass" é barrado pela trava do modo automático do Claude Code (lição do Kakashi, 27/10).
"""
import argparse, datetime, hashlib, json, os, shutil, subprocess, sys, tempfile, time, urllib.request, zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SEM_JANELA = 0x08000000
MARCA_SKILL = ".tandera-fly"        # a skill /tandera instalada por ESTE pacote (nunca troca uma /tandera de outra origem)
DADOS = {"analises", "cache", "estado", "minhas-receitas", "config.json", "perfil.json"}          # da pessoa: nunca apaga
AMBIENTES = {".venv", ".venv-sep", "venv-ler", ".python", ".uv-cache", ".apoio"}                 # criados aqui (não vêm no zip)
NAO_COPIAR = DADOS | AMBIENTES | {"__pycache__"}
OLHOS = ["ficha", "descricao", "descricao_leve", "tiras", "tracado", "roteiro_previsto"]        # etapas do olho local (Ollama)
FORA_DO_PACOTE = ["corpo", "rosto", "efeitos", "tiras"]                                          # ficam no PC do Luan
TORCH_IDX = "https://download.pytorch.org/whl/"
HF = "https://huggingface.co/"
GH = "https://github.com/"

# Downloads. Modelos: tamanho EXATO da fonte (bytes) e sha256 quando a fonte publica (conferidos em 27/10; MODELOS.md).
# Pacotes do Python: o uv não diz o tamanho antes, então é ESTIMATIVA. Medido na instalação de teste de 27/10 (torch do processador):
# Python 21 MB, venv-ler ~84 MB, principal ~350 MB (o torch do processador = 109 MB). O torch da placa (cu128) e o .venv-sep NÃO foram
# medidos (passavam do teto de 5 GB do teste): o torch cu128 do Windows tem ~3 GB. No disco, o pacote ocupa ~3× o que baixa (o uv guarda
# tudo descompactado no .uv-cache; os ambientes são links pra ele, não ocupam de novo).
GB = 2**30
PACOTES_GB = {"python": 0.03, "uv": 0.02, "ler": 0.09, "principal_cpu": 0.40, "principal_cu128": 3.4, "sep": 0.45}
OCR = [("PaddlePaddle/PP-OCRv6_medium_det_onnx", "61323801669c338b7891481ec7bac61ce31b576a", "inference.onnx", "PP-OCRv6_medium_det.onnx",
        62032837, "eb13b44b25bb36f89528b68720af8a61d9cf381176107f465db1757b65d086e1"),
       ("PaddlePaddle/PP-OCRv6_medium_rec_onnx", "50c7eacafc52fa7bcf4194e8cd08e46f8558504b", "inference.onnx", "PP-OCRv6_medium_rec.onnx",
        76554979, "9c09abf0957f7968c7586464b7397b84ad2387a0497a351af40e9acc71b673ba"),
       ("PaddlePaddle/PP-OCRv6_medium_rec_onnx", "50c7eacafc52fa7bcf4194e8cd08e46f8558504b", "inference.yml", "inference_rec_v6.yml", 150580, None)]
DIC_SHA = "769e7fa79bb297b5f18d8dbd149e364a45bc61f2b3f574e5ea836f0b261c23a6"      # dict_v6.txt (sai do inference.yml, em CRLF)
WHISPER = ("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478",
           [("model.bin", 3087284237, "69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1"), ("config.json", 2394, None),
            ("tokenizer.json", 2480617, None), ("vocabulary.json", 1068114, None), ("preprocessor_config.json", 340, None)])
MMS = ("https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt", 1262047414)
ROFORMER = ("model_bs_roformer_ep_317_sdr_12.9755.ckpt", 639331213)
BANDIT = (GH + "ZFTurbo/Music-Source-Separation-Training/releases/download/v.1.0.3/model_bandit_plus_dnr_sdr_11.47.chpt", 148891175,
          "c48284779f7d1258a6527d3aaa18a532d45c1f506e2dcc25d5ab179a8c5e2573")
MSST = (GH + "ZFTurbo/Music-Source-Separation-Training/archive/2ba884c2083070c4061fb2d5e3afc41e32420b8a.zip", "inference.py")
BEAT_THIS = GH + "CPJKU/beat_this/archive/b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c.zip"
COTRACKER = (HF + "facebook/cotracker3/resolve/bf55ea50d4390e1820a267f131cd6587240fb2c5/scaled_offline.pth", 101890938,
             "2670d4562ed69326dda775a26e54883925cd11b6fc9b24cb7aa9f8078bce7834")
COTRACKER_COD = (GH + "facebookresearch/co-tracker/archive/82e02e8029753ad4ef13cf06be7f4fc5facdda4d.zip", "hubconf.py")
GEMMA = ("gemma4:12b", 8021618699)


def p(*partes):
    return os.path.join(*partes)


def gb(b):
    return ("%.1f" % (b / GB)).replace(".", ",")


def tam(b):
    return ("%d MB" % max(1, round(b / 2**20))) if b < 0.1 * GB else gb(b) + " GB"


def titulo(t):
    print("\n-- %s" % t, flush=True)


def rodar(cmd, env=None, cwd=None, mostrar=True):
    """roda e PARA com a mensagem se der erro (nada fica pela metade sem aviso)"""
    if mostrar:
        print("   $ " + " ".join('"%s"' % c if " " in str(c) else str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], env=env, cwd=cwd)
    if r.returncode != 0:
        sys.exit("\nERRO: o passo acima falhou (código %d). Nada foi apagado: rode o instalador de novo (ele continua de onde parou).\n"
                 "Se falhar de novo, mande esta janela (print) pro Luan." % r.returncode)


def ler_json(arq):
    try:
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def gravar_json(arq, d):
    with open(arq, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def sha_arq(arq):
    h = hashlib.sha256()
    with open(arq, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def baixar(url, dest, nome, tamanho=None, sha=None):
    """baixa com progresso e RETOMA de onde parou (o .parcial fica); confere o tamanho e, se a fonte publica, o sha256"""
    if os.path.isfile(dest) and (not tamanho or os.path.getsize(dest) == tamanho):
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    parcial = dest + ".parcial"
    for tentativa in range(1, 4):
        ja = os.path.getsize(parcial) if os.path.isfile(parcial) else 0
        cab = {"User-Agent": "tandera-fly-instalar"}
        if ja:
            cab["Range"] = "bytes=%d-" % ja
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=60) as r:
                if ja and r.status != 206:
                    ja = 0                                          # o servidor não retoma: começa de novo
                total = (int(r.headers.get("Content-Length") or 0) + ja) or tamanho or 0
                t0, ultimo, feito = time.time(), 0.0, ja
                with open(parcial, "ab" if ja else "wb") as f:
                    for bloco in iter(lambda: r.read(1 << 20), b""):
                        f.write(bloco); feito += len(bloco)
                        if time.time() - ultimo > 10:
                            ultimo = time.time()
                            pct = (" %d%%" % (100 * feito / total)) if total else ""
                            print("     %s:%s (%s de %s GB)" % (nome, pct, gb(feito), gb(total) if total else "?"), flush=True)
            break
        except Exception as e:
            print("     %s: a conexão caiu (%s); tentativa %d de 3" % (nome, str(e)[:80], tentativa), flush=True)
            time.sleep(5 * tentativa)
    else:
        sys.exit("\nERRO: não consegui baixar %s de %s.\nConfira a internet e rode o instalador de novo (ele continua de onde parou)." % (nome, url))
    if tamanho and os.path.getsize(parcial) != tamanho:
        os.remove(parcial)
        sys.exit("\nERRO: %s veio com tamanho errado (a fonte mudou?). Rode de novo; se repetir, avise o Luan." % nome)
    if sha and sha_arq(parcial) != sha:
        os.remove(parcial)
        sys.exit("\nERRO: %s veio diferente do conferido (sha256). Rode de novo; se repetir, avise o Luan." % nome)
    os.replace(parcial, dest)
    print("     %s: pronto (%s GB)" % (nome, gb(os.path.getsize(dest))), flush=True)
    return True


def baixar_codigo(url, alvo, conferir, nome):
    """código de terceiros num commit FIXO do GitHub (o mesmo testado): baixa o .zip e extrai em alvo\\ (sem a pasta de cima)"""
    if os.path.isfile(p(alvo, conferir)):
        return
    tmp = tempfile.mkdtemp(prefix="tandera-cod-")
    zp = p(tmp, "cod.zip")
    baixar(url, zp, nome)
    with zipfile.ZipFile(zp) as z:
        z.extractall(tmp)
    raiz = next(p(tmp, d) for d in os.listdir(tmp) if os.path.isdir(p(tmp, d)))
    os.makedirs(alvo, exist_ok=True)
    for n in os.listdir(raiz):
        s, d = p(raiz, n), p(alvo, n)
        if os.path.isdir(d):
            shutil.rmtree(d)
        shutil.move(s, d)
    shutil.rmtree(tmp, ignore_errors=True)
    if not os.path.isfile(p(alvo, conferir)):
        sys.exit("ERRO: o código de %s veio sem %s." % (nome, conferir))


def pc_check(dest, sem_ardi, mostrar):
    """roda o pc_check.py (só LÊ o PC) e devolve o perfil"""
    arq = p(tempfile.gettempdir(), "tandera-fly-perfil-%d.json" % os.getpid())
    cmd = [sys.executable, p(AQUI, "pc_check.py"), "--json", arq] + (["--sem-ardi"] if sem_ardi else [])
    r = subprocess.run(cmd, capture_output=not mostrar, text=True, encoding="utf-8", errors="replace")
    perfil = ler_json(arq)
    if r.returncode != 0 or not perfil:
        sys.exit("ERRO: o PC check não rodou: %s" % ((r.stderr or "")[-400:] if not mostrar else ""))
    os.remove(arq)
    return perfil


def montar_plano(perfil, nivel_max, com_limite):
    """o que fica LOCAL neste PC (pelo PC check), o torch e o config"""
    onde = perfil["tandera"]
    local = {k for k, v in onde.items() if v == "LOCAL" or (com_limite and v == "LIMITE")}
    if nivel_max == "N0":
        local &= {"cortes", "texto", "cor"}
    elif nivel_max == "N1":
        local -= {"camera", "olho"}
    placa = perfil["maquina"]["placa"]
    vram = placa.get("vram_gb") or 0
    na_placa = bool(local & {"cortes2", "separacao", "fala", "batida", "camera"}) and placa["tipo"] == "nvidia"
    return {"local": local, "na_placa": na_placa, "torch": "cu128" if na_placa else "cpu", "vram": vram,
            "nivel": perfil["maquina"]["nivel"] if not nivel_max else min(perfil["maquina"]["nivel"], nivel_max)}


def tem_gemma():
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
        return GEMMA[0] in r.stdout
    except Exception:
        return False


def itens(plano, dest):
    """(o que, bytes que ainda faltam baixar) — o que já está na pasta não conta"""
    L, venv_ok = plano["local"], lambda d: os.path.isfile(p(dest, d, "Scripts", "python.exe"))
    torch_atual = ler_json(p(dest, "config.json")).get("torch")
    out = [("Python 3.12 (o Tandera tem o dele, separado do seu)", 0 if os.path.isdir(p(dest, ".python")) else PACOTES_GB["python"] * GB),
           ("uv (instala o Python e os pacotes)", 0 if os.path.isfile(p(dest, ".apoio", "Scripts", "uv.exe")) else PACOTES_GB["uv"] * GB),
           ("pacotes do texto na tela (venv-ler)", 0 if venv_ok("venv-ler") else PACOTES_GB["ler"] * GB),
           ("pacotes principais + torch %s" % ("da placa NVIDIA (cu128)" if plano["torch"] == "cu128" else "do processador"),
            0 if venv_ok(".venv") and torch_atual == plano["torch"] else PACOTES_GB["principal_" + plano["torch"]] * GB)]
    falta = lambda arq, b: 0 if os.path.isfile(p(dest, *arq.split("/"))) else b
    out.append(("modelos do texto na tela (PP-OCRv6, %s MB)" % 139, sum(falta("modelos/ocr/" + d, b) for _, _, _, d, b, _ in OCR[:2]) + OCR[2][4] * (0 if os.path.isfile(p(dest, "modelos", "ocr", "dict_v6.txt")) else 1)))
    if "separacao" in L:
        out += [("pacotes da separação (.venv-sep)", 0 if venv_ok(".venv-sep") else PACOTES_GB["sep"] * GB),
                ("separação: Roformer (voz)", falta("modelos/audio-separator/" + ROFORMER[0], ROFORMER[1])),
                ("separação: BandIt Plus (música × efeitos) + código", falta("separador-cinema/modelos-teste/bandit_plus/model_bandit_plus_dnr_sdr_11.47.chpt", BANDIT[1]) + 3 * 2**20)]
    if "fala" in L:
        out += [("fala: faster-whisper large-v3", sum(falta("modelos/faster-whisper-large-v3/" + n, b) for n, b, _ in WHISPER[2])),
                ("fala: MMS (a palavra no milissegundo)", falta("modelos/torch/hub/checkpoints/model.pt", MMS[1]))]
    if "camera" in L:
        out.append(("câmera: CoTracker3 + código", falta("modelos/cotracker3/scaled_offline.pth", COTRACKER[1]) + (0 if os.path.isfile(p(dest, "repos", "co-tracker", "hubconf.py")) else 16 * 2**20)))
    if "olho" in L:
        out.append(("olho local: gemma4:12b (pelo Ollama)", 0 if tem_gemma() else GEMMA[1]))
    return out


NOMES = {"cortes": "cortes", "cortes2": "2ª opinião de corte", "texto": "texto na tela", "cor": "cor", "separacao": "separação de voz/música/efeitos",
         "fala": "fala no milissegundo", "entonacao": "entonação", "batida": "batida e música", "camera": "câmera", "olho": "olho local (ficha do shot)",
         "visao_modelo": "visão geral do vídeo inteiro", "corpo": "corpo", "rosto": "rosto/boca", "efeitos": "qual efeito da biblioteca"}


def resumo_fora(perfil, plano):
    """o que este PC NÃO roda no Tandera, em português simples (pra pessoa e pro Claude)"""
    linhas = []
    for l in perfil["etapas"]:
        if l["app"] != "tandera" or l["chave"] in plano["local"]:
            continue
        nome = NOMES.get(l["chave"], l["etapa"])
        if l["onde"] == "ARDI":
            linhas.append("%s → pela sua conta ARDI (o Claude faz)" % nome)
        elif l["onde"] == "LIMITE":
            linhas.append("%s → roda NO LIMITE neste PC: ficou desligado (pra ligar: instalar.py --com-limite, com tudo fechado)" % nome)
        elif l["onde"] == "LOCAL":
            linhas.append("%s → desligado nesta instalação (--nivel)" % nome)
        else:
            linhas.append("%s → não roda aqui (%s)" % (nome, l["obs"]))
    return linhas


def variaveis(plano):
    """o config.json: o que roda e o que fica desligado neste PC (o tandera.py do pacote lê ele)"""
    L = plano["local"]
    pular = []
    if "cortes2" not in L:
        pular.append("cortes2")
    if "separacao" not in L:
        pular += ["separacao", "fala", "entonacao", "batida", "grade", "musica"]
    if "fala" not in L:
        pular += ["fala", "entonacao"]
    if "batida" not in L:
        pular += ["batida", "grade", "musica"]
    if "camera" not in L:
        pular.append("camera")
    if "olho" not in L:
        pular += OLHOS
    pular += FORA_DO_PACOTE
    v = {"TANDERA_PULAR": ",".join(dict.fromkeys(pular)), "TORCH_HOME": "{pasta}\\modelos\\torch"}
    if "olho" in L:
        v["TANDERA_OLHO"] = GEMMA[0]
    if "separacao" in L:
        v["AUDIO_SEPARATOR_MODEL_DIR"] = "{pasta}\\modelos\\audio-separator"
    if "fala" in L:
        v["REGUA_WHISPER"] = "{pasta}\\modelos\\faster-whisper-large-v3"
        if plano["vram"] < 8:
            v["REGUA_WHISPER_TIPO"] = "int8_float16"          # o que coube nos 4 GB do notebook (2,2 GB de placa)
    if plano["na_placa"] and plano["vram"] < 8:
        v["REGUA_PLACA_FRACAO"] = "0.85"                      # placa pequena: o torch para com erro em vez de transbordar pra RAM
    return v


def rodando(dest):
    """processos Python que rodam DESTA pasta (um Tandera analisando agora).
    27/10 (sessão principal): o instalador NÃO conta. Rodando pelo .venv (a atualização usa o Python do Kakashi), o Windows abre 2
    processos com a mesma linha de comando (o lançador do venv + o Python de verdade): excluir só o próprio pid achava o lançador e
    dizia «O Tandera está rodando agora» sem análise nenhuma, e a atualização pulava o Tandera."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*' + '%s' + '*' "
                            "-and $_.CommandLine -notlike '*instalar.py*' } | ForEach-Object { $_.ProcessId }" % dest.replace("'", "''")],
                           capture_output=True, text=True, timeout=60, creationflags=SEM_JANELA)
        return [x for x in r.stdout.split() if x.isdigit() and int(x) != os.getpid()]
    except Exception:
        return []


def copiar(dest):
    os.makedirs(dest, exist_ok=True)
    for raiz, dirs, arqs in os.walk(AQUI):
        rel = os.path.relpath(raiz, AQUI)
        dirs[:] = [d for d in dirs if not (rel == "." and d in NAO_COPIAR) and d != "__pycache__"]
        os.makedirs(p(dest, rel), exist_ok=True)
        for a in arqs:
            if rel == "." and a in NAO_COPIAR:
                continue
            if a.endswith(".parcial"):
                continue
            s, d = p(raiz, a), p(dest, rel, a)
            if os.path.isfile(d) and os.path.getsize(d) == os.path.getsize(s) and a.endswith((".onnx", ".ckpt", ".pth", ".chpt")):
                continue                                        # modelo grande igual: não copia de novo
            shutil.copy2(s, d)
    for d in ("analises", "cache", "minhas-receitas"):
        os.makedirs(p(dest, d), exist_ok=True)


def requisitos_principal(dest, torch):
    """o venv-principal.txt é o da placa (cu128); sem placa, o mesmo com o torch do processador"""
    txt = open(p(dest, "requisitos", "venv-principal.txt"), encoding="utf-8").read()
    if torch == "cpu":
        txt = txt.replace("+cu128", "+cpu")
    arq = p(dest, "requisitos", "_principal_%s.txt" % torch)
    with open(arq, "w", encoding="utf-8") as f:
        f.write(txt)
    return arq


def instalar_ambientes(dest, plano):
    env = dict(os.environ, UV_CACHE_DIR=p(dest, ".uv-cache"), UV_PYTHON_INSTALL_DIR=p(dest, ".python"), UV_PYTHON_PREFERENCE="only-managed",
               UV_LINK_MODE="hardlink")
    titulo("1/4 · o instalador de pacotes (uv) e o Python 3.12 do Tandera")
    apoio = p(dest, ".apoio"); uv = p(apoio, "Scripts", "uv.exe")
    if not os.path.isfile(uv):
        if not os.path.isfile(p(apoio, "Scripts", "python.exe")):
            rodar([sys.executable, "-m", "venv", apoio])
        rodar([p(apoio, "Scripts", "python.exe"), "-m", "pip", "install", "-q", "--disable-pip-version-check", "uv"])
    # --no-bin e --no-registry: NADA fora da pasta (sem eles o uv põe um python3.12.exe em ~\.local\bin e registra o Python no Windows,
    # e o "py -3.12" da pessoa passaria a achar o do Tandera; visto no teste de 27/10)
    rodar([uv, "python", "install", "3.12", "--no-bin", "--no-registry"], env=env)
    py = lambda d: p(dest, d, "Scripts", "python.exe")
    titulo("2/4 · os ambientes (os pacotes do Python; o maior é o torch)")
    print("   texto na tela (venv-ler)...", flush=True)
    if not os.path.isfile(py("venv-ler")):
        rodar([uv, "venv", p(dest, "venv-ler"), "--python", "3.12"], env=env)
    rodar([uv, "pip", "install", "--python", py("venv-ler"), "-r", p(dest, "requisitos", "venv-ler.txt")], env=env)
    print("   principal (.venv), com o torch %s..." % ("da placa (cu128)" if plano["torch"] == "cu128" else "do processador"), flush=True)
    if not os.path.isfile(py(".venv")):
        rodar([uv, "venv", p(dest, ".venv"), "--python", "3.12"], env=env)
    rodar([uv, "pip", "install", "--python", py(".venv"), "-r", requisitos_principal(dest, plano["torch"]),
           "--extra-index-url", TORCH_IDX + plano["torch"], "--index-strategy", "unsafe-best-match"], env=env)
    if "batida" in plano["local"]:
        rodar([uv, "pip", "install", "--python", py(".venv"), "--no-deps", "beat-this @ " + BEAT_THIS], env=env)
    if "separacao" in plano["local"]:
        print("   separação (.venv-sep)...", flush=True)
        if not os.path.isfile(py(".venv-sep")):
            rodar([uv, "venv", p(dest, ".venv-sep"), "--python", "3.12"], env=env)
        rodar([uv, "pip", "install", "--python", py(".venv-sep"), "-r", p(dest, "requisitos", "venv-sep.txt"),
               "--extra-index-url", TORCH_IDX + "cu128", "--index-strategy", "unsafe-best-match"], env=env)


def instalar_modelos(dest, plano):
    L = plano["local"]
    titulo("3/4 · os modelos (só os que este PC usa; das fontes oficiais, ver MODELOS.md)")
    m = p(dest, "modelos")
    print("   cortes: AutoShot (veio no pacote)", flush=True)
    for repo, commit, arq, nome, b, sha in OCR:
        baixar(HF + "%s/resolve/%s/%s" % (repo, commit, arq), p(m, "ocr", nome), "texto na tela: " + nome, b, sha)
    dic = p(m, "ocr", "dict_v6.txt")
    if not os.path.isfile(dic) or sha_arq(dic) != DIC_SHA:       # o dicionário do v6 = a lista character_dict do inference.yml oficial
        rodar([p(dest, "venv-ler", "Scripts", "python.exe"), "-c",
               "import sys, yaml; y = yaml.safe_load(open(sys.argv[1], encoding='utf-8')); "
               "open(sys.argv[2], 'wb').write(('\\r\\n'.join(y['PostProcess']['character_dict']) + '\\r\\n').encode('utf-8'))",
               p(m, "ocr", "inference_rec_v6.yml"), dic], mostrar=False)
        if sha_arq(dic) != DIC_SHA:
            sys.exit("ERRO: o dicionário do texto na tela não saiu igual ao conferido. Avise o Luan.")
    if "separacao" in L:
        pasta_sep = p(m, "audio-separator"); os.makedirs(pasta_sep, exist_ok=True)
        if not os.path.isfile(p(pasta_sep, ROFORMER[0])):
            print("   separação: Roformer (%s GB, do repositório de modelos do UVR)..." % gb(ROFORMER[1]), flush=True)
            rodar([p(dest, ".venv-sep", "Scripts", "audio-separator.exe"), "--download_model_only", "-m", ROFORMER[0], "--model_file_dir", pasta_sep])
        baixar(BANDIT[0], p(dest, "separador-cinema", "modelos-teste", "bandit_plus", "model_bandit_plus_dnr_sdr_11.47.chpt"),
               "separação: BandIt Plus", BANDIT[1], BANDIT[2])
        baixar_codigo(MSST[0], p(dest, "separador-cinema", "msst"), MSST[1], "separação: código do BandIt (MSST)")
    if "fala" in L:
        repo, commit, arqs = WHISPER
        for n, b, sha in arqs:
            baixar(HF + "%s/resolve/%s/%s" % (repo, commit, n), p(m, "faster-whisper-large-v3", n), "fala: faster-whisper " + n, b, sha)
        baixar(MMS[0], p(m, "torch", "hub", "checkpoints", "model.pt"), "fala: MMS", MMS[1])
    if "camera" in L:
        baixar(COTRACKER[0], p(m, "cotracker3", "scaled_offline.pth"), "câmera: CoTracker3", COTRACKER[1], COTRACKER[2])
        baixar_codigo(COTRACKER_COD[0], p(dest, "repos", "co-tracker"), COTRACKER_COD[1], "câmera: código do CoTracker3")
    if "olho" in L and not tem_gemma():
        print("   olho local: gemma4:12b pelo Ollama (%s GB)..." % gb(GEMMA[1]), flush=True)
        rodar(["ollama", "pull", GEMMA[0]])


def conferir(dest, plano):
    """liga cada ambiente e importa o que o Tandera usa (não toca a placa: só pergunta se ela existe)"""
    titulo("4/4 · conferindo")
    ok = True
    testes = [("principal", p(dest, ".venv", "Scripts", "python.exe"),
               "import numpy, cv2, onnxruntime, PIL, soundfile, librosa, scipy, torch; print('torch', torch.__version__, '· placa:', torch.cuda.is_available())"),
              ("texto na tela", p(dest, "venv-ler", "Scripts", "python.exe"), "import rapidocr_onnxruntime; print('rapidocr ok')")]
    if "separacao" in plano["local"]:
        testes.append(("separação", p(dest, ".venv-sep", "Scripts", "python.exe"), "import audio_separator, torch; print('audio-separator ok · placa:', torch.cuda.is_available())"))
    if "batida" in plano["local"]:
        testes.append(("batida", p(dest, ".venv", "Scripts", "python.exe"), "import beat_this.inference; print('beat_this ok')"))
    for nome, py, cod in testes:
        r = subprocess.run([py, "-c", cod], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, TORCH_HOME=p(dest, "modelos", "torch")))
        ok &= r.returncode == 0
        print("   %-14s %s" % (nome, (r.stdout.strip() or "ok") if r.returncode == 0 else "FALHOU: " + r.stderr.strip()[-300:]), flush=True)
    return ok


def instalar_skill(dest, trocar):
    alvo = p(os.path.expanduser("~"), ".claude", "skills", "tandera")
    if os.path.isdir(alvo) and not os.path.exists(p(alvo, MARCA_SKILL)):
        if not trocar:
            print("  SKILL: já existe uma /tandera neste Claude Code que NÃO veio deste pacote: deixei como está.\n"
                  "         Pra trocar pela do pacote: rode de novo com --trocar-skill (a antiga vai pra tandera.antiga-<data>).")
            return False
        shutil.move(alvo, alvo + ".antiga-" + datetime.datetime.now().strftime("%Y%m%d-%H%M"))
    elif os.path.isdir(alvo):
        shutil.rmtree(alvo)                                     # a nossa: troca inteira (as receitas da pessoa moram em minhas-receitas\)
    shutil.copytree(p(dest, "skill"), alvo, ignore=shutil.ignore_patterns("__pycache__"))
    with open(p(alvo, MARCA_SKILL), "w", encoding="utf-8") as f:
        f.write(dest + "\n")
    return True


def desinstalar(dest):
    if rodando(dest):
        sys.exit("O Tandera está rodando agora (uma análise). Espere acabar e rode de novo.")
    alvo = p(os.path.expanduser("~"), ".claude", "skills", "tandera")
    marca = p(alvo, MARCA_SKILL)
    if os.path.exists(marca) and os.path.normcase(open(marca, encoding="utf-8").read().strip()) == os.path.normcase(dest):
        shutil.rmtree(alvo); print("Skill /tandera removida.")      # só a desta instalação (outra pasta do pacote fica com a dela)
    if os.path.isdir(dest):
        for n in os.listdir(dest):
            if n in DADOS:
                continue
            q = p(dest, n)
            shutil.rmtree(q, ignore_errors=True) if os.path.isdir(q) else os.remove(q)
    print("Programas e modelos do Tandera removidos. Ficaram (são seus): %s\nApague a pasta à mão se quiser: %s"
          % (", ".join(sorted(n for n in DADOS if os.path.exists(p(dest, n)))) or "nada", dest))


def main():
    ap = argparse.ArgumentParser(description="instala o TANDERA da Fly (Windows)")
    ap.add_argument("--destino", default=p(os.environ.get("LOCALAPPDATA", ""), "Programs", "Tandera-Fly"))
    ap.add_argument("--sem-perguntas", action="store_true"); ap.add_argument("--so-tamanho", action="store_true")
    ap.add_argument("--sem-skill", action="store_true"); ap.add_argument("--trocar-skill", action="store_true")
    ap.add_argument("--sem-ardi", action="store_true"); ap.add_argument("--com-limite", action="store_true")
    ap.add_argument("--nivel", choices=["N0", "N1"], default=""); ap.add_argument("--desinstalar", action="store_true")
    a = ap.parse_args()
    dest = os.path.abspath(a.destino)
    if sys.platform != "win32":
        sys.exit("Este pacote é pra Windows. A versão do Mac está com o Piloto.")
    if sys.version_info < (3, 10):
        sys.exit("Precisa do Python 3.10 ou mais novo pra rodar o instalador. Dois cliques no Instalar.bat resolve.")
    if a.desinstalar:
        return desinstalar(dest)
    if os.path.normcase(dest) == os.path.normcase(AQUI):
        sys.exit("Rode o instalador da pasta extraída do zip, não da pasta onde ele instala.")
    links = p(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links")
    if links not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + links      # onde o winget põe o ffmpeg
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        sys.exit("Falta o ffmpeg. Dois cliques no Instalar.bat instala ele (ou: winget install Gyan.FFmpeg) e rode de novo.")

    # 27/10 (sessão principal): a ATUALIZAÇÃO (instalar_tudo.py --atualizar) roda isto de novo sem opções; sem lembrar as escolhas de
    # antes, quem instalou leve (--nivel N0) ia receber o nível cheio do PC e baixar ~9 GB sem ninguém pedir. Repete o que foi escolhido.
    anterior = ler_json(p(dest, "config.json")) or {}
    esc = anterior.get("escolhas") or {}
    if not a.nivel:
        a.nivel = esc.get("nivel") or (anterior.get("nivel") if anterior.get("nivel") in ("N0", "N1") and "escolhas" not in anterior else "")
    a.com_limite = a.com_limite or bool(esc.get("com_limite"))
    a.sem_ardi = a.sem_ardi or bool(esc.get("sem_ardi"))
    perfil = pc_check(dest, a.sem_ardi, mostrar=not (a.so_tamanho or a.sem_perguntas))
    plano = montar_plano(perfil, a.nivel, a.com_limite)
    lista = itens(plano, dest)
    total = sum(b for _, b in lista)
    livre = shutil.disk_usage(os.path.splitdrive(dest)[0] + "\\").free
    pacotes = sum(b for n, b in lista if n.startswith(("Python", "uv", "pacotes")))
    precisa = 3 * pacotes + 1.1 * (total - pacotes) + 1 * GB          # pacotes ~3× descompactados; modelos ~1×; 1 GB de folga
    placa = perfil["maquina"]["placa"]
    print("TANDERA · neste PC: nível %s%s%s · %s" % (perfil["maquina"]["nivel"], " (instalando como %s)" % plano["nivel"] if a.nivel else "",
                                                     " + o que roda no limite" if a.com_limite else "",
                                                     "placa %s (%s GB)" % (placa["nome"], placa["vram_gb"]) if placa.get("vram_gb") else "sem placa NVIDIA"), flush=True)
    print("  Vai baixar (só o que ainda falta nesta pasta):")
    for nome, b in lista:
        if b:
            print("    ~%8s  %s" % (tam(b), nome))
    print("  TOTAL: ~%s GB (os pacotes do Python são estimativa; os modelos, o tamanho exato da fonte) · disco: precisa de ~%s GB livres, tem %s GB"
          % (gb(total), gb(precisa), gb(livre)))
    fora = resumo_fora(perfil, plano)
    if fora:
        print("  Fica de fora neste PC:")
        for l in fora:
            print("    - " + l)
    if a.so_tamanho:
        return
    if livre < precisa:
        sys.exit("\nNão cabe: libere espaço no disco %s (precisa de ~%s GB livres) e rode de novo." % (os.path.splitdrive(dest)[0], gb(precisa)))
    if not a.sem_perguntas and input("\nInstalar o Tandera agora? Enter = sim · N = cancelar: ").strip().lower().startswith("n"):
        sys.exit("Cancelado. Nada foi instalado.")
    if rodando(dest):
        sys.exit("O Tandera está rodando agora (uma análise). Espere acabar e rode de novo.")
    print("\nTANDERA da Fly → %s" % dest, flush=True)
    copiar(dest)
    instalar_ambientes(dest, plano)
    instalar_modelos(dest, plano)
    c = ler_json(p(dest, "config.json")) or ler_json(p(AQUI, "config.json"))      # 1ª vez: o molde do pacote
    c.update({"_leia": "Escrito pelo instalar.py a partir do PC check (perfil.json). 'variaveis' é refeito a cada instalação; o que você "
                       "quiser fixar vai em 'minhas' (vence 'variaveis'). {pasta} = a pasta do Tandera.",
              "versao": open(p(dest, "VERSAO.txt"), encoding="utf-8").read().strip() if os.path.isfile(p(dest, "VERSAO.txt")) else "?",
              "instalado_em": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "nivel": plano["nivel"],
              "torch": plano["torch"], "sem_placa": not plano["na_placa"], "etapas_no_pc": sorted(plano["local"]),
              "escolhas": {"nivel": a.nivel, "com_limite": a.com_limite, "sem_ardi": a.sem_ardi},   # a atualização repete
              "variaveis": variaveis(plano)})
    c.setdefault("minhas", {})
    gravar_json(p(dest, "config.json"), c)
    gravar_json(p(dest, "perfil.json"), perfil)
    ok = conferir(dest, plano)
    skill_ok = False if a.sem_skill else instalar_skill(dest, a.trocar_skill)
    print("\nPRONTO%s. O Tandera está em %s" % ("" if ok else " (com AVISO: um ambiente não abriu, ver acima)", dest))
    print("  Roda neste PC: " + ", ".join(NOMES.get(k, k) for k in sorted(plano["local"])) + ".")
    for l in fora:
        print("  - " + l)
    print("  Usar: no Claude Code, digite /tandera e diga o vídeo (o caminho) e o que você quer saber dele."
          + ("" if skill_ok or a.sem_skill else " (a skill não foi instalada: ver o aviso acima)"))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    main()
