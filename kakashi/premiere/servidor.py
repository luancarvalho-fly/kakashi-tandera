"""CORRETOR - servidor local (porta 7815 no vivo; 7816 na copia DEV). So stdlib + ffmpeg no PATH.

O Luan corrige no Premiere uma edicao feita pelo Claude. O painel UXP (pasta painel/)
manda pra ca, em lotes, tudo o que ele faz (agulha, selecao, diferencas da timeline,
marcadores). Este servidor:
  - grava o MICROFONE (ffmpeg dshow), o SOM DO PC (WASAPI loopback da saida de som, gravar_pc.py com
    PyAudioWPatch; desde 14/10) e a TELA de reserva (ffmpeg gdigrab, 5 fps desde a v0.2, so CPU),
    em PARTES: cada Iniciar/Retomar abre a parte NN, cada Pausar fecha;
  - carimba cada evento com t_gravacao (segundos de gravacao SEM as pausas = o segundo
    do audio.wav, do pc.wav e do tela.mp4) e quando (ISO, relogio de parede);
  - no Concluir junta as partes em audio.wav (so a voz) / pc.wav (so o som do PC) / tela.mp4 (ALINHADOS: o
    atraso de abertura de cada gravador vira silencio no comeco de cada parte) e escreve o resumo.md.

Endpoints: GET /status, GET /dispositivos, POST /iniciar, /pausar, /retomar, /concluir,
POST /eventos, POST /log, GET|POST /comando (fila de comando remoto pro Claude testar),
POST /sonda (linhas do painel CORRETOR SONDA -> sonda.log, so pra testes da API).
0.3.0 (15/10, pedido do Luan): POST /cancelar (joga fora a sessao gravando/pausada: para os gravadores, NAO gera
resumo, sessao.json ganha "descartada": true e a pasta vai pra sessoes\\_descartadas - nunca apaga do disco);
POST /apagar_pedaco {n} e /voltar_pedaco {n} (pedaco = parte; tira/devolve a parte N da juncao, os arquivos dela vao
pra <sessao>\\_pedacos_apagados). No Concluir, tirar_pedacos_apagados() reconta os tempos sem os pedacos apagados
(eventos.jsonl reescrito, o original fica em _pedacos_apagados\\eventos_com_tudo.jsonl). O /status traz "pedacos"
[{n, dur, apagado, gravando}] e "t_valendo" (gravado sem os apagados = o relogio do painel).

So pra teste (config.json): "teste_fonte_falsa": true troca o microfone por um tom (lavfi sine) e a
tela por uma imagem de teste (lavfi testsrc), pra testar gravar/pausar/juntar sem abrir o mic nem
capturar a tela de verdade. Padrao: false. "teste_som_pc_falso": true troca o loopback por pacotes de
tom gerados (com buracos e uma troca de saida aos 3 s; nada toca nas caixas). Padrao: false.

Som do PC (config.json): "gravar_som_pc": true (padrao) e "dispositivo_saida": "" (vazio = a saida padrao do
Windows, seguindo a troca se ela mudar no meio; um nome = aquele aparelho). Se o loopback nao abrir, a sessao
segue so com o microfone e o sessao.json (parte -> erro_pc) e o resumo dizem por que.

Nada de GPU (regra da casa: placa fica pro Premiere).
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSAO = "0.3.0"
# 7815, longe da faixa 7788-7799 dos outros apps e das copias de teste deles (13/10: uma copia de
# teste do app Projetos subiu na 7799 e o Corretor nao ligava). O painel fala SO com esta porta.
PORTA = int(os.environ.get("CORRETOR_PORTA") or 7815)
BASE = Path(__file__).resolve().parent
SESSOES = BASE / "sessoes"
# CORRETOR_CONFIG: outro config.json (so pros testes: o simulador --tela usa teste\config_tela.json)
CONFIG = Path(os.environ["CORRETOR_CONFIG"]).resolve() if os.environ.get("CORRETOR_CONFIG") else BASE / "config.json"
LOG_GERAL = BASE / "servidor.log"
MTIME_CODIGO = os.path.getmtime(__file__)

CONFIG_PADRAO = {
    "dispositivo_audio": "",      # vazio = o primeiro microfone que o ffmpeg listar
    "gravar_tela": True,
    "tela_fps": 5,
    "tela_largura": 3840,         # 4K nativo (14/10, Luan: "pode colocar em 4K mesmo ... isso é importante" - pico pequeno da waveform legível)
    "gravar_som_pc": True,        # som do PC (o que sai na saida de som) em trilha propria: pc.wav
    "dispositivo_saida": "",      # vazio = a saida padrao do Windows (segue a troca no meio da sessao)
}
GRAVAR_PC = BASE / "gravar_pc.py"


def python_console():
    """o lancador sobe o servidor com pythonw (sem console): o gravar_pc.py roda no python.exe do mesmo lugar
    (stdin/stdout de verdade pro 'q' e pras linhas de estado), sem janela (CREATE_NO_WINDOW)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and exe.with_name("python.exe").exists():
        return str(exe.with_name("python.exe"))
    return str(exe)


def som_pc_disponivel():
    """(True, 'PyAudioWPatch x.y') ou (False, motivo em portugues)"""
    if not GRAVAR_PC.exists():
        return False, "falta o gravar_pc.py na pasta do servidor"
    try:
        from importlib.metadata import version
        return True, "PyAudioWPatch " + version("PyAudioWPatch")
    except Exception:
        return False, "biblioteca PyAudioWPatch nao instalada no Python do servidor (rodar: pip install PyAudioWPatch)"

SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# ffmpeg da TELA e o juntar do Concluir: prioridade abaixo do normal (o Premiere vem primeiro). O do MICROFONE
# fica normal (nao pode falhar). REVISAO-desempenho, "tela a 5 qps".
ABAIXO_DO_NORMAL = 0x00004000 if os.name == "nt" else 0


def _criar_job():
    """Job Object do Windows com KILL_ON_JOB_CLOSE: se este servidor morrer (crash, taskkill),
    o Windows mata os ffmpeg filhos junto. Sem isto eles ficam gravando pra sempre (medido 13/10)."""
    if os.name != "nt":
        return None, None
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        class Basica(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class Estendida(ctypes.Structure):
            _fields_ = [("Basic", Basica), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        job = k32.CreateJobObjectW(None, None)
        info = Estendida()
        info.Basic.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None, None
        return job, k32
    except Exception:
        return None, None


JOB, _K32 = _criar_job()


def amarrar_ao_servidor(proc):
    if JOB and proc is not None:
        try:
            _K32.AssignProcessToJobObject(JOB, int(proc._handle))
        except Exception:
            pass
ACOES_REMOTAS = ("iniciar", "pausar", "retomar", "concluir")


# ------------------------------------------------------------------ utilidades
def agora():
    return time.time()


def iso(t):
    return datetime.fromtimestamp(t).isoformat(timespec="milliseconds")


def substituir(tmp, destino):
    """os.replace com nova tentativa: no Windows ele da "Acesso negado" (WinError 5) se outro fio estiver
    LENDO o destino nessa hora (o /status le todos os sessao.json via pendentes() a cada 0,5 s). Achado no
    teste de peso de 14/10 (v0.2): o Concluir falhava e a sessao ficava "finalizando"."""
    for _ in range(60):
        try:
            os.replace(tmp, destino)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, destino)


def log_geral(msg):
    linha = "%s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_GERAL, "a", encoding="utf-8") as f:
            f.write(linha)
    except OSError:
        pass


def achar_ffmpeg(nome="ffmpeg"):
    p = shutil.which(nome)
    if p:
        return p
    # winget instala fora do PATH de quem nao reabriu o terminal
    padrao = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\%s.exe" % nome)
    achados = sorted(glob.glob(padrao))
    return achados[-1] if achados else None


FFMPEG = achar_ffmpeg("ffmpeg")
FFPROBE = achar_ffmpeg("ffprobe")


def ler_config():
    cfg = dict(CONFIG_PADRAO)
    if CONFIG.exists():
        try:
            cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        except Exception as e:
            log_geral("config.json ilegivel (%s); usando padrao" % e)
    else:
        try:
            CONFIG.write_text(json.dumps(CONFIG_PADRAO, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    return cfg


def listar_dispositivos():
    """[{nome, tipo}] do dshow. tipo = audio | video | none."""
    if not FFMPEG:
        return []
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                           capture_output=True, timeout=15, creationflags=SEM_JANELA)
    except Exception as e:
        log_geral("list_devices falhou: %s" % e)
        return []
    texto = (r.stderr or b"").decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'"([^"]+)"\s+\((audio|video|none)\)', texto):
        out.append({"nome": m.group(1), "tipo": m.group(2)})
    return out


def listar_saidas_de_som():
    """{saidas: [nomes], padrao: nome} pelo gravar_pc.py --listar (o servidor nao carrega o PortAudio)"""
    ok, motivo = som_pc_disponivel()
    if not ok:
        return {"saidas": [], "padrao": None, "erro": motivo}
    try:
        r = subprocess.run([python_console(), str(GRAVAR_PC), "--listar"], capture_output=True, timeout=20,
                           creationflags=SEM_JANELA)
        return json.loads((r.stdout or b"{}").decode("utf-8", "replace").strip().splitlines()[-1])
    except Exception as e:
        return {"saidas": [], "padrao": None, "erro": str(e)}


def microfone(cfg):
    if cfg.get("teste_fonte_falsa"):
        return "tom de teste (lavfi sine)"
    if cfg.get("dispositivo_audio"):
        return cfg["dispositivo_audio"]
    for d in listar_dispositivos():
        if d["tipo"] == "audio":
            return d["nome"]
    return ""


def nome_limpo(s, maximo=60):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(s or "")).strip().strip(".")
    s = re.sub(r"\s+", " ", s)
    return (s[:maximo].strip() or "sem-sequencia")


