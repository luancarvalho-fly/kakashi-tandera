# -*- coding: utf-8 -*-
"""PC CHECK do pacote Kakashi + Tandera (21/10/2026).

Olha a máquina (Windows ou Mac), diz o NÍVEL dela e, etapa por etapa, onde cada coisa roda:
LOCAL (no PC da pessoa), ARDI (pelos modelos da Fly, na conta ARDI dela) ou NÃO (não roda aqui).
Só lê o sistema: não instala nada, não usa a placa, não toca som.

Uso:  python pc_check.py              → mostra a tabela
      python pc_check.py --json x.json → também grava o perfil (o pacote lê ele pra escolher o motor de cada etapa)
      python pc_check.py --modo poupar|equilibrado|ardi   (padrão: equilibrado)
        poupar      = tudo que der local (gasta zero na ARDI, usa mais o PC)
        equilibrado = local o que o PC faz bem; ARDI no resto
        ardi        = só o leve fica local (gravar, medir cortes); o resto vai pela ARDI
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

def nivel(m):
    """N0 leve · N1 médio · N2 forte (os números de corte saíram do que já medimos na RTX 5070 12 GB; o resto é estimativa, ver PLANO)."""
    p, ram = m["placa"], m["ram_gb"]
    if p["tipo"] == "nvidia":
        v = p["vram_gb"] or 0
        if v >= 11.5 and ram >= 24: return "N2"
        if v >= 6: return "N1"
        return "N0"
    if p["tipo"] == "apple":
        if ram >= 32: return "N2"
        if ram >= 16: return "N1"
        return "N0"
    return "N0"

# Etapas do Kakashi e do Tandera. Pra cada uma: o que precisa pra rodar LOCAL por nível, e se a ARDI tem caminho.
#  local: nível mínimo pra rodar local ("N0" = qualquer PC); None = não roda local fora do PC de referência
#  ardi:  como vai pela ARDI ("" = não tem caminho pela ARDI hoje)
#  so:    sistemas onde existe local hoje ("win", "mac")
ETAPAS = [
    # KAKASHI
    ("kakashi", "gravar (tela + microfone + som do PC + mouse/janela)", "N0", "", ("win",),
     "leve (0,1–1% do PC, ~1,2 GB/h de disco no replay); no Mac falta escrever (ffmpeg avfoundation + ScreenCaptureKit + Acessibilidade)"),
    ("kakashi", "painel do Premiere (timeline, agulha, cliques)", "N0", "", ("win",), "servidor Python + painel; no Mac falta testar o painel"),
    ("kakashi", "transcrever a fala", "N1", "ARDI view_file (Whisper no fal; centavos; guarda a transcrição)", ("win", "mac"),
     "local: Whisper na placa (NVIDIA) ou whisper.cpp/MLX no Mac; N0 = só modelo pequeno, lento"),
    ("kakashi", "montar a LEITURA (fala × mouse × prints)", "N0", "", ("win", "mac"), "só Python, processador"),
    # TANDERA
    ("tandera", "cortes (AutoShot + TransNetV2 + diferença de pixel)", "N0", "", ("win", "mac"), "roda no processador (mais lento) ou na placa"),
    ("tandera", "separar voz / música / efeitos", "N2", "ARDI MVSEP (o mesmo do Autopilot, DnR v3)", ("win", "mac"),
     "local = Roformer → BandIt Plus (NVIDIA 12 GB; no processador ~25 min por episódio)"),
    ("tandera", "fala no milissegundo (texto + MMS na onda)", "N1", "ARDI: texto pelo Whisper do fal; o alinhamento MMS fica local (processador)", ("win", "mac"), ""),
    ("tandera", "batida da música (Beat This)", "N0", "", ("win", "mac"), "processador aguenta"),
    ("tandera", "entonação (Praat)", "N0", "", ("win", "mac"), "processador"),
    ("tandera", "texto na tela (PP-OCRv6)", "N0", "", ("win", "mac"), "processador"),
    ("tandera", "qual efeito da biblioteca (encaixe na onda)", "N0", "", ("win", "mac"), "processador; precisa da biblioteca da pessoa indexada"),
    ("tandera", "olho: ficha do shot (Qwen3-VL 8B local × Gemini Flash)", "N1", "ARDI Gemini Flash (9/10, o 1º lugar) — combinar com o Piloto como chamar", ("win", "mac"),
     "local = Qwen3-VL 8B no Ollama (7–7,5/10, o 2º lugar): NVIDIA 8 GB+ ou Mac 16 GB+"),
    ("tandera", "visão geral do vídeo inteiro", "", "ARDI view_file com a pergunta (o modelo vê e ouve o vídeo)", ("win", "mac"), "o Qwen não aguenta o vídeo inteiro"),
    ("tandera", "câmera (CoTracker3: a curva)", "N2", "", ("win",), "NVIDIA; no Mac/processador fica lento demais (a medir)"),
    ("tandera", "corpo (Sapiens2-1B, só cinemático de academia)", "N2", "", ("win",), "NVIDIA 12 GB; sem caminho na ARDI hoje"),
    ("tandera", "rosto / boca (OpenFace 3.0)", "N2", "", ("win",), "só Windows com WSL"),
]
ORDEM = {"N0": 0, "N1": 1, "N2": 2}

def decidir(m, modo):
    nv, so = m["nivel"], ("mac" if sys.platform == "darwin" else "win")
    linhas = []
    for app, nome, minimo, ardi, sistemas, obs in ETAPAS:
        pode_local = bool(minimo) and ORDEM[nv] >= ORDEM[minimo] and so in sistemas
        if nome.startswith("rosto") and not m.get("wsl"):
            pode_local = False
        if modo == "ardi":          # tudo que tem caminho pela ARDI vai pra ela; o resto fica local se der
            esc = "ARDI" if ardi else ("LOCAL" if pode_local else "NÃO")
        elif modo == "poupar":      # tudo que o PC aguenta fica local (zero gasto na ARDI)
            esc = "LOCAL" if pode_local else ("ARDI" if ardi else "NÃO")
        else:                       # equilibrado: o leve fica local; o pesado só fica local se o PC é forte (N2) ou passa folgado do mínimo
            folgado = pode_local and (minimo == "N0" or not ardi or nv == "N2" or ORDEM[nv] > ORDEM[minimo])
            esc = "LOCAL" if folgado else ("ARDI" if ardi else ("LOCAL" if pode_local else "NÃO"))
        linhas.append({"app": app, "etapa": nome, "onde": esc, "minimo_local": minimo or "—", "pela_ardi": ardi or "—", "obs": obs})
    return linhas

def main():
    modo = "equilibrado"
    if "--modo" in sys.argv:
        modo = sys.argv[sys.argv.index("--modo") + 1]
    nome_cpu, nucleos = cpu()
    m = {
        "sistema": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "cpu": nome_cpu, "nucleos": nucleos, "ram_gb": ram_gb(), "placa": placa(),
        "disco_livre_gb": disco_livre_gb(os.path.expanduser("~")),
        "ffmpeg": tem("ffmpeg"), "ollama": tem("ollama"), "python": platform.python_version(),
        "wsl": sys.platform == "win32" and tem("wsl"),
    }
    SIMULAR = {   # pra montar a tabela do PLANO sem ter a máquina na mão (não é medida)
        "notebook": ({"tipo": "outra", "nome": "Intel Iris (integrada)", "vram_gb": None}, 16, "win"),
        "nvidia8": ({"tipo": "nvidia", "nome": "RTX 4060 8 GB", "vram_gb": 8.0}, 32, "win"),
        "mac8": ({"tipo": "apple", "nome": "Apple M1 8 GB", "vram_gb": None}, 8, "mac"),
        "mac16": ({"tipo": "apple", "nome": "Apple M2 16 GB", "vram_gb": None}, 16, "mac"),
        "mac36": ({"tipo": "apple", "nome": "Apple M3 Pro 36 GB", "vram_gb": None}, 36, "mac"),
    }
    if "--simular" in sys.argv:
        k = sys.argv[sys.argv.index("--simular") + 1]
        m["placa"], m["ram_gb"], so_sim = SIMULAR[k]
        m["sistema"] = f"SIMULADO: {k}"
        m["wsl"] = False
        if so_sim == "mac":
            sys.platform = "darwin"   # só pra escolher as linhas de Mac; nada mais é lido daqui pra frente
    m["nivel"] = nivel(m)
    linhas = decidir(m, modo)
    nomes = {"N0": "N0 · LEVE (sem placa forte)", "N1": "N1 · MÉDIO", "N2": "N2 · FORTE"}
    p = m["placa"]
    print(f"\nPC CHECK — {m['sistema']}")
    print(f"  processador: {m['cpu']} ({m['nucleos']} núcleos) · RAM {m['ram_gb']} GB · disco livre {m['disco_livre_gb']} GB")
    print(f"  placa: {p['nome']}" + (f" · {p['vram_gb']} GB" if p.get("vram_gb") else (" · memória unificada" if p["tipo"] == "apple" else "")))
    print(f"  tem: ffmpeg {'sim' if m['ffmpeg'] else 'NÃO'} · ollama {'sim' if m['ollama'] else 'não'} · python {m['python']}"
          + (f" · WSL {'sim' if m['wsl'] else 'não'}" if sys.platform == "win32" else ""))
    print(f"\n  NÍVEL: {nomes[m['nivel']]}   ·   modo: {modo}\n")
    larg = max(len(l["etapa"]) for l in linhas)
    for app in ("kakashi", "tandera"):
        print(f"  {app.upper()}")
        for l in [x for x in linhas if x["app"] == app]:
            print(f"    {l['etapa']:<{larg}}  {l['onde']:<6} {('· ' + l['pela_ardi']) if l['onde'] == 'ARDI' else ''}")
        print()
    if not m["ffmpeg"]:
        print("  ⚠ falta o ffmpeg (o Kakashi e o Tandera precisam dele)")
    if "--json" in sys.argv:
        dest = sys.argv[sys.argv.index("--json") + 1]
        json.dump({"maquina": m, "modo": modo, "etapas": linhas}, open(dest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  perfil gravado em {dest}")

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
