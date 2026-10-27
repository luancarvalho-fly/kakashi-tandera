# -*- coding: utf-8 -*-
"""KAKASHI da Fly (Windows) — instala pra ESTE usuário, sem administrador. Rodar de novo = atualiza (gravações, config e atalho ficam).

  py -3 instalar.py                          → instala com o atalho padrão (Ctrl+Page Down) ou o que já estava no config.json
  py -3 instalar.py --atalho "ctrl+alt+k"    → instala com o atalho que a pessoa escolheu (o atalho.py confere se vale e se está livre)
  py -3 instalar.py --transcricao local      → transcreve no próprio PC (quem não tem conta na ARDI); padrão: ardi
  py -3 instalar.py --sem-premiere           → não instala o painel do Premiere
  py -3 instalar.py --desinstalar            → tira atalhos, skill e painel; as gravações ficam
Teste (não liga nada, não cria atalho, não mexe na skill nem no Premiere):
  py -3 instalar.py --destino <pasta de teste> --sem-ligar --sem-skill --sem-premiere

O que faz: copia pra %LOCALAPPDATA%\\Programs\\Kakashi-Fly, cria um Python só dele (.venv) com o requirements.txt, põe o Kakashi pra ligar
com o Windows (Inicializar) + atalho "KAKASHI" na área de trabalho (a janelinha), instala o painel do Premiere (se tiver Premiere) e a
skill /kakashi no Claude Code, e roda o PC check. (27/10/2026: era um instalar.ps1; virou Python porque o PowerShell com
"-ExecutionPolicy Bypass" é barrado pela trava do modo automático do Claude Code.)
"""
import argparse, ctypes, datetime, json, os, shutil, subprocess, sys, tempfile, urllib.request, zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SEM_JANELA = 0x08000000
UPIA = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Common Files", "Adobe", "Adobe Desktop Common",
                    "RemoteComponents", "UPI", "UnifiedPluginInstallerAgent", "UnifiedPluginInstallerAgent.exe")
MARCA_SKILL = ".kakashi-fly"          # a skill /kakashi instalada por ESTE pacote (nunca troca uma skill /kakashi de outra origem)
NAO_COPIAR = {"sessoes", "__pycache__", ".venv"}      # o instalar.py vai junto: dali mesmo a pessoa desinstala (--desinstalar)
GUARDAR = {"config.json", "lidas.json", "perfil.json", os.path.join("premiere", "config.json")}   # de quem já usa: não sobrescreve


def ps(cmd):
    """PowerShell numa linha (-Command não esbarra na política de scripts)."""
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=SEM_JANELA)


def aspas(p):
    return "'" + str(p).replace("'", "''") + "'"


def status(porta):
    try:
        return json.load(urllib.request.urlopen("http://127.0.0.1:%d/status" % porta, timeout=2))
    except Exception:
        return None


def fechar_os_desta_pasta(dest):
    """fecha o Kakashi e o servidor do Premiere QUE RODAM DESTA PASTA (de outra pasta, nunca), conferindo antes se não estão gravando."""
    for porta, nome in ((7816, "Kakashi"), (7815, "painel do Premiere")):
        s = status(porta)
        if s and s.get("estado") in ("gravando", "pausado"):
            sys.exit("O %s está GRAVANDO. Conclua a gravação e rode de novo." % nome)
    ps("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | Where-Object { $_.CommandLine -like '*' + %s + '*' "
       "-and ($_.CommandLine -like '*kakashi.pyw*' -or $_.CommandLine -like '*servidor.py*') } | ForEach-Object { Stop-Process -Id "
       "$_.ProcessId -Force -ErrorAction SilentlyContinue }" % aspas(dest))


def atalho_lnk(lnk, alvo, args, pasta, icone):
    r = ps("$s = New-Object -ComObject WScript.Shell; $l = $s.CreateShortcut(%s); $l.TargetPath = %s; $l.Arguments = %s; "
           "$l.WorkingDirectory = %s; $l.IconLocation = %s; $l.Save()" % (aspas(lnk), aspas(alvo), aspas(args), aspas(pasta), aspas(icone)))
    if r.returncode != 0:
        print("  aviso: não consegui criar o atalho %s (%s)" % (lnk, r.stderr.strip()[:200]))


