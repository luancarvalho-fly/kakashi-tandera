"""CORRETOR - grava o SOM DO PC (o que sai na saida de som do Windows) por WASAPI loopback, numa PARTE da sessao.

Pedido do Luan (14/10): separar a trilha do microfone (a voz dele) da trilha do PC (o que ele esta ouvindo/editando).
O PC dele nao tem "Mixagem estereo", entao o dshow do ffmpeg nao pega o som do PC: o loopback vem do PyAudioWPatch.

O servidor.py chama um processo deste por parte (cada Iniciar/Retomar), igual ao ffmpeg do microfone:
  python gravar_pc.py --pasta <sessao> --parte N --inicio <epoch do inicio da parte> [--dispositivo "<nome>"] [--falso]
Para limpo com 'q' (ou fim) no stdin, como o ffmpeg. Nao toca som nenhum: so escuta a saida.

Saidas na pasta da sessao:
  pcNN.wav, pcNN_2.wav ...  um SEGMENTO por abertura da saida (trocou a saida = segmento novo), no formato nativo
                            dela (taxa e canais da saida, 16 bits). O servidor junta tudo em pc.wav no Concluir.
  pcNN.json                 manifesto: em que instante do relogio cada segmento comeca (t0, epoch), trocas, erros,
                            pico e segundos com som. Regravado a cada 5 s (sobrevive a queda do servidor).
  stdout                    uma linha JSON por acontecimento (o servidor le pra mostrar no /status)
  stderr                    log legivel (o servidor manda pro som_pc.log da sessao)

RELOGIO: o loopback do WASAPI NAO entrega pacote quando nada toca (depende de algum app estar com o som aberto).
Entao o arquivo e preenchido com silencio PELO RELOGIO: cada pacote cai no segundo em que chegou; buraco maior
que 0,08 s vira silencio; se o escrito passar 0,2 s a frente do relogio (relogio da placa x do PC, rajada depois
de um engasgo) o pacote perde a sobra. Erro de alinhamento: no maximo ~0,1-0,2 s (a tela e de 0,2 s por quadro).
Sem pacote ha 0,5 s, o silencio e escrito ate 0,35 s atras: o arquivo cresce em tempo real, entao se o servidor
cair a duracao do arquivo ainda diz ate quando gravou.

TROCA DE SAIDA (fone Bluetooth conectou etc.): a cada 2 s confere a saida padrao do Windows (Core Audio, so leitura).
Mudou -> log + fecha o segmento + reabre na nova (segmento novo; o buraco vira silencio na juncao). A saida sumiu
-> tenta reabrir a cada 3 s. Com --dispositivo fixo (config "dispositivo_saida") segue aquele aparelho.
Stream que PAROU sozinho com a mesma saida padrao (PortAudio pode desistir depois de muito tempo sem pacote) ->
reabre no mesmo aparelho e anota "reabriu" (conta no resumo, sem linha de troca). Revisao 14/10.

--falso (SO TESTE, nada toca nas caixas): no lugar do loopback, gera pacotes de tom com buracos SEM pacote (como o
loopback com nada tocando) e uma troca de "saida" aos 3 s (48 kHz estereo -> 44,1 kHz mono). Cada rajada de tom
vai pro manifesto ("tom"), pro teste conferir que ela caiu no segundo certo do pc.wav.
"""
import argparse
import array
import json
import math
import os
import queue
import struct
import sys
import threading
import time
import unicodedata
from pathlib import Path

TOL_BURACO = 0.08       # pacote que chega mais que isto (s) DEPOIS do fim do que foi escrito: o buraco vira silencio
TOL_ADIANTADO = 0.20    # escrito mais que isto (s) A FRENTE do relogio (placa x PC, rajada depois de engasgo): corta a sobra
SEM_PACOTE = 0.5        # sem pacote ha este tempo -> escreve silencio...
ATRAS = 0.35            # ...ate este tanto atras do agora
CHECAR_SAIDA = 2.0      # confere a saida padrao a cada
RETENTAR = 3.0          # saida que nao abriu/sumiu: tenta de novo a cada
MANIFESTO_A_CADA = 5.0
LIMIAR_SOM = 100        # pico de 16 bits acima disto (~ -50 dBFS) = "tinha som" naquele pacote


def agora():
    return time.time()


