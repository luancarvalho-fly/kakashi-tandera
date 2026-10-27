# -*- coding: utf-8 -*-
"""KAKASHI + TANDERA da Fly — instala TUDO no Windows (27/10/2026). O Instalar.bat (dois cliques) chama este arquivo.

Ele (27/10): «coloca da maneira mais fácil pra pessoa só instalar no PC dela, tá? Plugin e tudo mais».

  py -3 instalar_tudo.py                       → ffmpeg (se faltar) → PC check → Kakashi + plugin do Premiere → Tandera (pergunta 1 vez: os GB)
  py -3 instalar_tudo.py --atalho "ctrl+alt+k" → o atalho do Kakashi (sem isso: Ctrl+Page Down; troca depois na janelinha)
  py -3 instalar_tudo.py --sem-tandera | --sem-premiere | --sim (não pergunta nada)
  --atualizar (o atualizar.py usa): sem pergunta, mantém atalho/config/gravações; Tandera só se já estiver instalado.
  --teste: instala em pastas de teste (%TEMP%), sem ligar nada, sem skill e sem Premiere.
"""
import argparse, json, os, shutil, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.environ.get("LOCALAPPDATA", "")
WINGET_LINKS = os.path.join(LOCAL, "Microsoft", "WinGet", "Links")


def titulo(t):
    print("\n== %s ==" % t, flush=True)


def garantir_ffmpeg():
    if WINGET_LINKS not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + WINGET_LINKS     # onde o winget põe o ffmpeg (vale já, sem reabrir)
    if shutil.which("ffmpeg"):
        return True
    if not shutil.which("winget"):
        print("Falta o ffmpeg e este Windows não tem o winget. Instale o ffmpeg (gyan.dev) e rode de novo.")
        return False
    print("Instalando o ffmpeg (grava a tela e o som; só pra você, sem administrador)...", flush=True)
    subprocess.run(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--silent", "--accept-package-agreements",
                    "--accept-source-agreements"])
    return bool(shutil.which("ffmpeg"))


def rodar(*args):
    return subprocess.run([sys.executable, *args], cwd=AQUI).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--atalho", default=""); ap.add_argument("--sem-tandera", action="store_true")
    ap.add_argument("--sem-premiere", action="store_true"); ap.add_argument("--sim", action="store_true")
    ap.add_argument("--atualizar", action="store_true"); ap.add_argument("--teste", action="store_true")
    ap.add_argument("--destino-kakashi", default="")
    a = ap.parse_args()
    if sys.platform != "win32":
        sys.exit("Este pacote é pra Windows. No Mac o Kakashi ainda não existe (o Piloto está terminando).")
    versao = open(os.path.join(AQUI, "VERSAO.txt"), encoding="utf-8").read().strip()
    print("KAKASHI + TANDERA da Fly · versão %s%s" % (versao, " · ATUALIZANDO" if a.atualizar else ""), flush=True)
    if not garantir_ffmpeg():
        sys.exit(1)
    tmp = os.environ.get("TEMP", "")
    dest_k = a.destino_kakashi or (os.path.join(tmp, "teste-kakashi-fly") if a.teste else os.path.join(LOCAL, "Programs", "Kakashi-Fly"))
    dest_t = os.path.join(tmp, "teste-tandera-fly") if a.teste else os.path.join(LOCAL, "Programs", "Tandera-Fly")
    teste = ["--sem-ligar", "--sem-skill", "--sem-premiere"] if a.teste else []

    if not a.atualizar:
        titulo("1. O QUE O SEU PC AGUENTA (PC check)")
        rodar(os.path.join(AQUI, "kakashi", "pc_check.py"))

    titulo("2. KAKASHI + plugin do Premiere")
    k = [os.path.join(AQUI, "kakashi", "instalar.py"), "--destino", dest_k] + teste
    if a.atalho:
        k += ["--atalho", a.atalho]
    if a.sem_premiere and not a.teste:
        k.append("--sem-premiere")
    if rodar(*k) != 0:
        sys.exit("O Kakashi não instalou (veja a mensagem acima). Nada do Tandera foi mexido.")

    tandera = os.path.join(AQUI, "tandera", "instalar.py")
    if os.path.isfile(tandera) and not a.sem_tandera:
        titulo("3. TANDERA (análise de vídeo)")
        cfg_k = os.path.join(dest_k, "config.json")
        try:
            c = json.load(open(cfg_k, encoding="utf-8"))
        except (OSError, ValueError):
            c = {}
        if a.atualizar and not os.path.isdir(dest_t) and (c.get("tandera") is False or a.teste):
            print("O Tandera não está instalado neste PC (você pulou antes): pra instalar, rode o Instalar.bat de novo.")
        elif a.atualizar and not os.path.isdir(dest_t):
            # o Tandera chegou numa versão nova e esta pessoa só tinha o Kakashi: pergunta UMA vez e guarda a resposta
            rodar(tandera, "--destino", dest_t, "--so-tamanho")
            quer = not input("\nO Tandera (análise de vídeo) chegou nesta versão. Instalar agora? Enter = sim · N = não: ").strip().lower().startswith("n")
            c["tandera"] = quer; json.dump(c, open(cfg_k, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            if quer and rodar(tandera, "--destino", dest_t, "--sem-perguntas") != 0:
                print("O Tandera não instalou (veja a mensagem acima). O Kakashi já está atualizado e funcionando.")
        else:
            t = [tandera, "--destino", dest_t, "--sem-perguntas"] + (["--sem-skill"] if a.teste else [])
            if not (a.atualizar or a.sim):
                rodar(tandera, "--destino", dest_t, "--so-tamanho")
                if input("\nInstalar o Tandera agora? Enter = sim · N = pular: ").strip().lower().startswith("n"):
                    print("Tandera pulado. Dá pra instalar depois rodando o Instalar.bat de novo.")
                    t = None
                    try:              # guarda: a atualização não pergunta de novo
                        c["tandera"] = False; json.dump(c, open(cfg_k, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                    except OSError:
                        pass
            if t and rodar(*t) != 0:
                print("O Tandera não instalou (veja a mensagem acima). O Kakashi já está instalado e funcionando.")

    titulo("PRONTO")
    print("Kakashi: aperte o atalho, fale e mexa à vontade, aperte de novo e digite /kakashi no Claude Code.")
    print("Trocar o atalho e procurar atualização: atalho KAKASHI na área de trabalho.")
    if os.path.isfile(tandera):
        print("Tandera: no Claude Code, /tandera e o caminho do vídeo.")
    if not a.teste:
        pyw = os.path.join(dest_k, ".venv", "Scripts", "pythonw.exe")
        if os.path.isfile(pyw):          # mostra a janelinha (com o atalho escolhido e o botão de atualização)
            subprocess.Popen([pyw, os.path.join(dest_k, "kakashi.pyw"), "--painel"], cwd=dest_k)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    main()