def pasta_especial(nome):
    return ps("[Environment]::GetFolderPath('%s')" % nome).stdout.strip()


def lnk_e_desta_pasta(lnk, dest):
    """o atalho .lnk aponta pra esta instalação? (o Kakashi do Luan tem atalhos com os MESMOS nomes: nunca mexer num que não é nosso)"""
    r = ps("$l = (New-Object -ComObject WScript.Shell).CreateShortcut(%s); $l.TargetPath + '|' + $l.Arguments + '|' + $l.WorkingDirectory" % aspas(lnk))
    return os.path.normcase(dest) in os.path.normcase(r.stdout)


def lugar_do_lnk(pasta, nome, dest):
    """onde gravar o atalho: o nome normal, ou «<nome> (Fly)» se já existe um com esse nome que é de outro Kakashi."""
    p = os.path.join(pasta, nome + ".lnk")
    if os.path.exists(p) and not lnk_e_desta_pasta(p, dest):
        return os.path.join(pasta, nome + " (Fly).lnk")
    return p


def lnks_desta_pasta(dest):
    out = []
    for pasta in (pasta_especial("Startup"), pasta_especial("Desktop")):
        for nome in ("Kakashi", "Kakashi (Premiere)", "KAKASHI"):
            for n in (nome + ".lnk", nome + " (Fly).lnk"):
                p = os.path.join(pasta, n)
                if os.path.exists(p) and lnk_e_desta_pasta(p, dest):
                    out.append(p)
    return out


def largura_da_tela():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    return int(ctypes.windll.user32.GetSystemMetrics(0)) or 1920


def copiar(dest):
    os.makedirs(dest, exist_ok=True)
    for raiz, dirs, arqs in os.walk(AQUI):
        rel = os.path.relpath(raiz, AQUI)
        dirs[:] = [d for d in dirs if d not in NAO_COPIAR]
        os.makedirs(os.path.join(dest, rel), exist_ok=True)
        for a in arqs:
            r = os.path.normpath(os.path.join(rel, a))
            if a in NAO_COPIAR or (r in GUARDAR and os.path.exists(os.path.join(dest, r))):
                continue
            shutil.copy2(os.path.join(raiz, a), os.path.join(dest, r))
    for s in ("sessoes", os.path.join("premiere", "sessoes")):
        os.makedirs(os.path.join(dest, s), exist_ok=True)


def ler_cfg(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def gravar_cfg(p, c):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)


def escolher_atalho(dest, pedido):
    sys.path.insert(0, dest)
    import atalho
    cfgp = os.path.join(dest, "config.json"); c = ler_cfg(cfgp)
    txt = pedido or c.get("atalho") or atalho.PADRAO
    try:
        a = atalho.ler(txt)
    except ValueError as e:
        sys.exit("O atalho «%s» não vale: %s. Rode de novo com --atalho \"ctrl+alt+k\" (ou outro)." % (txt, e))
    if not atalho.livre(a):
        if pedido:
            sys.exit("O atalho %s já é de outro programa neste PC. Escolha outro e rode de novo com --atalho." % a["nome"])
        print("  AVISO: %s já é de outro programa neste PC. Depois troque na janelinha do KAKASHI (TROCAR O ATALHO)." % a["nome"])
    c["atalho"] = a["texto"]; c.pop("atalho_cancelar", None); gravar_cfg(cfgp, c)
    cn = atalho.cancelar_de(a)
    return a["nome"], (cn["nome"] if cn else "botão direito no olho")


def montar_ccx(dest, ccx):
    """o .ccx é um zip com o manifest, o html, o js e os ícones (os mesmos arquivos que o "Atualizar CORRETOR no Premiere.bat" do Luan)."""
    painel = os.path.join(dest, "premiere", "painel")
    with zipfile.ZipFile(ccx, "w", zipfile.ZIP_DEFLATED) as z:
        for n in ("manifest.json", "index.html", "main.js"):
            z.write(os.path.join(painel, n), n)
        for raiz, _, arqs in os.walk(os.path.join(painel, "icones")):
            for a in arqs:
                if a.endswith(".png"):
                    p = os.path.join(raiz, a); z.write(p, os.path.relpath(p, painel).replace("\\", "/"))
    return ccx