def log(msg):
    try:
        sys.stderr.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
        sys.stderr.flush()
    except Exception:
        pass


def avisar(**kw):
    try:
        sys.stdout.write(json.dumps(kw, ensure_ascii=True) + "\n")     # ASCII puro: o pipe nao estraga acento
        sys.stdout.flush()
    except Exception:
        pass


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).lower().strip()


def versao_lib():
    try:
        from importlib.metadata import version
        return "PyAudioWPatch " + version("PyAudioWPatch")
    except Exception:
        return "PyAudioWPatch ?"


# ------------------------------------------------------------------ saida padrao do Windows (Core Audio, so leitura)
class SaidaPadrao:
    """Le o ID do aparelho de saida padrao (IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia), o
    mesmo que o PortAudio usa). So ctypes, sem biblioteca. Nao muda nada no Windows."""
    CLSID = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"   # MMDeviceEnumerator
    IID = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"     # IMMDeviceEnumerator

    def __init__(self):
        import ctypes
        self.ct = ctypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

        def guid(s):
            g = GUID()
            ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
            return g

        self.ole = ctypes.windll.ole32
        self.ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        self.ole.CoInitialize(None)        # STA, como o PortAudio (que aceita COM ja iniciado)
        self.enum = ctypes.c_void_p()
        hr = self.ole.CoCreateInstance(ctypes.byref(guid(self.CLSID)), None, 0x17, ctypes.byref(guid(self.IID)),
                                       ctypes.byref(self.enum))
        if hr != 0 or not self.enum:
            raise OSError("CoCreateInstance(MMDeviceEnumerator) = 0x%08X" % (hr & 0xFFFFFFFF))

    def _metodo(self, ptr, idx, *argtypes):
        ct = self.ct
        vt = ct.cast(ptr, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        return ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, *argtypes)(vt[idx])

    def id(self):
        ct = self.ct
        dev = ct.c_void_p()
        hr = self._metodo(self.enum, 4, ct.c_int, ct.c_int, ct.POINTER(ct.c_void_p))(self.enum, 0, 1, ct.byref(dev))
        if hr != 0 or not dev:
            return None                     # nenhuma saida (E_NOTFOUND)
        try:
            pid = ct.c_void_p()
            if self._metodo(dev, 5, ct.POINTER(ct.c_void_p))(dev, ct.byref(pid)) != 0 or not pid.value:
                return None
            s = ct.wstring_at(pid.value)
            self.ole.CoTaskMemFree(pid)
            return s
        finally:
            self._metodo(dev, 2)(dev)       # Release


# ------------------------------------------------------------------ arquivo
class Segmento:
    """Um wav PCM 16 bits escrito aos poucos. O cabecalho sai com tamanho 'desconhecido' e e corrigido no fechar
    (wav de processo morto continua legivel com -ignore_length 1, como as partes do microfone)."""

    def __init__(self, caminho, taxa, canais, t0, dispositivo):
        self.caminho, self.taxa, self.canais, self.t0, self.dispositivo = Path(caminho), int(taxa), int(canais), t0, dispositivo
        self.bpf = 2 * self.canais
        self.frames = 0
        self.fim = None
        self.f = open(self.caminho, "wb")
        self.f.write(self._cabecalho(0xFFFFFFFF))
        self._zeros = b"\0" * (self.bpf * 4800)

    def _cabecalho(self, n_dados):
        riff = 0xFFFFFFFF if n_dados == 0xFFFFFFFF else min(0xFFFFFFFF, 36 + n_dados)
        return (b"RIFF" + struct.pack("<I", riff) + b"WAVE" + b"fmt " +
                struct.pack("<IHHIIHH", 16, 1, self.canais, self.taxa, self.taxa * self.bpf, self.bpf, 16) +
                b"data" + struct.pack("<I", min(0xFFFFFFFF, n_dados)))

    def silencio(self, n):
        while n > 0:
            k = min(n, 4800)
            self.f.write(self._zeros[:k * self.bpf])
            self.frames += k
            n -= k

    def ate(self, t):
        """silencio do fim do que foi escrito ate o instante t do relogio"""
        alvo = int(round((t - self.t0) * self.taxa))
        if alvo > self.frames:
            self.silencio(alvo - self.frames)

    def pacote(self, dados, n, chegada):
        """o pacote de n quadros que chegou no instante 'chegada' cobre ~[chegada - n/taxa, chegada]"""
        pos = int(round((chegada - n / self.taxa - self.t0) * self.taxa))
        dif = pos - self.frames
        if dif > TOL_BURACO * self.taxa:
            self.silencio(dif)                          # nada tocou (loopback sem pacote): silencio pelo relogio
        elif dif < -TOL_ADIANTADO * self.taxa:
            corta = min(n, -dif)                        # relogio da placa adiantou: perde a sobra pra realinhar
            dados = dados[corta * self.bpf:]
        if dados:
            self.f.write(dados)
            self.frames += len(dados) // self.bpf

    def fechar(self, t_fim):
        self.fim = t_fim
        try:
            self.f.flush()
            n = self.frames * self.bpf
            self.f.seek(0)
            self.f.write(self._cabecalho(n))
            self.f.close()
        except Exception:
            pass

    def info(self):
        return {"arquivo": self.caminho.name, "t0": round(self.t0, 4), "taxa": self.taxa, "canais": self.canais,
                "dispositivo": self.dispositivo, "frames": self.frames, "dur": round(self.frames / float(self.taxa), 3),
                "fim": round(self.fim, 4) if self.fim else None}