def duracao(caminho, wav=False):
    """Duracao em segundos pelo ffprobe (None se ilegivel). wav=True ignora o tamanho do
    cabecalho (parte de wav de ffmpeg morto fica com tamanho errado no cabecalho)."""
    if not FFPROBE or not Path(caminho).exists() or Path(caminho).stat().st_size < 100:
        return None
    cmd = [FFPROBE, "-v", "error"]
    if wav:
        cmd += ["-ignore_length", "1"]
    cmd += ["-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(caminho)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=SEM_JANELA)
        v = (r.stdout or b"").decode().strip().splitlines()
        return float(v[0]) if v and v[0] not in ("N/A", "") else None
    except Exception:
        return None


# ------------------------------------------------------------------ gravador ffmpeg
class Gravador:
    """Um processo ffmpeg que para limpo com 'q' no stdin (arquivo fecha valido)."""

    def __init__(self, tipo, cmd, arquivo, log, prioridade_baixa=False, ler_saida=False, env=None):
        self.tipo, self.cmd, self.arquivo, self.log = tipo, cmd, Path(arquivo), Path(log)
        self.prioridade_baixa = prioridade_baixa
        self.ler_saida = ler_saida    # gravar_pc.py: uma linha JSON por acontecimento no stdout -> self.info
        self.env = env
        self.info = {"aberto": False, "dispositivo": "", "erro": "", "trocas": 0}
        self.proc = None
        self.erro = ""
        self.saiu_em = None       # relogio de parede de quando o ffmpeg terminou (por qualquer motivo)

    def iniciar(self):
        try:
            self._lf = open(self.log, "ab")
            self._lf.write(("\n=== %s %s\n%s\n" % (iso(agora()), self.tipo, subprocess.list2cmdline(self.cmd))).encode("utf-8"))
            self._lf.flush()
            self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE if self.ler_saida else subprocess.DEVNULL, stderr=self._lf,
                                         creationflags=SEM_JANELA | (ABAIXO_DO_NORMAL if self.prioridade_baixa else 0),
                                         env=self.env)
            amarrar_ao_servidor(self.proc)
            threading.Thread(target=self._vigiar, daemon=True).start()
            if self.ler_saida:
                threading.Thread(target=self._ler, daemon=True).start()
        except Exception as e:
            self.erro = "nao abriu o %s: %s" % ("ffmpeg" if not self.ler_saida else self.tipo, e)
            self.proc = None

    def _ler(self):
        try:
            for linha in self.proc.stdout:
                try:
                    ev = json.loads(linha.decode("utf-8", "replace"))
                except Exception:
                    continue
                o = ev.get("evento")
                if o == "abriu":
                    self.info.update(aberto=True, dispositivo=ev.get("dispositivo") or "", erro="")
                elif o == "trocou":
                    if not ev.get("reaberto"):      # reaberto = ja veio o 'abriu' da saida nova antes desta linha
                        self.info["aberto"] = False
                    self.info["trocas"] += 1
                elif o == "reabrindo":              # o stream parou sozinho: o 'abriu' seguinte liga de novo
                    self.info["aberto"] = False
                elif o == "erro":
                    self.info["erro"] = ev.get("msg") or "erro"
        except Exception:
            pass

    def _vigiar(self):
        """Anota a hora em que o ffmpeg saiu: se o microfone cair NO MEIO da parte, o buraco
        fica no FIM do arquivo (e nao no comeco, como o atraso de abertura)."""
        try:
            self.proc.wait()
        except Exception:
            return
        self.saiu_em = agora()

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    def parar(self):
        if not self.proc:
            # 0.3.0: o Popen falhou mas o log ja estava aberto - fechar (handle aberto impede mover a pasta no Cancelar)
            try:
                self._lf.close()
            except Exception:
                pass
            return
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q")
                self.proc.stdin.flush()
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
        try:
            self._lf.close()
        except Exception:
            pass


