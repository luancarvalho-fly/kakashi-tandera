# -*- coding: utf-8 -*-
"""RÉGUA — um comando só pra analisar um vídeo (V1, 17/10/2026). Ferramentas = as escolhidas por teste (RESULTADOS.md);
uso e regras = skill /analise-de-video, references\\regua.md.

  python regua.py <video> [--estilo camera-parada|cinematico|vlog] [--sem-placa] [--saida PASTA]

O que faz, em ordem:
 0. CALIBRA o arquivo: fps, quadros, folga do AAC (áudio atrasado), orientação (take deitado), se tem fala.
 1. ESTILO: se não for dito, reconhece pelo que é barato medir (rosto grande e parado, câmera mexendo, cortes por minuto,
    quanto tempo tem fala) — regra 389: câmera parada = áudio; cinemático = imagem; vlog = tudo + piada/contexto.
 2. MEDE só o que o estilo pede:
      corte (AutoShot)                         → todos
      separação (Roformer → BandIt Plus)       → todos que têm som que importa
      fala palavra a palavra (MMS + onda)      → câmera parada, vlog
      entonação (Praat: altura, final, ritmo)  → câmera parada, vlog
      batida + música (Beat This! + medidor)   → cinemático, vlog
      corpo (Sapiens2) e câmera                → cinemático (e vlog quando pedir)
 3. MONTA o pacote de cada corte (regra 382): quadro, ms, o que acabou de acontecer (falas e sons dos 4 s antes),
    distância até a palavra / batida (ataque) / pico de efeito, entonação do fim da fala antes e do começo depois.
 4. ESCREVE <saida>\\relatorio.md (legível) + momentos.json (tudo) + as folhas de quadros dos cortes (pro meu olho).
O que NÃO faz: interpretar emoção/intenção (isso é meu, depois, com o pacote na mão — e ele confirma no teste cego)."""
import argparse, json, os, re, subprocess, sys, tempfile, time, unicodedata
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
M = os.path.join(AQUI, "modelos")
AUTOSHOT = os.path.join(M, "autoshot.onnx")   # NOTEBOOK: no PC fica em apps\CUTX\modelos
ROFO = os.path.join(AQUI, ".venv-sep", "Scripts", "audio-separator.exe")   # NOTEBOOK: relativo à pasta   # 18/10: venv próprio com torch na PLACA (o do DUBX roda no processador, ~6x mais lento)
CINE = os.path.join(AQUI, "separador-cinema")   # NOTEBOOK: só o msst + o BandIt Plus, dentro da REGUA
PY_CINE = os.environ.get("REGUA_PY_CINE") or os.path.join(AQUI, ".venv", "Scripts", "python.exe")   # NOTEBOOK: o BandIt roda no .venv principal
RECEITA = {
    "camera-parada": ["corte", "separacao", "fala", "entonacao"],
    "cinematico": ["corte", "separacao", "batida", "musica"],
    "vlog": ["corte", "separacao", "fala", "entonacao", "batida", "musica"],
}

def log(*a): print(time.strftime("[%H:%M:%S]"), *a, flush=True)
def ffprobe(v, *args):
    return subprocess.run(["ffprobe", "-v", "error", *args, v], capture_output=True, text=True).stdout.strip()

# ---------------------------------------------------------------- 0. calibração
def calibrar(video):
    fr = ffprobe(video, "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,width,height,nb_frames:stream_side_data=rotation", "-of", "json")
    j = json.loads(fr)["streams"][0]
    num, den = j["r_frame_rate"].split("/"); fps = float(num) / float(den)
    rot = 0
    for sd in j.get("side_data_list", []) or []:
        if "rotation" in sd: rot = int(sd["rotation"])
    a = ffprobe(video, "-select_streams", "a:0", "-show_entries", "stream=codec_name,initial_padding,sample_rate", "-of", "json")
    aj = (json.loads(a).get("streams") or [{}])[0]
    aac = aj.get("codec_name") == "aac"
    folga = 1024 / float(aj.get("sample_rate") or 48000) if aac and not int(aj.get("initial_padding") or 0) else 0.0
    return {"fps": fps, "largura": j.get("width"), "altura": j.get("height"), "rotacao_metadado": rot, "audio": aj.get("codec_name"),
            "folga_aac_s": round(folga, 6), "deitado_suspeito": (j.get("width") or 0) > (j.get("height") or 0) and rot == 0}

