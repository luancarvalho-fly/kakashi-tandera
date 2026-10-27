# -*- coding: utf-8 -*-
"""TANDERA V2 (20/10/2026) — as medidas que a RÉGUA ainda não juntava num comando. O que o regua.py já faz (calibrar, cortes
AutoShot, separação Roformer → BandIt, fala MMS + onda, entonação, batida Beat This + ataque, pacote por corte) é chamado de
lá, sem reescrever. Aqui entram, cada uma com o modelo escolhido por teste (RESULTADOS.md):
  - texto da fala pelo whisper-server do OpenWhispr (porta 8178) → alinhado no ms pelo MMS do regua.fala
  - 2ª opinião de corte: TransNetV2
  - câmera: CoTracker3 + geometria (a CURVA: deslocamento e escala quadro a quadro)
  - corpo / fase da rep: Sapiens2-1B (punhos = 62/41 no esqueleto de 308)
  - grade de batida FECHADA NA ONDA (grade reta ajustada nos ataques fortes)
  - texto na tela: PP-OCRv6 medium no RapidOCR (venv-ler, processador)
  - qual efeito: encaixe na onda contra a biblioteca (scripts\\sfx_video.py)
  - cor por take (medida simples, sem modelo)
Tudo aqui trabalha com o NÚMERO do quadro (−ss (F−0,5)/fps), nunca com o tempo cru."""
import json, os, re, subprocess, sys, time, types, urllib.request, uuid
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import regua as R  # noqa: E402

PY = os.path.join(AQUI, ".venv", "Scripts", "python.exe")
VENV_LER = os.environ.get("REGUA_PY_LER") or os.path.join(AQUI, "venv-ler", "Scripts", "python.exe")   # NOTEBOOK
OCR_DET = os.path.join(AQUI, "modelos", "ocr", "PP-OCRv6_medium_det.onnx")   # NOTEBOOK: o mesmo arquivo do PC
OCR_REC = os.path.join(AQUI, "modelos", "ocr", "PP-OCRv6_medium_rec.onnx")
OCR_DIC = os.path.join(AQUI, "modelos", "ocr", "dict_v6.txt")
WHISPER_8178 = os.environ.get("REGUA_WHISPER_URL") or "http://127.0.0.1:8178/inference"   # NOTEBOOK
log = R.log


# ---------------------------------------------------------------- quadros
def dimensoes(cal):
    """largura × altura como o ffmpeg entrega (já girado pelo metadado)"""
    w, h = cal["largura"], cal["altura"]
    return (h, w) if abs(int(cal.get("rotacao_metadado") or 0)) in (90, 270) else (w, h)


def ler_quadros(video, a, b, fps, larg, alt, w=512):
    """quadros a..b−1 pelo NÚMERO, RGB, largura w (altura na proporção, par)"""
    H = max(2, int(round(w * alt / larg / 2)) * 2)
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", "%.5f" % max(0.0, (a - 0.5) / fps), "-i", video, "-frames:v", str(max(1, b - a)),
                        "-map", "0:v:0", "-an", "-vf", f"scale={w}:{H}", "-fps_mode", "passthrough", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                       capture_output=True)
    n = len(r.stdout) // (w * H * 3)
    return np.frombuffer(r.stdout[: n * w * H * 3], np.uint8).reshape(n, H, w, 3)


def gravar_jpg(dst, im):
    """T5: grava ao lado e troca no fim — processo morto no meio (pausar e liberar a placa) não deixa jpg pela metade,
    e quem confere "o quadro já existe" nunca pega um quebrado"""
    import cv2
    tmp = dst[:-4] + f".parcial{os.getpid()}.jpg"
    cv2.imwrite(tmp, im, [cv2.IMWRITE_JPEG_QUALITY, 90])
    os.replace(tmp, dst)


def quadro_arq(video, f, fps, dst, w=None):
    """um quadro pelo número, gravado em jpg (fica guardado: não extrai de novo)"""
    if os.path.exists(dst):
        return dst
    im = R.quadro(video, f, fps, w)
    if im is None:
        return None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    gravar_jpg(dst, im)
    return dst


# ---------------------------------------------------------------- cortes: 2ª opinião
def _prob_para_cortes(prob, limiar):
    out, i, n = [], 0, len(prob)
    while i < n:
        if prob[i] > limiar:
            p = i
            while i < n and prob[i] > limiar:
                if prob[i] > prob[p]: p = i
                i += 1
            if p < n - 1: out.append(p + 1)
        else:
            i += 1
    return out