# ------------------------------------------------------------------ sessao
class Sessao:
    def __init__(self, pasta, meta):
        self.pasta = Path(pasta)
        self.meta = meta
        self.audio = None
        self.tela = None
        self.pc = None          # gravar_pc.py (som do PC) da parte aberta
        self.n_eventos = meta.get("eventos", 0)
        self._ev = open(self.pasta / "eventos.jsonl", "a", encoding="utf-8")

    # -- tempo
    def parte_em(self, w):
        """A parte (pedaco) dona de um instante do relogio de parede: a ultima que comecou antes dele (instante
        numa pausa = a parte que acabou de fechar; antes da 1a = None)."""
        escolhida = None
        for p in self.meta["partes"]:
            if p["inicio"] <= w + 0.001:
                escolhida = p
            else:
                break
        return escolhida

    def t_gravacao(self, t_parede=None):
        """Segundos de gravacao (sem pausas) correspondentes a um instante do relogio de parede.
        Instante dentro de uma pausa = fim da parte anterior; antes da 1a parte = 0."""
        partes = self.meta["partes"]
        if not partes:
            return 0.0
        w = agora() if t_parede is None else t_parede
        escolhida = self.parte_em(w)
        if escolhida is None:
            return 0.0
        fim = escolhida["fim"] if escolhida["fim"] is not None else agora()
        return escolhida["t0"] + max(0.0, min(w, fim) - escolhida["inicio"])

    def total_gravado(self):
        return self.t_gravacao(agora())

    # -- persistencia
    def salvar(self):
        self.meta["eventos"] = self.n_eventos
        tmp = self.pasta / "sessao.json.tmp"
        tmp.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")
        substituir(tmp, self.pasta / "sessao.json")

    def gravar_eventos(self, eventos):
        linhas = []
        for ev in eventos:
            if not isinstance(ev, dict):
                continue
            ms = ev.get("ms")
            try:
                w = float(ms) / 1000.0 if ms is not None else agora()
            except (TypeError, ValueError):
                w = agora()
            self.n_eventos += 1
            ev["n"] = self.n_eventos
            ev["t_gravacao"] = round(self.t_gravacao(w), 3)
            ev["quando"] = iso(w)
            dona = self.parte_em(w)      # 0.3.0: o pedaco do evento (apagar pedaco tira os eventos dele)
            ev["parte"] = dona["n"] if dona is not None else (self.meta["partes"][0]["n"] if self.meta["partes"] else 1)
            linhas.append(json.dumps(ev, ensure_ascii=False))
        if linhas:
            self._ev.write("\n".join(linhas) + "\n")
            self._ev.flush()
            try:
                os.fsync(self._ev.fileno())
            except OSError:
                pass
        return len(linhas)

    def log_painel(self, nivel, msg):
        with open(self.pasta / "painel.log", "a", encoding="utf-8") as f:
            f.write("%s [%s] t=%.1f  %s\n" % (datetime.now().strftime("%H:%M:%S"), nivel, self.total_gravado(), msg))

    # -- partes
    def abrir_parte(self, cfg):
        n = len(self.meta["partes"]) + 1
        t0 = sum((p["fim"] - p["inicio"]) for p in self.meta["partes"] if p["fim"] is not None)
        parte = {"n": n, "inicio": agora(), "fim": None, "t0": round(t0, 3),
                 "audio": "parte%02d.wav" % n, "tela": "tela%02d.mp4" % n,
                 "mic_ok": False, "tela_ok": False, "erro_mic": "", "erro_tela": ""}
        flog = self.pasta / "ffmpeg.log"
        dev = self.meta.get("dispositivo") or ""
        if not dev:
            # sem mic na hora do Iniciar (ou sessao reaberta sem o campo): tenta de novo a cada parte
            dev = microfone(cfg)
            self.meta["dispositivo"] = dev
        falsa = bool(cfg.get("teste_fonte_falsa"))
        if FFMPEG and (dev or falsa):
            entrada = (["-f", "lavfi", "-re", "-i", "sine=frequency=440:sample_rate=48000"] if falsa
                       else ["-f", "dshow", "-audio_buffer_size", "50", "-i", "audio=" + dev])
            cmd = [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "warning"] + entrada + [
                   "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
                   # flush a cada pacote: sem isto o wav segura 256 KB (~2,7 s de fala) no buffer e
                   # perde isso se o servidor cair (medido 13/10 na revisao)
                   "-flush_packets", "1",
                   "-y", str(self.pasta / parte["audio"])]
            self.audio = Gravador("audio", cmd, self.pasta / parte["audio"], flog)
            self.audio.iniciar()
        else:
            self.audio = None
            parte["erro_mic"] = "sem ffmpeg" if not FFMPEG else "nenhum microfone encontrado"
        # som do PC (14/10): processo proprio por parte, igual ao microfone. O relogio e o mesmo: ele recebe o
        # inicio da parte e o atraso de abertura vira silencio no comeco (o "offset" de cada segmento)
        self.pc = None
        if self.meta.get("gravar_som_pc"):
            parte.update({"pc": "pc%02d.wav" % n, "pc_ok": False, "erro_pc": ""})
            falso = bool(cfg.get("teste_som_pc_falso"))
            ok, motivo = (True, "teste") if falso else som_pc_disponivel()
            if ok:
                cmd = [python_console(), str(GRAVAR_PC), "--pasta", str(self.pasta), "--parte", str(n),
                       "--inicio", repr(parte["inicio"]), "--dispositivo", self.meta.get("dispositivo_saida") or ""]
                if falso:
                    cmd.append("--falso")
                env = dict(os.environ, PYTHONIOENCODING="utf-8")
                self.pc = Gravador("som_pc", cmd, self.pasta / parte["pc"], self.pasta / "som_pc.log",
                                   ler_saida=True, env=env)
                self.pc.iniciar()
                if self.pc.proc is None:
                    parte["erro_pc"] = self.pc.erro
                    self.pc = None
            else:
                parte["erro_pc"] = motivo
        if FFMPEG and cfg.get("gravar_tela", True):
            larg = int(cfg.get("tela_largura", 3840))
            # defeito G (v0.2): o fps e o da SESSAO (gravado no Iniciar), nao o do config.json relido a
            # cada Retomar - o juntar usa o da sessao; se o config mudasse no meio, as partes desalinhavam
            fps = str(self.meta.get("tela_fps") or cfg.get("tela_fps", 5))
            gop = str(max(2, int(round(2 * float(fps)))))      # quadro-chave a cada 2 s (fragmento de 2 s)
            entrada = (["-f", "lavfi", "-re", "-i", "testsrc=size=1280x720:rate=" + fps] if cfg.get("teste_fonte_falsa")
                       else ["-f", "gdigrab", "-framerate", fps, "-draw_mouse", "1", "-i", "desktop"])
            cmd = [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "warning"] + entrada + [
                   "-vf", "scale=%d:-2:flags=bilinear,format=yuv420p" % larg,
                   # zerolatency + fragmento de 2 s + flush: se o servidor/PC cair, o mp4 ate ali abre
                   # (sem isto o x264 segura ~6 s no buffer e o arquivo morto fica sem cabecalho; medido 13/10)
                   "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-crf", "28", "-g", gop,
                   "-threads", "2", "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
                   "-frag_duration", "2000000", "-flush_packets", "1",
                   "-y", str(self.pasta / parte["tela"])]
            self.tela = Gravador("tela", cmd, self.pasta / parte["tela"], flog, prioridade_baixa=True)
            self.tela.iniciar()
        else:
            self.tela = None
        self.meta["partes"].append(parte)
        self.meta["estado"] = "gravando"
        self.salvar()
        # o ffmpeg que nao achou o dispositivo morre em menos de 1 s: conferir depois
        threading.Timer(1.5, self._conferir_parte, args=(parte,)).start()

    def _conferir_parte(self, parte):
        with TRAVA:
            if parte["fim"] is not None:
                return
            if self.audio is not None:
                parte["mic_ok"] = self.audio.vivo()
                if not parte["mic_ok"]:
                    parte["erro_mic"] = self.audio.erro or "o ffmpeg do microfone fechou (ver ffmpeg.log)"
            if self.tela is not None:
                parte["tela_ok"] = self.tela.vivo()
                if not parte["tela_ok"]:
                    parte["erro_tela"] = self.tela.erro or "o ffmpeg da tela fechou (ver ffmpeg.log)"
            if self.pc is not None:
                # so o de agora (pra quem olhar o sessao.json no meio): o valor final sai do manifesto no fechar_parte
                parte["pc_ok"] = self.pc.vivo() and self.pc.info["aberto"]
                if not parte["pc_ok"]:
                    parte["erro_pc"] = (self.pc.info["erro"] or self.pc.erro or
                                        ("o gravador do som do PC fechou (ver som_pc.log)" if not self.pc.vivo() else ""))
            self.salvar()

    def fechar_parte(self):
        partes = self.meta["partes"]
        if not partes or partes[-1]["fim"] is not None:
            return
        p = partes[-1]
        p["fim"] = agora()      # o fim conta do clique, nao de quando o ffmpeg terminou de fechar
        if self.audio is not None and self.audio.vivo():
            p["mic_ok"], p["erro_mic"] = True, ""
        if self.tela is not None and self.tela.vivo():
            p["tela_ok"], p["erro_tela"] = True, ""
        for g in (self.audio, self.pc, self.tela):
            if g is not None:
                g.parar()
        # ffmpeg que morreu ANTES do clique (mic USB solto, driver caiu): anota quando
        for g, campo, ok, erro, nome in ((self.audio, "mic_caiu_em", "mic_ok", "erro_mic", "microfone"),
                                         (self.tela, "tela_caiu_em", "tela_ok", "erro_tela", "tela")):
            if g is not None and g.saiu_em is not None and g.saiu_em < p["fim"] - 0.3:
                p[campo] = round(g.saiu_em, 3)
                p[ok] = False
                p[erro] = p[erro] or ("o ffmpeg do %s parou aos %.1f s da parte (ver ffmpeg.log)" % (nome, g.saiu_em - p["inicio"]))
        if p.get("pc"):
            _anotar_pc(self.pasta, p, self.pc.saiu_em if self.pc is not None else None)
        self.audio = self.tela = self.pc = None
        p["dur"] = round(p["fim"] - p["inicio"], 3)
        self.salvar()

    def mic_ok(self):
        return self.audio is not None and self.audio.vivo()

    def tela_ok(self):
        return self.tela is not None and self.tela.vivo()

    def pc_ok(self):
        return self.pc is not None and self.pc.vivo() and self.pc.info["aberto"]

    def fechar_arquivos(self):
        try:
            self._ev.close()
        except Exception:
            pass


TRAVA = threading.RLock()
ATUAL = None            # Sessao gravando/pausada
ULTIMA = None           # pasta da ultima concluida
FINALIZANDO = False
COMANDOS = []
PAINEL = {"visto": 0.0, "versao": ""}
FECHANDO_NO_BOOT = set()  # pastas de sessoes antigas largadas que o boot esta juntando em segundo plano
FINALIZANDO_PASTA = [None]  # pasta que o Concluir esta juntando agora (o /status nao le o sessao.json dela)


PEND_CACHE = {"t": 0.0, "estados": None}   # pasta -> estado do sessao.json (relido no maximo a cada 10 s)


def esquecer_pendentes():
    """chamar quando uma sessao muda de estado (iniciar, concluir, boot): o proximo /status rele o disco"""
    PEND_CACHE["t"] = 0.0


def pendentes():
    """Sessoes que ficaram abertas (servidor caiu no meio).
    Revisao 14/10 (REVISAO-desempenho 6): o painel pede o /status a cada 0,5 s e isto lia TODOS os sessao.json,
    com a trava fechada, toda vez (a causa do WinError 5 no Concluir). Agora o disco e relido no maximo a cada 10 s
    ou quando alguma sessao muda de estado; os filtros (sessao atual, juntando, fechando no boot) valem na hora."""
    if not SESSOES.exists():
        return []
    if PEND_CACHE["estados"] is None or agora() - PEND_CACHE["t"] >= 10.0:
        estados = {}
        for js in sorted(SESSOES.glob("*/sessao.json")):
            try:
                m = json.loads(js.read_text(encoding="utf-8"))
            except Exception:
                continue
            estados[str(js.parent)] = m.get("estado")
        PEND_CACHE["estados"], PEND_CACHE["t"] = estados, agora()
    out = []
    for pasta, estado in PEND_CACHE["estados"].items():
        if (estado in ("gravando", "pausado", "finalizando") and (ATUAL is None or str(ATUAL.pasta) != pasta)
                and pasta not in FECHANDO_NO_BOOT and pasta != str(FINALIZANDO_PASTA[0])):
            out.append(pasta)
    return out


def status():
    with TRAVA:
        s = {"ok": True, "app": "corretor", "versao": VERSAO, "pid": os.getpid(), "porta": PORTA,
             "servidor_mtime": MTIME_CODIGO, "ffmpeg": bool(FFMPEG),
             "painel_visto_ha_s": round(agora() - PAINEL["visto"], 1) if PAINEL["visto"] else None,
             "painel_versao": PAINEL["versao"], "ultima": str(ULTIMA) if ULTIMA else None,
             "pendentes": pendentes(), "finalizando": FINALIZANDO}
        if ATUAL is None:
            s.update({"estado": "finalizando" if FINALIZANDO else "parado", "t_gravacao": 0, "t_valendo": 0,
                      "eventos": 0, "pedacos": []})
        else:
            m = ATUAL.meta
            peds = pedacos_de(m)
            total = ATUAL.total_gravado()
            s.update({"pedacos": peds,
                      "t_valendo": round(max(0.0, total - sum(p["dur"] for p in peds if p["apagado"])), 2)})
            s.update({"estado": m["estado"], "sessao": ATUAL.pasta.name, "pasta": str(ATUAL.pasta),
                      "sequencia": m.get("sequencia"), "projeto": m.get("projeto"),
                      "t_gravacao": round(ATUAL.total_gravado(), 2), "eventos": ATUAL.n_eventos,
                      "partes": len(m["partes"]), "dispositivo": m.get("dispositivo"),
                      "mic_ok": ATUAL.mic_ok(), "tela_ok": ATUAL.tela_ok(),
                      "gravar_tela": m.get("gravar_tela"),
                      "gravar_som_pc": m.get("gravar_som_pc"), "som_pc_ok": ATUAL.pc_ok(),
                      "som_pc": (ATUAL.pc.info["dispositivo"] if ATUAL.pc is not None else "") or None,
                      "som_pc_erro": ((ATUAL.pc.info["erro"] if ATUAL.pc is not None else "") or
                                      ((m["partes"][-1].get("erro_pc") or "") if m["partes"] else "")) or None})
        return s


