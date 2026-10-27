# -*- coding: utf-8 -*-
"""KAKASHI ÚNICO — fase 1 (19/10/2026). Desenho: apps\\CORRETOR\\DESENHO-KAKASHI-UNICO.md (aprovado por ele: "Pode").

Pedido dele: "um atalho pra eu poder começar a gravar, sem ter que clicar em nada, tipo o Whisper... aperto o atalho de novo pra parar"
+ "fica aqui o Whisper do lado, você coloca o Sharinganzinho do Kakashi rodando, pra eu saber que tá rodando".

- Ctrl+Page Down   = começa / conclui.      Ctrl+Shift+Page Down = cancela (vai pra _descartadas, nunca apaga).
  (era Ctrl+Alt+K; ele trocou em 19/10: "coloca Ctrl + Page Down")
- Sharingan no canto (do lado da bolinha do Whisper): parado e apagado = pronto; vermelho girando + relógio = gravando.
  Clique = começa/conclui. Arrastar = muda de lugar (fica lembrado). Botão direito = cancelar / sair.
- O TIPO sai da janela da frente na hora do atalho:
    Premiere (com o painel do KAKASHI aberto) → manda o painel gravar (CORRETOR 7815, o rastro da timeline é dele)
    Luluka                                    → o gravador do Luluka (7798, rastro dos cartões e do quiz)
    qualquer outra coisa                      → grava aqui: microfone + som do PC + tela + janela da frente + cliques
- Gravação esquecida (o caso dos 47 min de 19/10): 10 min sem voz → o Sharingan pisca amarelo.
- OLHO DE DEUS (P3, 21/10, aprovado por ele; peças em olho.py), no tipo "pc", sem tecla nenhuma a mais:
    caminho do mouse (~0,25 s, só quando mexe) · elemento debaixo do mouse (UI Automation) na pausa >0,8 s e em todo clique ·
    card do Luluka sob o mouse (o Luluka manda pra porta 7816) · print NATIVO + recorte 800x500 na pausa, na fala e a cada página nova ·
    o que ele copia (texto, link, imagem, Win+Shift+S; senha nunca) · links do Chrome no fim (+ imagem dos pins) ·
    REPLAY: os últimos 2 min (tela + voz + som do PC) ficam num disco rotativo e entram no começo da gravação (config "replay": false desliga)
- GRAVAÇÃO MUDA (P20, 21/10): voz do buffer em silêncio digital 60 s → reabre só o microfone · no atalho, buffer mudo →
  o microfone dele fecha antes da captura nova + "replay_sem_voz" · gravando mudo 15 s → Sharingan cinza + "SEM SOM" ·
  saída de som trocada no meio → um pc.wav só · ffmpeg órfão de buffer antigo é encerrado (LEIA-ME, seção P20)
- TROCA SOZINHA PRO PREMIERE (23/10; ele: "Sim, óbvio", depois de "Eu não tô no PC, ó. Aí como é que eu faço? É difícil, né?"):
    gravando como PC e o Premiere fica na frente 1,5 s com o painel do KAKASHI vivo → o painel começa a gravar e, SÓ depois de
    ele estar gravando, a parte PC fecha (sessao.json: continua_em = "premiere", troca_epoch). As duas são UMA correção:
    Ctrl+Page Down conclui a do Premiere; Ctrl+Shift+Page Down cancela as duas. Config "troca_premiere": false desliga.
- OLHO NO PREMIERE (23/10 noite; ele: "faz o Kakashi ser o mais completo possível... É o olho de Deus, mano, é minha tela"):
    enquanto o painel do Premiere grava (7815 gravando/pausado), o olho do PC (mouse, elemento sob o mouse, print nativo, cópias,
    links do Chrome) grava junto em <sessão do CORRETOR>\\_olho, no RELÓGIO do painel (t_gravacao, pausas tiradas). Pausado = não
    grava nada. No fim liga fala.wav/tela.mp4/pc.wav do painel (hardlink) e escreve sessao.json (tipo pc, olho_premiere) → o
    resumo_pc.py lê a _olho como uma sessão PC. Abre/fecha o arquivo a cada evento: o painel pode mover a pasta (descartada).
    Gravação PC ativa tem prioridade (alvo = PC). Config "olho_premiere": false desliga.
- Porta 7816: GET /status (estado: gravando/parado — o Claude confere antes de reiniciar) · POST /luluka (card sob o mouse)
Só CPU. Nunca toca som.
"""
import array, collections, ctypes, ctypes.wintypes as wt, datetime, glob, json, os, queue, re, shutil, subprocess, sys, threading, time
import tkinter as tk
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import olho  # noqa: E402
import atalho  # noqa: E402   # pacote da Fly (27/10): o atalho que a pessoa escolher
import atualizar  # noqa: E402   # pacote da Fly (27/10): versão nova no GitHub da Fly
SESSOES = os.path.join(AQUI, "sessoes")
PORTA = 7816
CFG = os.path.join(AQUI, "config.json")
CORRETOR = AQUI   # pacote da Fly: gravar_pc.py, config.json e painel\icones vêm junto, na mesma pasta
PY = (os.path.join(os.path.dirname(sys.executable), "python.exe")
      if os.path.isfile(os.path.join(os.path.dirname(sys.executable), "python.exe")) else sys.executable)
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
SEM_JANELA = 0x08000000
LOG = os.path.join(AQUI, "kakashi.log")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%d/%m %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def cfg():
    try:
        return json.load(open(CFG, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_cfg(c):
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)


def http(url, corpo=None, t=3):
    try:
        req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Content-Type": "application/json"}, method="POST" if corpo is not None else "GET")
        return json.load(urllib.request.urlopen(req, timeout=t))
    except Exception:
        return None


# ---------- janela da frente ----------
def janela_frente(hwnd=None):
    hwnd = hwnd or user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, b, n + 1)
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    h = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(520); tam = wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
            exe = os.path.basename(buf.value)
        kernel32.CloseHandle(h)
    return {"app": exe, "titulo": b.value}


def _pid_da_janela(hwnd):
    pid = wt.DWORD()
    if hwnd:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def tipo_da_frente():
    j = janela_frente()
    if j["app"].lower() == "pythonw.exe" and j["titulo"] in ("tk", ""):     # a própria bolinha: pega a janela de baixo dela
        hw = user32.GetWindow(user32.GetForegroundWindow(), 2)   # GW_HWNDNEXT
        while hw and not (user32.IsWindowVisible(hw) and user32.GetWindowTextLengthW(hw)):
            hw = user32.GetWindow(hw, 2)
        if hw:
            j = janela_frente(hw)
    if "premiere" in j["app"].lower():
        st = http("http://127.0.0.1:7815/status")
        if st and st.get("painel_visto_ha_s") is not None and st["painel_visto_ha_s"] < 10:
            return "premiere", j
    if re.search(r"\bLuluka\b", j["titulo"]) and http("http://127.0.0.1:7798/api/luluka/gravacao") is not None:
        return "luluka", j
    return "pc", j


# ---------- "/kakashi" no Ctrl+V e colado onde está o cursor (21/10, pedido dele) ----------
# "quando terminar a gravação, ele já deixar copiado automaticamente ... e ele já colar automático também ... aonde tiver o
# cursor ... Exatamente como o Whisper faz ... mesmo se colou em algum outro lugar, eu posso apertar um Ctrl V que vai tá lá"
# DLLs próprias: os argtypes daqui não mexem nas funções do user32 que o resto do arquivo (e o olho.py) usa.
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.GlobalAlloc.restype = ctypes.c_void_p; _k32.GlobalAlloc.argtypes = (wt.UINT, ctypes.c_size_t)
_k32.GlobalLock.restype = ctypes.c_void_p; _k32.GlobalLock.argtypes = (ctypes.c_void_p,)
_k32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
_u32.OpenClipboard.argtypes = (wt.HWND,)
_u32.SetClipboardData.restype = ctypes.c_void_p; _u32.SetClipboardData.argtypes = (wt.UINT, ctypes.c_void_p)
TEXTO_COLAR = "/kakashi"


def _copiar(texto):
    dados = (texto + "\0").encode("utf-16-le")
    for _ in range(20):                       # outro programa pode estar com a área de transferência aberta
        if _u32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        _u32.EmptyClipboard()
        h = _k32.GlobalAlloc(0x0002, len(dados))            # GMEM_MOVEABLE
        ptr = _k32.GlobalLock(h)
        ctypes.memmove(ptr, dados, len(dados))
        _k32.GlobalUnlock(h)
        return bool(_u32.SetClipboardData(13, h))           # CF_UNICODETEXT
    finally:
        _u32.CloseClipboard()


def colar_kakashi(colar=True):
    """Copia "/kakashi" e (se colar) aperta Ctrl+V na janela da frente. Espera ele soltar o Ctrl/Shift/Page Down do atalho,
    senão o Ctrl+V sai como Ctrl+Shift+V. No Premiere só copia: lá Ctrl+V cola clipe na timeline."""
    try:
        fim = time.time() + 3
        while time.time() < fim and any(_u32.GetAsyncKeyState(vk) & 0x8000 for vk in atalho.teclas_soltar()):
            time.sleep(0.03)
        if not _copiar(TEXTO_COLAR):
            log("colar: área de transferência ocupada"); return
        if colar and "premiere" not in janela_frente()["app"].lower():
            time.sleep(0.08)
            _u32.keybd_event(0x11, 0, 0, 0); _u32.keybd_event(0x56, 0, 0, 0)          # Ctrl down, V down
            _u32.keybd_event(0x56, 0, 2, 0); _u32.keybd_event(0x11, 0, 2, 0)          # V up, Ctrl up
        log("colar: %s %s" % (TEXTO_COLAR, "copiado e colado" if colar else "copiado"))
    except Exception as e:
        log("colar: %s" % e)

# ---------- microfone (mesma escolha do CORRETOR / Luluka) ----------
def microfone():
    for arq, chave in ((os.path.join(CORRETOR, "config.json"), "dispositivo_audio"),):
        try:
            v = json.load(open(arq, encoding="utf-8")).get(chave)
            if v:
                return v
        except (OSError, ValueError):
            pass
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                           capture_output=True, timeout=15, creationflags=SEM_JANELA)
        for m in re.finditer(r'"([^"]+)"\s+\((audio|video|none)\)', (r.stderr or b"").decode("utf-8", "replace")):
            if m.group(2) == "audio":
                return m.group(1)
    except Exception:
        pass
    return ""


# de onde vêm a voz, a tela e o som do PC (o teste do P20 troca por fonte nula do ffmpeg / --falso, sem tocar som nenhum)
def entrada_mic(dev):
    return ["-f", "dshow", "-audio_buffer_size", "50", "-i", "audio=" + dev]


ENTRADA_TELA = ["-f", "gdigrab", "-framerate", "5", "-draw_mouse", "1", "-i", "desktop"]
GRAVAR_PC_EXTRA = []
MUDO_AVISO_S = 15        # P20: gravando, tanto tempo em silêncio digital → o olho fica cinza e o "SEM SOM" pisca


class VozViva:
    """P20: há quanto tempo o wav da gravação está em SILÊNCIO DIGITAL (< -85 dB). O microfone sem fio dele corta pra zero
    nas pausas (até ~7,5 s nas gravações boas de 20-21/10), por isso o aviso só vem depois de MUDO_AVISO_S.
    'faltando_e_mudo': o wav nem existir conta como mudo (PC: o ffmpeg do microfone não abriu); no Luluka, não sabe."""

    def __init__(self, arq, ini, faltando_e_mudo=True):
        self.arq, self.ini, self.faltando_e_mudo = arq, ini, faltando_e_mudo
        self.ult_som = ini; self.avisou = False; self.trechos = []

    def medir(self, agora):
        if not os.path.isfile(self.arq) and not self.faltando_e_mudo:
            self.ult_som = agora
        else:
            p = olho.pico_fim([self.arq], 1.5)
            if p is not None and p >= olho.MUDO:
                if self.avisou:
                    log("a voz voltou na gravação (%.0f s em silêncio digital)" % (agora - self.ult_som))
                    self.trechos.append((self.ult_som, agora))
                self.ult_som = agora; self.avisou = False
        mudo = agora - self.ult_som
        if mudo > MUDO_AVISO_S and not self.avisou:
            self.avisou = True
            log("gravação MUDA há %.0f s (%s): o olho ficou cinza" % (mudo, os.path.basename(os.path.dirname(self.arq))))
        return mudo

    def trechos_mudos(self, t0, agora):
        """[[de, até], ...] no relógio da sessão (t0 = 0:00) dos trechos que passaram do aviso, o aberto fecha em 'agora'"""
        tr = self.trechos + ([(self.ult_som, agora)] if self.avisou else [])
        return [[round(a - t0, 1), round(b - t0, 1)] for a, b in tr]


