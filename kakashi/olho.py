# -*- coding: utf-8 -*-
"""OLHO DE DEUS do Kakashi do PC (P3, 21/10/2026). As peças que o kakashi.pyw usa gravando e o resumo_pc.py usa lendo.

Pedido dele: "o Kakashi é a evolução de uma gravação de vídeo" / "o bom do Kakashi é que eu só falo ... você que tem que ser
inteligente pra entender o que eu tô falando". Nada de tecla extra pra ele apertar.

- UIA ............ o elemento debaixo do mouse pelo Windows UI Automation (nome, tipo, app, retângulo), só ctypes (sem biblioteca)
- print_nativo ... print na resolução NATIVA do monitor onde o cursor está, cursor marcado + recorte 800x500 em volta
- ler_area ....... o que ele copiou (texto, link, imagem, arquivos); conteúdo de gerenciador de senha NUNCA é lido
- historico_chrome / baixar_refs ... páginas abertas no Chrome (endereço + título + hora) e a imagem dos pins do Pinterest
- extrair_* / juntar_* ... o replay (os 2 min antes do atalho) e a junção com a gravação
Só CPU. Nunca toca som.
"""
import array, ctypes, ctypes.wintypes as wt, datetime, hashlib, html, json, os, re, shutil, sqlite3, subprocess, tempfile, time
import urllib.request, wave

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
ole32 = ctypes.windll.ole32
oleaut32 = ctypes.windll.oleaut32
oleaut32.SysFreeString.argtypes = [ctypes.c_void_p]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
SEM_JANELA = 0x08000000


def exe_do_pid(pid):
    h = kernel32.OpenProcess(0x1000, False, int(pid or 0))   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520); tam = wt.DWORD(520)
        return os.path.basename(buf.value) if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)) else ""
    finally:
        kernel32.CloseHandle(h)


# ------------------------------------------------------------------ UI Automation (o que está debaixo do mouse)
class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


def _guid(s):
    g = GUID()
    ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    return g


def _metodo(ptr, idx, *argtypes):
    vt = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vt[idx])


class UIA:
    """IUIAutomation pela tabela de métodos (UIAutomationClient.h). Um objeto por thread (cada thread faz o seu CoInitialize).
    IUIAutomation: 7 ElementFromPoint, 8 GetFocusedElement, 14 ControlViewWalker. Elemento: 20 ProcessId, 21 ControlType,
    22 LocalizedControlType, 23 Name, 29 AutomationId, 30 ClassName, 35 IsPassword, 43 BoundingRectangle. Walker: 3 GetParent."""

    def __init__(self):
        ole32.CoInitializeEx(None, 0)          # MTA
        self.p = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(_guid("{FF48DBA4-60EF-4201-AA87-54103EEF594E}")), None, 1,
                                    ctypes.byref(_guid("{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}")), ctypes.byref(self.p))
        if hr != 0 or not self.p.value:
            raise OSError("UIA: CoCreateInstance = 0x%08X" % (hr & 0xFFFFFFFF))
        w = ctypes.c_void_p()
        self.walker = w if _metodo(self.p, 14, ctypes.POINTER(ctypes.c_void_p))(self.p, ctypes.byref(w)) == 0 and w.value else None

    @staticmethod
    def _solta(el):
        try:
            if el and el.value:
                _metodo(el, 2)(el)
        except Exception:
            pass

    @staticmethod
    def _bstr(el, idx):
        b = ctypes.c_void_p()
        if _metodo(el, idx, ctypes.POINTER(ctypes.c_void_p))(el, ctypes.byref(b)) != 0 or not b.value:
            return ""
        try:
            return ctypes.wstring_at(b.value)
        finally:
            oleaut32.SysFreeString(b)

    @staticmethod
    def _int(el, idx):
        v = ctypes.c_int()
        return v.value if _metodo(el, idx, ctypes.POINTER(ctypes.c_int))(el, ctypes.byref(v)) == 0 else None

    @staticmethod
    def _ret(el):
        r = wt.RECT()
        if _metodo(el, 43, ctypes.POINTER(wt.RECT))(el, ctypes.byref(r)) != 0:
            return None
        return [r.left, r.top, r.right, r.bottom]

    def _pai(self, el):
        if not self.walker:
            return None
        p = ctypes.c_void_p()
        if _metodo(self.walker, 3, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(self.walker, el, ctypes.byref(p)) != 0:
            return None
        return p if p.value else None

    def em(self, x, y):
        """o elemento no ponto (x, y) da tela: {nome, controle, tipo_id, app, ret, [dentro_de], [senha]}"""
        el = ctypes.c_void_p()
        if _metodo(self.p, 7, wt.POINT, ctypes.POINTER(ctypes.c_void_p))(self.p, wt.POINT(int(x), int(y)), ctypes.byref(el)) != 0 \
                or not el.value:
            return None
        soltar = [el]
        try:
            senha = bool(self._int(el, 35))
            d = {"nome": "" if senha else self._bstr(el, 23).strip()[:200], "controle": self._bstr(el, 22),
                 "tipo_id": self._int(el, 21), "app": exe_do_pid(self._int(el, 20)), "ret": self._ret(el)}
            if senha:
                d["senha"] = True
            aid = self._bstr(el, 29)
            if aid and not senha:
                d["automation_id"] = aid[:80]
            # quem contém (o card, o item da lista, o botão): sobe até achar um nome, no máximo 4 níveis
            atual = el
            for _ in range(4):
                pai = self._pai(atual)
                if not pai:
                    break
                soltar.append(pai); atual = pai
                n = self._bstr(atual, 23).strip()
                if n and n != d["nome"]:
                    d["dentro_de"] = {"nome": n[:120], "controle": self._bstr(atual, 22)}
                    break
            return d
        finally:
            for e in soltar:
                self._solta(e)

    def foco_e_senha(self):
        el = ctypes.c_void_p()
        if _metodo(self.p, 8, ctypes.POINTER(ctypes.c_void_p))(self.p, ctypes.byref(el)) != 0 or not el.value:
            return False
        try:
            return bool(self._int(el, 35))
        finally:
            self._solta(el)


# ------------------------------------------------------------------ print nativo
class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


user32.MonitorFromPoint.argtypes = [wt.POINT, wt.DWORD]
user32.MonitorFromPoint.restype = ctypes.c_void_p
user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]