def pedacos_de(meta):
    """0.3.0: o trilho do painel. Um pedaco por parte: {n, dur, apagado, gravando} (dur do que grava = ate agora)."""
    out = []
    for p in meta.get("partes") or []:
        fim = p["fim"] if p.get("fim") is not None else agora()
        out.append({"n": p["n"], "dur": round(max(0.0, fim - p["inicio"]), 2), "apagado": bool(p.get("apagada")),
                    "gravando": p.get("fim") is None})
    return out


# ------------------------------------------------------------------ pedacos (0.3.0)
PASTA_APAGADOS = "_pedacos_apagados"     # dentro da sessao: arquivos e eventos dos pedacos que ele apagou
PASTA_DESCARTADAS = "_descartadas"       # dentro de sessoes\: sessoes canceladas (nunca apagadas do disco)
# eventos de um pedaco apagado que FICAM (nao sao acao dele: dizem onde e como a sessao estava). Vao pro segundo em que
# o pedaco foi cortado. O resto sai do eventos.jsonl (guardado em _pedacos_apagados\eventos_dos_pedacos_apagados.jsonl).
TIPOS_QUE_FICAM = ("sequencia", "foto_inicial", "projeto_inicial", "capacidades", "desempenho")


def arquivos_da_parte(pasta, p):
    """nomes dos arquivos da parte N (mic, tela, som do PC com os segmentos e o manifesto) que existem em `pasta`"""
    n = p["n"]
    nomes = [p.get("audio"), p.get("tela"), p.get("pc"), "pc%02d.json" % n]
    nomes += [s.get("arquivo") for s in p.get("pc_segmentos") or []]
    nomes += [x.name for x in Path(pasta).glob("pc%02d_*.wav" % n)]
    return [x for x in dict.fromkeys(nomes) if x and (Path(pasta) / x).exists()]


def mover(origem, destino):
    """move arquivo/pasta no mesmo disco (rename: nada e copiado nem apagado). Tenta de novo por 3 s se o Windows
    disser "Acesso negado" (alguem lendo na hora, ex.: o /status lendo um sessao.json)."""
    for _ in range(60):
        try:
            os.rename(origem, destino)
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            time.sleep(0.05)
        except OSError:
            break
    try:
        os.rename(origem, destino)
        return True
    except OSError as e:
        log_geral("nao moveu %s -> %s: %s" % (origem, destino, e))
        return False


def _dur_parte(p):
    return max(0.0, (p["fim"] if p.get("fim") is not None else p["inicio"]) - p["inicio"])


def tirar_pedacos_apagados(pasta, meta):
    """No Concluir (e no fechamento pelo disco): tira da sessao as partes marcadas "apagada" pelo painel.
    - arquivos que ainda estiverem na pasta vao pra _pedacos_apagados (o clique ja moveu; aqui e a garantia);
    - eventos.jsonl: o original inteiro vai pra _pedacos_apagados\\eventos_com_tudo.jsonl; os eventos dos pedacos
      apagados saem (guardados em _pedacos_apagados\\eventos_dos_pedacos_apagados.jsonl); os que ficam ganham o
      t_gravacao RECONTADO sem os pedacos apagados (o original fica em "t_bruto"); TIPOS_QUE_FICAM de pedaco apagado
      ficam, no segundo do corte, com "de_pedaco_apagado": N;
    - meta: partes = so as que ficaram (t0 recontado, "t0_bruto" = o de antes; pc_eventos recontados);
      pedacos_apagados = as que sairam (+ dur, cortado_em = segundo da gravacao final em que o pedaco estava,
      eventos_tirados); pausas refeitas entre as partes que ficaram (+ "pedacos_apagados": [N] quando um apagado
      estava ali no meio; pausas_originais = as de antes); quedas recontadas.
    Idempotente: parte que ja saiu nao esta mais em meta["partes"]."""
    partes = meta.get("partes") or []
    apagadas = [p for p in partes if p.get("apagada")]
    if not apagadas:
        return
    pasta = Path(pasta)
    guarda = pasta / PASTA_APAGADOS
    guarda.mkdir(exist_ok=True)
    # 1. arquivos (garantia: o clique no painel ja moveu)
    for p in apagadas:
        movidos = list(p.get("arquivos_apagados") or [])
        for nome in arquivos_da_parte(pasta, p):
            if mover(pasta / nome, guarda / nome):
                movidos.append(nome)
        p["arquivos_apagados"] = list(dict.fromkeys(movidos))
    # 2. relogio novo: cada parte -> (t0 bruto, t0 novo, apagada)
    info, novo = {}, 0.0
    for p in partes:
        info[p["n"]] = {"t0_bruto": float(p.get("t0") or 0.0), "t0_novo": novo, "apagada": bool(p.get("apagada")),
                        "dur": _dur_parte(p), "p": p}
        if not p.get("apagada"):
            novo += _dur_parte(p)
    ordem = sorted(partes, key=lambda x: x["inicio"])

    def dona_do_evento(ev):
        n = ev.get("parte")
        if n in info:
            return info[n]
        w = None
        try:
            w = float(ev["ms"]) / 1000.0
        except Exception:
            try:
                w = datetime.fromisoformat(str(ev["quando"])).timestamp()
            except Exception:
                w = None
        if w is not None:
            esc = ordem[0]
            for p in ordem:
                if p["inicio"] <= w + 0.001:
                    esc = p
                else:
                    break
            return info[esc["n"]]
        t = float(ev.get("t_gravacao") or 0.0)      # sem relogio: pelo segundo bruto (borda = a parte de antes)
        esc = ordem[0]
        for p in ordem:
            if info[p["n"]]["t0_bruto"] < t - 0.0005:
                esc = p
        return info[esc["n"]]

    def t_novo_de_bruto(t):
        for p in ordem:
            i = info[p["n"]]
            if t <= i["t0_bruto"] + i["dur"] + 0.0005:
                return i["t0_novo"] if i["apagada"] else i["t0_novo"] + max(0.0, t - i["t0_bruto"])
        return novo
    # 3. eventos
    arq = pasta / "eventos.jsonl"
    ficam, saem = [], []
    tirados = {p["n"]: 0 for p in apagadas}
    if arq.exists():
        copia = guarda / "eventos_com_tudo.jsonl"
        k = 2
        while copia.exists():
            copia = guarda / ("eventos_com_tudo_%d.jsonl" % k)
            k += 1
        shutil.copy2(arq, copia)
        for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
            s = linha.strip()
            if not s:
                continue
            try:
                ev = json.loads(s)
            except Exception:
                ficam.append(s)             # linha cortada por queda: fica como estava (o resumo pula)
                continue
            i = dona_do_evento(ev)
            fica_mesmo_assim = ev.get("tipo") in TIPOS_QUE_FICAM or (
                ev.get("tipo") == "painel" and "começou a registrar" in str(ev.get("msg") or ""))
            if i["apagada"] and not fica_mesmo_assim:
                saem.append(s)
                tirados[i["p"]["n"]] = tirados.get(i["p"]["n"], 0) + 1
                continue
            t_bruto = float(ev.get("t_gravacao") or 0.0)
            t = i["t0_novo"] if i["apagada"] else i["t0_novo"] + max(0.0, t_bruto - i["t0_bruto"])
            t = round(t, 3)
            mudou = False
            if abs(t - t_bruto) > 0.0005:
                ev["t_bruto"] = t_bruto
                ev["t_gravacao"] = t
                mudou = True
            if i["apagada"]:
                ev["de_pedaco_apagado"] = i["p"]["n"]
                mudou = True
            ficam.append(json.dumps(ev, ensure_ascii=False) if mudou else s)
        if saem:
            with open(guarda / "eventos_dos_pedacos_apagados.jsonl", "a", encoding="utf-8") as f:
                f.write("\n".join(saem) + "\n")
        tmp = pasta / "eventos.jsonl.tmp"
        tmp.write_text(("\n".join(ficam) + "\n") if ficam else "", encoding="utf-8")
        substituir(tmp, arq)
        meta["eventos"] = len(ficam)
    # 4. meta
    ficaram = [p for p in partes if not p.get("apagada")]
    for p in ficaram:
        i = info[p["n"]]
        delta = i["t0_bruto"] - i["t0_novo"]
        if abs(delta) > 0.0005:
            p["t0_bruto"] = round(i["t0_bruto"], 3)
            p["t0"] = round(i["t0_novo"], 3)
            for e in p.get("pc_eventos") or []:
                for k in ("t_gravacao", "t_inicio", "t_fim"):
                    if e.get(k) is not None:
                        e[k] = round(e[k] - delta, 3)
    sairam = []
    for p in apagadas:
        q = dict(p)
        q["dur"] = round(info[p["n"]]["dur"], 3)
        q["cortado_em"] = round(info[p["n"]]["t0_novo"], 3)
        q["eventos_tirados"] = tirados.get(p["n"], 0)
        sairam.append(q)
    meta["pedacos_apagados"] = (meta.get("pedacos_apagados") or []) + sairam
    velhas = meta.get("pausas") or []
    meta.setdefault("pausas_originais", velhas)
    novas = []
    for a, b in zip(ficaram, ficaram[1:]):
        pa = {"inicio": a["fim"], "fim": b["inicio"], "t_gravacao": round(info[a["n"]]["t0_novo"] + _dur_parte(a), 3)}
        entre = [p["n"] for p in apagadas if a["inicio"] < p["inicio"] < b["inicio"]]
        if entre:
            pa["pedacos_apagados"] = entre
        if any(v.get("queda") for v in velhas if v.get("inicio") is not None and a["fim"] - 0.01 <= v["inicio"] <= b["inicio"] + 0.01):
            pa["queda"] = True
        novas.append(pa)
    meta["pausas"] = novas
    for q in meta.get("quedas") or []:
        if q.get("t_gravacao") is not None and "t_bruto" not in q:
            q["t_bruto"] = q["t_gravacao"]
            q["t_gravacao"] = round(t_novo_de_bruto(float(q["t_gravacao"])), 3)
    meta["partes"] = ficaram
    log_geral("%s: %d pedaco(s) apagado(s) por ele (%s), %d evento(s) tirados" % (
        pasta.name, len(apagadas), ", ".join(str(p["n"]) for p in apagadas), len(saem)))


