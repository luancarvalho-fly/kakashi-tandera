# -*- coding: utf-8 -*-
"""MEDIDOR DE MÚSICA da régua (regra 385: emoção da música = BPM, energia, ciclo, subidas, viradas — MEDIDA, sem modelo).
Pra uma música inteira (ou um stem), segundo a segundo:
  - batidas e tempos fortes (Beat This!; no processador se a placa estiver ocupada) → BPM local
  - ENERGIA (volume em dB, janela de 0,4 s) · BRILHO (centroide do espectro) · DENSIDADE (ataques por segundo)
  - CICLO: partes da música (mudança de "cara" na matriz de semelhança) encaixadas no tempo forte mais perto, e o tamanho
    de cada parte em compassos
  - SUBIDAS: energia/brilho crescendo por ≥ 2 s seguidos · DROP: salto de energia depois de subida · VIRADA: pico de
    ataques no último tempo antes de uma parte nova · RESPIRO: queda forte de energia
Uso: medir(arquivo, ini=0, dur=None, dispositivo="cpu") -> dict. Rodando direto: python musica.py <arquivo> [ini] [dur]"""
import json, os, sys
import numpy as np, librosa

def medir(arq, ini=0.0, dur=None, dispositivo="cpu"):
    import subprocess
    sr = 22050
    cmd = ["ffmpeg", "-v", "error", "-ss", "%.4f" % ini] + (["-t", "%.4f" % dur] if dur else []) + ["-i", arq, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    y = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32).copy()   # ffmpeg abre qualquer formato (aac incluso)
    T = len(y) / sr
    # batidas
    try:
        from beat_this.inference import File2Beats
        import soundfile as sf, tempfile
        tmp = os.path.join(tempfile.gettempdir(), "regua_musica.wav"); sf.write(tmp, y, sr)
        b, db = File2Beats(checkpoint_path="final0", device=dispositivo, dbn=False)(tmp)
        b, db = np.asarray(b, float), np.asarray(db, float)
    except Exception:
        tempo, fr = librosa.beat.beat_track(y=y, sr=sr); b = librosa.frames_to_time(fr, sr=sr); db = b[::4]
    bpm_local = [(float(b[i]), round(60 / float(np.median(np.diff(b[max(0, i - 4):i + 5]))), 1)) for i in range(len(b)) if len(b[max(0, i - 4):i + 5]) > 2]
    # curvas por quadro de 0,1 s
    hop = int(sr * 0.1)
    rms = librosa.feature.rms(y=y, frame_length=int(sr * 0.4), hop_length=hop)[0]
    energia = 20 * np.log10(rms + 1e-6)
    brilho = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    on = librosa.onset.onset_detect(y=y, sr=sr, hop_length=512, units="time")
    t = np.arange(len(energia)) * 0.1
    dens = np.array([((on >= x - 0.5) & (on < x + 0.5)).sum() for x in t])
    # ciclo: novidade na matriz de semelhança (MFCC + croma) → fronteiras, encaixadas no tempo forte
    feat = np.vstack([librosa.feature.mfcc(y=y, sr=sr, hop_length=hop, n_mfcc=13), librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)])
    feat = librosa.util.normalize(feat, axis=0)
    K = 32
    if feat.shape[1] < 2 * K + 12:                                 # trecho curto demais (ou leitura falhou): sem fronteiras de parte
        R = np.zeros((feat.shape[1], feat.shape[1]))
    else:
        R = librosa.segment.recurrence_matrix(feat, mode="affinity", width=5, sym=True)
    ker = np.kron(np.array([[1, -1], [-1, 1]]), np.ones((K, K)))
    nov = np.zeros(R.shape[0])
    for i in range(K, R.shape[0] - K):
        nov[i] = (R[i - K:i + K, i - K:i + K] * ker).sum()
    nov = np.clip(nov, 0, None); nov /= nov.max() + 1e-9
    pk = librosa.util.peak_pick(nov, pre_max=30, post_max=30, pre_avg=30, post_avg=30, delta=0.08, wait=60)
    fronteiras = [0.0] + [float(min(db, key=lambda d: abs(d - x * 0.1))) if len(db) else x * 0.1 for x in pk] + [T]
    fronteiras = sorted(set(round(f, 3) for f in fronteiras))
    compasso = float(np.median(np.diff(db))) if len(db) > 2 else None
    partes = [{"ini": a, "fim": f, "compassos": round((f - a) / compasso, 1) if compasso else None,
               "energia_db": round(float(energia[int(a * 10):max(int(a * 10) + 1, int(f * 10))].mean()), 1)} for a, f in zip(fronteiras, fronteiras[1:]) if f - a > 1.0]
    # subidas, drops, viradas, respiros
    suave = np.convolve(energia, np.ones(5) / 5, "same"); bs = np.convolve(brilho, np.ones(5) / 5, "same")
    sub = []; i = 0
    while i < len(suave) - 20:
        j = i
        while j + 1 < len(suave) and (suave[j + 1] >= suave[j] - 0.15 or bs[j + 1] >= bs[j]): j += 1
        if (j - i) * 0.1 >= 2.0 and suave[j] - suave[i] >= 4: sub.append({"ini": round(i * 0.1, 1), "fim": round(j * 0.1, 1), "sobe_db": round(float(suave[j] - suave[i]), 1)})
        i = j + 1
    drops = [{"t": s["fim"], "salto_db": round(float(suave[min(len(suave) - 1, int(s["fim"] * 10) + 5)] - suave[int(s["fim"] * 10)]), 1)} for s in sub]
    viradas = []
    for p in partes[1:]:
        a = p["ini"]; ultimo = [x for x in b if a - 0.6 <= x < a]
        antes = ((on >= a - 0.6) & (on < a)).sum(); normal = ((on >= a - 4) & (on < a - 1)).sum() / 3 * 0.6
        if antes > normal * 1.6 and antes >= 3: viradas.append({"t": round(a, 2), "ataques_ultimo_tempo": int(antes)})
    respiros = [{"t": round(k * 0.1, 1), "cai_db": round(float(suave[k] - suave[k - 10]), 1)} for k in range(10, len(suave)) if suave[k] - suave[k - 10] < -10 and (k < 11 or suave[k - 1] - suave[k - 11] >= -10)]
    return {"arquivo": arq, "ini": ini, "dur": T, "bpm": round(60 / float(np.median(np.diff(b))), 1) if len(b) > 2 else None,
            "batidas": [round(float(x), 3) for x in b], "tempos_fortes": [round(float(x), 3) for x in db], "bpm_local": bpm_local[::4],
            "curvas_0_1s": {"energia_db": [round(float(x), 1) for x in energia], "brilho_hz": [int(x) for x in brilho], "ataques_por_s": [int(x) for x in dens]},
            "partes": partes, "subidas": sub, "drops": drops, "viradas": viradas, "respiros": respiros}

if __name__ == "__main__":
    r = medir(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.0, float(sys.argv[3]) if len(sys.argv) > 3 else None)
    print(json.dumps({k: v for k, v in r.items() if k not in ("batidas", "tempos_fortes", "curvas_0_1s", "bpm_local")}, ensure_ascii=False, indent=1))