def monitor_de(x, y):
    h = user32.MonitorFromPoint(wt.POINT(int(x), int(y)), 2)     # MONITOR_DEFAULTTONEAREST
    mi = MONITORINFO(); mi.cbSize = ctypes.sizeof(mi)
    if h and user32.GetMonitorInfoW(h, ctypes.byref(mi)):
        r = mi.rcMonitor
        return (r.left, r.top, r.right, r.bottom)
    return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def miniatura(im):
    return im.resize((96, 54)).convert("L")


def parecida(a, b):
    """duas miniaturas quase iguais (a tela não mudou)"""
    if a is None or b is None:
        return False
    from PIL import ImageChops, ImageStat
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] < 1.5


def print_nativo(x, y):
    """(imagem do monitor inteiro em resolução nativa, retângulo do monitor). A marca do cursor entra no salvar_print."""
    from PIL import ImageGrab
    l, t, r, b = monitor_de(x, y)
    return ImageGrab.grab(bbox=(l, t, r, b), all_screens=True), (l, t, r, b)


def salvar_print(im, mon, x, y, base):
    """base.jpg = monitor inteiro com o cursor marcado; base_perto.jpg = recorte 800x500 em volta do cursor"""
    from PIL import ImageDraw
    l, t = mon[0], mon[1]
    cx, cy = int(x) - l, int(y) - t
    im = im.convert("RGB")
    d = ImageDraw.Draw(im)
    # anel largo + ponto pequeno: marca onde está o cursor sem tampar a palavra que ele aponta
    for rad, larg, cor in ((52, 7, (0, 0, 0)), (49, 4, (255, 30, 46))):
        d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), outline=cor, width=larg)
    d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(255, 30, 46), outline=(0, 0, 0))
    im.save(base + ".jpg", quality=82)
    W, H = im.size
    cl, ct = max(0, min(cx - 400, W - 800)), max(0, min(cy - 250, H - 500))
    im.crop((cl, ct, cl + min(800, W), ct + min(500, H))).save(base + "_perto.jpg", quality=90)