def apagar_pedaco(dados, voltar=False):
    """0.3.0: tira (voltar=False) ou devolve (voltar=True) a parte N da juncao. So parte FECHADA (a que grava agora,
    nao: pausar antes). Os arquivos dela vao pra (ou voltam de) <sessao>\\_pedacos_apagados. Nada e apagado do disco."""
    try:
        n = int(dados.get("n"))
    except (TypeError, ValueError):
        return {"ok": False, "erro": "qual pedaço? (falta o numero n)"}
    with TRAVA:
        if ATUAL is None:
            return {"ok": False, "erro": "nada gravando"}
        p = next((x for x in ATUAL.meta["partes"] if x["n"] == n), None)
        if p is None:
            return {"ok": False, "erro": "nao existe o pedaço %d" % n}
        if p.get("fim") is None:
            return {"ok": False, "erro": "o pedaço %d ainda esta gravando: pause antes" % n}
        if bool(p.get("apagada")) != voltar:
            return dict(status(), aviso="o pedaço %d ja estava %s" % (n, "na gravação" if voltar else "apagado"))
        guarda = ATUAL.pasta / PASTA_APAGADOS
        de, para = (guarda, ATUAL.pasta) if voltar else (ATUAL.pasta, guarda)
        para.mkdir(exist_ok=True)
        falhou = []
        for nome in arquivos_da_parte(de, p):
            if not mover(de / nome, para / nome):
                falhou.append(nome)
        if voltar:
            p.pop("apagada", None)
            p.pop("apagada_em", None)
            p.pop("arquivos_apagados", None)
            p["voltou_em"] = iso(agora())
        else:
            p["apagada"] = True
            p["apagada_em"] = iso(agora())
            p["arquivos_apagados"] = [x for x in arquivos_da_parte(guarda, p)]
        if falhou:
            p["arquivos_nao_movidos"] = falhou      # o Concluir tenta de novo (e a juncao ja ignora a parte apagada)
        else:
            p.pop("arquivos_nao_movidos", None)
        ATUAL.salvar()
        try:
            ATUAL.log_painel("info", "pedaço %d %s pelo painel%s" % (n, "VOLTOU" if voltar else "APAGADO",
                             (" (nao moveu: %s)" % ", ".join(falhou)) if falhou else ""))
        except OSError:
            pass
        return status()


def cancelar():
    """0.3.0: joga fora a sessao em andamento (gravando ou pausada). Para os gravadores (arquivos fecham validos),
    NAO junta nem gera resumo, sessao.json ganha "descartada": true e a pasta inteira vai pra sessoes\\_descartadas
    (rename no mesmo disco: nada e apagado; se o Windows nao deixar mover, fica onde esta, marcada descartada)."""
    global ATUAL
    with TRAVA:
        if FINALIZANDO:
            return {"ok": False, "erro": "ainda juntando a sessao anterior"}
        alvo = ATUAL
        if alvo is None:
            return {"ok": False, "erro": "nada gravando"}
        alvo.fechar_parte()
        m = alvo.meta
        while m.get("pausas") and m["pausas"][-1].get("fim") is None:
            m["pausas"][-1]["fim"] = agora()
        m["estado"] = "descartada"
        m["descartada"] = True
        m["descartada_em"] = iso(agora())
        m["fim"] = agora()
        m["fim_iso"] = iso(m["fim"])
        alvo.salvar()
        alvo.fechar_arquivos()
        ATUAL = None
        esquecer_pendentes()
        destino_dir = SESSOES / PASTA_DESCARTADAS
        destino_dir.mkdir(exist_ok=True)
        destino = destino_dir / alvo.pasta.name
        k = 2
        while destino.exists():
            destino = destino_dir / ("%s_%d" % (alvo.pasta.name, k))
            k += 1
        movida = mover(alvo.pasta, destino)
        final = destino if movida else alvo.pasta
    log_geral("CANCELOU %s (descartada pelo painel, %s; %d parte(s), %.1f s gravados)" % (
        alvo.pasta.name, ("movida pra %s" % final) if movida else "NAO consegui mover: ficou no lugar, marcada descartada",
        len(m.get("partes") or []), sum(_dur_parte(p) for p in m.get("partes") or [])))
    return {"ok": True, "estado": "parado", "descartada": True, "pasta": str(final), "sessao": final.name, "movida": movida}


# ------------------------------------------------------------------ acoes
def iniciar(dados):
    global ATUAL
    with TRAVA:
        if FINALIZANDO:
            return {"ok": False, "erro": "ainda juntando a sessao anterior; tente em alguns segundos"}
        if ATUAL is not None:
            if ATUAL.meta["estado"] == "pausado":
                return retomar()
            return dict(status(), aviso="ja estava gravando")
        cfg = ler_config()
        seq = dados.get("sequencia") or ""
        quando = datetime.now()
        nome = "%s_%s" % (quando.strftime("%Y-%m-%d_%H%M"), nome_limpo(seq))
        SESSOES.mkdir(parents=True, exist_ok=True)
        pasta = SESSOES / nome
        k = 2
        while pasta.exists():
            pasta = SESSOES / ("%s_%d" % (nome, k))
            k += 1
        pasta.mkdir(parents=True)
        som_pc = bool(cfg.get("gravar_som_pc", True))
        lib_ok, lib = som_pc_disponivel() if som_pc else (False, "")
        meta = {"app": "CORRETOR", "versao": VERSAO, "estado": "gravando",
                "projeto": dados.get("projeto") or "", "projeto_caminho": dados.get("projeto_caminho") or "",
                "sequencia": seq, "sequencia_id": dados.get("sequencia_id") or "",
                "inicio": agora(), "inicio_iso": iso(agora()), "fim": None, "fim_iso": None,
                "dispositivo": microfone(cfg), "gravar_tela": bool(cfg.get("gravar_tela", True)),
                "tela_fps": cfg.get("tela_fps", 5), "tela_largura": int(cfg.get("tela_largura", 3840)),
                "gravar_som_pc": som_pc, "dispositivo_saida": str(cfg.get("dispositivo_saida") or ""),
                "som_pc_lib": lib if lib_ok else "", "som_pc_falso": bool(cfg.get("teste_som_pc_falso")),
                "partes": [], "pausas": [], "eventos": 0,
                "painel_versao": PAINEL["versao"]}
        ATUAL = Sessao(pasta, meta)
        ATUAL.abrir_parte(cfg)
        esquecer_pendentes()
        log_geral("iniciou %s (mic: %s · som do PC: %s)" % (pasta.name, meta["dispositivo"] or "nenhum",
                  ("desligado no config" if not som_pc else (lib if lib_ok else "NAO: " + lib))))
        return status()


def pausar():
    with TRAVA:
        if ATUAL is None:
            return {"ok": False, "erro": "nada gravando"}
        if ATUAL.meta["estado"] != "gravando":
            return dict(status(), aviso="ja estava pausado")
        ATUAL.fechar_parte()
        ATUAL.meta["pausas"].append({"inicio": ATUAL.meta["partes"][-1]["fim"], "fim": None,
                                     "t_gravacao": round(ATUAL.total_gravado(), 3)})
        ATUAL.meta["estado"] = "pausado"
        ATUAL.salvar()
        return status()


def retomar():
    with TRAVA:
        if ATUAL is None:
            return {"ok": False, "erro": "nada pra retomar"}
        if ATUAL.meta["estado"] != "pausado":
            return dict(status(), aviso="ja estava gravando")
        if ATUAL.meta["pausas"] and ATUAL.meta["pausas"][-1]["fim"] is None:
            ATUAL.meta["pausas"][-1]["fim"] = agora()
        ATUAL.abrir_parte(ler_config())
        return status()