def cortes_transnet(video, placa=True):
    import torch
    from transnetv2_pytorch import TransNetV2
    W, H = 48, 27
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-map", "0:v:0", "-an", "-vf", f"scale={W}:{H}:flags=bilinear", "-fps_mode", "passthrough",
                        "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True)
    q = np.frombuffer(r.stdout[: len(r.stdout) // (W * H * 3) * W * H * 3], np.uint8).reshape(-1, H, W, 3)
    dev = "cuda" if placa else "cpu"
    m = TransNetV2(device=dev).eval()
    with torch.no_grad():
        sp, _ = m.predict_frames(torch.from_numpy(np.ascontiguousarray(q)).to(dev), quiet=True)
    del m
    if placa: torch.cuda.empty_cache()
    return {"quadros": int(len(q)), "cortes": _prob_para_cortes(sp.cpu().numpy().reshape(-1), 0.5)}


def cortes_pixel(video, ja, tol=1):
    """3ª opinião, barata: salto de diferença de pixel (cinza 96×54) bem acima dos vizinhos. Pega jump cut (mesmo ângulo, outro take)
    que AutoShot e TransNetV2 deixam passar (T3: dois jump cuts num vídeo de teste). NÃO vira corte sozinho: sai como 'possível corte, conferir no olho'."""
    W, H = 96, 54
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-map", "0:v:0", "-an", "-vf", f"scale={W}:{H}", "-fps_mode", "passthrough",
                        "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True)
    g = np.frombuffer(r.stdout[: len(r.stdout) // (W * H) * W * H], np.uint8).reshape(-1, H, W).astype(np.int16)
    dif = np.zeros(len(g)); dif[1:] = np.abs(g[1:] - g[:-1]).mean(axis=(1, 2))
    out = []
    for f in range(1, len(dif)):
        viz = np.concatenate([dif[max(1, f - 12):max(1, f - 1)], dif[f + 2:f + 13]])
        if len(viz) and dif[f] > max(6.0, 3 * float(np.median(viz))) and dif[f] >= dif[max(0, f - 1):f + 2].max() and not any(abs(f - c) <= tol for c in ja):
            out.append({"q": int(f), "dif": round(float(dif[f]), 1), "vizinhos": round(float(np.median(viz)), 1)})
    return out


def comparar_cortes(a, b, tol=1):
    """cortes que só um dos dois achou (a ±tol quadros) → conferir no olho"""
    so_a = [c for c in a if not any(abs(c - x) <= tol for x in b)]
    so_b = [c for c in b if not any(abs(c - x) <= tol for x in a)]
    return {"so_autoshot": so_a, "so_transnet": so_b}


# ---------------------------------------------------------------- fala: texto do whisper-server (8178)
def _multipart(campos, arq_campo, arq):
    fronteira = uuid.uuid4().hex
    corpo = b""
    for k, v in campos.items():
        corpo += f"--{fronteira}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    corpo += (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"{arq_campo}\"; filename=\"{os.path.basename(arq)}\"\r\n"
              "Content-Type: audio/wav\r\n\r\n").encode() + open(arq, "rb").read() + f"\r\n--{fronteira}--\r\n".encode()
    return corpo, f"multipart/form-data; boundary={fronteira}"


def segmentos_8178(wav, idioma="auto"):
    """texto do Whisper pelo whisper-server do OpenWhispr (não mexe nele: só manda o arquivo). Devolve os segmentos no formato que
    o regua.fala usa (.start .end .words[.word .start .end]); as palavras vêm em pedaços (" sav" + "ana") e são juntadas pelo espaço."""
    w16 = os.path.splitext(wav)[0] + "_16k.wav"
    if not os.path.exists(w16):     # T5: grava ao lado e troca (processo morto no meio não deixa wav pela metade)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", w16[:-4] + ".parcial.wav"], check=True)
        os.replace(w16[:-4] + ".parcial.wav", w16)
    corpo, tipo = _multipart({"response_format": "verbose_json", "language": idioma or "auto", "temperature": "0.0"}, "file", w16)
    req = urllib.request.Request(WHISPER_8178, data=corpo, headers={"Content-Type": tipo})
    j = json.load(urllib.request.urlopen(req, timeout=1800))
    NS = types.SimpleNamespace
    # T3: no EP01 o whisper-server escreveu "E aí?" 13 vezes onde não tem fala (o laço do Whisper em trecho de música).
    # Filtros: (1) o mesmo texto 3+ vezes seguidas = laço, sai tudo; (2) trecho sem energia no stem de voz (pico < −40 dB) sai.
    import soundfile as sf
    x16, _ = sf.read(w16, dtype="float32")
    def pico_db(a, b):
        y = x16[int(a * 16000):max(int(a * 16000) + 1, int(b * 16000))]
        if not len(y): return -99.0
        k = 160; n = len(y) // k
        return float(10 * np.log10(np.max(np.mean(y[: n * k].reshape(n, k) ** 2, axis=1)) + 1e-12)) if n else float(10 * np.log10(np.mean(y ** 2) + 1e-12))
    brutos = j.get("segments", [])
    chave = [re.sub(r"\W+", " ", s.get("text", "").lower()).strip() for s in brutos]
    laco = set()
    i = 0
    while i < len(brutos):
        k = i
        while k + 1 < len(brutos) and chave[k + 1] == chave[i]: k += 1
        if k - i + 1 >= 3: laco.update(range(i, k + 1))
        i = k + 1
    descartados = []
    segs = []
    for n_s, s in enumerate(brutos):
        if n_s in laco or pico_db(float(s["start"]), float(s["end"])) < -40:
            descartados.append(s.get("text", "").strip()); continue
        ws = []
        for t in s.get("words") or []:
            p = t.get("word", "")
            if not p.strip():
                continue
            if p.startswith(" ") or not ws:
                ws.append({"word": p.strip(), "start": float(t["start"]), "end": float(t["end"])})
            else:
                ws[-1]["word"] += p; ws[-1]["end"] = float(t["end"])
        ws = [x for x in ws if re.search(r"\w", x["word"])]
        if not ws:
            continue
        segs.append(NS(start=float(s["start"]), end=float(s["end"]), text=s.get("text", ""), words=[NS(**x) for x in ws]))
    if descartados:
        log(f"fala: {len(descartados)} trecho(s) do Whisper descartado(s) (laço repetido ou sem voz no stem)")
    return segs, j.get("language"), descartados


# ---------------------------------------------------------------- câmera: CoTracker3 + geometria (a CURVA)
def _classe_geo(dx, dy, ls, lim_t=0.06, lim_s=0.04):
    """mesmos limiares do teste do CameraBench (77%); não ajustados de propósito"""
    if max(abs(dx), abs(dy)) < lim_t and abs(ls) < lim_s: return "parada"
    if abs(ls) * 1.5 > max(abs(dx), abs(dy)): return "entrando (zoom/travelling pra frente)" if ls > 0 else "saindo (zoom/travelling pra trás)"
    if abs(dx) >= abs(dy): return "pan esquerda" if dx > 0 else "pan direita"     # a cena anda pra direita = a câmera vira pra esquerda
    return "tilt cima" if dy > 0 else "tilt baixo"


def torch_igual():
    """T5: o mesmo modo do torch em qualquer processo. A TransNetV2 liga, pro processo INTEIRO, o modo determinístico do torch e a
    semente 42 (transnetv2_pytorch._setup_deterministic_behavior). Numa rodada direta a câmera roda depois dela e herda isso; num
    processo retomado (2ª opinião já no cache) a TransNetV2 não roda e a curva da câmera saía diferente na 4ª casa (660 números no
    teste do T5; antes do T5 já acontecia ao rodar de novo com a 2ª opinião guardada). Ligado aqui, igual ao dela, o resultado não
    depende do que rodou antes no mesmo processo."""
    import random, torch
    torch.manual_seed(42); np.random.seed(42); random.seed(42)
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass
    if torch.backends.cudnn.is_available():
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def camera(video, shots, fps, larg, alt, placa=True, n_max=48, pedacos=None):
    """pedacos (T5): cada shot é guardado assim que fica pronto (o CoTracker olha um shot de cada vez, sozinho: guardar por shot
    não muda nada); rodar de novo pula os guardados. O modelo só carrega se faltar algum shot."""
    import torch, cv2
    dev = "cuda" if placa else "cpu"
    ct = None
    out = []
    for a, b in shots:
        if pedacos and pedacos.tem((a, b)):
            out.append(pedacos.ler((a, b))); continue
        if b - a < 4:
            out.append({"de_q": a, "ate_q": b, "classe": "curto demais (< 4 quadros)", "curva": []})
            if pedacos: pedacos.guardar((a, b), out[-1])
            continue
        Q = ler_quadros(video, a, b, fps, larg, alt, 512)
        if len(Q) < 4:
            out.append({"de_q": a, "ate_q": b, "classe": "?", "curva": []})
            if pedacos: pedacos.guardar((a, b), out[-1])
            continue
        if ct is None:
            torch_igual()
            ct = torch.hub.load(os.path.join(AQUI, "repos", "co-tracker"), "cotracker3_offline", source="local", pretrained=False)
            sd = torch.load(os.path.join(AQUI, "modelos", "cotracker3", "scaled_offline.pth"), map_location="cpu")
            (ct.model if hasattr(ct, "model") else ct).load_state_dict(sd)
            ct = ct.to(dev).eval()
        idx = np.unique(np.linspace(0, len(Q) - 1, min(n_max, len(Q))).round().astype(int))
        fs = Q[idx]; h, w = fs.shape[1:3]
        v = torch.from_numpy(np.ascontiguousarray(fs)).permute(0, 3, 1, 2)[None].float().to(dev)
        with torch.no_grad():
            tr, vis = ct(v, grid_size=24)
        tr, vis = tr[0].cpu().numpy(), vis[0].cpu().numpy()
        dx = dy = ls = 0.0
        curva = [{"q": int(a + idx[0]), "dx": 0.0, "dy": 0.0, "escala": 0.0}]; vel = []
        for i in range(1, len(fs)):
            m = (vis[i] > 0.5) & (vis[i - 1] > 0.5)
            M = None
            if m.sum() >= 8:
                M, _ = cv2.estimateAffinePartial2D(tr[i - 1][m], tr[i][m], method=cv2.RANSAC, ransacReprojThreshold=2.0)
            if M is not None:
                ddx, ddy = M[0, 2] / w, M[1, 2] / h; dls = float(np.log(np.sqrt(abs(np.linalg.det(M[:, :2])))))
                dx += ddx; dy += ddy; ls += dls
                passo = max(1, idx[i] - idx[i - 1])
                vel.append((int(a + idx[i]), float(np.hypot(ddx, ddy) + abs(dls)) / passo))
            curva.append({"q": int(a + idx[i]), "dx": round(dx, 4), "dy": round(dy, 4), "escala": round(ls, 4)})
        pico = max(vel, key=lambda x: x[1]) if vel else (None, 0)
        vis_pct = round(100 * float((vis > 0.5).mean()), 0)
        cl = _classe_geo(dx, dy, ls)
        if vis_pct < 60:   # T3, EP01 shot 48: explosão cobrindo a tela, os pontos somem no fogo e a curva saiu ao contrário
            cl += f" (pouca confiança: só {vis_pct:.0f}% dos pontos seguidos — conferir no olho)"
        out.append({"de_q": a, "ate_q": b, "classe": cl, "dx": round(dx, 3), "dy": round(dy, 3), "log_escala": round(ls, 3),
                    "pontos_seguidos_pct": vis_pct, "pico_de_velocidade_q": pico[0], "curva": curva})
        if pedacos: pedacos.guardar((a, b), out[-1])
    del ct
    if placa: torch.cuda.empty_cache()
    return out


# ---------------------------------------------------------------- corpo: Sapiens2-1B → fase da rep
SAP2COCO = [0, 1, 2, 3, 4, 5, 6, 7, 8, 62, 41, 9, 10, 11, 12, 13, 14]   # punhos = 62 (esq.) e 41 (dir.) no esqueleto de 308
ARTIC = {"cotovelo esq.": (5, 7, 9), "cotovelo dir.": (6, 8, 10), "joelho esq.": (11, 13, 15), "joelho dir.": (12, 14, 16),
         "quadril esq.": (5, 11, 13), "quadril dir.": (6, 12, 14)}


def _angulo(k, a, b, c):
    v1, v2 = k[:, a] - k[:, b], k[:, c] - k[:, b]
    return np.degrees(np.arccos(np.clip((v1 * v2).sum(1) / (np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1) + 1e-9), -1, 1)))


def corpo(video, shots, fps, larg, alt, placa=True, passo=2, pedacos=None):
    """pedacos (T5): cada take é guardado assim que fica pronto (o Sapiens olha quadro a quadro, um take de cada vez: guardar por
    take não muda nada); rodar de novo pula os guardados. Os modelos só carregam se faltar algum take."""
    import torch, cv2
    from PIL import Image
    from scipy.signal import find_peaks
    dev = "cuda" if placa else "cpu"
    W = min(720, larg)
    model = None
    out = []
    for a, b in shots:
        if pedacos and pedacos.tem((a, b)):
            out.append(pedacos.ler((a, b))); continue
        if model is None:
            sys.path.insert(0, os.path.join(AQUI, "repos", "sapiens2"))
            from sapiens.pose.models import init_model
            from sapiens.pose.datasets import UDPHeatmap
            from transformers import DetrForObjectDetection, DetrImageProcessor
            CK = os.path.join(AQUI, "modelos", "sapiens2")
            cfg = os.path.join(AQUI, "repos", "sapiens2", "sapiens", "pose", "configs", "keypoints308", "shutterstock_goliath_3po",
                               "sapiens2_1b_keypoints308_shutterstock_goliath_3po-1024x768.py")
            model = init_model(cfg, os.path.join(CK, "pose", "sapiens2_1b_pose.safetensors"), device=dev)
            _c = dict(model.cfg.codec); _c.pop("type"); model.codec = UDPHeatmap(**_c)
            dp = DetrImageProcessor.from_pretrained(os.path.join(CK, "detector", "detr-resnet-101-dc5"))
            dm = DetrForObjectDetection.from_pretrained(os.path.join(CK, "detector", "detr-resnet-101-dc5")).eval().to(dev)
        Q = ler_quadros(video, a, b, fps, larg, alt, W)
        qs = list(range(0, len(Q), passo))
        if len(Q) and qs[-1] != len(Q) - 1: qs.append(len(Q) - 1)   # o último quadro do take sempre entra (é onde o corte cai)
        k = np.zeros((len(qs), 17, 2)); s = np.zeros((len(qs), 17))
        for j, i in enumerate(qs):
            f = cv2.cvtColor(Q[i], cv2.COLOR_RGB2BGR)
            with torch.no_grad():
                o = dm(**dp(images=Image.fromarray(Q[i]), return_tensors="pt").to(dev))
            res = dp.post_process_object_detection(o, target_sizes=torch.tensor([Q[i].shape[:2]], device=dev), threshold=0.5)[0]
            bx = res["boxes"][res["labels"] == 1].cpu().numpy()
            if not len(bx): continue
            bb = bx[int(np.argmax((bx[:, 2] - bx[:, 0]) * (bx[:, 3] - bx[:, 1])))]
            d = model.data_preprocessor(model.pipeline(dict(img=f, bbox=bb[None], bbox_score=np.ones(1, np.float32))))
            with torch.no_grad():
                pr = model(d["inputs"].unsqueeze(0) if d["inputs"].dim() == 3 else d["inputs"])
            kp, sc = model.codec.decode(pr[0].cpu().numpy())
            meta = d["data_samples"]["meta"]
            kp = kp / meta["input_size"] * meta["bbox_scale"] + meta["bbox_center"] - 0.5 * meta["bbox_scale"]
            k[j], s[j] = kp[0][SAP2COCO], sc[0][SAP2COCO]
        com = s.sum(1) > 0
        r = {"de_q": a, "ate_q": b, "quadros_medidos": len(qs), "com_pessoa": int(com.sum())}
        if com.sum() >= 3:
            ang = {n: _angulo(k, *ix) for n, ix in ARTIC.items()}
            conf = {n: float(s[com][:, list(ix)].mean()) for n, ix in ARTIC.items()}
            boas = [n for n in ang if conf[n] > 0.3] or list(ang)
            n = max(boas, key=lambda n: float(np.ptp(ang[n][com])))      # a articulação que mais mexe = o sinal da rep
            g = ang[n].copy(); g[~com] = np.interp(np.where(~com)[0], np.where(com)[0], g[com]) if (~com).any() else g[~com]
            tq = np.array([a + i for i in qs]); vel = np.gradient(g, tq / fps) if len(g) > 1 else np.zeros_like(g)
            def fase(i):
                v = vel[i]; x = g[i]
                dirc = "dobrando" if v < -25 else ("esticando" if v > 25 else "parado")
                ponto = "dobrado ao máximo" if x < 70 else ("esticado" if x > 150 else "no meio")
                return {"angulo": round(float(x), 1), "vel_graus_s": round(float(v), 1), "movimento": dirc, "ponto": ponto}
            pk, _ = find_peaks(-g, prominence=35, distance=max(1, int(fps * 0.8 / passo)))
            lo, hi = float(g.min()), float(g.max())
            fim_no_extremo = bool(hi - lo > 30 and min(abs(g[-1] - lo), abs(g[-1] - hi)) < 0.15 * (hi - lo))
            r.update({"articulacao": n, "faixa_graus": [round(lo, 1), round(hi, 1)], "reps_contadas": int(len(pk)), "entrada": fase(0), "saida": fase(len(g) - 1),
                      "termina_num_extremo": fim_no_extremo, "curva": [[int(t), round(float(x), 1)] for t, x in zip(tq, g)]})
        out.append(r)
        if pedacos: pedacos.guardar((a, b), r)
    if model is not None:
        del model, dm
        if placa: torch.cuda.empty_cache()
    return out


# ---------------------------------------------------------------- batida: grade FECHADA NA ONDA
def grade_na_onda(wav, batidas, T=None):
    """Música de tempo fixo (loop de DAW) = grade reta t_k = t0 + k·P. Como no teste de 21/10: ajusta a grade na lista do
    Beat This, testa se o Beat This marcou em meio tempo (golpes fortes no meio da grade também), e fecha a grade nos ataques
    medidos (agudo = palma/caixa; grave = bumbo/808). Se o resíduo for grande, a música não é de tempo fixo: fica a lista crua."""
    import soundfile as sf
    from scipy.signal import butter, sosfiltfilt
    bt = np.asarray(batidas, float)
    if len(bt) < 8:
        return {"fechada": False, "motivo": "poucas batidas"}
    x, sr = sf.read(wav, dtype="float64", always_2d=True); x = x.mean(1); T = T or len(x) / sr
    def env(lo, hi):
        sos = butter(4, [lo, hi], "bandpass", fs=sr, output="sos") if lo and hi else (butter(4, lo, "highpass", fs=sr, output="sos") if lo else butter(4, hi, "lowpass", fs=sr, output="sos"))
        y = np.abs(sosfiltfilt(sos, x)); kk = max(1, int(sr * 0.002)); return np.convolve(y, np.ones(kk) / kk, "same")
    E = {"agudo": env(2000, None), "grave": env(None, 150)}
    def ataque(e, t, jan=0.05):
        a, b = max(0, int((t - jan) * sr)), min(len(e), int((t + jan) * sr))
        if b - a < 10: return t, 0.0
        seg = e[a:b]; ip = int(np.argmax(seg)); pico = seg[ip]
        base = np.percentile(e[max(0, a - int(0.1 * sr)):a + 1], 20) if a > 0 else 0
        lim = base + 0.5 * (pico - base); j = ip
        while j > 0 and seg[j] > lim: j -= 1
        return (a + j) / sr, float(20 * np.log10(pico + 1e-12) - 20 * np.log10(base + 1e-12))
    def golpe(t):
        ta, sa = ataque(E["agudo"], t); tg, sg = ataque(E["grave"], t)
        return (ta, sa, "agudo") if sa >= sg else (tg, sg, "grave")
    # 1) andamento e fase por PENTE nos ataques da onda (T3: a lista do Beat This no stem é irregular e o ajuste reto nela errou o
    #    passo: 116,7 × 126 BPM num vídeo de teste). Candidatos perto do andamento do Beat This, do dobro e da metade.
    from scipy.ndimage import maximum_filter1d
    cheio = np.convolve(np.abs(x), np.ones(max(1, int(sr * 0.002))) / max(1, int(sr * 0.002)), "same")[:: int(sr / 1000)]   # 1 ms
    o = np.maximum(0, np.diff(np.log(cheio + 1e-6), prepend=np.log(cheio[0] + 1e-6)))
    o = maximum_filter1d(o, 9)                                   # ±4 ms
    bpm_bt = 60 / float(np.median(np.diff(bt)))
    melhor = {}
    for mult in (0.5, 1.0, 2.0):
        b0 = bpm_bt * mult
        if not 50 <= b0 <= 220: continue
        res_m = (0, None, None)
        for bpm in np.arange(b0 * 0.92, b0 * 1.08, 0.02):
            Pm = 60 / bpm * 1000; n = int((len(o) - 1) / Pm)
            if n < 6: continue
            fases = np.arange(0, Pm, 2.0)
            idx = (fases[:, None] + np.arange(n)[None] * Pm).astype(int)
            sc = o[idx].mean(1); j = int(np.argmax(sc))
            if sc[j] > res_m[0]: res_m = (float(sc[j]), 60 / bpm, fases[j] / 1000)
        melhor[mult] = res_m
    cand = sorted([v for v in melhor.values() if v[1]], key=lambda v: v[1])   # do mais rápido (P menor) pro mais lento
    topo = max(v[0] for v in cand)
    P, t0 = next(v[1:] for v in cand if v[0] >= 0.6 * topo)        # o mais rápido que ainda cai nos ataques (o Beat This às vezes marca meio tempo)
    meio_tempo = bool(abs(60 / P - 2 * bpm_bt) < 0.1 * bpm_bt)
    # a fase: o pente acha os ataques, mas palma/chimbal no contratempo batem tão forte quanto a batida (T3: 234 ms fora num vídeo de teste).
    # Quem diz onde é a BATIDA é o Beat This: fica a fase (na batida ou meia batida depois) mais perto das batidas dele.
    dist = lambda f: float(np.median(np.abs(((bt - f) / P + 0.5) % 1 - 0.5)))
    t0 = min((t0, t0 + P / 2), key=dist)
    pts = []
    for i in range(int(np.ceil(-t0 / P)) - 1, int((T - t0) / P) + 2):
        t = t0 + i * P
        if 0.05 < t < T - 0.05:
            ta, salto, faixa = golpe(t)
            if salto > 12 and abs(ta - t) < 0.05: pts.append((i, ta))
    if len(pts) < 6:
        return {"fechada": False, "motivo": f"só {len(pts)} golpes fortes perto da grade", "bpm_cru": round(60 / P, 2), "meio_tempo": meio_tempo}
    ki, ti = np.array(pts).T
    P2, t02 = np.polyfit(ki, ti, 1); res = ti - (t02 + ki * P2)
    fechada = bool(np.median(np.abs(res)) < 0.012)
    grade = [round(float(t02 + i * P2), 4) for i in range(int(np.ceil(-t02 / P2)), int((T - t02) / P2) + 1) if 0 <= t02 + i * P2 <= T]
    return {"fechada": fechada, "bpm": round(float(60 / P2), 3), "P_s": round(float(P2), 5), "t0_s": round(float(t02), 4), "meio_tempo_corrigido": meio_tempo,
            "golpes_usados": int(len(pts)), "residuo_mediano_ms": round(float(np.median(np.abs(res))) * 1000, 1), "residuo_max_ms": round(float(np.max(np.abs(res))) * 1000, 1),
            "grade": grade if fechada else [], "motivo": "" if fechada else "resíduo grande: a música não é de tempo fixo (fica a lista crua do Beat This)"}


def corte_x_batida(cortes_q, fps, batidas_s, folga=0.0, meias=False):
    """pra cada corte: a batida mais perto, o quadro que contém a batida, a distância em quadros e em ms (+ = corte depois).
    meias=True (grade fechada): a meia batida (contratempo) também vale, marcada — um vídeo de teste tem corte no 38,5."""
    bt = np.asarray(batidas_s, float) - folga
    if not len(bt):
        return {"lista": [], "resumo": {}}
    alvos = [(t, "batida") for t in bt]
    if meias and len(bt) > 1:
        alvos += [((a + b) / 2, "meia batida") for a, b in zip(bt[:-1], bt[1:])]
    out = []
    for c in cortes_q:
        t = c / fps; tb, tipo = min(alvos, key=lambda x: abs(x[0] - t)); qb = int(np.floor(tb * fps + 1e-6))
        out.append({"corte_q": int(c), "batida_s": round(float(tb), 4), "tipo": tipo, "batida_q": qb, "desvio_q": int(c - qb), "desvio_ms": round((t - tb) * 1000, 1)})
    P = float(np.median(np.diff(bt))) / (2 if meias else 1) if len(bt) > 1 else 0
    d = np.array([o["desvio_q"] for o in out])
    resumo = {"cortes": len(out), "no_quadro_da_batida": int((d == 0).sum()), "a_1_quadro": int((np.abs(d) <= 1).sum()),
              "mediana_ms": round(float(np.median([o["desvio_ms"] for o in out])), 1),
              "acaso_a_1_quadro_pct": round(min(100.0, 300.0 / (P * fps)) if P else 0, 1)}
    return {"lista": out, "resumo": resumo}


# ---------------------------------------------------------------- texto na tela (PP-OCRv6, processador, venv-ler)
def texto_na_tela(imagens, pasta):
    """pacote da Fly (27/10, defeito (b) do teste do notebook): entrada e saída com nome ÚNICO por chamada (duas rodadas no mesmo vídeo
    usavam o mesmo ocr_entrada.json / ocr_saida.json, e uma podia ler a saída da outra), arquivos fechados antes de chamar o OCR, e TODA
    imagem pedida tem que voltar: a que não voltou PARA com erro, em vez de virar "linhas: []" guardado no cache pra sempre."""
    os.makedirs(pasta, exist_ok=True)
    marca = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    ent, sai = os.path.join(pasta, f"ocr_entrada_{marca}.json"), os.path.join(pasta, f"ocr_saida_{marca}.json")
    with open(ent, "w", encoding="utf-8") as f:
        json.dump({"imagens": imagens, "det": OCR_DET, "rec": OCR_REC, "dic": OCR_DIC}, f, ensure_ascii=False)
    subprocess.run([VENV_LER, os.path.join(AQUI, "scripts", "tandera_ocr.py"), ent, sai], check=True)
    with open(sai, encoding="utf-8") as f:
        res = json.load(f)
    faltou = [i for i in imagens if i not in res]
    if faltou:
        raise RuntimeError(f"o OCR não devolveu {len(faltou)} de {len(imagens)} quadro(s) (ex.: {faltou[0]}): nada foi guardado")
    for p in (ent, sai):
        try:
            os.remove(p)
        except OSError:
            pass
    return res


# ---------------------------------------------------------------- qual efeito (encaixe na onda; scripts\sfx_video.py)
def efeitos(wav_efeitos, pasta, folga=0.0, placa=True):
    sai = os.path.join(pasta, "efeitos_sfx_video.json")
    env = dict(os.environ); env["PYTHONIOENCODING"] = "utf-8"
    if not placa: env["REGUA_DISP"] = "cpu"
    subprocess.run([PY, os.path.join(AQUI, "scripts", "sfx_video.py"), wav_efeitos, sai, str(folga)], check=True, env=env)
    ach = json.load(open(sai, encoding="utf-8"))["achados"]
    for a in ach:   # onde fica o PICO do arquivo (o quadro da imagem casa com o pico; o clipe entra antes por esse tanto)
        try:
            y = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", a["arquivo"], "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True).stdout, np.float32)
            e = np.convolve(np.abs(y), np.ones(80) / 80, "same")
            a["ate_o_pico_ms"] = round(float(np.argmax(e)) / 8.0, 1)
            a["pico_no_video_s"] = round(a["inicio_do_arquivo_s"] + a["ate_o_pico_ms"] / 1000, 4)
        except Exception as ex:
            a["ate_o_pico_ms"] = None; a["erro_pico"] = str(ex)[:200]
    return ach