# ------------------------------------------------------------------ área de transferência (o que ele copiou)
CF_UNICODETEXT, CF_BITMAP, CF_DIB, CF_HDROP, CF_DIBV5 = 13, 2, 8, 15, 17
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [wt.UINT]
user32.EnumClipboardFormats.argtypes = [wt.UINT]
user32.EnumClipboardFormats.restype = wt.UINT
user32.GetClipboardSequenceNumber.restype = wt.DWORD
user32.RegisterClipboardFormatW.restype = wt.UINT
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]; kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]; kernel32.GlobalSize.restype = ctypes.c_size_t
# formatos que gerenciador de senha (KeePass, 1Password, Bitwarden...) põe pra ninguém ler/guardar o que ele copiou
F_EXCLUIR = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
F_IGNORAR = user32.RegisterClipboardFormatW("Clipboard Viewer Ignore")
F_HISTORICO = user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
F_NUVEM = user32.RegisterClipboardFormatW("CanUploadToCloudClipboard")
F_HTML = user32.RegisterClipboardFormatW("HTML Format")
GERENCIADORES = {"keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe", "lastpass.exe", "dashlane.exe", "nordpass.exe",
                 "enpass.exe", "roboform.exe", "keeper.exe", "keeperpasswordmanager.exe", "proton pass.exe", "protonpass.exe"}


def _dword(fmt):
    h = user32.GetClipboardData(fmt)
    p = kernel32.GlobalLock(h) if h else None
    if not p:
        return None
    try:
        return ctypes.c_uint32.from_address(p).value
    finally:
        kernel32.GlobalUnlock(h)


def ler_area():
    """{"protegido": True} | {"texto", "html_fonte", "html_img", "imagem": bool, "arquivos": bool} | None (não abriu)"""
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return None
    try:
        fmts = set(); f = 0
        while True:
            f = user32.EnumClipboardFormats(f)
            if not f:
                break
            fmts.add(f)
        if F_EXCLUIR in fmts or F_IGNORAR in fmts:
            return {"protegido": True}
        for fp in (F_HISTORICO, F_NUVEM):
            if fp in fmts and _dword(fp) == 0:
                return {"protegido": True}
        r = {"imagem": bool(fmts & {CF_DIB, CF_DIBV5, CF_BITMAP}), "arquivos": CF_HDROP in fmts}
        if CF_UNICODETEXT in fmts:
            h = user32.GetClipboardData(CF_UNICODETEXT); p = kernel32.GlobalLock(h) if h else None
            if p:
                try:
                    r["texto"] = ctypes.wstring_at(p)
                finally:
                    kernel32.GlobalUnlock(h)
        if F_HTML in fmts:
            h = user32.GetClipboardData(F_HTML); p = kernel32.GlobalLock(h) if h else None
            if p:
                try:
                    raw = ctypes.string_at(p, min(kernel32.GlobalSize(h), 400000)).decode("utf-8", "replace")
                finally:
                    kernel32.GlobalUnlock(h)
                m = re.search(r"SourceURL:(\S+)", raw)
                if m:
                    r["html_fonte"] = m.group(1)
                m = re.search(r"<img[^>]+src=\"([^\"]+)\"", raw, re.I)
                if m:
                    r["html_img"] = html.unescape(m.group(1))[:500]
        return r
    finally:
        user32.CloseClipboard()


def pasta_capturas():
    """Imagens\\Capturas de Tela (onde a Ferramenta de Captura / Win+Shift+S salva sozinha)"""
    p = ctypes.c_void_p()
    try:
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(_guid("{B7BEDE81-DF94-4682-A7D8-57A52620B86F}")), 0, None,
                                                      ctypes.byref(p)) == 0 and p.value:
            s = ctypes.wstring_at(p.value); ole32.CoTaskMemFree(p)
            return s
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Pictures", "Screenshots")


def hash_imagem(im):
    return hashlib.sha1(im.convert("RGB").tobytes()).hexdigest()


# ------------------------------------------------------------------ Chrome: páginas abertas + imagens dos pins
def _chrome_hist():
    """pacote da Fly: o perfil do Chrome mais usado DESTA pessoa (o History mexido por último)"""
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
    try:
        cands = [os.path.join(base, d, "History") for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, "History"))]
    except OSError:
        cands = []
    return max(cands, key=os.path.getmtime) if cands else os.path.join(base, "Default", "History")


CHROME_HIST = _chrome_hist()


