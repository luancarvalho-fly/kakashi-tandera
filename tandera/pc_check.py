# -*- coding: utf-8 -*-
"""PC CHECK do pacote Kakashi + Tandera (21/10/2026; números do Windows trocados pelos MEDIDOS em 27/10).

Olha a máquina e diz o NÍVEL dela e, etapa por etapa, onde cada coisa roda:
  LOCAL  = no PC da pessoa
  ARDI   = pela conta ARDI dela (quem chama é o Claude, pelas ferramentas da ARDI)
  LIMITE = roda no PC, mas sem folga: só com tudo fechado e com o OK da pessoa (o instalador não liga sozinho)
  NÃO    = não roda aqui
Só lê o sistema: não instala nada, não usa a placa, não toca som.

Uso:  python pc_check.py               → mostra a tabela
      python pc_check.py --json x.json → também grava o perfil (os instaladores leem: o do Tandera escolhe o que baixar e o config.json)
      python pc_check.py --sem-ardi    → a pessoa não tem conta na ARDI: o que só ia pela ARDI vira NÃO (ou fica no PC, devagar)
      python pc_check.py --simular notebook|nvidia4|nvidia8|nvidia12|sem-placa|mac8|mac16|mac36   → a tabela de outra máquina
      python pc_check.py --modo poupar|equilibrado|ardi   (padrão: equilibrado)
        poupar      = tudo que der local (gasta zero na ARDI, usa mais o PC)
        equilibrado = local o que o PC faz bem; ARDI no resto
        ardi        = só o leve fica local (gravar, medir cortes); o resto vai pela ARDI
        No TANDERA o LOCAL sempre vence quando o PC aguenta: a medida local é mais precisa (a fala no ms, por exemplo).

De onde vêm os números do Windows: o teste no notebook (i5-11400H, RTX 3050 Laptop 4 GB, 7,7 GB de RAM; veredito e sabotador de
26/10) e o PC de referência (RTX 5070 12 GB). Os níveis (por RAM + placa NVIDIA):
  N0 LEVE  = sem NVIDIA de 4 GB, ou menos de 16 GB de RAM → cortes (AutoShot), quadros, texto na tela, cor
  N1 MÉDIO = NVIDIA ≥ 4 GB e RAM ≥ 16 GB → + separação na placa, fala no ms, entonação, batida/música, 2ª opinião de corte
  N2 FORTE = NVIDIA ≥ 12 GB e RAM ≥ 24 GB → + câmera (CoTracker3) e o olho local (gemma4:12b, 8 GB de placa, com o Ollama)
  NVIDIA de 4 GB com pouca RAM (o notebook): separação e fala rodam NO LIMITE (medido: 56 s pra 21 s de vídeo; a RAM bateu 97 % na
  carga do modelo da fala). Separação no PROCESSADOR: proibida em PC fraco (não foi medida: o notebook caiu no começo desse teste).
  O "16 GB" do N1 é o degrau acima do notebook (7,7 GB = no limite): estimado, não medido. O "24 GB" do N2 é o do PC de referência.
O Mac fica como estava (a versão do Mac é do Piloto: ele termina).
"""
import json, os, platform, re, shutil, subprocess, sys

def rodar(cmd, t=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t, encoding="utf-8", errors="replace")
        return r.stdout.strip()
    except Exception:
        return ""