def instalar_premiere(dest, ligar, pyw):
    if not os.path.isfile(UPIA):
        print("  Premiere: não achei o instalador de plugins da Adobe (Premiere não instalado?): o painel fica de fora.")
        return False
    ccx = montar_ccx(dest, os.path.join(tempfile.gettempdir(), "KAKASHI-Fly.ccx"))
    # desinstalar antes: com o mesmo id+versão o instalador da Adobe PULA a troca e ainda diz "Installation Successful" (lição do DUBX)
    subprocess.run([UPIA, "/remove", "KAKASHI"], capture_output=True, creationflags=SEM_JANELA)
    r = subprocess.run([UPIA, "/install", ccx], capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SEM_JANELA)
    if r.returncode != 0:
        print("  Premiere: a instalação do painel falhou (feche o Premiere e rode de novo):", (r.stdout + r.stderr).strip()[-300:])
        return False
    cfgp = os.path.join(dest, "premiere", "config.json"); c = ler_cfg(cfgp)
    if not c.get("_largura_conferida"):
        c["tela_largura"] = min(largura_da_tela(), 3840); c["_largura_conferida"] = True; gravar_cfg(cfgp, c)
    if ligar:
        startup = pasta_especial("Startup")
        atalho_lnk(lugar_do_lnk(startup, "Kakashi (Premiere)", dest), pyw, '"%s"' % os.path.join(dest, "premiere", "servidor.py"),
                   os.path.join(dest, "premiere"), os.path.join(dest, "kakashi.ico"))
        subprocess.Popen([pyw, os.path.join(dest, "premiere", "servidor.py")], cwd=os.path.join(dest, "premiere"),
                         env=dict(os.environ, PYTHONUTF8="1"), creationflags=SEM_JANELA)
    print("  Premiere: painel KAKASHI instalado (Janela > Extensões / Plugins > KAKASHI). Feche e abra o Premiere se ele estava aberto.")
    return True


def instalar_skill(dest, trocar):
    alvo = os.path.join(os.path.expanduser("~"), ".claude", "skills", "kakashi")
    if os.path.isdir(alvo) and not os.path.exists(os.path.join(alvo, MARCA_SKILL)):
        if not trocar:
            print("  SKILL: já existe uma /kakashi neste Claude Code que NÃO veio deste pacote: deixei como está.\n"
                  "         Pra trocar pela do pacote: rode de novo com --trocar-skill (a antiga vai pra kakashi.antiga-<data>).")
            return False
        shutil.move(alvo, alvo + ".antiga-" + datetime.datetime.now().strftime("%Y%m%d-%H%M"))
    os.makedirs(alvo, exist_ok=True)
    shutil.copy2(os.path.join(dest, "skill", "SKILL.md"), os.path.join(alvo, "SKILL.md"))
    open(os.path.join(alvo, MARCA_SKILL), "w", encoding="utf-8").write(dest + "\n")
    return True


def desinstalar(dest):
    fechar_os_desta_pasta(dest)
    for p in lnks_desta_pasta(dest):          # só os atalhos que apontam pra ESTA instalação
        os.remove(p)
    alvo = os.path.join(os.path.expanduser("~"), ".claude", "skills", "kakashi")
    if os.path.exists(os.path.join(alvo, MARCA_SKILL)):
        shutil.rmtree(alvo)
    if os.path.isfile(UPIA):
        subprocess.run([UPIA, "/remove", "KAKASHI"], capture_output=True, creationflags=SEM_JANELA)
    print("Atalhos, skill e painel removidos. As gravações continuam em %s (apague a pasta à mão se quiser)." % os.path.join(dest, "sessoes"))