def historico_chrome(ini_epoch, fim_epoch):
    """[{epoch, url, titulo}] das visitas entre os dois instantes (cópia do History; a hora bate com o relógio da gravação)"""
    tmp = os.path.join(tempfile.gettempdir(), "kakashi_history_%d.sqlite" % os.getpid())
    for src in (CHROME_HIST, CHROME_HIST.replace("\\\\localhost\\C$", "C:")):
        try:
            shutil.copyfile(src, tmp)
            break
        except OSError:
            continue
    else:
        raise OSError("não consegui copiar o histórico do Chrome")
    try:
        con = sqlite3.connect(tmp)
        a = int((ini_epoch + 11644473600) * 1e6); b = int((fim_epoch + 11644473600) * 1e6)
        linhas = con.execute("SELECT v.visit_time, u.url, u.title FROM visits v JOIN urls u ON u.id = v.url "
                             "WHERE v.visit_time BETWEEN ? AND ? ORDER BY v.visit_time", (a, b)).fetchall()
        con.close()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    out = []
    for vt, url, tit in linhas:
        if re.match(r"(chrome|about|chrome-extension|devtools|edge)://", url or "") or url.startswith("chrome-search:"):
            continue
        if out and out[-1]["url"] == url and vt / 1e6 - 11644473600 - out[-1]["epoch"] < 3:
            continue                     # redirecionamento / recarregou na hora: uma visita só
        out.append({"epoch": round(vt / 1e6 - 11644473600, 2), "url": url, "titulo": tit or ""})
    return out


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"


def _baixar(url, t=20, limite=40_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=t) as r:
        return r.read(limite), r.headers.get("Content-Type", "")


def og_image(url):
    pagina, _ = _baixar(url, limite=3_000_000)
    s = pagina.decode("utf-8", "replace")
    for pad in (r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"',
                r'<meta[^>]+name="og:image"[^>]+content="([^"]+)"'):
        m = re.search(pad, s, re.I)
        if m:
            return html.unescape(m.group(1))
    return None


def imagem_do_pin(pin_id, url):
    """A página do pin NÃO traz og:image (21/10: o Pinterest manda só o app em JS). O widget público dá a imagem dos pins
    públicos; pin de pasta SECRETA (a LULUKA dele) volta vazio → None (fica valendo o print nativo da página)."""
    try:
        b, _ = _baixar("https://widgets.pinterest.com/v3/pidgets/pins/info/?pin_ids=" + pin_id)
        d = (json.loads(b).get("data") or [None])[0]
        if d and d.get("images"):
            maior = max(d["images"].values(), key=lambda v: v.get("width") or 0)
            return maior.get("url")
    except Exception:
        pass
    try:
        return og_image(url)
    except Exception:
        return None


def baixar_refs(links, pasta):
    """Pin do Pinterest = baixa a imagem (tenta a original); link direto de imagem = baixa. Marca link["ref"] = _refs\\arquivo.
    Pin privado: link["ref_erro"] = "pin privado" (a imagem não sai sem o login dele; o print da página fica valendo)."""
    dest = os.path.join(pasta, "_refs")
    feitos = {}
    for l in links:
        u = l["url"]
        m = re.search(r"pinterest\.[a-z.]+/pin/([\w-]+)", u)
        img = nome = None
        try:
            if m:
                nome = "pin_" + m.group(1)
                if nome in feitos:
                    if feitos[nome]:
                        l["ref"] = feitos[nome]
                    else:
                        l["ref_erro"] = "pin privado"
                    continue
                feitos[nome] = None
                img = imagem_do_pin(m.group(1), u)
                if not img:
                    l["ref_erro"] = "pin privado"
                    continue
            elif re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", u, re.I) or "i.pinimg.com" in u:
                nome = "img_" + hashlib.sha1(u.encode()).hexdigest()[:10]
                img = u
            if not img:
                continue
            tentativas = [img]
            if "i.pinimg.com" in img and "/originals/" not in img:
                tentativas.insert(0, re.sub(r"i\.pinimg\.com/[^/]+/", "i.pinimg.com/originals/", img))
            for tent in tentativas:
                try:
                    dados, tipo = _baixar(tent)
                except Exception:
                    continue
                if not dados or not tipo.startswith("image"):
                    continue
                ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(tipo.split(";")[0], ".jpg")
                os.makedirs(dest, exist_ok=True)
                with open(os.path.join(dest, nome + ext), "wb") as f:
                    f.write(dados)
                l["ref"] = feitos[nome] = "_refs\\" + nome + ext
                l["ref_url"] = tent
                break
        except Exception as e:
            l["ref_erro"] = str(e)[:120]
    return links