# ---------- gravação própria (tipo "pc") ----------
class GravacaoPC:
    def __init__(self, janela, k=None, replay=None):
        """replay = o que o Replay.parar() devolveu ({fim, segundos}): o relógio da sessão começa 'segundos' antes do atalho,
        os eventos desses 2 min (que o Vigia guardou na memória) entram já, e os arquivos do replay entram no começo no concluir"""
        agora = datetime.datetime.now()
        self.k = k
        self.pasta = os.path.join(SESSOES, agora.strftime("%Y-%m-%d_%H%M%S") + "_pc")
        os.makedirs(self.pasta, exist_ok=True)
        self.t_grav = time.time()                       # o atalho (a gravação de agora em diante)
        self.replay_s = round(replay["segundos"], 2) if replay and replay.get("segundos", 0) >= 1 else 0.0
        self.t0 = (replay["fim"] - self.replay_s) if self.replay_s else self.t_grav     # 0:00 da sessão
        self.replay_arqs = None; self.replay_pronto = threading.Event()
        if not self.replay_s:
            self.replay_pronto.set()
        self.meta = {"tipo": "pc", "inicio_local": datetime.datetime.fromtimestamp(self.t0).replace(microsecond=0).isoformat(),
                     "inicio_epoch": self.t0, "gravacao_epoch": self.t_grav, "replay_s": self.replay_s,
                     "janela_inicial": janela, "erros": []}
        if replay and "sem_voz" in replay:          # P20: a voz do buffer estava em silêncio digital nos últimos ~10 s
            self.meta.update(replay_sem_voz=replay["sem_voz"], replay_voz_muda_s=replay.get("voz_muda_s"))
        self.procs = []
        self.parar_ev = threading.Event()
        self.concluida = threading.Event()              # o concluir terminou (a troca pro Premiere espera isso pra descartar junto)
        self.ev = open(os.path.join(self.pasta, "eventos.jsonl"), "a", encoding="utf-8")
        self.ev_trava = threading.Lock()
        self.hashes = set()                             # imagens já salvas (área de transferência x pasta de capturas)
        self.flog = open(os.path.join(self.pasta, "ffmpeg.log"), "ab")
        dev = microfone(); self.meta["microfone"] = dev
        if dev:
            self._abrir("fala", [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "warning"] + entrada_mic(dev) + ["-ac", "1", "-ar", "48000",
                                 "-c:a", "pcm_s16le", "-flush_packets", "1", "-y", os.path.join(self.pasta, "fala.wav")])
        else:
            self.meta["erros"].append("nenhum microfone encontrado")
        self._abrir("tela", [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "warning"] + ENTRADA_TELA +
                            ["-vf", "scale=1920:-2:flags=bilinear,format=yuv420p",
                             "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-crf", "30", "-g", "10",
                             "-threads", "2", "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
                             "-frag_duration", "2000000", "-flush_packets", "1", "-y", os.path.join(self.pasta, "tela.mp4")])
        gp = os.path.join(CORRETOR, "gravar_pc.py")
        if os.path.isfile(gp):
            self._abrir("som_pc", [PY, gp, "--pasta", self.pasta, "--parte", "1", "--inicio", "%.3f" % self.t_grav] + GRAVAR_PC_EXTRA,
                        stdout=subprocess.DEVNULL, stderr=open(os.path.join(self.pasta, "som_pc.log"), "ab"))
        if k is not None and self.replay_s:            # mouse/janela/cliques dos 2 min do replay (só estavam na memória)
            for quando, e in k.vigia.desde(self.t0):
                self._evento(e, quando)
        self._evento({"tipo": "janela", **janela, "atalho": True})
        threading.Thread(target=self._area, daemon=True).start()
        threading.Thread(target=self._capturas, daemon=True).start()
        self._salvar_meta()

    def _abrir(self, nome, cmd, stdout=subprocess.DEVNULL, stderr=None):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr or self.flog, creationflags=SEM_JANELA)
            self.procs.append((nome, p))
        except Exception as e:
            self.meta["erros"].append("%s: %s" % (nome, e))

    def _evento(self, d, quando=None):
        """uma linha no eventos.jsonl, no relógio da sessão (t = segundos desde o 0:00, que inclui o replay)"""
        d = dict(d); d["t"] = round((quando or time.time()) - self.t0, 2)
        with self.ev_trava:
            if not self.ev.closed:
                self.ev.write(json.dumps(d, ensure_ascii=False) + "\n"); self.ev.flush()

    def _rotulo(self, quando, nome):
        s = max(0, int(quando - self.t0))
        return "%02d%02d_%s" % (s // 60, s % 60, nome)

    def _salvar_imagem(self, im, quando, nome):
        os.makedirs(os.path.join(self.pasta, "_copias"), exist_ok=True)
        base = os.path.join("_copias", self._rotulo(quando, nome)); rel = base + ".png"; i = 2
        while os.path.exists(os.path.join(self.pasta, rel)):
            rel = "%s_%d.png" % (base, i); i += 1
        im.save(os.path.join(self.pasta, rel))
        return rel

    def _area(self):
        """o que ele copia (Ctrl+C, print, Win+Shift+S) entra no log com a hora. SENHA NUNCA: conteúdo marcado por
        gerenciador de senha, gerenciador na frente, janela de senha ou campo de senha em foco = nem é lido."""
        try:
            uia = olho.UIA()
        except Exception as e:
            uia = None; log("área/uia: %r" % e)
        seq = olho.user32.GetClipboardSequenceNumber()
        while not self.parar_ev.wait(0.3):
            s = olho.user32.GetClipboardSequenceNumber()
            if s == seq:
                continue
            seq = s; quando = time.time(); time.sleep(0.15)
            try:
                j = janela_frente()
                dono = olho.exe_do_pid(_pid_da_janela(user32.GetClipboardOwner())) or j["app"]
                if {j["app"].lower(), dono.lower()} & olho.GERENCIADORES or re.search(r"senha|password|passkey", j["titulo"], re.I):
                    continue
                if uia is not None and uia.foco_e_senha():
                    continue
                a = olho.ler_area()
                if not a or a.get("protegido"):
                    continue
                ev = {"tipo": "copiou", "app": dono, "janela": j["titulo"][:90]}
                if a.get("html_fonte"):
                    ev["de"] = a["html_fonte"][:300]
                from PIL import ImageGrab
                if a["imagem"]:
                    im = ImageGrab.grabclipboard()
                    if im is None or isinstance(im, list):
                        continue
                    h = olho.hash_imagem(im)
                    if h in self.hashes:
                        continue
                    self.hashes.add(h)
                    captura = dono.lower() in ("snippingtool.exe", "screenclippinghost.exe", "screensketch.exe")
                    ev.update(o_que="captura" if captura else "imagem", arquivo=self._salvar_imagem(im, quando, "captura" if captura else "imagem"),
                              tamanho=list(im.size))
                    if a.get("html_img"):
                        ev["url_imagem"] = a["html_img"]
                elif a["arquivos"]:
                    lst = ImageGrab.grabclipboard()
                    ev.update(o_que="arquivos", arquivos=[str(x) for x in (lst or [])][:30])
                elif a.get("texto", "").strip():
                    t = a["texto"].strip()
                    ev["o_que"] = "link" if re.fullmatch(r"(https?://|www\.)\S+", t) else "texto"
                    ev["texto"] = t[:2000]
                    if len(t) > 2000:
                        os.makedirs(os.path.join(self.pasta, "_copias"), exist_ok=True)
                        rel = os.path.join("_copias", self._rotulo(quando, "texto") + ".txt")
                        open(os.path.join(self.pasta, rel), "w", encoding="utf-8").write(t); ev["arquivo"] = rel
                else:
                    continue
                self._evento(ev, quando)
            except Exception as e:
                log("área: %r" % e)

    def _capturas(self):
        """Win+Shift+S / Ferramenta de Captura salvam sozinhas em Imagens\\Capturas de Tela: cada nova vem pra sessão"""
        from PIL import Image
        pasta = olho.pasta_capturas()
        try:
            vistos = set(os.listdir(pasta))
        except OSError:
            vistos = set()
        while not self.parar_ev.wait(2.0):
            try:
                novos = [n for n in os.listdir(pasta) if n not in vistos]
            except OSError:
                continue
            for n in novos:
                vistos.add(n)
                if not n.lower().endswith((".png", ".jpg", ".jpeg")):
                    continue
                src = os.path.join(pasta, n)
                try:
                    time.sleep(0.4)
                    quando = os.path.getmtime(src)
                    im = Image.open(src); im.load()
                    h = olho.hash_imagem(im)
                    if h in self.hashes:
                        continue
                    self.hashes.add(h)
                    self._evento({"tipo": "copiou", "o_que": "captura", "arquivo": self._salvar_imagem(im, quando, "captura"),
                                  "origem": src, "tamanho": list(im.size)}, quando)
                except Exception as e:
                    log("capturas: %r" % e)

    def fala_wav(self):
        return os.path.join(self.pasta, "fala.wav")

    def _salvar_meta(self):
        with open(os.path.join(self.pasta, "sessao.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=1)

    def concluir(self, cancelar=False):
        try:
            self._concluir(cancelar)
        finally:
            self.concluida.set()

    def _concluir(self, cancelar=False):
        self.parar_ev.set()
        for nome, p in self.procs:
            try:
                p.stdin.write(b"q"); p.stdin.flush()
            except Exception:
                pass
        for nome, p in self.procs:
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill(); self.meta["erros"].append(nome + ": não fechou em 15 s, foi encerrado")
        try:
            with self.ev_trava:
                self.ev.close()
            self.flog.close()
        except Exception:
            pass
        # som do PC: o gravar_pc.py do CORRETOR deixa pc01*.wav; um só vira pc.wav
        pcs = sorted(f for f in os.listdir(self.pasta) if re.match(r"pc\d+.*\.wav$", f))
        if len(pcs) == 1:
            os.replace(os.path.join(self.pasta, pcs[0]), os.path.join(self.pasta, "pc.wav"))
        elif len(pcs) > 1:
            self._juntar_pc(pcs)
        fim = time.time()
        self.meta.update(fim_local=datetime.datetime.now().replace(microsecond=0).isoformat(), duracao_s=round(fim - self.t0, 1))
        if cancelar:
            self.meta["descartada"] = True
        self._salvar_meta()
        if cancelar:
            dest = os.path.join(SESSOES, "_descartadas"); os.makedirs(dest, exist_ok=True)
            try:
                shutil.move(self.pasta, dest)
            except OSError as e:
                log("cancelar: %s" % e)
            log("cancelada " + self.pasta)
            return
        if self.replay_s:
            self._juntar_replay()
            self._salvar_meta()
        log("concluída " + self.pasta)
        # links do Chrome: o History só vai pro disco alguns segundos depois da visita
        time.sleep(12)
        try:
            n = len(olho.links_da_sessao(self.pasta, self.meta))
            self.meta["links"] = n
        except Exception as e:
            self.meta["erros"].append("links do Chrome: %s" % e)
        self._salvar_meta()

    def _juntar_pc(self, pcs):
        """P20: a saída de som trocou no meio (fone, monitor...): o gravar_pc.py deixou um pc01_N.wav por saída. Antes ficavam
        soltos (sem pc.wav o resumo não lia o som do PC e o replay não juntava); agora viram um pc.wav na linha do tempo
        (t0 de cada segmento no pc01.json; buraco da troca = silêncio; formato diferente é convertido)."""
        man = os.path.join(self.pasta, "pc01.json")
        try:
            m = json.load(open(man, encoding="utf-8"))
            segs = m.get("segmentos") or []
            ini = m.get("inicio") or self.t_grav       # o atalho (o --inicio): a abertura atrasada vira silêncio no começo
            fim = m.get("fim") or max(s["t0"] + s.get("dur", 0) for s in segs)
            if olho.extrair_pc([man], ini, fim, os.path.join(self.pasta, "pc.wav")):
                for f in pcs:
                    os.remove(os.path.join(self.pasta, f))
                self.meta["pc_saidas"] = [s.get("dispositivo") for s in segs]
            else:
                self.meta["erros"].append("som do PC: %d pedaços (%s) não juntaram" % (len(pcs), ", ".join(pcs)))
        except Exception as e:
            self.meta["erros"].append("som do PC: juntar %s: %s" % (", ".join(pcs), e))

    def _juntar_replay(self):
        """replay_*.(mp4|wav) + o gravado → tela.mp4 / fala.wav / pc.wav, tudo no relógio da sessão (0:00 = começo do replay)"""
        if not self.replay_pronto.wait(90):
            self.meta["erros"].append("replay: a extração não terminou em 90 s (ficou de fora)"); return
        r = self.replay_arqs or {}
        p = lambda n: os.path.join(self.pasta, n)
        feitos = []
        for chave, final, tipo in (("tela", "tela.mp4", "v"), ("fala", "fala.wav", "a"), ("pc", "pc.wav", "a")):
            rep = r.get(chave)
            if not rep or not os.path.isfile(p(final)):
                continue
            meio = p("_gravacao_" + final)
            try:
                os.replace(p(final), meio)
                ok = olho.juntar_video([rep, meio], p(final), log) if tipo == "v" else olho.juntar_wav([rep, meio], p(final))
                d_rep, d_meio, d_fim = olho.duracao(rep), olho.duracao(meio), olho.duracao(p(final)) if ok else 0
                if ok and d_fim >= d_rep + d_meio - 1.5:
                    os.remove(rep); os.remove(meio); feitos.append(chave)
                else:
                    if os.path.isfile(p(final)):
                        os.remove(p(final))
                    os.replace(meio, p(final))
                    self.meta["erros"].append("replay %s: não juntou (%.1f + %.1f → %.1f s); ficou separado em %s" %
                                              (chave, d_rep, d_meio, d_fim, os.path.basename(rep)))
            except Exception as e:
                self.meta["erros"].append("replay %s: %s" % (chave, e))
                if os.path.isfile(meio) and not os.path.isfile(p(final)):
                    os.replace(meio, p(final))
        self.meta["replay_juntado"] = feitos


class OlhoPremiere(GravacaoPC):
    """23/10 (ele: "faz o Kakashi ser o mais completo possível pra não ter mais problema, tá ligado? É o olho de Deus, mano, é minha
    tela"): enquanto o painel do Premiere grava (começou lá ou trocou do PC), o olho do PC continua — janela, mouse, elemento sob o
    mouse, print do "aqui", o que ele copia — numa pasta _olho DENTRO da sessão do Premiere, no MESMO relógio da gravação do painel
    (sem as pausas: o relógio sai do t_gravacao do 7815/status). Sem ffmpeg nenhum: a tela, a voz e o som do PC continuam sendo do
    painel. No fim, a fala.wav e a tela.mp4 do painel são ligadas na _olho e ela vira uma sessão "pc" que o resumo_pc.py lê igual.
    Arquivo nenhum fica aberto (abre, escreve, fecha): o painel pode descartar/mover a pasta da sessão a qualquer hora."""

    def __init__(self, pasta_premiere, k, t_gravacao=0.0, gravando=True):
        self.k = k
        self.pasta_premiere = pasta_premiere
        self.pasta = os.path.join(pasta_premiere, "_olho")
        os.makedirs(self.pasta, exist_ok=True)
        self.t0 = self.t_grav = time.time()
        self.replay_s = 0.0; self.replay_arqs = None
        self.replay_pronto = threading.Event(); self.replay_pronto.set()
        self.relogio = (float(t_gravacao or 0.0), self.t0, bool(gravando))
        j = janela_frente()
        self.meta = {"tipo": "pc", "olho_premiere": True, "sessao_premiere": os.path.basename(pasta_premiere),
                     "inicio_local": datetime.datetime.fromtimestamp(self.t0).replace(microsecond=0).isoformat(),
                     "inicio_epoch": self.t0, "gravacao_epoch": self.t0, "replay_s": 0.0, "t_gravacao_inicio": round(self.relogio[0], 2),
                     "janela_inicial": j, "erros": []}
        self.procs = []
        self.parar_ev = threading.Event()
        self.concluida = threading.Event()
        self.ev_trava = threading.Lock()
        self.hashes = set()
        self._evento({"tipo": "janela", **j, "atalho": True})
        threading.Thread(target=self._area, daemon=True).start()
        threading.Thread(target=self._capturas, daemon=True).start()
        self._salvar_meta()

    def sincronizar(self, t_gravacao, gravando):
        """o vigia chama a cada ~0,5 s com o t_gravacao do painel: o relógio do olho anda junto (parado na pausa)"""
        self.relogio = (float(t_gravacao or 0.0), time.time(), bool(gravando))

    def t_rec(self, quando):
        t, e, grav = self.relogio
        return max(0.0, t + (max(0.0, quando - e) if grav else 0.0))

    def viva(self):
        return not self.parar_ev.is_set() and os.path.isdir(self.pasta_premiere)

    def _evento(self, d, quando=None):
        quando = quando or time.time()
        if not self.relogio[2] or not self.viva():      # pausado (o painel não grava) ou a sessão já saiu do lugar
            return
        d = dict(d); d["t"] = round(self.t_rec(quando), 2); d["epoch"] = round(quando, 2)
        with self.ev_trava:
            try:
                with open(os.path.join(self.pasta, "eventos.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
            except OSError:
                pass

    def _rotulo(self, quando, nome):
        s = int(self.t_rec(quando))
        return "%02d%02d_%s" % (s // 60, s % 60, nome)

    def _salvar_imagem(self, im, quando, nome):
        if not self.viva():
            raise OSError("a sessão do Premiere saiu do lugar")
        return GravacaoPC._salvar_imagem(self, im, quando, nome)

    def fala_wav(self):
        """a voz que o painel está gravando agora (parteNN.wav da sessão): o print do 'aqui' sai enquanto ele fala.
        Pausado ou terminando = nada (nem abre o arquivo: o painel vai juntar/apagar os pedaços)."""
        if not self.relogio[2] or not self.viva() or time.time() - self.relogio[1] > 1.0:
            return ""
        try:
            ps = sorted(f for f in os.listdir(self.pasta_premiere) if re.match(r"parte\d+\.wav$", f))
        except OSError:
            return ""
        return os.path.join(self.pasta_premiere, ps[-1]) if ps else ""

    def _salvar_meta(self):
        if os.path.isdir(self.pasta):
            GravacaoPC._salvar_meta(self)

    def _recontar(self, mp):
        """o relógio FINAL do painel (sessao.json dele, depois do Concluir): as partes que ficaram (t0 recontado quando ele apaga
        um pedaço) viram relogio_trechos e cada evento do olho ganha o t de novo pelo epoch (o ao vivo fica em t_bruto quando muda);
        evento de pedaço apagado sai pra eventos_dos_pedacos_apagados.jsonl — igual o CORRETOR faz com os eventos dele."""
        partes = sorted([p for p in (mp.get("partes") or []) if p.get("inicio") and p.get("fim")], key=lambda p: p["inicio"])
        if not partes:
            return
        tre = [[round(p["inicio"], 3), round(float(p.get("t0") or 0.0), 3), round(p["fim"], 3)] for p in partes]
        apag = [(p["inicio"], p["fim"]) for p in (mp.get("pedacos_apagados") or []) if p.get("inicio") and p.get("fim")]
        self.meta["relogio_trechos"] = tre
        arq = os.path.join(self.pasta, "eventos.jsonl")
        with self.ev_trava:
            try:
                evs = [json.loads(l) for l in open(arq, encoding="utf-8") if l.strip()]
            except (OSError, ValueError):
                return
            ficam, saem = [], []
            for e in evs:
                q = e.get("epoch")
                if q is not None and any(a - 0.3 <= q <= b + 0.3 for a, b in apag) and not any(a <= q <= b for a, _, b in tre):
                    saem.append(e); continue
                if q is not None:
                    t = round(olho.t_da_sessao(q, self.meta), 2)
                    if abs(t - e.get("t", t)) > 0.05:
                        e["t_bruto"] = e.get("t"); e["t"] = t
                ficam.append(e)
            try:
                with open(arq, "w", encoding="utf-8") as f:
                    f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in ficam)
                if saem:
                    with open(os.path.join(self.pasta, "eventos_dos_pedacos_apagados.jsonl"), "w", encoding="utf-8") as f:
                        f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in saem)
            except OSError as ex:
                self.meta["erros"].append("recontar o relógio: %s" % ex); return
        self.meta["eventos_recontados"] = sum(1 for e in ficam if "t_bruto" in e)
        if saem:
            self.meta["eventos_de_pedaco_apagado"] = len(saem)

    def _concluir(self, cancelar=False):
        self.parar_ev.set()
        fim = time.time()
        t_fim = self.t_rec(fim)
        if not os.path.isdir(self.pasta):               # descartada: o painel levou a pasta inteira pro _descartadas
            log("olho do Premiere: a sessão %s saiu do lugar (descartada?)" % os.path.basename(self.pasta_premiere)); return
        for _ in range(360):                            # o painel junta audio.wav / tela.mp4 depois do concluir (até 3 min)
            st = http("http://127.0.0.1:7815/status", t=1) or {}
            if not os.path.isdir(self.pasta):
                return
            if not st.get("finalizando") and os.path.isfile(os.path.join(self.pasta_premiere, "audio.wav")):
                break
            time.sleep(0.5)
        try:
            mp = json.load(open(os.path.join(self.pasta_premiere, "sessao.json"), encoding="utf-8"))
        except Exception:
            mp = {}
        self._recontar(mp)
        for src, dst in (("audio.wav", "fala.wav"), ("tela.mp4", "tela.mp4"), ("pc.wav", "pc.wav")):
            a, b = os.path.join(self.pasta_premiere, src), os.path.join(self.pasta, dst)
            if os.path.isfile(a) and not os.path.exists(b):
                try:
                    os.link(a, b)                       # link no mesmo disco: não duplica os 4K
                except OSError:
                    if dst != "tela.mp4":
                        shutil.copy2(a, b)
        tre = self.meta.get("relogio_trechos")
        self.meta.update(fim_local=datetime.datetime.now().replace(microsecond=0).isoformat(), fim_epoch=round(tre[-1][2] if tre else fim, 3),
                         duracao_s=round(float(mp.get("t_gravado") or t_fim), 1), microfone=mp.get("dispositivo"),
                         estado_premiere=mp.get("estado"))
        if cancelar or mp.get("estado") == "descartada":
            self.meta["descartada"] = True
        self._salvar_meta()
        log("olho do Premiere concluído: %s (%.0f s)" % (self.pasta, t_fim))
        time.sleep(12)                                  # links do Chrome: o History só vai pro disco uns segundos depois
        try:
            self.meta["links"] = len(olho.links_da_sessao(self.pasta, self.meta))
        except Exception as e:
            self.meta["erros"].append("links do Chrome: %s" % e)
        self._salvar_meta()


# ---------- o olho sempre aberto (P3) ----------
class Vigia:
    """Lê o Windows 20x/s: janela da frente, cliques e o caminho do mouse (amostra a cada ~0,25 s, só quando mexe).
    Parado (sem gravação): os eventos ficam SÓ na memória, os últimos ~2 min, pra entrar no replay. Gravando o tipo "pc":
    vão pro eventos.jsonl e, na pausa do mouse (>0,8 s depois de andar) e em todo clique, o elemento debaixo do mouse (UIA);
    print nativo na pausa, enquanto ele fala (o "aqui"), e ~1,5 s depois de cada janela/página nova."""
    PAUSA, PASSO, MEMORIA = 0.8, 0.25, 140

    def __init__(self, k):
        self.k = k
        self.anel = collections.deque(); self.trava = threading.Lock()
        self.jobs = queue.Queue(maxsize=12)
        self.ult_print = {"t": 0.0, "pos": None, "mini": None}
        threading.Thread(target=self._laco, daemon=True).start()
        threading.Thread(target=self._trabalhador, daemon=True).start()

    def emitir(self, ev, quando=None):
        quando = quando or time.time()
        g = self.k.alvo()                  # a gravação do PC, ou o olho do Premiere quando o painel grava (23/10)
        if g is not None and quando >= g.t0:
            g._evento(ev, quando); return
        with self.trava:
            self.anel.append((quando, ev))
            while self.anel and self.anel[0][0] < quando - self.MEMORIA:
                self.anel.popleft()

    def desde(self, t0):
        with self.trava:
            return [(q, e) for q, e in self.anel if q >= t0]

    def pedir(self, *job):
        try:
            self.jobs.put_nowait(job)
        except queue.Full:
            pass

    def _laco(self):
        pt = wt.POINT(); ult_j = None; botoes = {0x01: False, 0x02: False}
        ant = amostra = None; t_amostra = t_mexeu = t_voz = 0.0; andou = 0.0; print_janela = None
        while True:
            agora = time.time()
            try:
                g = self.k.alvo()
                j = janela_frente()
                if (j["app"], j["titulo"]) != ult_j:
                    ult_j = (j["app"], j["titulo"]); self.emitir({"tipo": "janela", **j}, agora)
                    print_janela = agora + 1.5            # página/janela nova: print nativo quando assentar
                user32.GetCursorPos(ctypes.byref(pt)); pos = (pt.x, pt.y)
                if ant is not None and pos != ant:
                    andou += abs(pos[0] - ant[0]) + abs(pos[1] - ant[1]); t_mexeu = agora
                ant = pos
                if agora - t_amostra >= self.PASSO:
                    t_amostra = agora
                    if amostra is None or abs(pos[0] - amostra[0]) + abs(pos[1] - amostra[1]) > 3:
                        amostra = pos; self.emitir({"tipo": "mouse", "x": pos[0], "y": pos[1]}, agora)
                if andou > 25 and agora - t_mexeu >= self.PAUSA:
                    andou = 0.0
                    self.emitir({"tipo": "parou", "x": pos[0], "y": pos[1]}, t_mexeu)
                    if g is not None:
                        self.pedir("uia", "parou", pos, t_mexeu); self.pedir("print", "parou", pos, t_mexeu)
                for vk in botoes:
                    baixo = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                    if baixo and not botoes[vk]:
                        alvo = janela_frente(user32.GetAncestor(user32.WindowFromPoint(pt), 2))
                        self.emitir({"tipo": "clique" if vk == 1 else "clique_direito", "x": pos[0], "y": pos[1], **alvo}, agora)
                        if g is not None:
                            self.pedir("uia", "clique", pos, agora)
                    botoes[vk] = baixo
                if g is None:
                    print_janela = None
                elif print_janela and agora >= print_janela:
                    print_janela = None; self.pedir("print", "pagina", pos, agora)
                if g is not None and agora - t_voz >= 0.5:          # falando = o "aqui" pode vir a qualquer hora
                    t_voz = agora
                    if olho.nivel_voz(g.fala_wav()) > 400:
                        self.pedir("print", "fala", pos, agora)
            except Exception as e:
                log("vigia: %r" % e)
            time.sleep(0.05)

    def _trabalhador(self):
        uia = None
        while True:
            tipo, motivo, pos, quando = self.jobs.get()
            g = self.k.alvo()
            if g is None:
                continue
            try:
                if tipo == "uia":
                    if uia is None:
                        uia = olho.UIA()
                    d = uia.em(*pos)
                    if d:
                        self.emitir({"tipo": "sob_mouse", "motivo": motivo, "x": pos[0], "y": pos[1], **d}, quando)
                else:
                    self._print(g, motivo, pos, quando)
            except Exception as e:
                log("olho %s: %r" % (tipo, e))

    def _print(self, g, motivo, pos, quando):
        u = self.ult_print; agora = time.time()
        perto = u["pos"] is not None and abs(pos[0] - u["pos"][0]) + abs(pos[1] - u["pos"][1]) < 40
        if motivo == "fala" and (agora - u["t"] < 3.0 or (perto and agora - u["t"] < 8.0)):
            return
        im, mon = olho.print_nativo(*pos)
        mini = olho.miniatura(im)
        if perto and olho.parecida(mini, u["mini"]):
            return                                      # mesma tela, cursor no mesmo lugar: nada novo
        os.makedirs(os.path.join(g.pasta, "_prints"), exist_ok=True)
        base = rel = os.path.join("_prints", g._rotulo(quando, motivo)); i = 2
        while os.path.exists(os.path.join(g.pasta, rel + ".jpg")):
            rel = "%s_%d" % (base, i); i += 1
        olho.salvar_print(im, mon, pos[0], pos[1], os.path.join(g.pasta, rel))
        u.update(t=agora, pos=pos, mini=mini)
        self.emitir({"tipo": "print", "motivo": motivo, "x": pos[0], "y": pos[1], "arquivo": rel + ".jpg",
                     "perto": rel + "_perto.jpg", "monitor": list(mon)}, quando)


class Replay:
    """Os últimos 2 min de tela + voz + som do PC num disco rotativo (sessoes\\_replay), pra entrarem no começo da gravação.
    Tela e voz: ffmpeg em pedaços de 10 s; som do PC: o gravar_pc.py do CORRETOR em peças de 60 s com 2 s de sobra
    (cada segmento tem o t0 no relógio do PC). Pedaço com mais de ~2,5 min é apagado. Liga sozinho quando nada grava;
    para quando qualquer Kakashi começa a gravar. config.json "replay": false = desligado; "replay_s": 120 = quanto.
    P20 (21/10): o buffer ficou 3 h ligado e a voz virou silêncio digital sem erro nenhum (o receptor do microfone sem fio
    dormiu/reconectou). Agora a voz é vigiada: MUDO_S em silêncio digital → reabre SÓ o microfone (fala_<geração>_<n>.wav);
    a saída de som do PC trocada vai pro kakashi.log (quem troca o loopback é o gravar_pc.py, a cada 2 s)."""
    PECA_PC = 60.0
    MUDO_S, MUDO_MAX = 60.0, 600.0      # 1ª reabertura depois de 60 s mudo; mudo de novo, espera o dobro (até 10 min)
    MUDO_ATALHO_S = 10.0                # no atalho: a voz dos últimos 10 s em silêncio digital = replay_sem_voz

    def __init__(self):
        self.base = os.path.join(SESSOES, "_replay")
        self.trava = threading.RLock()
        self.procs, self.pecas, self.pasta, self.ini = [], [], None, None
        self.flog = None; self.falhou_em = 0.0
        self.proc_fala = None; self.geracao = 0; self.voz = {}; self.saida = None
        self._limpar_orfaos()

    def _limpar_orfaos(self):
        """P20: ffmpeg / gravar_pc.py de um buffer de ANTES (Kakashi morto sem parar o replay) ficavam vivos segurando o
        microfone e a tela — em 21/10 dois do teste do P3 rodaram 13 h (8,8 GB; o microfone deles travou às 06:39 e seguiu
        aberto). Só existe um Kakashi (mutex): o que escreve nesta pasta de buffer e não é filho meu é sobra."""
        try:
            import psutil
        except ImportError:
            return
        meu, base = os.getpid(), self.base.lower()
        for p in psutil.process_iter(["pid", "ppid", "cmdline"]):
            try:
                cl = " ".join(p.info["cmdline"] or []).lower()
                if base in cl and p.info["pid"] != meu and p.info["ppid"] != meu:
                    p.kill(); log("replay: processo de buffer antigo encerrado (pid %d): ...%s" % (p.info["pid"], cl[-70:]))
            except Exception:
                pass

    @staticmethod
    def ligado_no_config():
        return bool(cfg().get("replay", True))

    @staticmethod
    def segundos():
        return float(cfg().get("replay_s", 120))

    def rodando(self):
        return bool(self.procs)

    def info(self):
        return {"ligado_no_config": self.ligado_no_config(), "rodando": self.rodando(),
                "segundos_guardados": round(min(self.segundos(), time.time() - self.ini), 1) if self.procs and self.ini else 0}

    def ligar(self):
        with self.trava:
            if self.procs or not self.ligado_no_config() or time.time() - self.falhou_em < 30:
                return
            os.makedirs(self.base, exist_ok=True)
            for n in os.listdir(self.base):          # sobras de antes (Kakashi fechado no meio): nunca é sessão, só buffer
                d = os.path.join(self.base, n)
                if os.path.isdir(d) and time.time() - os.path.getmtime(d) > 600:
                    shutil.rmtree(d, ignore_errors=True)
            self.pasta = os.path.join(self.base, "%d" % (time.time() * 1000)); os.makedirs(self.pasta)
            self.ini = time.time()
            self.flog = open(os.path.join(self.pasta, "ffmpeg.log"), "ab")
            self._abrir(self.BASE + ENTRADA_TELA + ["-vf", "scale=1920:-2:flags=bilinear,format=yuv420p"] + olho.VIDEO_ENC +
                        ["-threads", "2"] + self.SEG + ["-segment_format", "mpegts", os.path.join(self.pasta, "tela_%05d.ts")])
            self.geracao = 0; self.saida = None
            self._abrir_fala()
            self._peca_pc()
            threading.Thread(target=self._zelador, args=(self.pasta,), daemon=True).start()
            log("replay ligado")

    BASE = [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "warning"]
    SEG = ["-f", "segment", "-segment_time", "10", "-reset_timestamps", "1"]

    def _abrir(self, cmd):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self.flog, creationflags=SEM_JANELA)
            self.procs.append(p)
            return p
        except Exception as e:
            log("replay: %s" % e)

    def _abrir_fala(self):
        """o microfone do buffer: um ffmpeg por abertura (geração), pedaços fala_<geração>_<n>.wav de 10 s"""
        dev = microfone()
        self.proc_fala = None
        if dev:
            self.proc_fala = self._abrir(self.BASE + entrada_mic(dev) + ["-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le"] + self.SEG +
                                         ["-segment_format", "wav", os.path.join(self.pasta, "fala_%03d_%%05d.wav" % self.geracao)])
        agora = time.time()
        self.voz = {"ult_som": self.voz.get("ult_som", agora) if self.geracao else agora, "aberto": agora,
                    "espera": self.voz.get("espera", self.MUDO_S) if self.geracao else self.MUDO_S,
                    "reaberturas": self.voz.get("reaberturas", 0) if self.geracao else 0}

    def _fechar_fala(self, espera=2.0):
        """fecha o microfone do buffer e ESPERA ele soltar o aparelho (21/10 12:55: a captura nova aberta com o ffmpeg velho
        ainda segurando o microfone também veio zerada; a de 12:57, com tudo fechado, veio com som)"""
        p = self.proc_fala; self.proc_fala = None
        if p is None:
            return
        if p in self.procs:
            self.procs.remove(p)
        self._q(p)
        try:
            p.wait(timeout=espera)
        except subprocess.TimeoutExpired:
            p.kill()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                log("replay: o ffmpeg do microfone não fechou nem com kill")
        try:
            p.stdin.close()
        except Exception:
            pass

    def _falas(self, pasta):
        return sorted(glob.glob(os.path.join(pasta, "fala_*.wav")))

    def _vigiar_voz(self, pasta, agora):
        """P20: voz do buffer em silêncio digital há MUDO_S → reabre só o microfone. Ele calado também dá silêncio digital
        (o microfone sem fio corta pra zero nas pausas): mudo de novo, a próxima espera o dobro (60, 120, 240... até 600 s)."""
        if self.proc_fala is None or not self.voz:
            return
        v = self.voz
        p = olho.pico_fim(self._falas(pasta)[-2:], 2.5)
        if p is not None and p >= olho.MUDO:
            if v["reaberturas"]:
                log("replay: a voz voltou (%.0f s em silêncio digital, %d reabertura(s) do microfone)" % (agora - v["ult_som"], v["reaberturas"]))
            v.update(ult_som=agora, espera=self.MUDO_S, reaberturas=0)
            return
        if agora - max(v["ult_som"], v["aberto"]) < v["espera"]:
            return
        log("replay: voz em silêncio digital há %.0f s (pico < %d) — reabrindo o microfone (%dª vez)" %
            (agora - v["ult_som"], olho.MUDO, v["reaberturas"] + 1))
        self._fechar_fala()
        self.geracao += 1
        v["reaberturas"] += 1; v["espera"] = min(self.MUDO_MAX, v["espera"] * 2)
        self._abrir_fala()
        if self.proc_fala is None:
            log("replay: o microfone não reabriu (nenhum microfone encontrado)")

    def _vigiar_saida(self):
        """a saída de som do PC trocou (fone, monitor...): o gravar_pc.py já reabre o loopback na nova; aqui só vai pro log"""
        if not self.pecas:
            return
        try:
            m = json.load(open(os.path.join(self.pecas[-1][1], "pc01.json"), encoding="utf-8"))
            atual = (m.get("segmentos") or [{}])[-1].get("dispositivo")
        except (OSError, ValueError, IndexError, AttributeError):
            return
        if atual and atual != self.saida:
            if self.saida is not None:
                log("replay: som do PC agora de '%s' (era '%s')" % (atual, self.saida))
            self.saida = atual

    def _peca_pc(self):
        gp = os.path.join(CORRETOR, "gravar_pc.py")
        if not os.path.isfile(gp):
            return
        d = os.path.join(self.pasta, "pc_%d" % (time.time() * 1000)); os.makedirs(d)
        try:
            p = subprocess.Popen([PY, gp, "--pasta", d, "--parte", "1", "--inicio", "%.3f" % time.time()] + GRAVAR_PC_EXTRA, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL, stderr=open(os.path.join(d, "som_pc.log"), "ab"), creationflags=SEM_JANELA)
            self.pecas.append([p, d, time.time()])
        except Exception as e:
            log("replay pc: %s" % e)

    @staticmethod
    def _q(p):
        try:
            p.stdin.write(b"q"); p.stdin.flush()
        except Exception:
            pass

    def _zelador(self, pasta):
        """troca a peça do som do PC a cada 60 s, apaga pedaço velho, religa se um ffmpeg morrer"""
        while True:
            time.sleep(2)
            with self.trava:
                if self.pasta != pasta:
                    return
                agora = time.time(); guardar = self.segundos() + 30
                if any(p.poll() is not None for p in self.procs):
                    log("replay: um ffmpeg parou sozinho; religando em 30 s")
                    self.falhou_em = agora; self._parar_procs(); shutil.rmtree(pasta, ignore_errors=True); return
                vivas = [x for x in self.pecas if x[0].poll() is None]
                if vivas and agora - vivas[-1][2] >= self.PECA_PC:
                    self._peca_pc()
                elif len(vivas) >= 2 and agora - vivas[-1][2] >= 2:
                    for x in vivas[:-1]:
                        self._q(x[0])
                for x in list(self.pecas):
                    if x[0].poll() is not None and agora - x[2] > self.PECA_PC + guardar:
                        shutil.rmtree(x[1], ignore_errors=True); self.pecas.remove(x)
                for padrao in ("tela_*.ts", "fala_*.wav"):
                    for f in sorted(glob.glob(os.path.join(pasta, padrao)))[:-2]:
                        try:
                            if agora - os.path.getmtime(f) > guardar:
                                os.remove(f)
                        except OSError:
                            pass
                try:
                    self._vigiar_voz(pasta, agora)
                    self._vigiar_saida()
                except Exception as e:
                    log("replay vigia: %r" % e)

    def _parar_procs(self):
        for p in self.procs + [x[0] for x in self.pecas]:
            self._q(p)
        procs = self.procs + [x[0] for x in self.pecas]
        self.procs, self.pecas = [], []
        return procs

    def parar(self):
        """para o buffer AGORA e devolve {fim, segundos, pasta, procs} (None se não estava rodando)"""
        with self.trava:
            if not self.procs:
                return None
            fim = time.time()
            info = {"fim": fim, "segundos": max(0.0, min(self.segundos(), fim - self.ini - 2.0)), "pasta": self.pasta}
            # P20: voz dos últimos ~10 s em silêncio digital = não confia no buffer: o microfone dele fecha JÁ (e solta o
            # aparelho) antes de a gravação abrir a captura nova; a sessão fica marcada com replay_sem_voz
            if self.proc_fala is not None:
                p10 = olho.pico_fim(self._falas(self.pasta)[-3:], self.MUDO_ATALHO_S)
                info["sem_voz"] = p10 is None or p10 < olho.MUDO
                info["voz_muda_s"] = round(fim - self.voz.get("ult_som", fim), 1) if info["sem_voz"] else 0.0
                if info["sem_voz"]:
                    p = self.proc_fala
                    self._fechar_fala(espera=0.0)        # kill na hora (o fim dele é silêncio mesmo); devolve no info["procs"]
                    self.procs.append(p)
            info["procs"] = self._parar_procs()
            self.pasta = None; self.proc_fala = None
            try:
                self.flog.close()
            except Exception:
                pass
            log("replay parado (%.0f s guardados)" % info["segundos"] +
                (" — voz dos últimos %.0f s em silêncio digital (mudo há %.0f s): microfone do buffer fechado antes da captura nova"
                 % (self.MUDO_ATALHO_S, info["voz_muda_s"]) if info.get("sem_voz") else ""))
            return info

    @staticmethod
    def _esperar(info):
        for p in info["procs"]:
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill()
            try:
                p.stdin.close()
            except Exception:
                pass

    def descartar(self, info):
        if info:
            self._esperar(info); shutil.rmtree(info["pasta"], ignore_errors=True)

    def extrair(self, info, g):
        """os últimos 'segundos' do buffer → replay_tela.mp4 / replay_fala.wav / replay_pc.wav na pasta da sessão"""
        out = {}
        try:
            self._esperar(info)
            R, fim, pasta = info["segundos"], info["fim"], info["pasta"]
            if R >= 1:
                alvo = lambda n: os.path.join(g.pasta, n)
                if olho.extrair_video_fim(sorted(glob.glob(os.path.join(pasta, "tela_*.ts"))), R, alvo("replay_tela.mp4"), log):
                    out["tela"] = alvo("replay_tela.mp4")
                if olho.extrair_fala_fim(self._falas(pasta), R, alvo("replay_fala.wav")):
                    out["fala"] = alvo("replay_fala.wav")
                if olho.extrair_pc(sorted(glob.glob(os.path.join(pasta, "pc_*", "pc01.json"))), fim - R, fim, alvo("replay_pc.wav")):
                    out["pc"] = alvo("replay_pc.wav")
            shutil.rmtree(pasta, ignore_errors=True)
        except Exception as e:
            log("replay extrair: %r" % e)
        g.replay_arqs = out
        g.replay_pronto.set()


# ---------- o controle (qual gravação está ligada, de quem) ----------
class Kakashi:
    def __init__(self):
        self.pc = None          # GravacaoPC
        self.fora = None        # "premiere" | "luluka" quando fui eu que mandei gravar lá
        self.inicio = None
        self.ultima_voz = None
        self.aviso = ""
        self.quem_cache = None
        self.voz_viva = None    # P20: VozViva da gravação de agora (PC ou Luluka)
        self.mudo = 0.0
        self.trava = threading.Lock()
        self.troca_pedida = None  # troca PC → Premiere em andamento: {"g", "t", "janela"} (o painel ainda não começou)
        self.troca_pc = None      # a parte PC da correção que continuou no Premiere (pra cancelar junto)
        self.troca_desistiu = None  # a GravacaoPC em que o painel não começou: não tenta trocar de novo nela
        self.olho_prem = None       # 23/10: OlhoPremiere — o olho do PC dentro da sessão do painel enquanto ele grava
        self.vigia = Vigia(self)
        self.replay = Replay()
        threading.Thread(target=self._cuidar_replay, daemon=True).start()
        threading.Thread(target=self._vigiar_troca, daemon=True).start()
        threading.Thread(target=self._vigiar_olho_premiere, daemon=True).start()

    def alvo(self):
        """onde o olho escreve agora: a gravação do PC (tem prioridade, inclusive no ~1 s da troca) ou o olho do Premiere"""
        return self.pc or self.olho_prem

    def _vigiar_olho_premiere(self):
        """23/10 (ele: "faz o Kakashi ser o mais completo possível... É o olho de Deus, mano, é minha tela"): o painel do Premiere
        gravando (começou lá ou trocou do PC) → o olho do PC continua dentro da sessão dele (OlhoPremiere), no relógio da gravação
        do painel. O painel parou/terminou → o olho fecha na hora (antes de o painel juntar os pedaços)."""
        while True:
            time.sleep(0.25)
            try:
                if cfg().get("olho_premiere", True) is False:
                    if self.olho_prem is not None:
                        o = self.olho_prem; self.olho_prem = None; threading.Thread(target=o.concluir, daemon=True).start()
                    continue
                st = http("http://127.0.0.1:7815/status", t=1)
                if st is None:
                    continue
                est, pasta = st.get("estado"), st.get("pasta")
                o = self.olho_prem
                if est in ("gravando", "pausado") and pasta and os.path.isdir(pasta):
                    if o is not None and o.pasta_premiere != pasta:        # outra sessão: fecha a velha
                        self.olho_prem = None; threading.Thread(target=o.concluir, daemon=True).start(); o = None
                    if o is None:
                        self.olho_prem = o = OlhoPremiere(pasta, self, st.get("t_gravacao"), est == "gravando")
                        log("olho do Premiere: começou em %s (t_gravacao %.1f)" % (os.path.basename(pasta), st.get("t_gravacao") or 0))
                    o.sincronizar(st.get("t_gravacao"), est == "gravando")
                elif o is not None:
                    self.olho_prem = None
                    threading.Thread(target=o.concluir, daemon=True).start()
            except Exception as e:
                log("olho do Premiere: %r" % e)

    def estado(self):
        """quem está gravando agora (vale também se ele ligou pelo botão do Luluka ou do painel)"""
        if self.pc:
            self.quem_cache = "pc"
            return "pc", self.inicio
        lu = http("http://127.0.0.1:7798/api/luluka/gravacao", t=1)
        if lu and lu.get("gravando"):
            self.quem_cache = "luluka"
            return "luluka", time.time() - (lu.get("segundos") or 0)
        st = http("http://127.0.0.1:7815/status", t=1)
        if st and st.get("estado") in ("gravando", "pausado"):
            self.quem_cache = "premiere"
            return "premiere", time.time() - (st.get("t_gravacao") or 0)
        self.quem_cache = None
        if st is not None:        # nada gravando (ele concluiu pelo botão do painel): a parte PC de uma troca não é mais "a atual"
            self.troca_pc = None; self.fora = None
        return None, None

    def status(self):
        """GET 127.0.0.1:7816/status — o Claude confere aqui antes de reiniciar o Kakashi"""
        quem = "pc" if self.pc else self.quem_cache
        d = {"ok": True, "app": "kakashi", "porta": PORTA, "pid": os.getpid(), "estado": "gravando" if quem else "parado", "quem": quem,
             "replay": self.replay.info()}
        if self.pc:
            d.update(pasta=self.pc.pasta, t=round(time.time() - self.pc.t_grav, 1), replay_s=self.pc.replay_s)
        if quem:
            d["mudo_s"] = round(self.mudo, 1)      # P20: segundos em silêncio digital (> 15 = o olho está cinza)
        if self.olho_prem is not None:             # 23/10: o olho do PC dentro da sessão do Premiere
            d["olho_premiere"] = self.olho_prem.pasta
        return d

    def _cuidar_replay(self):
        """buffer ligado só quando NADA grava (o painel do Premiere e o Luluka gravam por conta própria)"""
        time.sleep(5)
        while True:
            try:
                with self.trava:
                    quem = "pc" if self.pc else self.quem_cache
                    if quem is None and not self.replay.rodando():
                        self.replay.ligar()
                    elif quem in ("luluka", "premiere") and self.replay.rodando():
                        info = self.replay.parar()
                        threading.Thread(target=self.replay.descartar, args=(info,), daemon=True).start()
                    elif quem is None and self.replay.rodando() and not self.replay.ligado_no_config():
                        info = self.replay.parar()
                        threading.Thread(target=self.replay.descartar, args=(info,), daemon=True).start()
            except Exception as e:
                log("cuidar replay: %r" % e)
            time.sleep(2)

    TROCA_S = 1.5             # o Premiere tem que ficar na frente esse tempo seguido (alt+tab de passagem não troca)
    TROCA_ESPERA_S = 15.0     # o painel pega o "iniciar" no próximo GET /comando; sem começar até aqui = painel morto, segue PC

    def _vigiar_troca(self):
        """23/10 (ele: "Sim, óbvio"): gravando como PC e ele entra no Premiere → troca sozinho pro modo Premiere (o rastro da
        timeline só vem de lá). Primeiro o painel começa; só com ele GRAVANDO a parte PC fecha (sem buraco de voz: ~1 s gravado
        nos dois). Não volta pro PC quando ele sai do Premiere: a sessão do Premiere grava a tela inteira e a voz do mesmo jeito,
        e o OlhoPremiere (_vigiar_olho_premiere) segue com mouse/elemento/prints/cópias dentro de <sessão>\\_olho."""
        frente_desde = None
        while True:
            time.sleep(0.3)
            try:
                g = self.pc
                if g is None:
                    frente_desde = None; continue
                pedida = self.troca_pedida
                if pedida is not None:                        # já pedi: espera o painel começar
                    st = http("http://127.0.0.1:7815/status", t=1)
                    with self.trava:
                        if self.pc is not g or self.troca_pedida is not pedida:
                            continue
                        if st and st.get("estado") == "gravando":
                            self._fechar_parte_pc(g, pedida)
                        elif time.time() - pedida["t"] > self.TROCA_ESPERA_S:
                            self.troca_pedida = None; self.troca_desistiu = g     # nesta gravação não tenta de novo (não enche a fila do painel)
                            log("troca: o painel do Premiere não começou em %.0f s; segue gravando como PC" % self.TROCA_ESPERA_S)
                            g._evento({"tipo": "troca_falhou", "para": "premiere"})
                            threading.Thread(target=self._cancelar_troca_atrasada, args=(pedida["t"],), daemon=True).start()
                    continue
                if self.troca_desistiu is g:
                    continue
                j = janela_frente()
                if "premiere" not in j["app"].lower():
                    frente_desde = None; continue
                agora = time.time()
                frente_desde = frente_desde or agora
                if agora - frente_desde < self.TROCA_S or cfg().get("troca_premiere", True) is False:
                    continue
                st = http("http://127.0.0.1:7815/status", t=1)
                if not (st and st.get("painel_visto_ha_s") is not None and st["painel_visto_ha_s"] < 10 and st.get("estado") == "parado"):
                    continue
                with self.trava:
                    if self.pc is not g or self.troca_pedida is not None:
                        continue
                    r = http("http://127.0.0.1:7815/comando", {"acao": "iniciar"})
                    if not (r and r.get("ok")):
                        log("troca: o Premiere não aceitou o iniciar (%r)" % (r,)); frente_desde = None; continue
                    self.troca_pedida = {"g": g, "t": time.time(), "janela": j}
                    log("troca: Premiere na frente %.1f s → pedi o iniciar ao painel (%s)" % (self.TROCA_S, j["titulo"][:60]))
                frente_desde = None
            except Exception as e:
                log("troca: %r" % e)

    def _fechar_parte_pc(self, g, pedida):
        """(com a trava) o Premiere já está gravando: a parte PC fecha e fica marcada como o começo da mesma correção"""
        t = time.time()
        self.troca_pedida = None
        self.pc = None; self.inicio = None
        self.fora = "premiere"; self.quem_cache = "premiere"; self.troca_pc = g
        vv = self.voz_viva
        if vv is not None and vv.arq == g.fala_wav():
            tr = vv.trechos_mudos(g.t0, t)
            if tr:
                g.meta["voz_muda"] = tr
        g.meta.update(continua_em="premiere", troca_epoch=round(t, 2), troca_s=round(t - g.t0, 2),
                      troca_janela=pedida["janela"], troca_pedida_epoch=round(pedida["t"], 2))
        g._evento({"tipo": "troca", "para": "premiere", **pedida["janela"]}, t)
        threading.Thread(target=g.concluir, args=(False,), daemon=True).start()
        log("troca: PC → Premiere em %.1f s da sessão (%s)" % (t - g.t0, g.pasta))

    def _descartar_parte_pc(self, g):
        """cancelou depois da troca: a parte PC (já concluída ou concluindo) vai junto pro _descartadas"""
        g.concluida.wait(60)
        ok = descartar({"pasta": g.pasta, "base": SESSOES})
        log("troca: parte PC %s %s" % (g.pasta, "descartada junto" if ok else "NÃO foi pro _descartadas"))

    def _cancelar_troca_atrasada(self, t0):
        """concluiu a PC com o "iniciar" ainda na fila do painel: se o Premiere começar mesmo assim, cancela essa sobra"""
        while time.time() - t0 < self.TROCA_ESPERA_S + 5:
            st = http("http://127.0.0.1:7815/status", t=1)
            if st and st.get("estado") == "gravando":
                http("http://127.0.0.1:7815/cancelar", {}); log("troca: o Premiere começou depois do fim da PC → cancelei essa sobra")
                return
            time.sleep(0.5)

    def alternar(self, cancelar=False):
        with self.trava:
            self._alternar(cancelar)

    def _alternar(self, cancelar=False):
        quem, _ = self.estado()
        if quem == "pc":
            g = self.pc; self.pc = None; self.inicio = None; self.quem_cache = None
            if self.troca_pedida is not None:         # apertou o atalho no meio da troca: a PC é a correção inteira
                threading.Thread(target=self._cancelar_troca_atrasada, args=(self.troca_pedida["t"],), daemon=True).start()
                self.troca_pedida = None
            vv = self.voz_viva
            if vv is not None and vv.arq == g.fala_wav():
                tr = vv.trechos_mudos(g.t0, time.time())
                if tr:
                    g.meta["voz_muda"] = tr        # P20: trechos em silêncio digital > 15 s (relógio da sessão)
            threading.Thread(target=g.concluir, args=(cancelar,), daemon=True).start()
            if not cancelar:
                threading.Thread(target=colar_kakashi, daemon=True).start()
            return
        if quem == "luluka":
            http("http://127.0.0.1:7798/api/luluka/gravacao", {"acao": "concluir"}, t=20); self.fora = None
            threading.Thread(target=colar_kakashi, daemon=True).start(); return
        if quem == "premiere":
            if cancelar:
                http("http://127.0.0.1:7815/cancelar", {})
                if self.troca_pc is not None:        # começou como PC e trocou: as duas partes são uma correção só
                    threading.Thread(target=self._descartar_parte_pc, args=(self.troca_pc,), daemon=True).start()
            else:
                http("http://127.0.0.1:7815/comando", {"acao": "concluir"})
                threading.Thread(target=colar_kakashi, args=(False,), daemon=True).start()   # no Premiere só copia
            self.fora = None; self.troca_pc = None; return
        if cancelar:
            return
        tipo, j = tipo_da_frente()
        log("começar: %s (%s · %s)" % (tipo, j["app"], j["titulo"][:60]))
        self.ultima_voz = time.time()
        info = self.replay.parar()            # o buffer solta o microfone/tela antes de a gravação abrir
        if tipo == "premiere":
            threading.Thread(target=self.replay.descartar, args=(info,), daemon=True).start()
            http("http://127.0.0.1:7815/comando", {"acao": "iniciar"}); self.fora = "premiere"; self.quem_cache = "premiere"
        elif tipo == "luluka":
            threading.Thread(target=self.replay.descartar, args=(info,), daemon=True).start()
            http("http://127.0.0.1:7798/api/luluka/gravacao", {"acao": "iniciar"}, t=20); self.fora = "luluka"; self.quem_cache = "luluka"
        else:
            g = GravacaoPC(j, self, info)
            self.pc = g; self.inicio = g.t_grav; self.quem_cache = "pc"
            if info:
                threading.Thread(target=self.replay.extrair, args=(info, g), daemon=True).start()

    def medir_voz(self):
        """1x/s (o olho chama): (voz_recente, segundos em silêncio digital). Só dá pra medir na gravação própria e na do Luluka."""
        g = self.pc; arq = None
        if g:
            arq, ini, pc = g.fala_wav(), g.t_grav, True
        else:
            lu = http("http://127.0.0.1:7798/api/luluka/gravacao", t=1)
            if lu and lu.get("gravando") and lu.get("pasta"):
                arq, ini, pc = os.path.join(lu["pasta"], "fala.wav"), time.time(), False
        if not arq:
            self.voz_viva = None; self.mudo = 0.0
            return True, 0.0
        if self.voz_viva is None or self.voz_viva.arq != arq:
            self.voz_viva = VozViva(arq, ini, faltando_e_mudo=pc)
        self.mudo = self.voz_viva.medir(time.time())
        return self.voz_recente(arq), self.mudo

    def voz_recente(self, arq):
        """10 min sem voz no microfone → aviso"""
        if not arq or not os.path.isfile(arq):
            return True
        try:
            tam = os.path.getsize(arq)
            with open(arq, "rb") as f:
                f.seek(max(44, tam - 48000 * 2 * 5)); b = f.read()
            a = array.array("h"); a.frombytes(b[: len(b) // 2 * 2])
            if a:
                rms = (sum(x * x for x in a[::8]) / len(a[::8])) ** 0.5
                if rms > 400:            # ~ -38 dBFS: fala
                    self.ultima_voz = time.time()
        except Exception:
            return True
        return time.time() - (self.ultima_voz or time.time()) < 600


# ---------- porta 7816 (status + o card do Luluka sob o mouse) ----------
ORIGENS = {"http://localhost:7798", "http://127.0.0.1:7798"}


def servidor(k):
    class H(BaseHTTPRequestHandler):
        def _cab(self, cod, n=0):
            self.send_response(cod)
            o = self.headers.get("Origin")
            if o in ORIGENS:                     # só o Luluka (outro site aberto no Chrome não lê nem escreve aqui)
                self.send_header("Access-Control-Allow-Origin", o)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(n))

        def _json(self, cod, obj):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._cab(cod, len(b)); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers()
            self.wfile.write(b)

        def do_OPTIONS(self):
            self._cab(204); self.end_headers()

        def do_GET(self):
            if self.path.split("?")[0] == "/status":
                return self._json(200, k.status())
            self._json(404, {"ok": False})

        def do_POST(self):
            if self.path.split("?")[0] != "/luluka":
                return self._json(404, {"ok": False})
            o = self.headers.get("Origin")
            if o and o not in ORIGENS:
                return self._json(403, {"ok": False})
            try:
                d = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)).decode("utf-8") or "{}")
            except ValueError:
                return self._json(400, {"ok": False})
            if k.pc is None:
                return self._json(200, {"ok": False, "motivo": "o Kakashi do PC não está gravando"})
            ev = {"tipo": "luluka", "acao": str(d.get("acao") or "")[:20]}
            for c in ("id", "k", "titulo", "aba", "url"):
                if d.get(c) not in (None, ""):
                    ev[c] = str(d[c])[:200]
            for c in ("sx", "sy"):
                if isinstance(d.get(c), (int, float)):
                    ev[c] = int(d[c])
            k.vigia.emitir(ev)
            self._json(200, {"ok": True})

        def log_message(self, *a):
            pass

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORTA), H)
    except OSError as e:
        log("porta %d ocupada: %s" % (PORTA, e)); return
    srv.daemon_threads = True
    log("porta %d no ar" % PORTA)
    srv.serve_forever()