# ------------------------------------------------------------------ fontes
class FonteLoopback:
    def __init__(self, fila, gen, pedido, saida_padrao):
        import pyaudiowpatch as pa
        self.pa = pa
        self.fila, self.gen = fila, gen
        self.saida_padrao = saida_padrao
        self.aviso = ""
        self.p = pa.PyAudio()          # inicia o PortAudio de novo: so assim ele ve a saida padrao NOVA
        try:
            dev = None
            if pedido:
                alvo = sem_acento(pedido).replace("[loopback]", "").strip()
                for lb in self.p.get_loopback_device_info_generator():
                    if alvo and alvo in sem_acento(lb["name"]):
                        dev = lb
                        break
                if dev is None:
                    self.aviso = "a saida pedida no config ('%s') nao existe agora: gravando a saida PADRAO" % pedido
            self.segue_padrao = dev is None
            if dev is None:
                dev = self.p.get_default_wasapi_loopback()
            self.id_padrao = saida_padrao.id() if (saida_padrao and self.segue_padrao) else None
            self.nome = str(dev["name"]).replace(" [Loopback]", "")
            self.taxa = int(dev["defaultSampleRate"])
            self.canais = max(1, int(dev["maxInputChannels"]))
            self.t0 = agora()
            self.stream = self.p.open(format=pa.paInt16, channels=self.canais, rate=self.taxa, input=True,
                                      input_device_index=dev["index"], stream_callback=self._cb)
        except Exception:
            try:
                self.p.terminate()
            except Exception:
                pass
            raise

    def _cb(self, dados, n, info, flags):
        self.fila.put((self.gen, agora(), n, dados))
        return (None, self.pa.paContinue)

    def problema(self):
        """None, ("mudou", msg) = a saida padrao do Windows trocou, ou ("parou", msg) = o stream parou sozinho.
        Revisao 14/10: a troca da padrao e conferida ANTES do is_active (fone que desliga = padrao muda E stream
        para: e troca). 'parou' com a padrao igual pode ser so o PortAudio desistindo depois de muito tempo sem
        pacote (nada tocando): o main reabre e, se for o mesmo aparelho, anota 'reabriu' (nao vira troca)."""
        if self.segue_padrao and self.saida_padrao is not None and self.id_padrao:
            try:
                atual = self.saida_padrao.id()
            except Exception:
                atual = self.id_padrao
            if atual != self.id_padrao:
                return ("mudou", "a saida padrao do Windows mudou (era '%s')" % self.nome)
        try:
            if not self.stream.is_active():
                return ("parou", "a saida '%s' parou de responder (sumiu, foi desligada ou ficou muito tempo sem som)" % self.nome)
        except Exception as e:
            return ("parou", "a saida '%s' deu erro (%s)" % (self.nome, e))
        return None

    def fechar(self):
        for f in (self.stream.stop_stream, self.stream.close, self.p.terminate):
            try:
                f()
            except Exception:
                pass