def quadro(video, f, fps, w=None):
    vf = ["-vf", f"scale={w}:-2"] if w else []
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.5f" % max(0.0, (f - 0.5) / fps), "-i", video, "-frames:v", "1", *vf, "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    import cv2
    return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR) if r.stdout else None

# ---------------------------------------------------------------- medidas
def cortes(video):
    import onnxruntime as ort
    W, H = 48, 27
    r = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-map", "0:v:0", "-an", "-vf", f"scale={W}:{H}:flags=bilinear", "-fps_mode", "passthrough", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True)
    q = np.frombuffer(r.stdout[: len(r.stdout) // (W * H * 3) * W * H * 3], np.uint8).reshape(-1, H, W, 3)
    s = ort.InferenceSession(AUTOSHOT, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    n = len(q); resto = (50 - n % 50) if n % 50 else 0
    fila = np.concatenate([np.repeat(q[:1], 25, 0), q, np.repeat(q[-1:], 25 + resto, 0)]); prob = np.zeros(n, np.float32)
    for i in range(0, len(fila) - 99, 50):
        lg = s.run(None, {"frames": fila[i:i + 100].astype(np.float32)[None]})[0].reshape(-1)
        for k in range(25, 75):
            if i + k - 25 < n: prob[i + k - 25] = 1 / (1 + np.exp(-lg[k]))
    out, i = [], 0
    while i < n:
        if prob[i] > 0.296:
            p = i
            while i < n and prob[i] > 0.296:
                if prob[i] > prob[p]: p = i
                i += 1
            if p < n - 1: out.append(p + 1)
        else: i += 1
    return {"quadros": int(n), "cortes": out}

def separar(video, pasta, placa=True, andou=None):
    """21/10 (T5, pausar e liberar a placa): cada parte é gravada ao lado (.parcial.wav) e trocada no fim, e o arquivo que diz
    "esta parte terminou" é trocado por ÚLTIMO (voz na 1ª parte, efeitos na 2ª). Assim, processo morto no meio não deixa wav pela
    metade, e rodar de novo pula a parte que já terminou (Roformer) e refaz só a que estava no meio. O som que sai é o mesmo."""
    import soundfile as sf, shutil
    p = lambda n: os.path.join(pasta, n); os.makedirs(pasta, exist_ok=True)
    parcial = lambda n: p(n[:-4] + ".parcial.wav")
    if not os.path.exists(p("mix_48k.wav")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-map", "0:a:0", "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", parcial("mix_48k.wav")], check=True)
        os.replace(parcial("mix_48k.wav"), p("mix_48k.wav"))
    if not os.path.exists(p("voz_48k.wav")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", p("mix_48k.wav"), "-ar", "44100", "-c:a", "pcm_f32le", p("mix_44k.wav")], check=True)
        d = p("rofo"); shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
        # NOTEBOOK (26/10): o audio-separator acha a placa sozinho; com --sem-placa ela fica escondida dele (no PC também: ver o recado)
        env_rofo = dict(os.environ, CUDA_VISIBLE_DEVICES="-1") if not placa else None   # "-1", nao "": com "" o torch diz que TEM placa (0 placas) e o audio-separator quebra (Invalid device id; rodada 3)
        subprocess.run([ROFO, p("mix_44k.wav"), "--output_dir", d, "--output_format", "WAV", "--model_filename", "model_bs_roformer_ep_317_sdr_12.9755.ckpt"], check=True, env=env_rofo)
        v = [f for f in os.listdir(d) if "vocal" in f.lower()][0]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(d, v), "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", parcial("voz_48k.wav")], check=True)
        x, _ = sf.read(p("mix_48k.wav"), dtype="float32", always_2d=True); v_, _ = sf.read(parcial("voz_48k.wav"), dtype="float32", always_2d=True); n = min(len(x), len(v_))
        sf.write(parcial("resto_48k.wav"), x[:n] - v_[:n], 48000, subtype="FLOAT")
        os.replace(parcial("resto_48k.wav"), p("resto_48k.wav")); os.replace(parcial("voz_48k.wav"), p("voz_48k.wav"))
    if andou: andou(1)      # T5: a 1ª parte (Roformer) está guardada; a tela mostra "1 de 2 partes"
    if not os.path.exists(p("efeitos_48k.wav")):
        ent = p("bandit_in"); os.makedirs(ent, exist_ok=True); shutil.copy2(p("resto_48k.wav"), os.path.join(ent, "resto.wav"))
        cmd = [PY_CINE, os.path.join(CINE, "modelos-teste", "bancada", "rodar_msst_stub.py"), "--model_type", "bandit",
               "--config_path", os.path.join(CINE, "msst", "configs", "config_dnr_bandit_bsrnn_multi_mus64.yaml"),
               "--start_check_point", os.path.join(CINE, "modelos-teste", "bandit_plus", "model_bandit_plus_dnr_sdr_11.47.chpt"), "--input_folder", ent, "--store_dir", p("bandit")]
        if not placa: cmd.append("--force_cpu")
        subprocess.run(cmd, check=True)
        pa = os.path.join(p("bandit"), "resto"); mf = [f for f in os.listdir(pa) if "music" in f.lower() and f.endswith(".wav")][0]
        import librosa
        mus, sr = sf.read(os.path.join(pa, mf), dtype="float32", always_2d=True)
        if sr != 48000: mus = librosa.resample(mus.T, orig_sr=sr, target_sr=48000).T
        r, _ = sf.read(p("resto_48k.wav"), dtype="float32", always_2d=True); n = min(len(r), len(mus))
        sf.write(parcial("musica_48k.wav"), mus[:n], 48000, subtype="FLOAT"); sf.write(parcial("efeitos_48k.wav"), r[:n] - mus[:n], 48000, subtype="FLOAT")
        os.replace(parcial("musica_48k.wav"), p("musica_48k.wav")); os.replace(parcial("efeitos_48k.wav"), p("efeitos_48k.wav"))
    return {k: p(k + "_48k.wav") for k in ("mix", "voz", "musica", "efeitos")}

def fala(wav_voz, placa=True, segs=None):
    """segs = texto já transcrito por fora (20/10, Tandera V2: o whisper-server do OpenWhispr, porta 8178), com .start/.end/.words;
    sem segs, transcreve aqui com o faster-whisper large-v3 (como antes)."""
    import librosa, torch
    x16 = librosa.load(wav_voz, sr=16000, mono=True)[0]
    dev = "cuda" if placa else "cpu"
    if segs is None:
        from faster_whisper import WhisperModel
        # NOTEBOOK: REGUA_WHISPER = pasta ou nome do modelo (ex.: large-v3, medium); REGUA_WHISPER_TIPO = int8, int8_float16...
        # sem a pasta do PC, o padrão é o NOME "large-v3" (o faster-whisper baixa do Hugging Face) — 26/10: a pasta inexistente quebrava
        _w = os.environ.get("REGUA_WHISPER") or (os.path.join(M, "faster-whisper-large-v3") if os.path.isdir(os.path.join(M, "faster-whisper-large-v3")) else "large-v3")
        fw = WhisperModel(_w, device=dev, compute_type=os.environ.get("REGUA_WHISPER_TIPO") or ("float16" if placa else "int8"))
        segs = list(fw.transcribe(x16, language=os.environ.get("REGUA_IDIOMA") or None, word_timestamps=True, vad_filter=False, beam_size=5)[0]); del fw   # 18/10: idioma automático (vídeo em inglês); REGUA_IDIOMA=pt força
    from torchaudio.pipelines import MMS_FA as b
    mdl = b.get_model().to(dev); tok = b.get_tokenizer(); aln = b.get_aligner()
    limpa = lambda t: [w for w in re.sub(r"[^a-z' ]", " ", "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")).split() if w]
    HOP = 16; n = len(x16) // HOP; env = 10 * np.log10(np.mean(x16[:n * HOP].reshape(n, HOP) ** 2, axis=1) + 1e-12)
    ws = []
    for s in segs:
        a, bb = max(0, s.start - 0.3), s.end + 0.3; orig = [w.word.strip() for w in s.words]; lw = limpa(" ".join(orig))
        if not lw: continue
        wav = torch.from_numpy(x16[int(a * 16000):int(bb * 16000)])[None].to(dev)
        try:
            with torch.inference_mode():
                em, _ = mdl(wav); sp = aln(em[0], tok(lw))
        except RuntimeError:          # 18/10: fala rápida demais pro alinhador (CTC) → fica o tempo do próprio Whisper nesse trecho
            ws += [{"p": w.word.strip(), "ini": w.start, "fim": w.end} for w in s.words]; continue
        r = wav.shape[1] / em.shape[1] / 16000
        for w, o, x in zip(lw, orig if len(orig) == len(lw) else lw, sp):
            ws.append({"p": o, "ini": a + x[0].start * r, "fim": a + x[-1].end * r})
    for i, w in enumerate(ws):   # conferência na onda (regra 384)
        pk = float(env[int(w["ini"] * 1000):max(int(w["ini"] * 1000) + 1, int(w["fim"] * 1000))].max()) if n else -60
        if i == 0 or w["ini"] - ws[i - 1]["fim"] > 0.12:
            k = int(w["ini"] * 1000); j = env[max(0, k - 150):k + 150]; ix = np.where(j > pk - 40)[0]
            if len(ix): w["ini"] = (max(0, k - 150) + ix[0]) / 1000
        if i == len(ws) - 1 or ws[i + 1]["ini"] - w["fim"] > 0.12:
            k = int(w["fim"] * 1000); j = env[max(0, k - 150):k + 150]; ix = np.where(j > pk - 40)[0]
            if len(ix): w["fim"] = (max(0, k - 150) + ix[-1] + 1) / 1000
    return [{"p": w["p"], "ini": round(w["ini"], 3), "fim": round(w["fim"], 3)} for w in ws]

def entonacao(wav_voz, palavras):
    """trechos contínuos de fala (pausa > 0,25 s quebra) com altura no começo/fim (semitons rel. 110 Hz), final (st/s) e ritmo"""
    import parselmouth
    snd = parselmouth.Sound(wav_voz); tr = []; cur = []
    for w in palavras:
        if cur and w["ini"] - cur[-1]["fim"] > 0.25: tr.append(cur); cur = []
        cur.append(w)
    if cur: tr.append(cur)
    out = []
    for t in tr:
        a, b = t[0]["ini"], t[-1]["fim"]
        p = snd.extract_part(from_time=max(0, a - 0.05), to_time=b + 0.05, preserve_times=True).to_pitch(time_step=0.01, pitch_floor=70, pitch_ceiling=350)
        f = p.selected_array["frequency"]; xs = p.xs(); v = f > 0
        st = 12 * np.log2(f[v] / 110.0); vt = xs[v]
        def med(x0, x1):
            m = (vt >= x0) & (vt <= x1); return round(float(st[m].mean()), 2) if m.any() else None
        incl = float(np.polyfit(vt[vt >= vt[-1] - 0.35], st[vt >= vt[-1] - 0.35], 1)[0]) if len(vt) > 5 and (vt >= vt[-1] - 0.35).sum() > 3 else None
        sil = sum(max(1, len(re.findall(r"[aeiouáéíóúâêôãõ]+", w["p"].lower()))) for w in t)
        out.append({"ini": round(a, 3), "fim": round(b, 3), "texto": " ".join(w["p"] for w in t), "altura_ini_st": med(a, a + 0.25) if len(vt) else None,
                    "altura_fim_st": med(b - 0.25, b) if len(vt) else None, "final_st_por_s": round(incl, 1) if incl is not None else None,
                    "final": None if incl is None else ("sobe (pergunta?)" if incl > 6 else ("desce" if incl < -6 else "plano")), "silabas_por_s": round(sil / max(0.2, b - a), 2)})
    return out

def batida(wav, placa=True):
    from beat_this.inference import File2Beats
    import soundfile as sf, librosa
    b, db = File2Beats(checkpoint_path="final0", device="cuda" if placa else "cpu", dbn=False)(wav)
    x, sr = sf.read(wav, dtype="float32", always_2d=True); x = x.mean(1)
    def ataque(t, jan=0.035):
        a, bb = max(0, int((t - jan) * sr)), min(len(x), int((t + jan) * sr))
        e = np.convolve(np.abs(x[a:bb]), np.ones(int(sr / 1000)) / int(sr / 1000), "same"); return (a + int(np.argmax(np.diff(e, prepend=e[0])))) / sr
    return {"batidas": [round(ataque(float(t)), 4) for t in b], "tempos_fortes": [round(ataque(float(t)), 4) for t in db]}

# ---------------------------------------------------------------- 1. estilo
def reconhecer_estilo(video, cal, cortes_q, palavras, dur):
    """barato: rosto grande e parado (MediaPipe, 1 quadro/s), cortes por minuto, fração do tempo com fala"""
    import cv2, mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    det = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(base_options=BaseOptions(model_asset_path=os.path.join(M, "face_detector.tflite")))) if os.path.exists(os.path.join(M, "face_detector.tflite")) else None
    grande = 0; amostras = 0
    for t in np.arange(0.5, dur, max(1.0, dur / 60)):
        q = quadro(video, int(t * cal["fps"]), cal["fps"], 640)
        if q is None: continue
        amostras += 1
        if det:
            r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(q, cv2.COLOR_BGR2RGB)))
            if r.detections and max(d.bounding_box.width for d in r.detections) / q.shape[1] > 0.12: grande += 1
    fala_frac = sum(w["fim"] - w["ini"] for w in palavras) / max(1.0, dur) if palavras else 0.0
    cpm = len(cortes_q) / max(1.0, dur / 60)
    rosto = grande / max(1, amostras)
    if fala_frac < 0.15: est = "cinematico"
    elif rosto > 0.6 and cpm < 8: est = "camera-parada"
    else: est = "vlog"
    return est, {"rosto_grande_frac": round(rosto, 2), "cortes_por_min": round(cpm, 1), "fala_frac": round(fala_frac, 2)}