def _alinhar_e_juntar(pasta, meta):
    """Cada parte vira um pedaco com EXATAMENTE a duracao de parede dela (o atraso de abertura
    do dispositivo vira silencio/quadro congelado no comeco), depois concat. Assim o segundo N
    do audio.wav/tela.mp4 = t_gravacao N dos eventos. Parte sem arquivo = silencio/preto."""
    saidas = {}
    if not FFMPEG:
        return {"erro": "sem ffmpeg: partes ficaram soltas"}
    tmp = pasta / "_juntar"
    tmp.mkdir(exist_ok=True)
    partes = [p for p in meta["partes"] if p.get("fim") is not None and p["fim"] > p["inicio"] and not p.get("apagada")]
    larg = int(meta.get("tela_largura") or ler_config().get("tela_largura", 3840))

    def rodar(cmd):
        r = subprocess.run(cmd, capture_output=True, timeout=1800, creationflags=SEM_JANELA | ABAIXO_DO_NORMAL)
        if r.returncode != 0:
            with open(pasta / "ffmpeg.log", "ab") as f:
                f.write(b"\n=== juntar falhou: " + subprocess.list2cmdline(cmd).encode("utf-8") + b"\n" + (r.stderr or b"")[-3000:])
        return r.returncode == 0

    # --- audio
    tem_audio = any((pasta / p["audio"]).exists() and (duracao(pasta / p["audio"], wav=True) or 0) > 0.05 for p in partes)
    if tem_audio:
        lista = []
        for p in partes:
            dw = p["fim"] - p["inicio"]
            src = pasta / p["audio"]
            da = duracao(src, wav=True)
            dst = tmp / ("a%02d.wav" % p["n"])
            if da and da > 0.05:
                # o que falta no arquivo e atraso de abertura (vai pro COMECO); se o ffmpeg morreu no
                # meio, so conta ate a hora em que morreu e o resto vira silencio no FIM (apad)
                atraso = max(0.0, _vivo_ate(p, "mic_caiu_em", dw) - da)
                p["atraso_audio"] = round(atraso, 3)
                ok = rodar([FFMPEG, "-hide_banner", "-v", "error", "-y", "-ignore_length", "1", "-i", str(src),
                            "-af", "adelay=%d:all=1,apad=whole_dur=%.3f" % (int(round(atraso * 1000)), dw),
                            "-t", "%.3f" % dw, "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(dst)])
            else:
                ok = False
            if not ok:
                p["audio_vazio"] = True
                ok = rodar([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "anullsrc=r=48000:cl=mono", "-t", "%.3f" % dw, "-c:a", "pcm_s16le", str(dst)])
            if ok:
                lista.append(dst)
        if lista and _concat(lista, pasta / "audio.wav", tmp / "lista_a.txt", rodar):
            saidas["audio"] = "audio.wav"
            saidas["audio_dur"] = duracao(pasta / "audio.wav")
    # --- som do PC (pc.wav): mesma regra do microfone (cada parte = exatamente a duracao de parede dela), mas a
    #     parte pode ter VARIOS segmentos (a saida trocou no meio: fone Bluetooth etc.), cada um no formato da sua
    #     saida. Cada segmento entra no instante dele (offset = atraso de abertura / volta depois da troca), o
    #     buraco entre eles e o fim viram silencio. Sai mono 48 kHz 16 bits, como o audio.wav.
    if meta.get("gravar_som_pc"):
        for p in partes:
            if p.get("pc") and "pc_segmentos" not in p:
                _anotar_pc(pasta, p)          # sessao fechada pelo disco (servidor caiu): le o manifesto agora

        def segs_validos(p, dw):
            return [s for s in (p.get("pc_segmentos") or []) if s.get("offset", 0) < dw
                    and (pasta / s["arquivo"]).exists() and (duracao(pasta / s["arquivo"], wav=True) or 0) > 0.02]
        if any(segs_validos(p, p["fim"] - p["inicio"]) for p in partes):
            lista = []
            for p in partes:
                dw = p["fim"] - p["inicio"]
                dst = tmp / ("p%02d.wav" % p["n"])
                segs = segs_validos(p, dw)
                ok = False
                if segs:
                    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y"]
                    filtros = []
                    for i, s in enumerate(segs):
                        cmd += ["-ignore_length", "1", "-i", str(pasta / s["arquivo"])]
                        filtros.append("[%d:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=mono,adelay=%d:all=1[s%d]"
                                       % (i, int(round(max(0.0, s.get("offset", 0)) * 1000)), i))
                    if len(segs) > 1:
                        filtros.append("".join("[s%d]" % i for i in range(len(segs))) +
                                       "amix=inputs=%d:normalize=0:duration=longest[m]" % len(segs))
                        ultimo = "m"
                    else:
                        ultimo = "s0"
                    filtros.append("[%s]apad=whole_dur=%.3f[o]" % (ultimo, dw))
                    ok = rodar(cmd + ["-filter_complex", ";".join(filtros), "-map", "[o]", "-t", "%.3f" % dw,
                                      "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(dst)])
                if not ok:
                    p["pc_vazio"] = True
                    ok = rodar([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                                "anullsrc=r=48000:cl=mono", "-t", "%.3f" % dw, "-c:a", "pcm_s16le", str(dst)])
                if ok:
                    lista.append(dst)
            if lista and _concat(lista, pasta / "pc.wav", tmp / "lista_p.txt", rodar):
                saidas["pc"] = "pc.wav"
                saidas["pc_dur"] = duracao(pasta / "pc.wav")
                pico = max([p.get("pc_pico") or 0 for p in partes] or [0])
                saidas["pc_pico"] = pico
                saidas["pc_pico_db"] = round(20 * math.log10(pico / 32768.0), 1) if pico > 0 else None
                saidas["pc_seg_com_som"] = round(sum(p.get("pc_seg_com_som") or 0 for p in partes), 1)
    # --- tela
    tem_tela = meta.get("gravar_tela") and any((duracao(pasta / p["tela"]) or 0) > 0.3 for p in partes)
    if tem_tela:
        lista = []
        fps = str(meta.get("tela_fps") or 5)
        alt = None
        for p in partes:
            dv = duracao(pasta / p["tela"])
            if dv:
                alt = alt or _altura(pasta / p["tela"])
        alt = alt or int(larg * 9 / 16) // 2 * 2
        # quadros por parte pela soma ACUMULADA: a 2 fps cada parte arredondava pra 0,5 s; sem isto o erro
        # somava a cada pausa (medido 13/10: 2 partes ja davam +0,8 s no fim)
        fps_f = float(fps)
        acumulado, quadros = 0.0, 0
        for p in partes:
            dw = p["fim"] - p["inicio"]
            acumulado += dw
            nq = int(round(acumulado * fps_f)) - quadros
            if nq <= 0:
                continue
            quadros += nq
            src = pasta / p["tela"]
            dv = duracao(src)
            dst = tmp / ("v%02d.mp4" % p["n"])
            comum = ["-r", fps, "-frames:v", str(nq), "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-g", "20",
                     "-pix_fmt", "yuv420p", "-threads", "2", "-an", str(dst)]
            ok = False
            if dv and dv > 0.3:
                atraso = max(0.0, _vivo_ate(p, "tela_caiu_em", dw) - dv)
                if p.get("recuperada"):
                    # servidor caiu: o mp4 perde o FIM (fragmento de 2 s nao gravado), nao o comeco.
                    # O gdigrab abre na hora (medido 13/10: atraso 0,0 nas partes normais)
                    atraso = 0.0
                p["atraso_tela"] = round(atraso, 3)
                ok = rodar([FFMPEG, "-hide_banner", "-v", "error", "-y", "-i", str(src), "-vf",
                            "scale=%d:%d,tpad=start_duration=%.3f:start_mode=clone:stop_duration=%.3f:stop_mode=clone"
                            % (larg, alt, atraso, dw + 1)] + comum)
            if not ok:
                p["tela_vazia"] = True
                ok = rodar([FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i",
                            "color=c=black:s=%dx%d:r=%s" % (larg, alt, fps)] + comum)
            if ok:
                lista.append(dst)
        if lista and _concat(lista, pasta / "tela.mp4", tmp / "lista_v.txt", rodar, mp4=True):
            saidas["tela"] = "tela.mp4"
            saidas["tela_dur"] = duracao(pasta / "tela.mp4")
    shutil.rmtree(tmp, ignore_errors=True)
    # as partes sao copia do que ja esta junto: so apagar se a saida conferiu. Parte fechada pelo
    # disco (servidor caiu) tem o fim ESTIMADO: a conferencia nao vale, entao as partes ficam.
    total = sum(p["fim"] - p["inicio"] for p in partes)
    estimada = any(p.get("recuperada") for p in partes)
    if estimada:
        saidas["aviso_partes"] = "sessao com parte fechada pelo disco (servidor caiu): partes mantidas"
    for chave, campo in (("audio_dur", "audio"), ("tela_dur", "tela"), ("pc_dur", "pc")):
        d = saidas.get(chave)
        if estimada:
            continue
        if d is not None and abs(d - total) < 1.5:
            for p in partes:
                if campo == "pc":
                    arqs = [s["arquivo"] for s in p.get("pc_segmentos") or []] + (["pc%02d.json" % p["n"]] if p.get("pc") else [])
                else:
                    arqs = [p.get(campo)]
                for a in arqs:
                    try:
                        if a:
                            (pasta / a).unlink()
                    except OSError:
                        pass
        elif d is not None:
            saidas["aviso_" + campo] = "duracao %.2f s difere do gravado %.2f s: partes mantidas" % (d, total)
    return saidas


def _vivo_ate(p, campo, dw):
    """Segundos da parte em que o ffmpeg estava vivo (dw se nao morreu antes do fim)."""
    caiu = p.get(campo)
    if caiu is None:
        return dw
    return min(dw, max(0.0, caiu - p["inicio"]))


def _ler_manifesto_pc(pasta, n):
    try:
        return json.loads((Path(pasta) / ("pc%02d.json" % n)).read_text(encoding="utf-8"))
    except Exception:
        return None


def _anotar_pc(pasta, p, saiu_em=None):
    """Copia pro sessao.json (parte) o que o gravar_pc.py anotou no manifesto pcNN.json: segmentos com o offset
    (segundos depois do inicio da parte em que cada um comeca), saidas usadas, trocas/erros com o t_gravacao,
    pico e segundos com som. pc_ok = gravou pelo menos um segmento."""
    m = _ler_manifesto_pc(pasta, p["n"])
    inicio, t0 = p["inicio"], p.get("t0") or 0.0
    if m is None:
        if (Path(pasta) / p["pc"]).exists():
            # sem manifesto (nao devia acontecer: ele sai antes do 1o pacote): assume que comecou no inicio da parte
            p["pc_segmentos"] = [{"arquivo": p["pc"], "offset": 0.0}]
            p["pc_ok"] = True
            p["erro_pc"] = "manifesto pc%02d.json sumiu: alinhamento estimado (offset 0)" % p["n"]
        else:
            p["pc_segmentos"] = []
            p["pc_ok"] = False
            p["erro_pc"] = p.get("erro_pc") or "o gravador do som do PC nao deixou arquivo nem manifesto (ver som_pc.log)"
        return
    segs = []
    for s in m.get("segmentos") or []:
        segs.append({"arquivo": s.get("arquivo"), "offset": round((s.get("t0") or inicio) - inicio, 3),
                     "taxa": s.get("taxa"), "canais": s.get("canais"), "dispositivo": s.get("dispositivo") or "",
                     "dur": s.get("dur")})
    p["pc_segmentos"] = segs
    p["pc_dispositivos"] = list(dict.fromkeys(s["dispositivo"] for s in segs if s["dispositivo"]))
    p["atraso_pc"] = m.get("atraso")
    p["pc_pico"] = m.get("pico") or 0
    p["pc_seg_com_som"] = m.get("seg_com_som") or 0.0
    p["pc_lib"] = m.get("lib") or ""
    evs = []
    for e in m.get("eventos") or []:
        if e.get("o_que") == "tom":       # so no teste (--falso): rajada de tom gerada, pra conferir o alinhamento
            evs.append({"o_que": "tom", "t_inicio": round(t0 + e["inicio"] - inicio, 3), "t_fim": round(t0 + e["fim"] - inicio, 3)})
        elif e.get("o_que") in ("trocou", "erro", "aviso"):
            evs.append({"o_que": e["o_que"], "t_gravacao": round(t0 + max(0.0, min((e.get("quando") or inicio), p.get("fim") or 1e18) - inicio), 3),
                        "msg": e.get("msg") or ""})
    p["pc_eventos"] = evs
    # revisao 14/10: stream que parou sozinho e reabriu no MESMO aparelho (nao e troca de saida)
    p["pc_reaberturas"] = sum(1 for e in m.get("eventos") or [] if e.get("o_que") == "reabriu")
    p["pc_ok"] = bool(segs)
    if not segs:
        p["erro_pc"] = m.get("erro") or p.get("erro_pc") or "o loopback nao abriu (ver som_pc.log)"
    else:
        p["erro_pc"] = ""
    if not m.get("terminou") and saiu_em is not None and p.get("fim") and saiu_em < p["fim"] - 0.3:
        # o gravador morreu no meio da parte: o resto vira silencio (apad no fim, como o mic que cai)
        p["pc_caiu_em"] = round(saiu_em, 3)
        p["erro_pc"] = "o gravador do som do PC parou aos %.1f s da parte (ver som_pc.log)" % (saiu_em - inicio)


def _fechar_pelo_disco(pasta, p):
    """Parte que ficou aberta (servidor caiu): o fim e o MAIOR entre a duracao do audio, a da tela, a do som
    do PC (offset + duracao de cada segmento: ele cresce pelo relogio) e a ultima escrita em disco. Nunca o
    primeiro que responder: um wav cortado no buffer daria um fim curto demais e a tela seria cortada junto
    (achado da revisao 13/10)."""
    arqs = [pasta / p["audio"], pasta / p["tela"]]
    cands = [duracao(arqs[0], wav=True), duracao(arqs[1])]
    if p.get("pc"):
        m = _ler_manifesto_pc(pasta, p["n"]) or {}
        for s in m.get("segmentos") or []:
            d = duracao(pasta / s.get("arquivo", ""), wav=True)
            if d is not None and s.get("t0"):
                cands.append(s["t0"] - p["inicio"] + d)
                arqs.append(pasta / s["arquivo"])
    mts = [a.stat().st_mtime for a in arqs if a.exists()]
    if mts:
        cands.append(max(mts) - p["inicio"])
    d = max([c for c in cands if c is not None] or [0.0])
    p["fim"] = p["inicio"] + max(0.0, d)
    p["dur"] = round(max(0.0, d), 3)
    p["recuperada"] = True


def _altura(arquivo):
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height",
                            "-of", "default=nw=1:nk=1", str(arquivo)], capture_output=True, timeout=30, creationflags=SEM_JANELA)
        h = int((r.stdout or b"0").decode().strip().splitlines()[0])
        return h if h > 0 else None
    except Exception:
        return None


def _concat(arquivos, destino, lista, rodar, mp4=False):
    lista.write_text("".join("file '%s'\n" % str(a).replace("\\", "/").replace("'", "'\\''") for a in arquivos), encoding="utf-8")
    cmd = [FFMPEG, "-hide_banner", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy"]
    if mp4:
        cmd += ["-movflags", "+faststart"]
    return rodar(cmd + [str(destino)])


def _finalizar(sessao_ou_pasta):
    """Fecha arquivos, junta partes, escreve resumo. Roda FORA da trava (pode levar segundos)."""
    if isinstance(sessao_ou_pasta, Sessao):
        pasta, meta = sessao_ou_pasta.pasta, sessao_ou_pasta.meta
    else:
        pasta = Path(sessao_ou_pasta)
        meta = json.loads((pasta / "sessao.json").read_text(encoding="utf-8"))
        # sessao que o servidor largou no meio: fecha a parte aberta pelo que estiver no disco
        for p in meta.get("partes", []):
            if p.get("fim") is None:
                _fechar_pelo_disco(pasta, p)
        meta["recuperada"] = True
        fins = [p["fim"] for p in meta.get("partes", []) if p.get("fim")]
        meta["fim"] = meta.get("fim") or (max(fins) if fins else None)
        try:
            with open(pasta / "eventos.jsonl", encoding="utf-8", errors="replace") as f:
                meta["eventos"] = sum(1 for linha in f if linha.strip())
        except OSError:
            pass
    meta["fim"] = meta.get("fim") or agora()
    meta["fim_iso"] = iso(meta["fim"])
    # pausa no fim (o Concluir pausa antes de juntar, ou ele pausou e concluiu depois) nao separa nada
    while meta.get("pausas") and meta["pausas"][-1].get("fim") is None:
        meta["pausas"].pop()
    # 0.3.0: pedacos que ele apagou no painel saem da juncao, dos eventos e do resumo (tempos recontados)
    try:
        tirar_pedacos_apagados(pasta, meta)
    except Exception:
        log_geral("tirar pedacos apagados de %s: %s" % (pasta.name, traceback.format_exc()))
        # nunca juntar um pedaco apagado: na falha, pelo menos a juncao fica sem ele (os tempos ficam brutos)
        meta.setdefault("pedacos_apagados", []).extend(dict(p, falhou_recontar=True) for p in meta["partes"] if p.get("apagada"))
        meta["partes"] = [p for p in meta["partes"] if not p.get("apagada")]
    meta["t_gravado"] = round(sum(p["fim"] - p["inicio"] for p in meta["partes"] if p.get("fim")), 3)
    try:
        meta["saidas"] = _alinhar_e_juntar(pasta, meta)
    except Exception as e:
        meta["saidas"] = {"erro": "juntar: %s" % e}
        log_geral(traceback.format_exc())
    try:
        import resumo
        texto = resumo.gerar(pasta, meta)
        (pasta / "resumo.md").write_text(texto, encoding="utf-8")
        meta["saidas"]["resumo"] = "resumo.md"
    except Exception as e:
        meta["saidas"]["erro_resumo"] = str(e)
        log_geral(traceback.format_exc())
        with open(pasta / "painel.log", "a", encoding="utf-8") as f:
            f.write("resumo falhou:\n" + traceback.format_exc())
    meta["estado"] = "concluida"
    tmp = pasta / "sessao.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    substituir(tmp, pasta / "sessao.json")
    return meta


def concluir(dados=None):
    global ATUAL, ULTIMA, FINALIZANDO
    dados = dados or {}
    with TRAVA:
        if FINALIZANDO:
            return {"ok": False, "erro": "ja esta juntando"}
        alvo = ATUAL
        if alvo is None:
            pend = pendentes()
            escolhida = dados.get("pasta") or (pend[-1] if pend else None)
            if not escolhida:
                return {"ok": False, "erro": "nada gravando"}
            alvo = Path(escolhida)
        else:
            alvo.fechar_parte()
            alvo.meta["estado"] = "finalizando"
            alvo.salvar()
            alvo.fechar_arquivos()
        FINALIZANDO = True
        FINALIZANDO_PASTA[0] = alvo.pasta if isinstance(alvo, Sessao) else Path(alvo)
        ATUAL = None
    try:
        meta = _finalizar(alvo)
    finally:
        with TRAVA:
            FINALIZANDO = False
            FINALIZANDO_PASTA[0] = None
            esquecer_pendentes()
    pasta = alvo.pasta if isinstance(alvo, Sessao) else alvo
    with TRAVA:
        ULTIMA = pasta
    log_geral("concluiu %s (%s eventos, %.1f s)" % (pasta.name, meta.get("eventos"), meta.get("t_gravado", 0)))
    arquivos = sorted(x.name for x in pasta.iterdir() if x.is_file())
    return {"ok": True, "estado": "parado", "pasta": str(pasta), "sessao": pasta.name, "arquivos": arquivos,
            "t_gravado": meta.get("t_gravado"), "eventos": meta.get("eventos"), "saidas": meta.get("saidas")}


# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, codigo=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        bruto = self.rfile.read(n)
        for cod in ("utf-8", "cp1252"):        # cp1252: curl do Git Bash manda acento assim
            try:
                v = json.loads(bruto.decode(cod))
                return v if isinstance(v, dict) else {"_": v}
            except Exception:
                continue
        return {"_texto": bruto.decode("utf-8", "replace")}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        rota, _, query = self.path.partition("?")
        try:
            if rota in ("/", "/status"):
                return self._json(status())
            if rota == "/dispositivos":
                return self._json({"ok": True, "dispositivos": listar_dispositivos(),
                                   "escolhido": microfone(ler_config()), "config": ler_config(),
                                   "saidas_de_som": listar_saidas_de_som()})
            if rota == "/comando":
                with TRAVA:
                    PAINEL["visto"] = agora()
                    m = re.search(r"(?:^|&)p=([^&]*)", query)
                    if m:
                        from urllib.parse import unquote
                        PAINEL["versao"] = unquote(m.group(1))
                    acao = COMANDOS.pop(0) if COMANDOS else None
                    return self._json(dict(status(), acao=acao))
            return self._json({"ok": False, "erro": "rota desconhecida"}, 404)
        except Exception as e:
            log_geral("GET %s: %s" % (rota, traceback.format_exc()))
            return self._json({"ok": False, "erro": str(e)}, 500)

    def do_POST(self):
        rota = self.path.partition("?")[0]
        dados = self._corpo()
        try:
            if rota == "/iniciar":
                return self._json(iniciar(dados))
            if rota == "/pausar":
                return self._json(pausar())
            if rota == "/retomar":
                return self._json(retomar())
            if rota == "/concluir":
                return self._json(concluir(dados))
            if rota == "/cancelar":                       # 0.3.0
                return self._json(cancelar())
            if rota == "/apagar_pedaco":                  # 0.3.0
                return self._json(apagar_pedaco(dados))
            if rota == "/voltar_pedaco":                  # 0.3.0
                return self._json(apagar_pedaco(dados, voltar=True))
            if rota == "/eventos":
                evs = dados.get("eventos") or []
                with TRAVA:
                    if ATUAL is None:
                        return self._json({"ok": False, "erro": "sem sessao", "descartados": len(evs)})
                    n = ATUAL.gravar_eventos(evs)
                    return self._json({"ok": True, "gravados": n, "eventos": ATUAL.n_eventos,
                                       "t_gravacao": round(ATUAL.total_gravado(), 2)})
            if rota == "/log":
                nivel = str(dados.get("nivel") or "info")
                msg = str(dados.get("msg") or dados.get("_texto") or "")
                with TRAVA:
                    if ATUAL is not None:
                        ATUAL.log_painel(nivel, msg)
                    else:
                        log_geral("painel [%s] %s" % (nivel, msg))
                return self._json({"ok": True})
            if rota == "/sonda":
                linhas = dados.get("linhas") or [dados.get("msg") or dados.get("_texto") or ""]
                with TRAVA:
                    with open(BASE / "sonda.log", "a", encoding="utf-8") as f:
                        for linha in linhas:
                            f.write("%s  %s\n" % (datetime.now().strftime("%H:%M:%S.%f")[:-3], str(linha)))
                return self._json({"ok": True, "gravadas": len(linhas)})
            if rota == "/comando":
                acao = str(dados.get("acao") or "").strip().lower()
                if acao not in ACOES_REMOTAS:
                    return self._json({"ok": False, "erro": "acao deve ser uma de: " + ", ".join(ACOES_REMOTAS)}, 400)
                with TRAVA:
                    COMANDOS.append(acao)
                    visto = PAINEL["visto"]
                aviso = None if visto and agora() - visto < 3 else "o painel nao consultou nos ultimos 3 s: esta aberto no Premiere?"
                return self._json({"ok": True, "fila": len(COMANDOS), "aviso": aviso})
            return self._json({"ok": False, "erro": "rota desconhecida"}, 404)
        except Exception as e:
            log_geral("POST %s: %s" % (rota, traceback.format_exc()))
            return self._json({"ok": False, "erro": str(e)}, 500)


def _contar_linhas(arq):
    try:
        with open(arq, encoding="utf-8", errors="replace") as f:
            return sum(1 for linha in f if linha.strip())
    except OSError:
        return 0


def reabrir_no_boot():
    """Servidor que caiu (ou foi reiniciado) no meio de uma sessao: a MAIS RECENTE que estava
    gravando/pausada volta como a sessao atual, PAUSADA (a parte aberta fecha pelo disco). O painel
    mostra Retomar/Concluir e os eventos que ele guardou na fila caem na mesma pasta.
    As outras largadas (antigas, ou que cairam no meio do juntar) sao fechadas em segundo plano."""
    global ATUAL
    achadas = []
    for js in SESSOES.glob("*/sessao.json"):
        try:
            m = json.loads(js.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("estado") in ("gravando", "pausado", "finalizando"):
            achadas.append((m.get("inicio") or 0, js.parent, m))
    achadas.sort(key=lambda x: x[0])
    reabrir = None
    for _, pasta, m in reversed(achadas):
        if m.get("estado") in ("gravando", "pausado"):
            reabrir = (pasta, m)
            break
    if reabrir:
        pasta, meta = reabrir
        try:
            aberta = False
            for p in meta.get("partes", []):
                if p.get("fim") is None:
                    _fechar_pelo_disco(pasta, p)
                    aberta = True
            total = round(sum(p["fim"] - p["inicio"] for p in meta.get("partes", []) if p.get("fim") is not None), 3)
            if aberta or meta.get("estado") == "gravando":
                # caiu GRAVANDO (reiniciar com a sessao pausada nao perde nada e nao vira queda)
                meta.setdefault("quedas", []).append({"quando": iso(agora()), "t_gravacao": total})
            if aberta or not (meta.get("pausas") and meta["pausas"][-1].get("fim") is None):
                ultimo = max([p["fim"] for p in meta.get("partes", []) if p.get("fim") is not None] or [agora()])
                meta.setdefault("pausas", []).append({"inicio": ultimo, "fim": None, "t_gravacao": total, "queda": True})
            meta["estado"] = "pausado"
            meta["eventos"] = _contar_linhas(pasta / "eventos.jsonl")
            with TRAVA:
                ATUAL = Sessao(pasta, meta)
                ATUAL.salvar()
            log_geral("reabriu %s PAUSADA depois de queda (%.1f s gravados, %d eventos)" % (pasta.name, total, meta["eventos"]))
        except Exception:
            log_geral("nao reabriu %s: %s" % (pasta.name, traceback.format_exc()))
    outras = [pasta for _, pasta, _ in achadas if not reabrir or pasta != reabrir[0]]
    if outras:
        for pasta in outras:
            FECHANDO_NO_BOOT.add(str(pasta))

        def fechar_todas():
            for pasta in outras:
                try:
                    _finalizar(pasta)
                    log_geral("fechou no boot a sessao largada %s" % pasta.name)
                except Exception:
                    log_geral("nao fechou %s: %s" % (pasta.name, traceback.format_exc()))
                finally:
                    FECHANDO_NO_BOOT.discard(str(pasta))
                    esquecer_pendentes()
        threading.Thread(target=fechar_todas, daemon=True).start()


def main():
    SESSOES.mkdir(parents=True, exist_ok=True)
    ler_config()
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    except OSError as e:
        log_geral("porta %d ocupada (%s): ja tem um servidor no ar" % (PORTA, e))
        sys.exit(1)
    srv.daemon_threads = True
    reabrir_no_boot()      # depois de pegar a porta: um segundo servidor que nao subiu nao mexe em nada
    log_geral("CORRETOR %s no ar em 127.0.0.1:%d (ffmpeg: %s · som do PC: %s)" % (
        VERSAO, PORTA, FFMPEG or "NAO ACHADO", (lambda r: r[1] if r[0] else "NAO: " + r[1])(som_pc_disponivel())))
    try:
        srv.serve_forever()
    finally:
        with TRAVA:
            if ATUAL is not None:
                ATUAL.fechar_parte()
                ATUAL.meta["estado"] = "pausado"
                ATUAL.salvar()


if __name__ == "__main__":
    main()