def main():
    ap = argparse.ArgumentParser(description="instala o KAKASHI da Fly (Windows)")
    ap.add_argument("--atalho", default="")
    ap.add_argument("--transcricao", choices=["ardi", "local"], default="")
    ap.add_argument("--destino", default=os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Kakashi-Fly"))
    ap.add_argument("--sem-ligar", action="store_true"); ap.add_argument("--sem-skill", action="store_true")
    ap.add_argument("--sem-premiere", action="store_true"); ap.add_argument("--trocar-skill", action="store_true")
    ap.add_argument("--desinstalar", action="store_true")
    a = ap.parse_args()
    dest = os.path.abspath(a.destino)
    if sys.platform != "win32":
        sys.exit("Este pacote é pra Windows. No Mac o gravador ainda não existe (o Piloto está terminando).")
    if sys.version_info < (3, 10):
        sys.exit("Precisa do Python 3.10 ou mais novo. Instale:  winget install Python.Python.3.12  e rode de novo.")
    if a.desinstalar:
        return desinstalar(dest)
    if not shutil.which("ffmpeg"):
        sys.exit("Falta o ffmpeg. Instale:  winget install Gyan.FFmpeg  (feche e abra o terminal) e rode de novo.")
    print("KAKASHI da Fly → %s" % dest)
    if os.path.normcase(dest) == os.path.normcase(AQUI):
        sys.exit("Rode o instalador da pasta extraída do zip, não da pasta onde ele instala.")
    if not a.sem_ligar:
        fechar_os_desta_pasta(dest)
    copiar(dest)
    venv = os.path.join(dest, ".venv"); py = os.path.join(venv, "Scripts", "python.exe"); pyw = os.path.join(venv, "Scripts", "pythonw.exe")
    if not os.path.isfile(py):
        subprocess.run([sys.executable, "-m", "venv", venv], check=True)
    print("  instalando as bibliotecas (1 a 3 min)...")
    subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", os.path.join(dest, "requirements.txt")], check=True)
    cfgp = os.path.join(dest, "config.json"); c = ler_cfg(cfgp)
    if a.transcricao:
        c["transcricao"] = a.transcricao; gravar_cfg(cfgp, c)
    if c.get("transcricao") == "local":
        print("  transcrição no próprio PC: instalando o faster-whisper...")
        subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "faster-whisper"], check=True)
    nome_at, nome_canc = escolher_atalho(dest, a.atalho)
    c = ler_cfg(cfgp)
    if a.sem_premiere and not a.sem_ligar:      # a escolha fica guardada: a atualização não põe o painel em quem não quis
        c["premiere"] = False; gravar_cfg(cfgp, c)
    tem_premiere = False if (a.sem_premiere or c.get("premiere") is False) else instalar_premiere(dest, not a.sem_ligar, pyw)
    if not a.sem_ligar:
        startup, desktop = pasta_especial("Startup"), pasta_especial("Desktop")
        kak = '"%s"' % os.path.join(dest, "kakashi.pyw"); ico = os.path.join(dest, "kakashi.ico")
        atalho_lnk(lugar_do_lnk(startup, "Kakashi", dest), pyw, kak, dest, ico)
        atalho_lnk(lugar_do_lnk(desktop, "KAKASHI", dest), pyw, kak + " --painel", dest, ico)
        subprocess.Popen([pyw, os.path.join(dest, "kakashi.pyw")], cwd=dest, creationflags=SEM_JANELA)
    skill_ok = False if a.sem_skill else instalar_skill(dest, a.trocar_skill)
    print()
    subprocess.run([py, os.path.join(dest, "pc_check.py"), "--json", os.path.join(dest, "perfil.json")] +
                   (["--sem-ardi"] if c.get("transcricao") == "local" and "--sem-ardi" in open(os.path.join(dest, "pc_check.py"),
                                                                                                encoding="utf-8").read() else []))
    print()
    print("Pronto. %s começa e conclui uma gravação; %s cancela." % (nome_at, nome_canc))
    print("Trocar o atalho: atalho KAKASHI na área de trabalho → TROCAR O ATALHO.")
    print("Painel do Premiere: %s." % ("instalado" if tem_premiere else "não instalado"))
    print("Depois de gravar, no Claude Code: /kakashi%s" % ("" if skill_ok or a.sem_skill else " (a skill não foi instalada: ver o aviso acima)"))
    print("Transcrição: %s." % ("no próprio PC (local)" if c.get("transcricao") == "local" else "pela sua conta ARDI (padrão)"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)      # na ordem certa com a saída do pc_check (outro processo)
    main()