class FonteFalsa:
    """SO TESTE (nada toca): pacotes de 10 ms gerados pelo relogio. Saida 1 = 48 kHz estereo, tom de 0,5-1,0 s e de
    2,0-2,3 s, SEM pacote no resto (como o loopback com nada tocando); aos 3,0 s "troca de saida". Saida 2 = 44,1 kHz
    mono, pacotes de SILENCIO o tempo todo (como quando algum app deixa o som aberto) e tom de 0,4-0,9 s e 2,0-2,5 s."""
    ROTEIRO = {1: (48000, 2, [(0.5, 1.0), (2.0, 2.3)], False, 3.0), 2: (44100, 1, [(0.4, 0.9), (2.0, 2.5)], True, None)}

    def __init__(self, fila, gen, pedido, saida_padrao, estado, parar_em=None):
        self.fila, self.gen, self.estado = fila, gen, estado
        self.aviso = ""
        self.segue_padrao = True
        self.id_padrao = "falso-%d" % gen
        self.versao = 1 if gen == 1 else 2
        # --falso-parou (so teste da revisao): a saida 2 "para de responder" 1 s depois de abrir, UMA vez
        self.parar_em = parar_em if gen == 2 else None
        self.taxa, self.canais, self.rajadas, self.silencio_continuo, self.troca = self.ROTEIRO[self.versao]
        self.nome = "saida falsa %d (%d Hz, %d canal(is))" % (self.versao, self.taxa, self.canais)
        self.t0 = agora()
        self.vivo = True
        threading.Thread(target=self._gerar, daemon=True).start()

    def _gerar(self):
        n = self.taxa // 100
        k = 0
        dentro = None
        while self.vivo:
            alvo = self.t0 + (k + 1) * 0.01
            espera = alvo - agora()
            if espera > 0:
                time.sleep(espera)
            t_ini = k * 0.01
            tom = any(a <= t_ini < b for a, b in self.rajadas)
            if tom and dentro is None:
                dentro = self.t0 + t_ini
            if not tom and dentro is not None:
                self.estado["eventos"].append({"o_que": "tom", "inicio": round(dentro, 4), "fim": round(self.t0 + t_ini, 4)})
                dentro = None
            if tom:
                a = array.array("h", (int(8000 * math.sin(2 * math.pi * 1000 * (k * n + i) / self.taxa))
                                      for i in range(n) for _ in range(self.canais)))
                self.fila.put((self.gen, agora(), n, a.tobytes()))
            elif self.silencio_continuo:
                self.fila.put((self.gen, agora(), n, b"\0" * (2 * self.canais * n)))
            k += 1

    def problema(self):
        if self.troca is not None and agora() - self.t0 >= self.troca:
            return ("mudou", "a saida padrao do Windows mudou (era '%s') [teste]" % self.nome)
        if self.parar_em is not None and agora() - self.t0 >= self.parar_em:
            self.parar_em = None
            return ("parou", "a saida '%s' parou de responder [teste]" % self.nome)
        return None

    def fechar(self):
        self.vivo = False