# ---------- atalho global ----------
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
WM_HOTKEY = 0x0312


def thread_atalhos(fila):
    """pacote da Fly (27/10): o atalho sai do config.json ("atalho" / "atalho_cancelar"; padrão Ctrl+Page Down, o do Luan) e
    a janelinha troca sem reiniciar: ela manda WM_RECARREGAR (registrar de novo) ou WM_SOLTAR (enquanto a pessoa aperta o novo)."""
    msg = wt.MSG()
    user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)        # cria a fila de mensagens desta thread antes de alguém postar
    atalho.THREAD_ID = kernel32.GetCurrentThreadId()

    def registrar():
        user32.UnregisterHotKey(None, 1); user32.UnregisterHotKey(None, 2)
        a = atalho.do_config(cfg()); g, c = a["gravar"], a["cancelar"]
        ok1 = bool(user32.RegisterHotKey(None, 1, g["mods"] | MOD_NOREPEAT, g["vk"]))
        ok2 = bool(c and user32.RegisterHotKey(None, 2, c["mods"] | MOD_NOREPEAT, c["vk"]))
        if a["erro"]:
            fila.put(("erro", a["erro"]))
        if not ok1:
            fila.put(("erro", "%s já é de outro programa: troque na janelinha do KAKASHI (TROCAR O ATALHO)" % g["nome"]))
        log("atalhos: %s=%s %s=%s" % (g["nome"], ok1, c["nome"] if c else "-", ok2))
        atalho.ATIVO = a if ok1 else None

    registrar()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY:
            fila.put(("cancelar" if msg.wParam == 2 else "alternar", None))
        elif msg.message == atalho.WM_RECARREGAR:
            registrar()
        elif msg.message == atalho.WM_SOLTAR:
            user32.UnregisterHotKey(None, 1); user32.UnregisterHotKey(None, 2)