def t_da_sessao(epoch, meta):
    """segundo da gravação de um instante do relógio de parede. Sessão PC: epoch − início. Olho do Premiere (23/10): relógio
    do PAINEL, sem as pausas nem os pedaços apagados (relogio_trechos = [[inicio, t0, fim], ...] das partes que ficaram);
    instante numa pausa ou num pedaço apagado = o segundo do corte (igual ao t_gravacao do CORRETOR)"""
    ini = meta.get("inicio_epoch") or 0
    tre = meta.get("relogio_trechos")
    if not tre:
        return epoch - ini
    for e0, t0, e1 in tre:
        if epoch < e0:
            return t0
        if epoch <= e1:
            return t0 + (epoch - e0)
    e0, t0, e1 = tre[-1]
    return t0 + (e1 - e0)


def fim_da_sessao(meta):
    """epoch do fim (o olho do Premiere guarda fim_epoch: com pausa, início + duração não chega no fim)"""
    return meta.get("fim_epoch") or (meta.get("inicio_epoch") or 0) + (meta.get("duracao_s") or 0)


def links_da_sessao(pasta, meta, baixar=True):
    """lê o histórico do Chrome no intervalo da sessão (com o replay) → links.json na pasta; devolve a lista"""
    ini = meta.get("inicio_epoch") or 0
    fim = fim_da_sessao(meta) + 5
    links = historico_chrome(ini - 2, fim)
    for l in links:
        l["t"] = round(t_da_sessao(l["epoch"], meta), 2)
    if baixar:
        baixar_refs(links, pasta)
    with open(os.path.join(pasta, "links.json"), "w", encoding="utf-8") as f:
        json.dump({"lido_em": datetime.datetime.now().replace(microsecond=0).isoformat(), "links": links}, f, ensure_ascii=False, indent=1)
    return links


# ------------------------------------------------------------------ áudio/vídeo: replay e junção
def duracao(arq):
    try:
        r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", arq],
                           capture_output=True, timeout=30, creationflags=SEM_JANELA)
        return float(r.stdout.decode().strip())
    except Exception:
        return 0.0