# ---------------------------------------------------------------- rosto: OpenFace 3.0 no WSL → boca × fala
def _wsl(p):
    p = os.path.abspath(p).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


LOTE_ROSTO = 150      # T5: quadros por chamada ao WSL (cada chamada carrega o OpenFace de novo: lote pequeno demais = tempo jogado fora)


def rosto(video, shots, fps, larg, alt, palavras, folga, pasta, passo=2, pedacos=None):
    """boca (98 pontos do OpenFace 3.0) a cada 2 quadros; por shot: quanto tempo tem rosto e se a boca mexe JUNTO com a fala medida
    (movimento da boca em janelas de 0,25 s, como no teste de 17/10). Boca mexendo sem fala, ou fala sem boca = conferir no olho.
    pedacos (T5): os quadros vão pro WSL em lotes de 150, cada lote guardado assim que volta (o OpenFace olha cada quadro sozinho:
    o lote não muda a medida); rodar de novo pula os lotes guardados."""
    import cv2
    os.makedirs(pasta, exist_ok=True)
    quadros = []
    for a, b in shots:
        Q = ler_quadros(video, a, b, fps, larg, alt, min(640, larg))
        for i in range(0, len(Q), passo):
            dst = os.path.join(pasta, f"r{a + i}.jpg")
            if not os.path.exists(dst): gravar_jpg(dst, cv2.cvtColor(Q[i], cv2.COLOR_RGB2BGR))
            quadros.append((a + i, dst))
    lotes = [quadros[i:i + LOTE_ROSTO] for i in range(0, len(quadros), LOTE_ROSTO)] if pedacos else [quadros]
    sh = _wsl(os.path.join(AQUI, "scripts", "tandera_rosto.sh"))
    medida = {}
    for k, lote in enumerate(lotes):
        if pedacos and pedacos.tem(lote):
            res = pedacos.ler(lote)
        else:
            sufixo = f"_{k + 1:03d}" if pedacos else ""
            lista, sai = os.path.join(pasta, f"rosto_lista{sufixo}.json"), os.path.join(pasta, f"rosto_saida{sufixo}.json")
            json.dump([_wsl(d) for _, d in lote], open(lista, "w"))
            subprocess.run(["wsl", "-d", "Ubuntu-24.04", "-u", "root", "--", "bash", "-c", f"tr -d '\\r' < {sh} > /tmp/tandera_rosto.sh && bash /tmp/tandera_rosto.sh {_wsl(lista)} {_wsl(sai)}"], check=True)
            res = json.load(open(sai))
            if pedacos: pedacos.guardar(lote, res)
        medida.update({q: res.get(_wsl(d), {}) for q, d in lote})
    fala_t = [(w["ini"] - folga, w["fim"] - folga) for w in palavras or []]
    falando = lambda t: any(a <= t <= b for a, b in fala_t)
    out = []
    for a, b in shots:
        qs = [q for q in range(a, b, passo)]
        boca = np.array([medida.get(q, {}).get("boca", np.nan) for q in qs])
        tem = ~np.isnan(boca)
        r = {"de_q": a, "ate_q": b, "rosto_pct": round(100 * float(tem.mean()), 0) if len(qs) else 0}
        if tem.sum() >= 4:
            mov = np.abs(np.diff(np.where(tem, boca, np.nanmedian(boca)), prepend=np.nanmedian(boca)))
            k = max(1, int(round(0.25 * fps / passo))); mov = np.convolve(mov, np.ones(k) / k, "same")
            fl = np.array([falando(q / fps) for q in qs])
            r["fala_pct"] = round(100 * float(fl.mean()), 0)
            r["boca_aberta_media"] = round(float(np.nanmean(boca)), 3)
            if fl.any() and (~fl).any():
                r["boca_mexe_na_fala_x_fora"] = round(float(mov[fl & tem].mean() / (mov[~fl & tem].mean() + 1e-6)), 2) if (fl & tem).any() and (~fl & tem).any() else None
            alto = float(np.nanpercentile(mov, 75))
            r["boca_mexe_sem_fala"] = bool(((mov > alto) & ~fl & tem).mean() > 0.25)
            r["fala_sem_boca"] = bool(fl.mean() > 0.3 and float(mov[fl & tem].mean() if (fl & tem).any() else 0) < float(np.nanmedian(mov)))
        out.append(r)
    return out


# ---------------------------------------------------------------- cor por take (medida simples)
def cor(imagens):
    import cv2
    ims = [cv2.imread(p) for p in imagens if p and os.path.exists(p)]
    ims = [i for i in ims if i is not None]
    if not ims:
        return None
    hsv = np.concatenate([cv2.cvtColor(i, cv2.COLOR_BGR2HSV).reshape(-1, 3) for i in ims]).astype(float)
    bgr = np.concatenate([i.reshape(-1, 3) for i in ims]).astype(float)
    return {"brilho": round(float(hsv[:, 2].mean() / 2.55), 1), "saturacao": round(float(hsv[:, 1].mean() / 2.55), 1),
            "quente_menos_frio": round(float(bgr[:, 2].mean() - bgr[:, 0].mean()), 1)}