def ram_gb():
    if sys.platform == "win32":
        import ctypes
        class M(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = M(); m.dwLength = ctypes.sizeof(M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round(m.ullTotalPhys / 2**30, 1)
    if sys.platform == "darwin":
        v = rodar(["sysctl", "-n", "hw.memsize"])
        return round(int(v) / 2**30, 1) if v.isdigit() else 0
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except Exception:
        return 0

def cpu():
    if sys.platform == "darwin":
        nome = rodar(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor()
    elif sys.platform == "win32":
        nome = rodar(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor | Select-Object -First 1).Name"]) or platform.processor()
    else:
        nome = platform.processor()
    return nome.strip(), os.cpu_count() or 0

def placa():
    """NVIDIA pelo nvidia-smi; Mac Apple Silicon = memória unificada (a 'VRAM' é parte da RAM)."""
    out = rodar(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if out:
        nome, mem = [x.strip() for x in out.splitlines()[0].split(",")[:2]]
        return {"tipo": "nvidia", "nome": nome, "vram_gb": round(float(mem) / 1024, 1)}
    if sys.platform == "darwin" and platform.machine() == "arm64":
        chip = rodar(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon"
        return {"tipo": "apple", "nome": chip, "vram_gb": None}   # usa a RAM (memória unificada)
    if sys.platform == "win32":
        nome = rodar(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name"])
        return {"tipo": "outra", "nome": nome or "?", "vram_gb": None}
    return {"tipo": "nenhuma", "nome": "?", "vram_gb": None}

def disco_livre_gb(p):
    try:
        return round(shutil.disk_usage(p).free / 2**30, 1)
    except Exception:
        return 0

def tem(cmd):
    return shutil.which(cmd) is not None

# limiares (o Windows mostra um pouco menos que o nominal: placa de 4 GB = 4,0; 12 GB = 11,9; RAM de 16 GB = 15,7; 8 GB = 7,7)
VRAM_N1, VRAM_N2, RAM_N1, RAM_N2 = 3.5, 11.5, 15, 23

def nvidia4(m):
    p = m["placa"]
    return p["tipo"] == "nvidia" and (p["vram_gb"] or 0) >= VRAM_N1

def nivel(m):
    """N0 leve · N1 médio · N2 forte. Windows: placa NVIDIA + RAM, pelos números medidos (ver o topo). Mac: como estava."""
    p, ram = m["placa"], m["ram_gb"]
    if p["tipo"] == "nvidia":
        v = p["vram_gb"] or 0
        if v >= VRAM_N2 and ram >= RAM_N2: return "N2"
        if v >= VRAM_N1 and ram >= RAM_N1: return "N1"
        return "N0"
    if p["tipo"] == "apple":
        if ram >= 32: return "N2"
        if ram >= 16: return "N1"
        return "N0"
    return "N0"

# Etapas do Kakashi e do Tandera. Pra cada uma: o que precisa pra rodar LOCAL por nível, e se a ARDI tem caminho.
#  local: nível mínimo pra rodar local ("N0" = qualquer PC); "" = não roda local; None = não vem no pacote da Fly
#  ardi:  como vai pela ARDI ("" = não tem caminho pela ARDI hoje)
#  so:    sistemas onde existe local hoje ("win", "mac")
#  chave: o nome da etapa no tandera.py (o instalador do Tandera monta o config.json por ela)
ETAPAS = [
    # KAKASHI
    ("kakashi", "gravar (tela + microfone + som do PC + mouse/janela)", "N0", "", ("win",),
     "leve (0,1–1% do PC, ~1,2 GB/h de disco no replay); no Mac falta escrever (ffmpeg avfoundation + ScreenCaptureKit + Acessibilidade)", ""),
    ("kakashi", "painel do Premiere (timeline, agulha, cliques)", "N0", "", ("win",), "servidor Python + painel; no Mac falta testar o painel", ""),
    ("kakashi", "transcrever a fala", "N1", "ARDI view_file (Whisper no fal; centavos; guarda a transcrição)", ("win", "mac"),
     "local: Whisper na placa (NVIDIA) ou whisper.cpp/MLX no Mac; N0 = só modelo pequeno, lento", ""),
    ("kakashi", "montar a LEITURA (fala × mouse × prints)", "N0", "", ("win", "mac"), "só Python, processador", ""),
    # TANDERA (medido no notebook e no PC de referência, 26–27/10)
    ("tandera", "cortes (AutoShot)", "N0", "", ("win",), "processador; 3–6 s num vídeo curto, 0,4–0,8 GB de RAM", "cortes"),
    ("tandera", "2ª opinião de corte (TransNetV2 + diferença de pixel)", "N1", "", ("win",),
     "na placa ~5 s, mas prende ~1,1 GB de RAM até o fim: em PC fraco fica de fora (o AutoShot sozinho deu os mesmos cortes do PC forte)", "cortes2"),
    ("tandera", "quadros + texto na tela (PP-OCRv6)", "N0", "", ("win",), "processador; ~1,4 s por quadro (tela de tutorial ~5,8 s)", "texto"),
    ("tandera", "cor por shot", "N0", "", ("win",), "processador; ~3 s", "cor"),
    ("tandera", "separar voz / música / efeitos (Roformer → BandIt Plus)", "N1", "", ("win",),
     "só na placa NVIDIA (~3 GB de placa; 56 s pra 21 s de vídeo); no processador é proibido em PC fraco (não medido: o notebook caiu)", "separacao"),
    ("tandera", "fala no milissegundo (faster-whisper large-v3 + MMS + onda)", "N1",
     "ARDI: o Claude transcreve pela sua conta (upload_file + view_file): texto com o tempo da frase, sem o ms de cada palavra", ("win",),
     "precisa da separação antes; na placa 23 s pra 25 s de fala; a RAM bateu 97 % na carga do modelo (notebook de 7,7 GB)", "fala"),
    ("tandera", "entonação (Praat)", "N1", "", ("win",), "leve (0,2 s), mas precisa da fala medida no PC", "entonacao"),
    ("tandera", "batida + grade + música (Beat This)", "N1", "", ("win",), "leve (0,3 GB de placa), mas precisa da separação antes", "batida"),
    ("tandera", "câmera (CoTracker3: a curva)", "N2", "", ("win",),
     "não coube em 4 GB do jeito que o Tandera chama hoje (48 quadros × 512 px por shot); medido só na NVIDIA de 12 GB", "camera"),
    ("tandera", "olho local: ficha do shot (gemma4:12b no Ollama)", "N2",
     "ARDI: o Claude mostra as folhas dos shots pela sua conta (view_file), com a pergunta da pessoa", ("win",),
     "8 GB de placa; precisa do Ollama instalado", "olho"),
    ("tandera", "visão geral do vídeo inteiro", "", "ARDI: view_file com o vídeo e a pergunta (o modelo vê e ouve)", ("win",),
     "nenhum modelo local aguenta o vídeo inteiro", "visao_modelo"),
    ("tandera", "corpo (Sapiens2-1B)", None, "", ("win",), "fica no PC do Luan: não vem no pacote da Fly (7,5 GB de placa)", "corpo"),
    ("tandera", "rosto / boca (OpenFace 3.0)", None, "", ("win",), "fica no PC do Luan: não vem no pacote da Fly (precisa de WSL)", "rosto"),
    ("tandera", "qual efeito da biblioteca (encaixe na onda)", None, "", ("win",),
     "fica no PC do Luan: precisa da biblioteca de efeitos dele indexada (não vem no pacote)", "efeitos"),
]
ORDEM = {"N0": 0, "N1": 1, "N2": 2}
NO_LIMITE = {"separacao", "fala", "entonacao", "batida"}     # o que a NVIDIA de 4 GB com pouca RAM roda sem folga (veredito de 26/10)

def decidir(m, modo, tem_ardi=True):
    nv, so = m["nivel"], ("mac" if sys.platform == "darwin" else "win")
    linhas = []
    for app, nome, minimo, ardi, sistemas, obs, chave in ETAPAS:
        ardi = ardi if tem_ardi else ""
        pode_local = bool(minimo) and ORDEM[nv] >= ORDEM[minimo] and so in sistemas
        if nome.startswith("rosto") and not m.get("wsl"):
            pode_local = False
        if chave == "olho" and pode_local and not m.get("ollama"):
            pode_local = False; obs += " — este PC não tem o Ollama (ollama.com)"
        if app == "tandera":
            if so == "mac":
                esc, obs = "NÃO", "Mac: o Piloto termina"
            elif pode_local:          # no Tandera o local sempre vence: é a medida precisa
                esc = "LOCAL"
            elif chave in NO_LIMITE and nv == "N0" and nvidia4(m):
                esc = "LIMITE"
            else:
                esc = "ARDI" if ardi else "NÃO"
        elif not tem_ardi and minimo and so in sistemas and not pode_local:
            esc = "LOCAL"; obs += " · sem ARDI: roda no processador, devagar"
        elif modo == "ardi":        # tudo que tem caminho pela ARDI vai pra ela; o resto fica local se der
            esc = "ARDI" if ardi else ("LOCAL" if pode_local else "NÃO")
        elif modo == "poupar":      # tudo que o PC aguenta fica local (zero gasto na ARDI)
            esc = "LOCAL" if pode_local else ("ARDI" if ardi else "NÃO")
        else:                       # equilibrado: o leve fica local; o pesado só fica local se o PC é forte (N2) ou passa folgado do mínimo
            folgado = pode_local and (minimo == "N0" or not ardi or nv == "N2" or ORDEM[nv] > ORDEM[minimo])
            esc = "LOCAL" if folgado else ("ARDI" if ardi else ("LOCAL" if pode_local else "NÃO"))
        minimo_txt = "não vem no pacote" if minimo is None else (minimo or "—")
        linhas.append({"app": app, "etapa": nome, "chave": chave, "onde": esc, "minimo_local": minimo_txt, "pela_ardi": ardi or "—", "obs": obs})
    return linhas

SIMULAR = {   # pra montar a tabela de outra máquina sem ter ela na mão ("notebook" = a máquina MEDIDA em 26/10)
    "notebook": ({"tipo": "nvidia", "nome": "RTX 3050 Laptop 4 GB (o notebook medido em 26/10)", "vram_gb": 4.0}, 7.7, "win"),
    "nvidia4": ({"tipo": "nvidia", "nome": "NVIDIA 4 GB", "vram_gb": 4.0}, 16, "win"),
    "nvidia8": ({"tipo": "nvidia", "nome": "RTX 4060 8 GB", "vram_gb": 8.0}, 32, "win"),
    "nvidia12": ({"tipo": "nvidia", "nome": "RTX 5070 12 GB (o PC de referência)", "vram_gb": 11.9}, 32, "win"),
    "sem-placa": ({"tipo": "outra", "nome": "Intel Iris (integrada)", "vram_gb": None}, 16, "win"),
    "mac8": ({"tipo": "apple", "nome": "Apple M1 8 GB", "vram_gb": None}, 8, "mac"),
    "mac16": ({"tipo": "apple", "nome": "Apple M2 16 GB", "vram_gb": None}, 16, "mac"),
    "mac36": ({"tipo": "apple", "nome": "Apple M3 Pro 36 GB", "vram_gb": None}, 36, "mac"),
}

def main():
    modo = "equilibrado"
    if "--modo" in sys.argv:
        modo = sys.argv[sys.argv.index("--modo") + 1]
    tem_ardi = "--sem-ardi" not in sys.argv
    nome_cpu, nucleos = cpu()
    m = {
        "sistema": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpu": nome_cpu, "nucleos": nucleos, "ram_gb": ram_gb(), "placa": placa(),
        "disco_livre_gb": disco_livre_gb(os.path.expanduser("~")),
        "ffmpeg": tem("ffmpeg"), "ollama": tem("ollama"), "python": platform.python_version(),
        "wsl": sys.platform == "win32" and tem("wsl"),
    }
    if "--simular" in sys.argv:
        k = sys.argv[sys.argv.index("--simular") + 1]
        if k not in SIMULAR:
            sys.exit("--simular: use um destes: " + ", ".join(SIMULAR))
        m["placa"], m["ram_gb"], so_sim = SIMULAR[k]
        m["sistema"] = f"SIMULADO: {k}"
        m["wsl"] = False
        if so_sim == "mac":
            sys.platform = "darwin"   # só pra escolher as linhas de Mac; nada mais é lido daqui pra frente
    m["nivel"] = nivel(m)
    linhas = decidir(m, modo, tem_ardi)
    nomes = {"N0": "N0 · LEVE", "N1": "N1 · MÉDIO", "N2": "N2 · FORTE"}
    p = m["placa"]
    print(f"\nPC CHECK — {m['sistema']}")
    print(f"  processador: {m['cpu']} ({m['nucleos']} núcleos) · RAM {m['ram_gb']} GB · disco livre {m['disco_livre_gb']} GB")
    print(f"  placa: {p['nome']}" + (f" · {p['vram_gb']} GB" if p.get("vram_gb") else (" · memória unificada" if p["tipo"] == "apple" else "")))
    print(f"  tem: ffmpeg {'sim' if m['ffmpeg'] else 'NÃO'} · ollama {'sim' if m['ollama'] else 'não'} · python {m['python']}"
          + (f" · WSL {'sim' if m['wsl'] else 'não'}" if sys.platform == "win32" else ""))
    print(f"\n  NÍVEL: {nomes[m['nivel']]}   ·   modo: {modo}" + ("" if tem_ardi else "   ·   SEM conta ARDI"))
    print("  LOCAL = roda no seu PC · ARDI = vai pela sua conta ARDI (o Claude faz) · LIMITE = roda, mas sem folga (só com tudo"
          " fechado e o seu OK) · NÃO = não roda aqui\n")
    larg = max(len(l["etapa"]) for l in linhas)
    for app in ("kakashi", "tandera"):
        print(f"  {app.upper()}")
        for l in [x for x in linhas if x["app"] == app]:
            extra = ("· " + l["pela_ardi"]) if l["onde"] == "ARDI" else (("· " + l["obs"]) if l["onde"] in ("NÃO", "LIMITE") and app == "tandera" else "")
            print(f"    {l['etapa']:<{larg}}  {l['onde']:<6} {extra}")
        print()
    if not m["ffmpeg"]:
        print("  ⚠ falta o ffmpeg (o Kakashi e o Tandera precisam dele)")
    if "--json" in sys.argv:
        dest = sys.argv[sys.argv.index("--json") + 1]
        with open(dest, "w", encoding="utf-8") as f:
            json.dump({"maquina": m, "modo": modo, "tem_ardi": tem_ardi, "etapas": linhas,
                       "tandera": {l["chave"]: l["onde"] for l in linhas if l["app"] == "tandera"}}, f, ensure_ascii=False, indent=1)
        print(f"  perfil gravado em {dest}")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