def ler_wav(arq):
    """(bytes PCM, taxa, canais, largura). Aguenta wav de processo morto (tamanho 'desconhecido' no cabeçalho)."""
    with open(arq, "rb") as f:
        b = f.read()
    i = b.find(b"fmt ")
    canais, taxa = int.from_bytes(b[i + 10:i + 12], "little"), int.from_bytes(b[i + 12:i + 16], "little")
    larg = int.from_bytes(b[i + 22:i + 24], "little") // 8
    j = b.find(b"data", i)
    dados = b[j + 8:]
    return dados[: len(dados) // (canais * larg) * canais * larg], taxa, canais, larg


def gravar_wav(arq, dados, taxa, canais, larg=2):
    with wave.open(arq, "wb") as w:
        w.setnchannels(canais); w.setsampwidth(larg); w.setframerate(taxa); w.writeframes(dados)


def extrair_wav_fim(segs, segundos, saida):
    """junta os pedaços de wav (em ordem) e fica com os ÚLTIMOS 'segundos' (silêncio no começo se faltar)"""
    partes, fmt = [], None
    for s in segs:
        try:
            d, taxa, can, larg = ler_wav(s)
        except Exception:
            continue
        if fmt is None:
            fmt = (taxa, can, larg)
        if (taxa, can, larg) == fmt:
            partes.append(d)
    if fmt is None:
        return False
    taxa, can, larg = fmt
    tudo = b"".join(partes)
    n = int(round(segundos * taxa)) * can * larg
    tudo = tudo[-n:] if len(tudo) >= n else b"\0" * (n - len(tudo)) + tudo
    gravar_wav(saida, tudo, taxa, can, larg)
    return True


MUDO = 2       # pico de 16 bits abaixo disto = silêncio digital (< -85 dBFS; o microfone sem fio dele corta pra 0/±1 nas pausas)


def pico_fim(arqs, segundos):
    """maior |amostra| dos ÚLTIMOS 'segundos' da sequência de wavs (o último pode estar sendo gravado); None = sem dado"""
    picos, falta = [], segundos
    for arq in reversed(arqs):
        try:
            with open(arq, "rb") as f:
                cab = f.read(4096)
                i = cab.find(b"fmt "); j = cab.find(b"data", i)
                if i < 0 or j < 0:
                    continue
                taxa, can = int.from_bytes(cab[i + 12:i + 16], "little"), int.from_bytes(cab[i + 10:i + 12], "little")
                ini_dados = j + 8; tam = os.path.getsize(arq)
                n = min(tam - ini_dados, int(falta * taxa) * can * 2)
                if n <= 0:
                    continue
                f.seek(tam - n); b = f.read(n)
        except (OSError, ValueError):
            continue
        a = array.array("h"); a.frombytes(b[: len(b) // 2 * 2])
        if a:
            picos.append(max(max(a), -min(a)))
        falta -= len(a) / float(taxa * can)
        if falta <= 0.05:
            break
    return max(picos) if picos else None


def extrair_fala_fim(segs, segundos, saida):
    """como o extrair_wav_fim, mas sabendo que o microfone pode ter sido REABERTO no meio (P20): os pedaços
    fala_<geração>_<n>.wav de cada abertura são juntados em sequência e cada abertura é posta na linha do tempo pela
    hora em que o último pedaço dela fechou (mtime). A abertura mais nova termina no fim do buffer (igual ao de antes);
    buraco entre aberturas = silêncio. Uma abertura só = exatamente o extrair_wav_fim."""
    geracoes = {}
    for s in segs:
        m = re.search(r"fala_(\d+)_\d+\.wav$", s)
        geracoes.setdefault(m.group(1) if m else "", []).append(s)
    if len(geracoes) <= 1:
        return extrair_wav_fim(segs, segundos, saida)
    ordem = sorted(geracoes)
    blocos, fmt = [], None
    for g in ordem:
        partes = []
        for s in sorted(geracoes[g]):
            try:
                d, taxa, can, larg = ler_wav(s)
            except Exception:
                continue
            if fmt is None:
                fmt = (taxa, can, larg)
            if (taxa, can, larg) == fmt:
                partes.append(d)
        if partes:
            try:
                fecha = os.path.getmtime(sorted(geracoes[g])[-1])
            except OSError:
                continue
            blocos.append((fecha, b"".join(partes)))
    if fmt is None or not blocos:
        return False
    taxa, can, larg = fmt
    bpf = can * larg
    n = int(round(segundos * taxa))
    buf = bytearray(n * bpf)
    ultimo = blocos[-1][0]
    for fecha, d in blocos:                       # a mais nova por último (por cima, se encostar)
        fim_q = n - int(round((ultimo - fecha) * taxa))
        ini_q = fim_q - len(d) // bpf
        a, b = max(0, ini_q), min(n, fim_q)
        if b > a:
            buf[a * bpf:b * bpf] = d[(a - ini_q) * bpf:(b - ini_q) * bpf]
    gravar_wav(saida, bytes(buf), taxa, can, larg)
    return True


def extrair_pc(pecas, ini, fim, saida):
    """som do PC no intervalo [ini, fim] (epoch), montado pelos manifestos do gravar_pc.py (t0 de cada segmento); buraco = silêncio.
    P20: segmento de outra saída com outro formato (fone 44,1 kHz mono x monitor 48 kHz estéreo) é convertido, não fica de fora."""
    segs = []
    for man in pecas:
        try:
            m = json.load(open(man, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for s in m.get("segmentos", []):
            arq = os.path.join(os.path.dirname(man), s["arquivo"])
            if os.path.isfile(arq):
                segs.append((s["t0"], arq))
    if not segs:
        return False
    segs.sort()
    fmt = None
    for t0, arq in reversed(segs):
        try:
            _, taxa, can, larg = ler_wav(arq); fmt = (taxa, can, larg); break
        except Exception:
            continue
    if not fmt:
        return False
    taxa, can, larg = fmt
    bpf = can * larg
    n = int(round((fim - ini) * taxa))
    buf = bytearray(n * bpf)
    for t0, arq in segs:
        try:
            d, tx, c, lg = ler_wav(arq)
            if (tx, c, lg) != fmt:
                tmp = arq + ".conv.wav"
                subprocess.run([FFMPEG, "-v", "error", "-y", "-ignore_length", "1", "-i", arq, "-ar", str(taxa), "-ac", str(can), "-c:a", "pcm_s16le", tmp],
                               capture_output=True, timeout=300, creationflags=SEM_JANELA)
                d, tx, c, lg = ler_wav(tmp)
                os.remove(tmp)
                if (tx, c, lg) != fmt:
                    continue
        except Exception:
            continue
        ini_q = int(round((t0 - ini) * taxa))
        a, b = max(0, ini_q), min(n, ini_q + len(d) // bpf)
        if b > a:
            buf[a * bpf:b * bpf] = d[(a - ini_q) * bpf:(b - ini_q) * bpf]
    gravar_wav(saida, bytes(buf), taxa, can, larg)
    return True


VIDEO_ENC = ["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-crf", "30", "-g", "10", "-pix_fmt", "yuv420p"]


def extrair_video_fim(segs, segundos, saida, log=None):
    """últimos 'segundos' dos pedaços .ts do buffer → mp4 com os MESMOS parâmetros da gravação (pra juntar sem reencodar)"""
    segs = [s for s in segs if os.path.getsize(s) > 0]
    if not segs:
        return False
    lista = saida + ".txt"
    with open(lista, "w", encoding="utf-8") as f:
        for s in segs:
            f.write("file '%s'\n" % s.replace("\\", "/").replace("'", "'\\''"))
    total = sum(duracao(s) for s in segs)
    ss = max(0.0, total - segundos)
    falta = max(0.0, segundos - total)
    vf = "fps=5,scale=1920:-2:flags=bilinear,format=yuv420p"
    if falta > 0.2:
        vf += ",tpad=start_duration=%.2f:color=black" % falta
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lista, "-ss", "%.3f" % ss,
           "-t", "%.3f" % segundos, "-vf", vf] + VIDEO_ENC + ["-threads", "2", "-an", "-y", saida]
    r = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=SEM_JANELA)
    try:
        os.remove(lista)
    except OSError:
        pass
    if r.returncode != 0 and log:
        log("replay vídeo: %s" % r.stderr.decode("utf-8", "replace")[-300:])
    return r.returncode == 0 and os.path.isfile(saida)


def juntar_video(partes, saida, log=None):
    lista = saida + ".txt"
    with open(lista, "w", encoding="utf-8") as f:
        for s in partes:
            f.write("file '%s'\n" % s.replace("\\", "/").replace("'", "'\\''"))
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy",
                        "-movflags", "+faststart", "-y", saida], capture_output=True, timeout=900, creationflags=SEM_JANELA)
    try:
        os.remove(lista)
    except OSError:
        pass
    if r.returncode != 0 and log:
        log("juntar vídeo: %s" % r.stderr.decode("utf-8", "replace")[-300:])
    return r.returncode == 0


def juntar_wav(partes, saida):
    """concatena wavs (o formato do ÚLTIMO manda; os outros são convertidos pelo ffmpeg se diferirem)"""
    _, taxa, can, larg = ler_wav(partes[-1])
    blocos = []
    for p in partes:
        d, tx, c, lg = ler_wav(p)
        if (tx, c, lg) != (taxa, can, larg):
            tmp = p + ".conv.wav"
            subprocess.run([FFMPEG, "-v", "error", "-y", "-i", p, "-ar", str(taxa), "-ac", str(can), "-c:a", "pcm_s16le", tmp],
                           creationflags=SEM_JANELA)
            d, _, _, _ = ler_wav(tmp)
            os.remove(tmp)
        blocos.append(d)
    gravar_wav(saida, b"".join(blocos), taxa, can, larg)
    return True


def nivel_voz(arq, segundos=0.4):
    """RMS do fim do wav que está sendo gravado (fala ~ > 400)"""
    try:
        tam = os.path.getsize(arq)
        with open(arq, "rb") as f:
            f.seek(max(44, tam - int(48000 * 2 * segundos))); b = f.read()
        a = array.array("h"); a.frombytes(b[: len(b) // 2 * 2])
        if not a:
            return 0
        a = a[::4]
        return (sum(x * x for x in a) / len(a)) ** 0.5
    except Exception:
        return 0