# ---------------------------------------------------------------- 3. pacote por corte
def pacotes(cortes_q, fps, palavras, ent, bat, folga):
    out = []
    pal_t = [((w["ini"] - folga), (w["fim"] - folga), w["p"]) for w in palavras or []]
    bats = np.array([b - folga for b in (bat or {}).get("batidas", [])])
    for f in cortes_q:
        t = f / fps; p = {"quadro": int(f), "s": round(t, 3)}
        antes = [w for w in pal_t if t - 4 <= w[1] <= t]
        p["falas_antes_4s"] = " ".join(w[2] for w in antes)
        if pal_t:
            fim_ant = max((w for w in pal_t if w[1] <= t + 0.05), key=lambda w: w[1], default=None)
            ini_dep = min((w for w in pal_t if w[0] >= t - 0.05), key=lambda w: w[0], default=None)
            if fim_ant: p["fim_da_palavra_antes_ms"] = round((t - fim_ant[1]) * 1000); p["palavra_antes"] = fim_ant[2]
            if ini_dep: p["inicio_da_palavra_depois_ms"] = round((ini_dep[0] - t) * 1000); p["palavra_depois"] = ini_dep[2]
        if len(bats):
            k = int(np.argmin(np.abs(bats - t))); p["batida_ms"] = round((t - bats[k]) * 1000)   # + = corte depois do ataque
        if ent:
            ta = max((e for e in ent if e["fim"] - folga <= t + 0.05), key=lambda e: e["fim"], default=None)
            td = min((e for e in ent if e["ini"] - folga >= t - 0.05), key=lambda e: e["ini"], default=None)
            if ta and td and ta["altura_fim_st"] is not None and td["altura_ini_st"] is not None:
                p["salto_de_altura_st"] = round(td["altura_ini_st"] - ta["altura_fim_st"], 1); p["final_antes"] = ta["final"]
        out.append(p)
    return out

# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("--estilo"); ap.add_argument("--sem-placa", action="store_true"); ap.add_argument("--saida")
    a = ap.parse_args(); placa = not a.sem_placa
    nome = os.path.splitext(os.path.basename(a.video))[0]
    out = a.saida or os.path.join(AQUI, "analises", nome); os.makedirs(out, exist_ok=True)
    R = {"video": a.video, "quando": time.strftime("%Y-%m-%d %H:%M")}
    log("calibrando"); R["calibracao"] = cal = calibrar(a.video)
    dur = float(ffprobe(a.video, "-show_entries", "format=duration", "-of", "csv=p=0") or 0)
    log("cortes"); C = cortes(a.video); R["cortes"] = C
    sep = None; pal = []
    if cal["audio"]:
        log("separando o som"); sep = separar(a.video, os.path.join(out, "stems"), placa)
        log("fala"); pal = fala(sep["voz"], placa); R["palavras"] = pal
    est = a.estilo
    if not est:
        log("reconhecendo o estilo"); est, ind = reconhecer_estilo(a.video, cal, C["cortes"], pal, dur); R["estilo_indicios"] = ind
    R["estilo"] = est; rec = RECEITA[est]; R["receita"] = rec
    ent = entonacao(sep["voz"], pal) if sep and "entonacao" in rec and pal else None; R["entonacao"] = ent
    bat = batida(sep["musica"], placa) if sep and "batida" in rec else None; R["batida"] = bat
    if sep and "musica" in rec:
        sys.path.insert(0, os.path.join(AQUI, "scripts")); from musica import medir
        R["musica"] = {k: v for k, v in medir(sep["musica"], dispositivo="cuda" if placa else "cpu").items() if k != "curvas_0_1s"}
    R["pacotes"] = pacotes(C["cortes"], cal["fps"], pal, ent, bat, cal["folga_aac_s"])
    json.dump(R, open(os.path.join(out, "momentos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    L = [f"# Régua — {nome}", "", f"- estilo: **{est}** {R.get('estilo_indicios', '(dito por ele)')} · receita: {', '.join(rec)}",
         f"- calibração: {cal['fps']:.3f} q/s · folga AAC {cal['folga_aac_s'] * 1000:.2f} ms · {'TAKE POSSIVELMENTE DEITADO' if cal['deitado_suspeito'] and est == 'cinematico' else 'orientação ok'}",
         f"- {C['quadros']} quadros · {len(C['cortes'])} cortes · {len(pal)} palavras", "", "## Cortes (quadro · s · palavra antes/depois · batida · salto de altura)"]
    for p in R["pacotes"]:
        L.append(f"- q{p['quadro']} · {p['s']:.3f} s · antes: …{p.get('falas_antes_4s', '')[-60:]} | fim da palavra '{p.get('palavra_antes', '')}' {p.get('fim_da_palavra_antes_ms', '–')} ms antes · "
                 f"'{p.get('palavra_depois', '')}' começa {p.get('inicio_da_palavra_depois_ms', '–')} ms depois · batida {p.get('batida_ms', '–')} ms · altura {p.get('salto_de_altura_st', '–')} st ({p.get('final_antes', '')})")
    open(os.path.join(out, "relatorio.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    log("pronto:", out)

if __name__ == "__main__":
    main()