# ------------------------------------------------------------------ principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta")
    ap.add_argument("--parte", type=int)
    ap.add_argument("--inicio", type=float)
    ap.add_argument("--dispositivo", default="")
    ap.add_argument("--falso", action="store_true")
    ap.add_argument("--falso-parou", action="store_true", help="so teste: a saida falsa 2 para sozinha 1 s depois de abrir")
    ap.add_argument("--listar", action="store_true", help="so lista as saidas de som (JSON no stdout) e sai")
    a = ap.parse_args()
    if a.listar:
        try:
            import pyaudiowpatch as pa
            p = pa.PyAudio()
            try:
                saidas = [str(d["name"]).replace(" [Loopback]", "") for d in p.get_loopback_device_info_generator()]
                try:
                    padrao = str(p.get_default_wasapi_loopback()["name"]).replace(" [Loopback]", "")
                except Exception:
                    padrao = None
            finally:
                p.terminate()
            avisar(saidas=saidas, padrao=padrao, lib=versao_lib())
        except Exception as e:
            avisar(saidas=[], padrao=None, erro=str(e))
        return
    if not a.pasta or a.parte is None or a.inicio is None:
        ap.error("--pasta, --parte e --inicio sao obrigatorios pra gravar")
    pasta = Path(a.pasta)
    manif = pasta / ("pc%02d.json" % a.parte)
    estado = {"parte": a.parte, "inicio": a.inicio, "pedido": a.dispositivo, "lib": versao_lib(), "falso": a.falso,
              "pid": os.getpid(), "segmentos": [], "eventos": [], "erro": "", "pico": 0, "seg_com_som": 0.0,
              "atraso": None, "fim": None, "terminou": False}

    def salvar():
        tmp = manif.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
            for _ in range(40):
                try:
                    os.replace(tmp, manif)
                    return
                except PermissionError:
                    time.sleep(0.05)
        except Exception as e:
            log("nao salvou o manifesto: %s" % e)

    def evento(o_que, msg, **kw):
        e = dict({"o_que": o_que, "quando": round(agora(), 4), "msg": msg}, **kw)
        estado["eventos"].append(e)
        log(msg)
        avisar(evento=o_que, msg=msg, **kw)

    if not a.falso:
        try:
            import pyaudiowpatch  # noqa: F401
        except Exception as e:
            estado["erro"] = "biblioteca PyAudioWPatch nao instalada (pip install PyAudioWPatch): %s" % e
            estado["terminou"], estado["fim"] = True, agora()
            log(estado["erro"])
            avisar(evento="erro", msg=estado["erro"])
            salvar()
            sys.exit(3)

    parar = threading.Event()
    t_parar = [None]

    def ler_stdin():
        try:
            entrada = sys.stdin.buffer if sys.stdin is not None else None
            while entrada is not None:
                b = entrada.read(1)
                if not b or b in (b"q", b"Q"):
                    break
            if entrada is None:
                return                     # sem stdin (rodado a mao): para so com Ctrl+C
        except Exception:
            pass
        t_parar[0] = agora()
        parar.set()
    threading.Thread(target=ler_stdin, daemon=True).start()

    saida_padrao = None
    if not a.falso:
        try:
            saida_padrao = SaidaPadrao()
            saida_padrao.id()
        except Exception as e:
            saida_padrao = None
            evento("aviso", "nao deu pra ler a saida padrao do Windows (troca de saida nao sera percebida): %s" % e)

    fila = queue.Queue()
    st = {"fonte": None, "seg": None, "gen": 0, "ultimo": agora(), "falhou": ""}

    def abrir():
        st["gen"] += 1
        try:
            if a.falso:
                fonte = FonteFalsa(fila, st["gen"], a.dispositivo, None, estado, 1.0 if a.falso_parou else None)
            else:
                fonte = FonteLoopback(fila, st["gen"], a.dispositivo, saida_padrao)
        except Exception as e:
            msg = "nao abriu o loopback da saida de som: %s" % (str(e) or type(e).__name__)
            if msg != st["falhou"]:
                evento("erro", msg)
            st["falhou"] = msg
            if not estado["segmentos"]:
                estado["erro"] = msg
            return False
        st["falhou"] = ""
        k = len(estado["segmentos"]) + 1
        nome = ("pc%02d.wav" % a.parte) if k == 1 else ("pc%02d_%d.wav" % (a.parte, k))
        seg = Segmento(pasta / nome, fonte.taxa, fonte.canais, fonte.t0, fonte.nome)
        st["fonte"], st["seg"], st["ultimo"] = fonte, seg, agora()
        estado["segmentos"].append(seg.info())
        estado["erro"] = ""
        if k == 1:
            estado["atraso"] = round(fonte.t0 - a.inicio, 3)
        if fonte.aviso:
            evento("aviso", fonte.aviso)
        evento("abriu", "gravando o som do PC de '%s' (%d Hz, %d canal(is))%s" % (
            fonte.nome, fonte.taxa, fonte.canais,
            (", %.2f s depois do inicio da parte (vira silencio no comeco)" % (fonte.t0 - a.inicio)) if k == 1 else ""),
            dispositivo=fonte.nome, taxa=fonte.taxa, canais=fonte.canais, segmento=nome)
        salvar()
        return True

    def fechar_fonte(t_fim):
        fonte, seg = st["fonte"], st["seg"]
        if fonte is not None:
            fonte.fechar()
        # pacotes que ja estavam na fila (ate t_fim) entram; o resto e de depois do fim
        while True:
            try:
                g, chegada, n, dados = fila.get_nowait()
            except queue.Empty:
                break
            if seg is not None and g == st["gen"] and chegada <= t_fim + 0.05:
                processar(seg, chegada, n, dados)
        if seg is not None:
            seg.ate(t_fim)
            seg.fechar(t_fim)
            estado["segmentos"][-1] = seg.info()
        st["fonte"] = st["seg"] = None

    def processar(seg, chegada, n, dados):
        seg.pacote(dados, n, chegada)
        try:
            amostras = array.array("h", dados)
            if amostras:
                pico = max(max(amostras), -min(amostras))
                if pico > estado["pico"]:
                    estado["pico"] = pico
                if pico > LIMIAR_SOM:
                    estado["seg_com_som"] += n / float(seg.taxa)
        except Exception:
            pass

    abrir()
    proxima_checagem = agora() + CHECAR_SAIDA
    proxima_tentativa = agora() + RETENTAR
    proximo_manifesto = agora() + MANIFESTO_A_CADA
    proximo_flush = agora() + 1.0
    try:
        while not parar.is_set():
            try:
                itens = [fila.get(timeout=0.1)]
            except queue.Empty:
                itens = []
            # revisao 14/10: esvazia a fila TODA a cada volta. Antes era 1 pacote por volta: depois de um engasgo
            # (> 0,5 s) o 'ultimo' ficava velho com pacotes ainda na fila, o silencio pelo relogio era escrito por
            # cima do lugar deles e o som do PC ficava ate 0,2 s atrasado dali pra frente
            while itens and len(itens) < 2000:
                try:
                    itens.append(fila.get_nowait())
                except queue.Empty:
                    break
            seg = st["seg"]
            for item in itens:
                if seg is not None and item[0] == st["gen"]:
                    processar(seg, item[1], item[2], item[3])
                    st["ultimo"] = item[1]
            t = agora()
            if seg is not None and fila.empty() and t - st["ultimo"] > SEM_PACOTE:
                seg.ate(t - ATRAS)
            if t >= proxima_checagem:
                proxima_checagem = t + CHECAR_SAIDA
                fonte = st["fonte"]
                if fonte is not None:
                    prob = fonte.problema()
                    if prob and prob[0] == "mudou":
                        fechar_fonte(t)
                        evento("trocou", prob[1] + ": reabrindo na saida atual (o buraco vira silencio)")
                        if not abrir():
                            proxima_tentativa = t + RETENTAR
                    elif prob:
                        # parou sozinho: reabre; mesmo aparelho = 'reabriu' (so no som_pc.log e na contagem, sem
                        # linha no resumo); outro aparelho (o pedido sumiu e foi pra padrao) = 'trocou'
                        nome_antes = fonte.nome
                        fechar_fonte(t)
                        log(prob[1] + ": reabrindo")
                        avisar(evento="reabrindo", msg=prob[1])
                        if not abrir():
                            proxima_tentativa = t + RETENTAR
                        elif st["fonte"].nome == nome_antes:
                            evento("reabriu", prob[1] + ": reabriu no mesmo aparelho (o buraco vira silencio)")
                        else:
                            evento("trocou", prob[1] + ": agora gravando '%s' (o buraco vira silencio)" % st["fonte"].nome,
                                   reaberto=True)
                elif t >= proxima_tentativa:
                    if not abrir():
                        proxima_tentativa = t + RETENTAR
            if t >= proximo_flush and st["seg"] is not None:
                proximo_flush = t + 1.0
                try:
                    st["seg"].f.flush()
                except Exception:
                    pass
            if t >= proximo_manifesto:
                proximo_manifesto = t + MANIFESTO_A_CADA
                if st["seg"] is not None:
                    estado["segmentos"][-1] = st["seg"].info()
                salvar()
    except KeyboardInterrupt:
        t_parar[0] = agora()
    fim = t_parar[0] or agora()
    fechar_fonte(fim)
    estado["fim"], estado["terminou"] = round(fim, 4), True
    estado["seg_com_som"] = round(estado["seg_com_som"], 2)
    salvar()
    avisar(evento="fim", segmentos=len(estado["segmentos"]), pico=estado["pico"])
    log("parou: %d segmento(s), pico %d, %.1f s com som" % (len(estado["segmentos"]), estado["pico"], estado["seg_com_som"]))


if __name__ == "__main__":
    main()