# ---------- o Sharingan ----------
TRANSP = "#010203"
try:
    ESC = user32.GetDpiForSystem() / 96.0      # tela 4K com zoom do Windows: tudo cresce junto
except Exception:
    ESC = 1.0
# o olho é o do painel do Premiere: arte de 40x40 ampliada 4x nos PNGs (160) → aqui 1 bloco = 1 px (40), ou 2 px (80) no config "olho": 80
ICONES = os.path.join(CORRETOR, "painel", "icones")
OLHO = int(cfg().get("olho", 40))
W, H, R = int(220 * ESC), int(max(64, OLHO + 16) * ESC), int(OLHO * ESC) // 2


def olho_cinza_pil(arq, k):
    """P20: o quadro do olho em CINZA (mesmo tamanho do subsample(k) do Tk: pega 1 pixel a cada k). Transparência mantida."""
    from PIL import Image, ImageEnhance
    im = Image.open(arq).convert("RGBA")
    im = im.resize((max(1, -(-im.width // k)), max(1, -(-im.height // k))), Image.NEAREST)
    a = im.getchannel("A")
    g = ImageEnhance.Brightness(im.convert("L")).enhance(0.85).convert("RGBA")
    g.putalpha(a)
    return g


def olho_cinza(arq, k, master):
    from PIL import ImageTk
    return ImageTk.PhotoImage(olho_cinza_pil(arq, k), master=master)


class Tela:
    def __init__(self, k, fila):
        self.k, self.fila = k, fila
        self.root = tk.Tk(); self.root.overrideredirect(True); self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSP); self.root.attributes("-transparentcolor", TRANSP)
        c = cfg()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        # padrão: do lado esquerdo da bolinha do Whisper (centro dela ~27 px da direita e ~76 px do fim da tela)
        # posição lembrada pelo CENTRO do olho (se a janela mudar de largura, o olho continua onde ele deixou)
        ox, oy = c.get("olho_x", sw - int(83 * ESC)), c.get("olho_y", sh - int(76 * ESC))
        x, y = ox - (W - R - int(4 * ESC)), oy - H // 2
        self.root.geometry("%dx%d+%d+%d" % (W, H, x, y))
        self.cv = tk.Canvas(self.root, width=W, height=H, bg=TRANSP, highlightthickness=0); self.cv.pack()
        self.olho = self._carregar_olho(); self.modo = "escondido"; self.quadro = 0; self.prox = 0.0; self.visivel = True
        self.painel = None
        self.ang = 0.0; self.quem = None; self.desde = None; self.aviso = None; self.pisca = False; self.mudo = False; self.ult_estado = 0
        self.arr = None
        self.cv.bind("<ButtonPress-1>", self._apertou); self.cv.bind("<B1-Motion>", self._arrastou)
        self.cv.bind("<ButtonRelease-1>", self._soltou); self.cv.bind("<Button-3>", self._menu)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Cancelar a gravação (vai pra descartadas)", command=lambda: self._acao(True))
        self.menu.add_command(label="Abrir o painel do Kakashi", command=lambda: self.abrir_painel())
        self.menu.add_separator(); self.menu.add_command(label="Fechar o Kakashi", command=self._sair)
        # a bolinha NUNCA pega o foco (senão a "janela da frente" vira ela mesma): ferramenta + não-ativa
        self.root.update_idletasks()
        try:
            hw = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            GWL_EXSTYLE = -20
            est = user32.GetWindowLongW(hw, GWL_EXSTYLE)
            user32.SetWindowLongW(hw, GWL_EXSTYLE, est | 0x08000000 | 0x00000080)   # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        except Exception as e:
            log("noactivate: %s" % e)
        self._mostrar(False)
        self.root.after(50, self._tique)

    def _carregar_olho(self):
        # mesmos quadros e tempos do painel (main.js: ligar 55 ms, giro 90 ms em loop, desligar 45 ms ao contrário)
        k = max(1, round(160 / (OLHO * ESC)))
        abre = lambda n: tk.PhotoImage(file=os.path.join(ICONES, n)).subsample(k)
        nomes = {"olho": "olho.png",
                 "ligar": ["ligar_%02d.png" % i for i in range(18) if os.path.isfile(os.path.join(ICONES, "ligar_%02d.png" % i))],
                 "giro": ["giro_%02d.png" % i for i in range(12)]}
        olho_ = {c: abre(v) if isinstance(v, str) else [abre(n) for n in v] for c, v in nomes.items()}
        try:     # P20: os mesmos quadros em cinza = gravando MUDO (silêncio digital > 15 s)
            cinza = lambda n: olho_cinza(os.path.join(ICONES, n), k, self.root)
            self.olho_cinza = {c: cinza(v) if isinstance(v, str) else [cinza(n) for n in v] for c, v in nomes.items()}
        except Exception as e:
            log("olho cinza: %r" % e); self.olho_cinza = olho_
        return olho_

    def _animar(self):
        agora = time.time()
        if agora < self.prox:
            return
        grav = bool(self.quem)
        n_lig = len(self.olho["ligar"])
        if self.modo == "escondido":
            if grav:
                self._mostrar(True); self.modo = "olho_ini"; self.prox = agora + 0.25; return   # o olho aparece um instante
            return
        if self.modo == "olho_ini":
            self.modo, self.quadro = ("ligando", 0) if grav else ("escondido", 0)
            if not grav: self._mostrar(False)
        elif self.modo == "olho":
            if grav: self.modo, self.quadro = "ligando", 0
            else: self.modo = "escondido"; self._mostrar(False)
        elif self.modo == "ligando":
            if not grav: self.modo = "desligando"
            elif self.quadro >= n_lig - 1: self.modo, self.quadro = "giro", 0
            else: self.quadro += 1
        elif self.modo == "giro":
            if not grav: self.modo, self.quadro = "desligando", n_lig - 1
            else: self.quadro = (self.quadro + 1) % len(self.olho["giro"])
        elif self.modo == "desligando":
            if grav: self.modo = "ligando"
            elif self.quadro <= 0: self.modo = "olho"; self.prox = agora + 0.3; return   # fica o olho 0,3 s e some
            else: self.quadro -= 1
        self.prox = agora + {"ligando": 0.055, "giro": 0.090, "desligando": 0.045}.get(self.modo, 0.2)

    def _pixel(self, txt, cor):
        if not hasattr(self, "_px_cache"): self._px_cache = {}
        k = (txt, cor)
        if k not in self._px_cache:
            import pixel
            from PIL import ImageTk
            # 19/10: limpar ANTES de criar (antes limpava depois e apagava a imagem que ia desenhar → erro → o olho congelava aos ~400 s)
            if len(self._px_cache) > 300:
                for kk in list(self._px_cache)[:200]:
                    del self._px_cache[kk]
            self._px_cache[k] = ImageTk.PhotoImage(pixel.render(txt, 2, cor), master=self.root)
        return self._px_cache[k]

    def _mostrar(self, sim):
        if sim == self.visivel: return
        self.visivel = sim
        if sim:
            self.root.deiconify(); self.root.attributes("-topmost", True)
        else:
            self.root.withdraw()

    def _img_olho(self):
        o = self.olho_cinza if (self.mudo and self.quem) else self.olho
        if self.modo in ("ligando", "desligando"):
            return o["ligar"][max(0, min(self.quadro, len(o["ligar"]) - 1))]
        if self.modo == "giro":
            return o["giro"][self.quadro]
        return o["olho"]

    def _acao(self, cancelar=False):
        threading.Thread(target=lambda: (self.k.alternar(cancelar), self._forcar()), daemon=True).start()

    def _forcar(self):
        self.ult_estado = 0

    def _apertou(self, e):
        self.arr = (e.x_root, e.y_root, self.root.winfo_x(), self.root.winfo_y(), False)

    def _arrastou(self, e):
        if not self.arr: return
        x0, y0, wx, wy, _ = self.arr
        if abs(e.x_root - x0) + abs(e.y_root - y0) > 5:
            self.arr = (x0, y0, wx, wy, True)
            self.root.geometry("+%d+%d" % (wx + e.x_root - x0, wy + e.y_root - y0))

    def _soltou(self, e):
        if self.arr and self.arr[4]:
            c = cfg(); c.pop("x", None); c.pop("y", None)
            c["olho_x"], c["olho_y"] = self.root.winfo_x() + W - R - int(4 * ESC), self.root.winfo_y() + H // 2; salvar_cfg(c)
        elif self.arr:
            self._acao(False)
        self.arr = None

    def abrir_painel(self):
        if self.painel and self.painel.vivo():
            self.painel.win.deiconify(); self.painel.win.lift(); self.painel.win.focus_force(); return
        self.painel = Painel(self)

    def _menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def _sair(self):
        if self.k.pc:
            self.k.alternar()
            time.sleep(1)
        try:        # P20: o buffer fecha junto (antes os ffmpeg dele ficavam órfãos segurando o microfone)
            self.k.replay.descartar(self.k.replay.parar())
        except Exception as e:
            log("sair/replay: %r" % e)
        self.root.destroy(); os._exit(0)

    def _tique(self):
        # 19/10: o laço do olho NUNCA pode morrer (um erro aqui congelava o olho e o atalho parava de responder)
        try:
            self._tique_corpo()
        except Exception as e:
            log("tique: %r" % e)
        self.root.after(50, self._tique)

    def _tique_corpo(self):
        try:
            while True:
                tipo, info = self.fila.get_nowait()
                if tipo == "erro": self.aviso = info; log(info)
                else: self._acao(tipo == "cancelar")
        except queue.Empty:
            pass
        agora = time.time()
        if agora - self.ult_estado > 1.0:        # quem está gravando (1x por segundo, em segundo plano)
            self.ult_estado = agora
            threading.Thread(target=self._ler_estado, daemon=True).start()
        self._animar()
        if self.visivel: self._desenhar()
        if self.visivel and agora - getattr(self, "_ult_topo", 0) > 2.0:
            # 22/10 (Kakashi PC 14:40 [12:15] "isso aqui era pra ficar em cima de tudo, né, ó, sumiu"): o "-topmost" do tk se perde
            # depois de outra janela "sempre na frente" (ex.: o Lightshot) e o Chrome cobria o olho. Reafirma a cada 2 s, sem pegar foco.
            self._ult_topo = agora
            try:
                hw = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                user32.SetWindowPos(hw, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)   # HWND_TOPMOST; SWP_NOSIZE|NOMOVE|NOACTIVATE
            except Exception as e:
                log("topo: %r" % e)
        if agora - getattr(self, "_ult_flag", 0) > 0.5:      # o atalho da área de trabalho pediu a janelinha?
            self._ult_flag = agora
            if os.path.exists(FLAG_PAINEL):
                try: os.remove(FLAG_PAINEL)
                except OSError: pass
                self.abrir_painel()
        if self.painel: self.painel.tique()

    def _ler_estado(self):
        q, d = self.k.estado()
        self.quem, self.desde = q, d
        recente, mudo = self.k.medir_voz() if q else (True, 0.0)
        if not q:
            self.k.voz_viva = None; self.k.mudo = 0.0
        self.pisca = bool(q) and not recente
        self.mudo = bool(q) and mudo > MUDO_AVISO_S

    def _desenhar(self):
        cv = self.cv; cv.delete("all")
        cx, cy = W - R - int(4 * ESC), H // 2
        grav = bool(self.quem)
        amarelo = self.pisca and int(time.time() * 2) % 2 == 0
        if amarelo:     # 10 min sem voz: anel amarelo piscando em volta do olho
            cv.create_oval(cx - R - 4, cy - R - 4, cx + R + 4, cy + R + 4, outline="#FFE600", width=3)
        cv.create_image(cx, cy, image=self._img_olho())
        mudo = grav and self.mudo
        if grav and self.desde:
            s = int(time.time() - self.desde)
            txt = "%s %d:%02d" % ({"pc": "PC", "luluka": "Luluka", "premiere": "Premiere"}.get(self.quem, ""), s // 60, s % 60)
            if mudo:          # P20: gravação muda há > 15 s: olho cinza + "SEM SOM" piscando (vermelho / cinza a cada 0,5 s)
                txt = "SEM SOM %d:%02d" % (s // 60, s % 60)
            x1 = cx - R - 8
            cor_txt = ("vermelho" if int(time.time() * 2) % 2 == 0 else "cinza") if mudo else ("amarelo" if amarelo else "branco")
            cv.create_rectangle(4, cy - 13, x1, cy + 13, fill="#FFE600" if (amarelo and not mudo) else "#0B0B0D", outline="")
            cv.create_image((4 + x1) // 2, cy, image=self._pixel(txt.upper(), cor_txt))
        elif self.aviso:
            cv.create_image(cx - R - 8, cy, image=self._pixel("ATALHO OCUPADO", "amarelo"), anchor="e")


FLAG_PAINEL = os.path.join(AQUI, "abrir_painel.flag")
LULUKA_COR = os.path.join(AQUI, "_sem_luluka")   # pacote da Fly: o Luluka é do Luan, aqui não existe
PREMIERE_SES = os.path.join(AQUI, "premiere", "sessoes")   # pacote da Fly: o servidor do painel mora em premiere\


def gravacoes(n=12):
    """as últimas correções dos 3 Kakashis (PC, Luluka, Premiere), mais nova primeiro"""
    out = []
    for base, tipo in ((SESSOES, "PC"), (LULUKA_COR, "Luluka"), (PREMIERE_SES, "Premiere")):
        if not os.path.isdir(base):
            continue
        for nome in os.listdir(base):
            pasta = os.path.join(base, nome)
            if not re.match(r"20\d\d-", nome) or not os.path.isdir(pasta):
                continue
            try:
                m = json.load(open(os.path.join(pasta, "sessao.json"), encoding="utf-8"))
            except (OSError, ValueError):
                m = {}
            dur = m.get("duracao_s")
            if dur is None and m.get("fim") and m.get("inicio"):
                dur = m["fim"] - m["inicio"]
            quando = (m.get("inicio_local") or m.get("inicio_iso") or nome)[:16].replace("T", " ")
            extra = m.get("sequencia") or (m.get("janela_inicial") or {}).get("titulo") or ""
            out.append({"pasta": pasta, "base": base, "tipo": tipo, "quando": quando, "dur": dur, "extra": extra[:40],
                        "descartada": bool(m.get("descartada"))})
    out.sort(key=lambda x: x["quando"], reverse=True)
    return out[:n]


def descartar(g):
    """vai pra <origem>/_descartadas (nunca apaga) e marca descartada no sessao.json"""
    arq = os.path.join(g["pasta"], "sessao.json")
    try:
        m = json.load(open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        m = {}
    m["descartada"] = True; m["descartada_em"] = datetime.datetime.now().replace(microsecond=0).isoformat()
    try:
        json.dump(m, open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except OSError:
        pass
    dest = os.path.join(g["base"], "_descartadas"); os.makedirs(dest, exist_ok=True)
    try:
        shutil.move(g["pasta"], dest); return True
    except OSError as e:
        log("descartar: %s" % e); return False


class Painel:
    """Janelinha do KAKASHI em 8 bits — mesma estética do painel do Premiere (CORRETOR\\painel\\index.html: fundo #0b0b0e, canto
    reto, borda grossa com relevo claro em cima/esquerda e escuro embaixo/direita, fonte pixel 5x7 em caixa alta, título titulo.png,
    relógio d_*.png). 19/10, ele: "o Kakashi todo é pra tá na estética do plugin do Premiere, todo 8 bits... Esse nome aqui".
    Não pisca: a lista só é refeita quando muda."""
    FUNDO = "#0b0b0e"
    EST = {   # (fundo, claro, escuro, cor da letra)
        "vermelho": ("#d6001c", "#ff6a6a", "#5e000c", "branco"),
        "concluir": ("#15151a", "#34343e", "#050507", "vermelho"),
        "neutro":   ("#2a2a33", "#4a4a56", "#0a0a0d", "amarelo"),
        "mini":     ("#15151a", "#34343e", "#050507", "branco"),
        "perigo":   ("#2a0006", "#6a0a16", "#0a0002", "vermelho"),
        "off":      ("#1a1a20", "#24242b", "#0a0a0d", "apagado"),
    }

    def __init__(self, tela):
        import pixel
        from PIL import Image, ImageTk
        self.px, self.Image, self.ImageTk = pixel, Image, ImageTk
        self.tela = tela; self.cache = {}
        self.win = tk.Toplevel(tela.root); self.win.title("KAKASHI"); self.win.configure(bg=self.FUNDO)
        self.win.resizable(False, False)
        self.win.geometry("+%d+%d" % (tela.root.winfo_screenwidth() // 2 - 300, tela.root.winfo_screenheight() // 2 - 330))
        self.win.attributes("-topmost", True)
        try:
            self.win.iconphoto(False, tk.PhotoImage(file=os.path.join(ICONES, "icone_48.png")))
        except Exception:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.fechar)
        self.win.update_idletasks()
        try:    # barra de título escura (Windows 11)
            hw = user32.GetParent(self.win.winfo_id())
            v = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hw, 20, ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass
        self.olho_g = {"olho": tk.PhotoImage(file=os.path.join(ICONES, "olho.png")).subsample(2),
                       "giro": [tk.PhotoImage(file=os.path.join(ICONES, "giro_%02d.png" % i)).subsample(2) for i in range(12)]}
        app = tk.Frame(self.win, bg=self.FUNDO); app.pack(padx=12, pady=(12, 14))
        topo = tk.Frame(app, bg=self.FUNDO); topo.pack(fill="x", pady=(0, 12))
        self.lb_olho = tk.Label(topo, bg=self.FUNDO, image=self.olho_g["olho"], bd=0); self.lb_olho.pack(side="left", padx=(0, 10))
        marca = tk.Frame(topo, bg=self.FUNDO); marca.pack(side="left", fill="x")
        self.img_tit = tk.PhotoImage(file=os.path.join(ICONES, "titulo.png"))
        tk.Label(marca, image=self.img_tit, bg=self.FUNDO, bd=0).pack(anchor="w")
        self.lb_sub = tk.Label(marca, bg=self.FUNDO, bd=0); self.lb_sub.pack(anchor="w", pady=(4, 0))
        self._texto(self.lb_sub, atalho.legenda(cfg()), "vermelho")
        # relógio + status (igual ao painel)
        self.lb_crono = tk.Label(app, bg=self.FUNDO, bd=0); self.lb_crono.pack(pady=(2, 0))
        lin = tk.Frame(app, bg=self.FUNDO); lin.pack(pady=(6, 0))
        self.ponto = tk.Frame(lin, width=8, height=8, bg="#5b5b63"); self.ponto.pack(side="left", padx=(0, 8))
        self.lb_status = tk.Label(lin, bg=self.FUNDO, bd=0); self.lb_status.pack(side="left")
        # botão grande + cancelar do lado
        self.bt_grav = self._botao(app, 520, 44, lambda: self.tela._acao(False)); self.bt_grav.pack(pady=(10, 0))
        self.bt_canc = self._botao(app, 520, 30, lambda: self.tela._acao(True)); self.bt_canc.pack(pady=(6, 0))
        # gravações
        self.lb_tit_lista = tk.Label(app, bg=self.FUNDO, bd=0); self.lb_tit_lista.pack(anchor="w", pady=(16, 6))
        self._texto(self.lb_tit_lista, "GRAVADAS", "amarelo", 3)
        self.lista = tk.Frame(app, bg=self.FUNDO); self.lista.pack(fill="x")
        pe = tk.Frame(app, bg=self.FUNDO); pe.pack(fill="x", pady=(12, 0))
        b1 = self._botao(pe, 256, 30, lambda: os.startfile(SESSOES)); b1.pack(side="left")
        self._pintar(b1, "mini", "ABRIR A PASTA DO PC")
        b2 = self._botao(pe, 256, 30, tela._sair); b2.pack(side="right")
        self._pintar(b2, "perigo", "FECHAR O KAKASHI")
        pe2 = tk.Frame(app, bg=self.FUNDO); pe2.pack(fill="x", pady=(6, 0))     # pacote da Fly: trocar o atalho
        self.bt_atalho = self._botao(pe2, 520, 30, self.trocar_atalho); self.bt_atalho.pack()
        self._pintar(self.bt_atalho, "mini", "TROCAR O ATALHO")
        pe3 = tk.Frame(app, bg=self.FUNDO); pe3.pack(fill="x", pady=(6, 0))     # pacote da Fly: atualização
        self.bt_atual = self._botao(pe3, 520, 30, self.atualizacao); self.bt_atual.pack()
        self._nova_pintada = "?"; self._pintar_atual()
        self.giro_i = 0; self.ult_giro = 0; self.ult_lista = 0; self.assinatura = None; self.estado_bt = None
        self.montar_lista(forcar=True)

    # ---- peças 8 bits
    def _img(self, txt, cor, E=2):
        k = (txt, cor, E)
        if k not in self.cache:
            self.cache[k] = self.ImageTk.PhotoImage(self.px.render(txt, E, cor), master=self.win)
        return self.cache[k]

    def _texto(self, label, txt, cor, E=2):
        label.configure(image=self._img(txt, cor, E))

    def _botao(self, pai, w, h, cmd):
        cv = tk.Canvas(pai, width=w, height=h, bg=self.FUNDO, highlightthickness=0, bd=0, cursor="hand2")
        cv._cmd = cmd; cv._est = None
        cv.bind("<Button-1>", lambda e: cv._cmd() if cv._est != "off" else None)
        return cv

    def _pintar(self, cv, est, txt, E=2):
        chave = (est, txt, E)
        if getattr(cv, "_chave", None) == chave:
            return
        cv._chave = chave; cv._est = est
        w, h = int(cv["width"]), int(cv["height"]); b = 4 if h >= 40 else 3
        f, cl, es, cor = self.EST[est]
        cv.delete("all")
        cv.create_rectangle(0, 0, w, h, fill=f, outline="")
        cv.create_rectangle(0, 0, w, b, fill=cl, outline=""); cv.create_rectangle(0, 0, b, h, fill=cl, outline="")
        cv.create_rectangle(0, h - b, w, h, fill=es, outline=""); cv.create_rectangle(w - b, 0, w, h, fill=es, outline="")
        cv.create_image(w // 2, h // 2 + 1, image=self._img(txt, cor, E))
        cv.configure(cursor="arrow" if est == "off" else "hand2")

    def trocar_atalho(self):
        """pacote da Fly (27/10): aperta o botão, aperta o atalho novo (Esc cancela); grava no config.json e vale na hora."""
        if self.tela.quem:
            self._pintar(self.bt_atalho, "mini", "CONCLUA A GRAVACAO ANTES")
            self.win.after(2500, lambda: self.vivo() and self._pintar(self.bt_atalho, "mini", "TROCAR O ATALHO")); return
        if getattr(self, "_capturando", False):
            return
        self._capturando = True; self._cap_r = None
        atalho.soltar()                       # o atalho de agora não dispara enquanto a pessoa aperta o novo
        self._pintar(self.bt_atalho, "neutro", "APERTE O ATALHO NOVO · ESC CANCELA")
        threading.Thread(target=lambda: setattr(self, "_cap_r", atalho.capturar()), daemon=True).start()

    def _fim_troca(self, r):
        self._capturando = False
        if r.get("ok"):
            c = cfg(); c["atalho"] = r["texto"]; c.pop("atalho_cancelar", None); salvar_cfg(c)
            log("atalho trocado na janelinha: " + r["texto"])
        atalho.recarregar()                   # registra o novo (ou devolve o antigo, se cancelou)
        self._texto(self.lb_sub, atalho.legenda(cfg()), "vermelho")
        self._pintar(self.bt_atalho, "mini", r["msg"])
        self.win.after(3500, lambda: self.vivo() and self._pintar(self.bt_atalho, "mini", "TROCAR O ATALHO"))

    def _pintar_atual(self):
        """pacote da Fly (27/10): o botão de atualização mostra a versão nova assim que o vigia (atualizar.py) acha."""
        self._nova_pintada = atualizar.NOVA
        if atualizar.NOVA:
            self._pintar(self.bt_atual, "neutro", "ATUALIZAR PRA " + atualizar.NOVA)
        else:
            self._pintar(self.bt_atual, "mini", "PROCURAR ATUALIZACAO · VERSAO " + atualizar.versao_local())

    def atualizacao(self):
        if getattr(self, "_procurando", False):
            return
        if atualizar.NOVA:
            if self.tela.quem:
                self._pintar(self.bt_atual, "mini", "CONCLUA A GRAVACAO ANTES")
                self.win.after(2500, lambda: self.vivo() and self._pintar_atual()); return
            atualizar.abrir_instalador_em_janela()     # janela preta à parte: ela fecha e reabre o Kakashi no fim
            log("atualização: o botão abriu o atualizador (%s)" % atualizar.NOVA)
            self._pintar(self.bt_atual, "neutro", "ATUALIZANDO · ACOMPANHE NA JANELA PRETA"); return
        self._procurando = True; self._atual_r = None
        self._pintar(self.bt_atual, "neutro", "PROCURANDO...")
        threading.Thread(target=lambda: setattr(self, "_atual_r", atualizar.checar()), daemon=True).start()

    def _fim_procura(self, r):
        self._procurando = False
        if r["estado"] == "erro":
            self._pintar(self.bt_atual, "mini", "SEM INTERNET OU GITHUB FORA")
            self.win.after(3500, lambda: self.vivo() and self._pintar_atual())
        elif r["estado"] == "em_dia":
            self._pintar(self.bt_atual, "mini", "EM DIA · VERSAO " + r["local"])
            self.win.after(3500, lambda: self.vivo() and self._pintar_atual())
        else:
            self._pintar_atual()

    def vivo(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def fechar(self):
        self.win.destroy(); self.tela.painel = None

    def montar_lista(self, forcar=False):
        gs = gravacoes(10)
        grav_pasta = os.path.normcase(self.tela.k.pc.pasta) if (self.tela.k.pc) else None
        ass = tuple((g["pasta"], g["dur"]) for g in gs) + (grav_pasta,)
        self.ult_lista = time.time()
        if ass == self.assinatura and not forcar:
            return          # nada mudou: não refaz (era isso que fazia piscar)
        self.assinatura = ass
        for w in self.lista.winfo_children():
            w.destroy()
        if not gs:
            l = tk.Label(self.lista, bg=self.FUNDO, bd=0); l.pack(anchor="w"); self._texto(l, "NENHUMA AINDA", "cinza")
        for g in gs:
            ln = tk.Frame(self.lista, bg="#121217", highlightthickness=0); ln.pack(fill="x", pady=2)
            d = g["dur"]; dur = "%d:%02d" % (int(d) // 60, int(d) % 60) if d else "GRAVANDO"
            q = g["quando"]      # 2026-10-19 15:31 → 19/10 15:31
            q = "%s/%s %s" % (q[8:10], q[5:7], q[11:16]) if len(q) >= 16 else q
            l = tk.Label(ln, bg="#121217", bd=0); l.pack(side="left", padx=8, pady=6)
            self._texto(l, "%s · %s · %s" % (q, g["tipo"], dur), "branco")
            esta = grav_pasta and os.path.normcase(g["pasta"]) == grav_pasta
            if not esta:
                b = self._botao(ln, 120, 26, lambda g=g: (descartar(g), self.montar_lista(forcar=True))); b.pack(side="right", padx=(4, 4), pady=3)
                self._pintar(b, "perigo", "DESCARTAR")
            b = self._botao(ln, 80, 26, lambda g=g: os.startfile(g["pasta"])); b.pack(side="right", pady=3)
            self._pintar(b, "mini", "ABRIR")

    def tique(self):
        if not self.vivo():
            self.tela.painel = None; return
        if getattr(self, "_capturando", False) and getattr(self, "_cap_r", None) is not None:
            r, self._cap_r = self._cap_r, None; self._fim_troca(r)
        if getattr(self, "_procurando", False) and getattr(self, "_atual_r", None) is not None:
            r, self._atual_r = self._atual_r, None; self._fim_procura(r)
        elif not getattr(self, "_procurando", False) and getattr(self, "_nova_pintada", "?") != atualizar.NOVA:
            self._pintar_atual()            # o vigia achou versão nova enquanto a janelinha estava aberta
        grav = bool(self.tela.quem); agora = time.time()
        if grav and agora - self.ult_giro > 0.09:
            self.ult_giro = agora; self.giro_i = (self.giro_i + 1) % 12
            self.lb_olho.configure(image=self.olho_g["giro"][self.giro_i])
        elif not grav and getattr(self, "_olho_parado", False) is False:
            self.lb_olho.configure(image=self.olho_g["olho"])
        self._olho_parado = not grav
        s_ = int(agora - self.tela.desde) if (grav and self.tela.desde) else 0
        crono = "%02d:%02d" % (s_ // 60 % 100, s_ % 60)
        if getattr(self, "_crono", None) != crono:
            self._crono = crono; self._texto(self.lb_crono, crono, "branco", 5)
        quem = {"pc": "PC", "luluka": "LULUKA", "premiere": "PREMIERE"}.get(self.tela.quem, "")
        mudo = grav and self.tela.mudo
        est = ("gravando", quem, mudo) if grav else ("parado",)
        if est != self.estado_bt:
            self.estado_bt = est
            self.ponto.configure(bg=("#5b5b63" if mudo else "#ff1e2e") if grav else "#39d353")
            self._texto(self.lb_status, ("GRAVANDO · " + quem + (" · SEM SOM" if mudo else "")) if grav else "PRONTO · NADA GRAVANDO",
                        ("vermelho" if mudo else "branco") if grav else "cinza")
            self._pintar(self.bt_grav, "concluir" if grav else "vermelho", "CONCLUIR" if grav else "INICIAR", 3)
            self._pintar(self.bt_canc, "mini" if grav else "off", "CANCELAR A GRAVAÇAO")
        if agora - self.ult_lista > 3:
            self.montar_lista()


def main():
    painel = "--painel" in sys.argv
    kernel32.CreateMutexW(None, False, "Global\\KakashiUnicoLuan")
    if kernel32.GetLastError() == 183:      # já tem um aberto: só pede pra ele abrir a janelinha
        if painel:
            open(FLAG_PAINEL, "w").close()
        return
    if painel:
        open(FLAG_PAINEL, "w").close()
    os.makedirs(SESSOES, exist_ok=True)
    fila = queue.Queue()
    threading.Thread(target=thread_atalhos, args=(fila,), daemon=True).start()
    threading.Thread(target=atualizar.vigia, args=(FLAG_PAINEL, cfg, salvar_cfg, log), daemon=True).start()   # pacote da Fly
    log("ligado")
    k = Kakashi()
    threading.Thread(target=servidor, args=(k,), daemon=True).start()
    Tela(k, fila).root.mainloop()


if __name__ == "__main__":
    main()
