"""
Pipeline de procesamiento ECG → Espectrograma → Clasificación ML
Clasificación de Enfermedades Cardiovasculares
"""

import numpy as np
import scipy.signal as signal
from scipy.io import wavfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import io, base64, json, os, csv, re, threading, uuid
from collections import OrderedDict
from pathlib import Path

# ─── Clases de diagnóstico ────────────────────────────────────────────────────
DIAGNOSES = {
    "Normal":                  {"color": "#22c55e", "risk": "Bajo",    "icon": "✓"},
    "Taquicardia":             {"color": "#f59e0b", "risk": "Medio",   "icon": "⚡"},
    "Bradicardia":             {"color": "#f59e0b", "risk": "Medio",   "icon": "🔻"},
    "Fibrilación Auricular":   {"color": "#ef4444", "risk": "Alto",    "icon": "⚠"},
    "Bloqueo AV":              {"color": "#ef4444", "risk": "Alto",    "icon": "🔒"},
    "Extrasístoles":           {"color": "#f97316", "risk": "Medio",   "icon": "💢"},
    "Isquemia Miocárdica":     {"color": "#dc2626", "risk": "Crítico", "icon": "🚨"},
    "Flutter Auricular":       {"color": "#f97316", "risk": "Medio",   "icon": "〰"},
}


# ─── 1. CARGA DE SEÑAL ECG ───────────────────────────────────────────────────
DEFAULT_FS = 500

# Frecuencias de muestreo nativas de las bases PhysioNet usadas en el proyecto
PHYSIONET_FS = {
    "mitdb": 360,   # MIT-BIH Arrhythmia
    "afdb": 250,    # MIT-BIH Atrial Fibrillation
    "nsrdb": 128,   # MIT-BIH Normal Sinus Rhythm
    "ltafdb": 128,  # Long-Term AF
    "svdb": 128,    # MIT-BIH Supraventricular Arrhythmia
    "nstdb": 360,   # Noise Stress Test
    "edb": 250,     # European ST-T
    "incartdb": 257,
}

_FS_HEADER_RE = re.compile(r"fs\s*[=:]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_FS_NAME_RE = re.compile(r"(?:^|[_\-.])fs([0-9]+(?:\.[0-9]+)?)(?:hz)?(?:[_\-.]|$)",
                         re.IGNORECASE)


def _fs_from_filename(filepath: str):
    """fs a partir del nombre: token '_fs360' o prefijo de base PhysioNet."""
    stem = Path(filepath).stem.lower()
    m = _FS_NAME_RE.search(stem)
    if m:
        return float(m.group(1)), f"nombre de archivo (fs{m.group(1)})"
    for db, fs in PHYSIONET_FS.items():
        if re.search(rf"(?:^|_){db}_", stem):
            return float(fs), f"base PhysioNet '{db}' detectada en el nombre"
    return None, None


def _read_text_signal(filepath: str):
    """Lee CSV/TXT: primera columna numérica. Detecta cabecera '# fs=360'."""
    rows, fs_header = [], None
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#") or not (s[0].isdigit() or s[0] in "+-."):
                m = _FS_HEADER_RE.search(s)
                if m and fs_header is None:
                    fs_header = float(m.group(1))
                continue  # comentario o cabecera de columnas
            for cell in re.split(r"[,;\t ]+", s):
                try:
                    rows.append(float(cell))
                    break
                except ValueError:
                    continue
    if not rows:
        raise ValueError("No se encontraron datos numéricos en el archivo.")
    return np.array(rows), fs_header


def load_ecg(filepath: str, fs: float | None = None) -> tuple[np.ndarray, float, str]:
    """
    Carga ECG desde: .csv, .txt, .wav, .dat (texto), .npy

    La frecuencia de muestreo (fs) se resuelve con esta prioridad:
      1. Parámetro explícito `fs` (lo que el usuario escribe en la interfaz)
      2. Cabecera del archivo:  '# fs=360'  (o fs nativa del .wav)
      3. Nombre del archivo:    'registro_fs360.csv' o prefijo PhysioNet
                                (mitdb_ → 360, afdb_ → 250, nsrdb_ → 128 …)
      4. 500 Hz por defecto  → se reporta como ASUMIDA (advertencia)

    Retorna (señal_1D, fs, fuente_de_fs)
    """
    ext = Path(filepath).suffix.lower()
    fs_file, data = None, None

    if ext == ".wav":
        fs_file, data = wavfile.read(filepath)
        if data.ndim > 1:
            data = data[:, 0]
        fs_file = float(fs_file)
    elif ext == ".npy":
        data = np.load(filepath)
        if data.ndim > 1:
            data = data[:, 0]
    elif ext in (".csv", ".txt", ".dat", ""):
        data, fs_file = _read_text_signal(filepath)
    else:
        raise ValueError(f"Formato no soportado: {ext}. Use .csv, .txt, .wav, .npy, .dat")

    data = np.asarray(data, dtype=float)

    if fs is not None and fs > 0:
        fs_val, src = float(fs), "indicada por el usuario"
    elif fs_file:
        fs_val, src = float(fs_file), "cabecera del archivo"
    else:
        fs_val, src = _fs_from_filename(filepath)
        if fs_val is None:
            fs_val, src = float(DEFAULT_FS), f"ASUMIDA ({DEFAULT_FS} Hz por defecto)"

    if not (50 <= fs_val <= 20000):
        raise ValueError(f"Frecuencia de muestreo fuera de rango: {fs_val} Hz")
    if fs_val == int(fs_val):
        fs_val = int(fs_val)
    return data, fs_val, src


# ─── 2. PREPROCESAMIENTO ──────────────────────────────────────────────────────
def preprocess_ecg(ecg: np.ndarray, fs: int) -> np.ndarray:
    """Filtrado baseline + ruido de alta frecuencia + normalización."""
    # Eliminar tendencia de baja frecuencia (baseline wander)
    b_high, a_high = signal.butter(4, 0.5 / (fs / 2), btype='high')
    ecg = signal.filtfilt(b_high, a_high, ecg)

    # Filtro pasa-bajos (eliminar ruido > 40 Hz)
    cutoff = min(40.0, fs / 2 - 1)
    b_low, a_low = signal.butter(4, cutoff / (fs / 2), btype='low')
    ecg = signal.filtfilt(b_low, a_low, ecg)

    # Filtro notch 50/60 Hz (interferencia de red)
    for freq in [50, 60]:
        if freq < fs / 2:
            b_n, a_n = signal.iirnotch(freq, 30, fs)
            ecg = signal.filtfilt(b_n, a_n, ecg)

    # Normalización Z-score
    ecg = (ecg - np.mean(ecg)) / (np.std(ecg) + 1e-8)
    return ecg


# ─── 3. ECG → ESPECTROGRAMA ──────────────────────────────────────────────────
def ecg_to_spectrogram(ecg: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    STFT → espectrograma en dB.
    Retorna (frecuencias, tiempos, Sxx_dB, Sxx_raw)
    """
    # Ventana fija en TIEMPO (0.5 s), no en muestras: así la resolución
    # tiempo-frecuencia no cambia con la fs (antes 256 muestras = 0.5 s a
    # 500 Hz pero 2 s a 128 Hz).
    nperseg = int(min(round(0.5 * fs), len(ecg) // 8))
    noverlap = nperseg * 3 // 4
    f, t, Zxx = signal.stft(ecg, fs=fs, nperseg=nperseg, noverlap=noverlap)
    Sxx = np.abs(Zxx) ** 2
    Sxx_db = 10 * np.log10(Sxx + 1e-12)
    return f, t, Sxx_db, Sxx


def ecg_to_cwt(ecg: np.ndarray, fs: int, n_freqs: int = 80,
               f_min: float = 0.5, f_max: float = 40.0, w0: float = 6.0,
               max_duration_sec: float = 10.0):
    """
    Transformada Wavelet Continua (CWT) con wavelet Morlet compleja.

    Implementación propia (no depende de scipy.signal.cwt, eliminada en
    scipy >= 1.15). La convolución señal * wavelet se calcula en el dominio
    de la frecuencia (teorema de convolución), equivalente a la convolución
    directa pero O(N log N) por escala:

        W(s, t) = IFFT{ X(ω) · conj(Ψ̂(s·ω)) } · sqrt(2π·s/dt)

        Ψ̂(ω) = π^(-1/4) · exp(-(ω - ω0)² / 2) · H(ω)   (Morlet analítica)

    Normalización de Torrence & Compo (1998). La potencia se divide por la
    escala (corrección de sesgo de Liu et al., 2007) para que escalas grandes
    no dominen artificialmente.

    Parámetros
    ----------
    ecg : señal preprocesada (1D)
    fs  : frecuencia de muestreo (Hz)
    n_freqs : número de frecuencias (espaciado logarítmico)
    f_min, f_max : rango de análisis en Hz (por defecto la banda del ECG)
    w0  : frecuencia central de la Morlet (6 → buen compromiso tiempo/frec.)
    max_duration_sec : ventana analizada (igual a la del gráfico ECG)

    Retorna
    -------
    freqs : (n_freqs,) Hz, de mayor a menor
    t     : (N,) s
    power : (n_freqs, N) potencia |W|²/s
    coi   : (N,) cono de influencia expresado en Hz (por debajo, efecto borde)
    """
    n = min(len(ecg), int(max_duration_sec * fs))
    x = np.asarray(ecg[:n], dtype=float)
    x = x - np.mean(x)
    dt = 1.0 / fs

    f_max = min(f_max, fs / 2.0 * 0.9)
    freqs = np.geomspace(f_max, f_min, num=n_freqs)          # alta → baja
    # Relación escala ↔ frecuencia de Fourier para Morlet
    fourier_factor = 4 * np.pi / (w0 + np.sqrt(2 + w0 ** 2))
    scales = 1.0 / (freqs * fourier_factor)

    # Zero-padding a potencia de 2 para reducir efecto circular
    n_fft = int(2 ** np.ceil(np.log2(2 * n)))
    X = np.fft.fft(x, n=n_fft)
    omega = 2 * np.pi * np.fft.fftfreq(n_fft, d=dt)           # rad/s

    W = np.empty((n_freqs, n), dtype=complex)
    for i, s in enumerate(scales):
        so = s * omega
        psi_hat = (np.pi ** -0.25) * np.exp(-0.5 * (so - w0) ** 2) * (omega > 0)
        psi_hat *= np.sqrt(2 * np.pi * s / dt)
        W[i, :] = np.fft.ifft(X * np.conj(psi_hat))[:n]

    power = (np.abs(W) ** 2) / scales[:, None]
    t = np.arange(n) * dt

    # Cono de influencia: e-folding time √2·s → en frecuencia
    edge = np.minimum(t - t[0], t[-1] - t) + dt
    coi = 1.0 / (fourier_factor * edge / np.sqrt(2))
    return freqs, t, power, coi


# ─── 4a. DETECCIÓN DE PICOS R (Pan-Tompkins simplificado) ────────────────────
def detect_r_peaks(ecg: np.ndarray, fs: float) -> np.ndarray:
    """
    Detector de complejos QRS inspirado en Pan & Tompkins (1985):
      pasa-banda 5–15 Hz → derivada → cuadrado → integración 150 ms
      → picos con periodo refractario de 250 ms (FC máx. detectable 240 lpm)
      → umbral adaptativo (mediana local de la envolvente)
      → refinamiento al máximo real del QRS en ±75 ms, con polaridad automática.
    Reemplaza a find_peaks(distance=0.5 s), que limitaba la FC a 120 lpm.
    """
    nyq = fs / 2
    hi = min(15.0, nyq * 0.9)
    b, a = signal.butter(2, [5.0 / nyq, hi / nyq], btype="band")
    bp = signal.filtfilt(b, a, ecg)

    der = np.gradient(bp) * fs
    sq = der ** 2
    win = max(1, int(0.150 * fs))
    integ = np.convolve(sq, np.ones(win) / win, mode="same")

    refractory = int(0.25 * fs)
    # umbral adaptativo: fracción del percentil alto en ventanas de ~2 s
    seg = int(2 * fs)
    thr = np.empty_like(integ)
    for i in range(0, len(integ), seg):
        chunk = integ[max(0, i - seg): i + 2 * seg]
        thr[i:i + seg] = 0.3 * np.percentile(chunk, 98)
    allc, _ = signal.find_peaks(integ, distance=refractory)
    cand = allc[integ[allc] > thr[allc]]
    if len(cand) == 0:
        return cand

    # Search-back (Pan & Tompkins, 1985): si un intervalo supera 1.66 × RR
    # típico, se busca allí el candidato más alto con umbral reducido a la mitad.
    # Recupera latidos normales perdidos cuando ectópicos grandes elevan el umbral.
    if len(cand) >= 4:
        for _ in range(3):
            added = []
            rr_c = np.diff(cand)
            for k in range(len(rr_c)):
                lo_k = max(0, k - 4)
                ref_rr = np.median(rr_c[lo_k:k + 5])
                if rr_c[k] > 1.66 * ref_rr:
                    a0, a1 = cand[k] + refractory, cand[k + 1] - refractory
                    inside = allc[(allc > a0) & (allc < a1)]
                    if len(inside):
                        best = inside[np.argmax(integ[inside])]
                        if integ[best] > 0.5 * thr[best]:
                            added.append(best)
            if not added:
                break
            cand = np.sort(np.concatenate([cand, added]))

    # Polaridad dominante del QRS (derivaciones con R negativa)
    half = int(0.075 * fs)
    pos = np.median([ecg[max(0, c - half): c + half].max() for c in cand])
    neg = np.median([-ecg[max(0, c - half): c + half].min() for c in cand])
    sig_ref = ecg if pos >= neg else -ecg

    # La integración retrasa ~win/2: buscar el pico real hacia atrás y adelante
    peaks = []
    for c in cand:
        lo, hi_i = max(0, c - win), min(len(ecg), c + half)
        p = lo + int(np.argmax(sig_ref[lo:hi_i]))
        if not peaks or p - peaks[-1] >= refractory:
            peaks.append(p)
        elif sig_ref[p] > sig_ref[peaks[-1]]:
            peaks[-1] = p
    return np.array(peaks, dtype=int)


# ─── 4b. HRV EN FRECUENCIA (sobre el tacograma RR) ───────────────────────────
HRV_MIN_DURATION_LF = 120.0   # s — mínimo para estimar LF (Task Force, 1996)
HRV_MIN_DURATION_HF = 60.0    # s — mínimo para estimar HF


def hrv_frequency_domain(peaks: np.ndarray, fs: float, fs_interp: float = 4.0) -> dict:
    """
    Análisis espectral de la variabilidad de la frecuencia cardíaca.

    Las bandas VLF (0.0033–0.04 Hz), LF (0.04–0.15 Hz) y HF (0.15–0.4 Hz)
    se definen sobre la SERIE DE INTERVALOS RR (tacograma), no sobre el ECG.
    Procedimiento: RR(t) → interpolación cúbica a 4 Hz → sin tendencia →
    Welch (Hann). Recomendación Task Force ESC/NASPE (1996).

    Retorna dict con potencias (ms²), razones, PSD y validez según duración.
    """
    out = {"vlf_power": 0.0, "lf_power": 0.0, "hf_power": 0.0,
           "vlf_ratio": 0.0, "lf_ratio": 0.0, "hf_ratio": 0.0,
           "lf_hf_ratio": 0.0, "lf_nu": 0.0, "hf_nu": 0.0,
           "hrv_duration_sec": 0.0, "hrv_lf_valid": False, "hrv_hf_valid": False,
           "_psd_f": None, "_psd": None}
    if len(peaks) < 4:
        return out

    t_beats = peaks / fs
    rr = np.diff(t_beats) * 1000.0                    # ms
    t_rr = t_beats[1:]
    # Excluir RR fisiológicamente imposibles (artefactos de detección)
    ok = (rr > 250) & (rr < 2500)
    t_rr, rr = t_rr[ok], rr[ok]
    if len(rr) < 4:
        return out

    from scipy.interpolate import CubicSpline
    t_u = np.arange(t_rr[0], t_rr[-1], 1.0 / fs_interp)
    if len(t_u) < 16:
        return out
    rr_u = CubicSpline(t_rr, rr)(t_u)
    rr_u = signal.detrend(rr_u, type="linear")

    nperseg = min(len(rr_u), int(256 * fs_interp / 4))
    f_h, psd = signal.welch(rr_u, fs=fs_interp, window="hann",
                            nperseg=nperseg, noverlap=nperseg // 2,
                            detrend=False, scaling="density")

    def band(lo, hi):
        m = (f_h >= lo) & (f_h < hi)
        return float(np.trapezoid(psd[m], f_h[m])) if m.sum() > 1 else 0.0

    vlf, lf, hf = band(0.0033, 0.04), band(0.04, 0.15), band(0.15, 0.40)
    tot = vlf + lf + hf + 1e-12
    dur = float(t_rr[-1] - t_rr[0])
    out.update({
        "vlf_power": vlf, "lf_power": lf, "hf_power": hf,
        "vlf_ratio": vlf / tot, "lf_ratio": lf / tot, "hf_ratio": hf / tot,
        "lf_hf_ratio": lf / (hf + 1e-12),
        "lf_nu": 100 * lf / (lf + hf + 1e-12), "hf_nu": 100 * hf / (lf + hf + 1e-12),
        "hrv_duration_sec": dur,
        "hrv_lf_valid": dur >= HRV_MIN_DURATION_LF,
        "hrv_hf_valid": dur >= HRV_MIN_DURATION_HF,
        "_psd_f": f_h, "_psd": psd,
    })
    return out


# ─── 4c. PATRÓN DEL RITMO (FA vs extrasístoles vs bloqueo AV) ────────────────
def rhythm_pattern(rr_ms: np.ndarray) -> dict:
    """
    Descriptores del PATRÓN de los intervalos RR (no solo de su variabilidad):

    - reg_frac:   fracción de RR dentro de ±12 % de la mediana local (7 latidos).
                  Alta en ritmo sinusal con ectópicos aislados; baja en FA.
    - n_prem:     latidos prematuros (RR < 85 % de la mediana local).
    - nrmssd_clean: RMSSD/RR medio tras excluir prematuros, pausas compensatorias
                  y pausas largas → irregularidad "de fondo". Alta en FA
                  (irregularmente irregular), baja con ectópicos aislados.
    - bi_ratio / bi_minor / bi_spread: agrupamiento de RR en dos grupos (k-means
                  1D). Dos grupos compactos con razón ≈ 2 → conducción 2:1
                  intermitente (bloqueo AV de 2.º grado).
    """
    out = {"reg_frac": 1.0, "n_prem": 0, "prem_frac": 0.0, "nrmssd_clean": 0.0,
           "bi_ratio": 0.0, "bi_minor": 0.0, "bi_spread": 1.0}
    rr = np.asarray(rr_ms, float)
    rr = rr[(rr > 250) & (rr < 3000)]
    n = len(rr)
    if n < 8:
        return out
    pad = np.pad(rr, (3, 3), mode="edge")
    loc = np.array([np.median(pad[i:i + 7]) for i in range(n)])
    rel = rr / loc
    prem = rel < 0.85
    comp = np.zeros(n, bool)
    comp[1:] = prem[:-1] & (rel[1:] > 1.08)
    excl = prem | comp | (rel > 1.5)
    clean = rr[~excl]
    out["reg_frac"] = float(np.mean(np.abs(rel - 1) < 0.12))
    out["n_prem"] = int(prem.sum())
    out["prem_frac"] = float(prem.mean())
    if len(clean) > 5:
        out["nrmssd_clean"] = float(np.sqrt(np.mean(np.diff(clean) ** 2)) / np.mean(clean))

    # Agrupamiento en dos niveles (k-means 1D)
    srt = np.sort(rr)
    c1, c2 = np.percentile(srt, 25), np.percentile(srt, 75)
    lab = None
    for _ in range(30):
        lab = np.abs(srt - c1) > np.abs(srt - c2)
        if lab.all() or (~lab).all():
            break
        c1, c2 = srt[~lab].mean(), srt[lab].mean()
    if lab is not None and 3 <= lab.sum() <= n - 3:
        lo, hi = srt[~lab], srt[lab]
        out["bi_ratio"] = float(hi.mean() / lo.mean())
        out["bi_minor"] = float(min(len(lo), len(hi)) / n)
        out["bi_spread"] = float(max(np.std(lo) / lo.mean(), np.std(hi) / hi.mean()))
    return out


# ─── 4d. EXTRACCIÓN DE CARACTERÍSTICAS ──────────────────────────────────────
def extract_features(ecg: np.ndarray, fs: int, f: np.ndarray,
                     Sxx: np.ndarray) -> dict:
    """Extrae features temporales, HRV (tiempo y frecuencia) y espectrales del ECG."""
    features = {}

    # ── Temporales ──
    features["mean_amplitude"]  = float(np.mean(np.abs(ecg)))
    features["std_amplitude"]   = float(np.std(ecg))
    features["rms"]             = float(np.sqrt(np.mean(ecg ** 2)))
    features["peak_to_peak"]    = float(np.ptp(ecg))
    features["skewness"]        = float(_skewness(ecg))
    features["kurtosis"]        = float(_kurtosis(ecg))

    # ── Detección de picos R ──
    peaks = detect_r_peaks(ecg, fs)

    if len(peaks) >= 2:
        rr = np.diff(peaks) / fs * 1000  # ms
        bpm = 60 / (np.mean(rr) / 1000)
        features["heart_rate"]   = float(bpm)
        features["rr_mean"]      = float(np.mean(rr))
        features["rr_std"]       = float(np.std(rr))
        features["rr_cv"]        = float(np.std(rr) / (np.mean(rr) + 1e-8))
        features["sdnn"]         = float(np.std(rr))
        features["rmssd"]        = float(np.sqrt(np.mean(np.diff(rr) ** 2)))
        features["pnn50"]        = float(np.sum(np.abs(np.diff(rr)) > 50) / len(rr) * 100)
        features["num_peaks"]    = int(len(peaks))
        features.update(rhythm_pattern(rr))
    else:
        features.update({k: 0.0 for k in [
            "heart_rate","rr_mean","rr_std","rr_cv","sdnn","rmssd","pnn50"]})
        features["num_peaks"] = int(len(peaks))
        features.update(rhythm_pattern(np.array([])))

    # ── HRV en frecuencia (tacograma RR, NO el espectro del ECG) ──
    hrv = hrv_frequency_domain(peaks, fs)
    features["_hrv_psd_f"] = hrv.pop("_psd_f")
    features["_hrv_psd"] = hrv.pop("_psd")
    features.update(hrv)

    # ── Espectrales del ECG (STFT) ──
    psd_mean = np.mean(Sxx, axis=1)
    features["dominant_freq"] = float(f[np.argmax(psd_mean)])

    # Energía espectral por decil
    for i, col in enumerate(np.array_split(Sxx, 5, axis=1)):
        features[f"spec_energy_seg{i}"] = float(np.mean(col))

    return features, peaks


def _skewness(x):
    m = np.mean(x)
    s = np.std(x) + 1e-8
    return np.mean(((x - m) / s) ** 3)

def _kurtosis(x):
    m = np.mean(x)
    s = np.std(x) + 1e-8
    return np.mean(((x - m) / s) ** 4) - 3


# ─── 5. CLASIFICACIÓN BASADA EN REGLAS + ML ──────────────────────────────────
# Umbrales de las reglas de ritmo. Ajustados en BUT PDB (conjunto de DESARROLLO,
# ver docs/validacion_but_pdb). El desempeño final debe medirse en bases
# independientes SIN modificar estos valores.
AF_NRMSSD_MIN = 0.12      # irregularidad de fondo (tras quitar ectópicos)
AF_REG_MAX = 0.80         # fracción máxima de RR "regulares" compatible con FA
BAV_RATIO = (1.6, 2.3)    # razón entre los dos grupos de RR (≈ 2 → conducción 2:1)
BAV_MINOR_MIN = 0.15      # el grupo minoritario debe ser ≥ 15 % de los latidos
BAV_SPREAD_MAX = 0.10     # cada grupo compacto (CV < 10 %)
EXT_MIN_PREM = 2          # latidos prematuros mínimos para extrasístoles


def classify_ecg(features: dict) -> tuple[str, float, list[str], dict]:
    """
    Clasificación por reglas clínicas en dos niveles:

    1. RITMO (prioridad): bloqueo AV 2:1 → fibrilación auricular → extrasístoles.
       Se basa en el PATRÓN de los RR (rhythm_pattern), no solo en su variabilidad:
       la versión anterior (CV > 0.15 y RMSSD > 50) clasificaba como FA cualquier
       ritmo irregular, incluidos extrasístoles y bloqueos (VPP de FA 32 % en BUT PDB).
    2. FRECUENCIA: taquicardia / bradicardia / flutter 2:1, cuando el ritmo es regular.
       Si hay un hallazgo de ritmo, la frecuencia se reporta como hallazgo secundario.

    Retorna (diagnóstico, confianza, notas_clínicas, puntajes)
    """
    hr     = features.get("heart_rate", 75)
    rr_cv  = features.get("rr_cv", 0.0)
    lf_hf  = features.get("lf_hf_ratio", 1.5)
    peaks  = features.get("num_peaks", 0)
    reg    = features.get("reg_frac", 1.0)
    nprem  = features.get("n_prem", 0)
    nrm    = features.get("nrmssd_clean", 0.0)
    bi_r   = features.get("bi_ratio", 0.0)
    bi_m   = features.get("bi_minor", 0.0)
    bi_s   = features.get("bi_spread", 1.0)

    notes = []
    rhythm = {}     # hallazgos de ritmo (prioritarios)
    rate = {}       # hallazgos de frecuencia

    if peaks < 8:
        notes.append(f"Solo {peaks} latidos detectados: el análisis de ritmo no es fiable.")

    # ── 1a. Bloqueo AV de 2.º grado (conducción 2:1 intermitente) ──
    is_bav = (BAV_RATIO[0] <= bi_r <= BAV_RATIO[1] and bi_m >= BAV_MINOR_MIN
              and bi_s < BAV_SPREAD_MAX)
    if is_bav:
        rhythm["Bloqueo AV"] = min(0.95, 0.70 + 0.5 * (BAV_SPREAD_MAX - bi_s) / BAV_SPREAD_MAX)
        notes.append(f"RR agrupados en dos niveles con razón {bi_r:.2f} ({100 * bi_m:.0f} % en el "
                     "grupo minoritario): compatible con bloqueo AV de 2.º grado con "
                     "conducción 2:1 intermitente. Confirmar ondas P no conducidas.")

    # ── 1b. Fibrilación auricular: irregularidad de fondo, sin patrón ──
    if not is_bav and nrm > AF_NRMSSD_MIN and reg < AF_REG_MAX:
        rhythm["Fibrilación Auricular"] = min(0.95, 0.55 + (nrm - AF_NRMSSD_MIN) * 2
                                              + (AF_REG_MAX - reg) * 0.5)
        notes.append(f"Ritmo irregularmente irregular: irregularidad de fondo {nrm:.3f} "
                     f"(> {AF_NRMSSD_MIN}) y solo {100 * reg:.0f} % de RR regulares.")

    # ── 1c. Extrasístoles: ritmo de base regular con latidos prematuros ──
    if not is_bav and "Fibrilación Auricular" not in rhythm and nprem >= EXT_MIN_PREM:
        rhythm["Extrasístoles"] = min(0.90, 0.55 + 0.02 * nprem)
        notes.append(f"{nprem} latidos prematuros (RR < 85 % del local) sobre un ritmo de base "
                     f"regular ({100 * reg:.0f} % de RR regulares): compatible con extrasístoles.")

    # ── 2. Frecuencia ──
    if hr > 100:
        rate["Taquicardia"] = min(0.95, 0.5 + (hr - 100) / 100)
        notes.append(f"FC elevada: {hr:.0f} lpm (normal 60-100)")
    elif 0 < hr < 60:
        rate["Bradicardia"] = min(0.95, 0.5 + (60 - hr) / 60)
        notes.append(f"FC reducida: {hr:.0f} lpm (normal 60-100)")
        if hr < 40 and not rhythm:
            notes.append("Bradicardia marcada y regular: descartar bloqueo AV avanzado (2:1 "
                         "fijo o completo) evaluando las ondas P.")
    # Flutter: solo como diferencial de taquicardia regular ≈ 150 lpm (2:1)
    if 140 <= hr <= 160 and rr_cv < 0.05 and not rhythm:
        rate["Flutter Auricular"] = 0.55
        notes.append(f"Taquicardia regular a {hr:.0f} lpm: considerar flutter auricular con "
                     "conducción 2:1 (confirmar ondas F).")

    # ── Isquemia: solo como hallazgo de HRV en registros ≥ 2 min ──
    if (features.get("hrv_lf_valid", False)
            and lf_hf > 4.0 and features.get("lf_ratio", 0) > 0.7):
        rate["Isquemia Miocárdica"] = min(0.6, lf_hf / 8.0)
        notes.append(f"Dominio LF marcado (LF/HF = {lf_hf:.2f}). Hallazgo inespecífico: "
                     "la isquemia requiere análisis del segmento ST.")

    # ── Selección: ritmo primero, luego frecuencia ──
    candidates = {**rate, **rhythm}
    if rhythm:
        diagnosis = max(rhythm, key=rhythm.get)
        confidence = float(rhythm[diagnosis])
    elif rate:
        diagnosis = max(rate, key=rate.get)
        confidence = float(rate[diagnosis])
    else:
        diagnosis = "Normal"
        confidence = float(max(0.70, min(0.95, 0.6 + 0.4 * reg - nrm)))
        notes.append("Ritmo sinusal regular, sin latidos prematuros ni pausas significativas.")
    others = [k for k in candidates if k != diagnosis]
    if others:
        notes.append(f"Hallazgos secundarios: {', '.join(others)}")

    all_scores = {d: 0.0 for d in DIAGNOSES}
    all_scores["Normal"] = 0.0 if candidates else confidence
    all_scores.update(candidates)
    total = sum(all_scores.values()) + 1e-8
    all_scores = {k: v / total for k, v in all_scores.items()}
    return diagnosis, confidence, notes, all_scores


# ─── 6. GENERACIÓN DE FIGURAS ────────────────────────────────────────────────
_DPI = 110


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


BG = "#0f172a"
GRID = "#1e293b"
ACCENT = "#06b6d4"
TEXT = "#e2e8f0"

# Temas de figuras: oscuro (interfaz) y claro (reporte PDF imprimible)
_THEMES = {
    "dark":  {"BG": "#0f172a", "GRID": "#1e293b", "ACCENT": "#06b6d4",
              "TEXT": "#e2e8f0", "_DPI": 110},
    "light": {"BG": "#ffffff", "GRID": "#cbd5e1", "ACCENT": "#0e7490",
              "TEXT": "#0f172a", "_DPI": 170},
}
_PLOT_LOCK = threading.Lock()


class _theme:
    """Cambia temporalmente los colores globales de las figuras (thread-safe)."""
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        _PLOT_LOCK.acquire()
        g = globals()
        self._prev = {k: g[k] for k in _THEMES["dark"]}
        g.update(_THEMES[self.name])

    def __exit__(self, *exc):
        globals().update(self._prev)
        _PLOT_LOCK.release()


# Caché de los últimos análisis (para regenerar figuras en el reporte PDF)
_ANALYSIS_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_MAX = 20


def _cache_put(d: dict) -> str:
    aid = uuid.uuid4().hex
    _ANALYSIS_CACHE[aid] = d
    while len(_ANALYSIS_CACHE) > _CACHE_MAX:
        _ANALYSIS_CACHE.popitem(last=False)
    return aid


def _render_plots(d: dict, theme: str = "dark") -> dict:
    with _theme(theme):
        return {
            "ecg":         plot_ecg_signal(d["ecg"], d["fs"], d["peaks"]),
            "spectrogram": plot_spectrogram(d["f"], d["t"], d["Sxx_db"], d["fs"]),
            "cwt":         plot_scalogram(*d["cwt"]),
            "compare":     plot_stft_vs_cwt(d["f"], d["t"], d["Sxx_db"], *d["cwt"]),
            "rr":          plot_rr_intervals(d["ecg"], d["fs"], d["peaks"]),
            "scores":      plot_scores_bar(d["scores"]),
            "psd":         plot_frequency_analysis(d["f"], d["Sxx"], d["features"]),
        }


def forget_analysis(analysis_id: str) -> bool:
    """Elimina un análisis de la caché (botón 'Nuevo paciente')."""
    return _ANALYSIS_CACHE.pop(analysis_id or "", None) is not None


def render_plots_for_report(analysis_id: str) -> dict | None:
    """Figuras en tema claro para el PDF; None si el análisis ya no está en caché."""
    d = _ANALYSIS_CACHE.get(analysis_id or "")
    return _render_plots(d, "light") if d else None


def plot_ecg_signal(ecg: np.ndarray, fs: int, peaks: np.ndarray,
                    duration_sec: float = 10.0) -> str:
    n = min(int(duration_sec * fs), len(ecg))
    t = np.linspace(0, n / fs, n)
    sig = ecg[:n]

    fig, ax = plt.subplots(figsize=(11, 3.2), facecolor=BG)
    ax.set_facecolor(BG)

    # grid estilo papel ECG
    for y in np.arange(-4, 5, 0.5):
        ax.axhline(y, color=GRID, linewidth=0.3, alpha=0.6)
    for x in np.arange(0, n / fs, 0.2):
        ax.axvline(x, color=GRID, linewidth=0.3, alpha=0.6)

    ax.plot(t, sig, color=ACCENT, linewidth=0.9, alpha=0.95)

    # marcar picos R visibles
    visible_peaks = peaks[peaks < n]
    if len(visible_peaks):
        ax.scatter(visible_peaks / fs, sig[visible_peaks],
                   color="#f43f5e", s=25, zorder=5, label="Pico R")
        ax.legend(loc="upper right", fontsize=8, facecolor=BG,
                  labelcolor=TEXT, framealpha=0.7)

    ax.set_xlim(0, n / fs)
    ax.set_xlabel("Tiempo (s)", color=TEXT, fontsize=9)
    ax.set_ylabel("Amplitud (mV)", color=TEXT, fontsize=9)
    ax.tick_params(colors=TEXT, labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    fig.tight_layout()
    b64 = _fig_to_b64(fig)
    plt.close(fig)
    return b64


def plot_spectrogram(f: np.ndarray, t: np.ndarray,
                     Sxx_db: np.ndarray, fs: int) -> str:
    # Limitar a 0-40 Hz
    mask = f <= 40
    f_plot = f[mask]
    S_plot = Sxx_db[mask, :]

    fig, ax = plt.subplots(figsize=(11, 3.8), facecolor=BG)
    ax.set_facecolor(BG)

    vmin, vmax = np.percentile(S_plot, [5, 98])
    im = ax.pcolormesh(t, f_plot, S_plot, shading="gouraud",
                       cmap="plasma", vmin=vmin, vmax=vmax)
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.set_label("Potencia (dB)", color=TEXT, fontsize=9)
    cb.ax.yaxis.set_tick_params(color=TEXT, labelcolor=TEXT, labelsize=8)

    # (Las bandas HRV LF/HF ya no se dibujan aquí: pertenecen al tacograma RR,
    #  no al espectro del ECG. Ver pestaña "HRV frecuencial".)

    ax.set_xlabel("Tiempo (s)", color=TEXT, fontsize=9)
    ax.set_ylabel("Frecuencia (Hz)", color=TEXT, fontsize=9)
    ax.tick_params(colors=TEXT, labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    fig.tight_layout()
    b64 = _fig_to_b64(fig)
    plt.close(fig)
    return b64


def _decimate_cols(t, power, coi, max_cols=1000):
    """Reduce columnas para graficar (máximo por bloque: conserva picos QRS)."""
    k = int(np.ceil(power.shape[1] / max_cols))
    if k <= 1:
        return t, power, coi
    n = (power.shape[1] // k) * k
    p = power[:, :n].reshape(power.shape[0], -1, k).max(axis=2)
    return t[:n:k], p, coi[:n:k]


def _plot_scalogram_ax(fig, ax, freqs, t, power, coi):
    t, power, coi = _decimate_cols(t, power, coi)
    P_db = 10 * np.log10(power + 1e-12)
    vmin, vmax = np.percentile(P_db, [5, 99.5])
    im = ax.pcolormesh(t, freqs, P_db, shading="gouraud",
                       cmap="plasma", vmin=vmin, vmax=vmax)
    ax.set_yscale("log")
    ax.set_ylim(freqs.min(), freqs.max())
    # Cono de influencia (zona afectada por bordes)
    ax.fill_between(t, coi, freqs.min(), color="#000000", alpha=0.45,
                    hatch="//", edgecolor="#64748b", linewidth=0)
    ax.plot(t, np.clip(coi, freqs.min(), freqs.max()), color="#e2e8f0",
            linewidth=0.7, linestyle="--", alpha=0.7)
    ticks = [f for f in (0.5, 1, 2, 5, 10, 20, 40) if freqs.min() <= f <= freqs.max()]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{f:g}" for f in ticks])
    cb = fig.colorbar(im, ax=ax, pad=0.01)
    cb.set_label("Potencia (dB)", color=TEXT, fontsize=9)
    cb.ax.yaxis.set_tick_params(color=TEXT, labelcolor=TEXT, labelsize=8)
    ax.set_ylabel("Frecuencia (Hz, log)", color=TEXT, fontsize=9)
    ax.tick_params(colors=TEXT, labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)


def plot_scalogram(freqs, t, power, coi) -> str:
    """Escalograma CWT (Morlet) con cono de influencia."""
    fig, ax = plt.subplots(figsize=(11, 3.8), facecolor=BG)
    ax.set_facecolor(BG)
    _plot_scalogram_ax(fig, ax, freqs, t, power, coi)
    ax.set_xlim(t[0], t[-1])
    ax.set_xlabel("Tiempo (s)", color=TEXT, fontsize=9)
    ax.set_title("Escalograma CWT — Morlet compleja (ω0 = 6)",
                 color=TEXT, fontsize=9, pad=4)
    fig.tight_layout()
    b64 = _fig_to_b64(fig)
    plt.close(fig)
    return b64


def plot_stft_vs_cwt(f, t_stft, Sxx_db, freqs, t_cwt, power, coi) -> str:
    """STFT y CWT sobre la misma ventana temporal, ejes alineados."""
    t_end = t_cwt[-1]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.4), facecolor=BG,
                                   sharex=True)
    # STFT
    ax1.set_facecolor(BG)
    mask = (f >= freqs.min()) & (f <= freqs.max())
    tm = t_stft <= t_end + 1e-9
    S = Sxx_db[np.ix_(mask, tm)]
    if S.size and tm.sum() > 1 and mask.sum() > 1:
        vmin, vmax = np.percentile(S, [5, 98])
        im = ax1.pcolormesh(t_stft[tm], f[mask], S, shading="gouraud",
                            cmap="plasma", vmin=vmin, vmax=vmax)
        cb = fig.colorbar(im, ax=ax1, pad=0.01)
        cb.set_label("Potencia (dB)", color=TEXT, fontsize=9)
        cb.ax.yaxis.set_tick_params(color=TEXT, labelcolor=TEXT, labelsize=8)
    ax1.set_ylabel("Frecuencia (Hz)", color=TEXT, fontsize=9)
    ax1.set_title("STFT — resolución tiempo-frecuencia fija",
                  color=TEXT, fontsize=9, pad=4)
    ax1.tick_params(colors=TEXT, labelsize=8)
    for sp in ax1.spines.values():
        sp.set_edgecolor(GRID)
    # CWT
    ax2.set_facecolor(BG)
    _plot_scalogram_ax(fig, ax2, freqs, t_cwt, power, coi)
    ax2.set_title("CWT Morlet — resolución adaptativa (fina en tiempo a alta frecuencia)",
                  color=TEXT, fontsize=9, pad=4)
    ax2.set_xlim(0, t_end)
    ax2.set_xlabel("Tiempo (s)", color=TEXT, fontsize=9)
    fig.tight_layout()
    b64 = _fig_to_b64(fig)
    plt.close(fig)
    return b64


def plot_rr_intervals(ecg: np.ndarray, fs: int, peaks: np.ndarray) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.2), facecolor=BG)

    if len(peaks) >= 2:
        rr = np.diff(peaks) / fs * 1000
        beat_idx = np.arange(1, len(rr) + 1)

        # RR en el tiempo
        ax = axes[0]
        ax.set_facecolor(BG)
        ax.plot(beat_idx, rr, color="#a78bfa", linewidth=1.2, marker="o",
                markersize=3, markerfacecolor="#f43f5e")
        ax.axhline(np.mean(rr), color=ACCENT, linewidth=0.9,
                   linestyle="--", label=f"Media {np.mean(rr):.0f} ms")
        ax.fill_between(beat_idx, np.mean(rr) - np.std(rr),
                        np.mean(rr) + np.std(rr), alpha=0.15, color=ACCENT)
        ax.legend(fontsize=8, facecolor=BG, labelcolor=TEXT, framealpha=0.7)
        ax.set_xlabel("Latido #", color=TEXT, fontsize=9)
        ax.set_ylabel("Intervalo RR (ms)", color=TEXT, fontsize=9)
        ax.tick_params(colors=TEXT, labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(GRID)

        # Poincaré plot
        ax2 = axes[1]
        ax2.set_facecolor(BG)
        ax2.scatter(rr[:-1], rr[1:], c="#06b6d4", s=18, alpha=0.7, edgecolors="none")
        ax2.plot([rr.min(), rr.max()], [rr.min(), rr.max()],
                 color=GRID, linewidth=0.8, linestyle="--")
        ax2.set_xlabel("RR_n (ms)", color=TEXT, fontsize=9)
        ax2.set_ylabel("RR_n+1 (ms)", color=TEXT, fontsize=9)
        ax2.tick_params(colors=TEXT, labelsize=8)
        for sp in ax2.spines.values():
            sp.set_edgecolor(GRID)
        ax2.set_title("Diagrama de Poincaré", color=TEXT, fontsize=9, pad=4)
    else:
        for ax in axes:
            ax.set_facecolor(BG)
            ax.text(0.5, 0.5, "Insuficientes picos R detectados",
                    ha="center", va="center", color=TEXT, transform=ax.transAxes)

    fig.tight_layout()
    b64 = _fig_to_b64(fig)
    plt.close(fig)
    return b64


def plot_scores_bar(scores: dict) -> str:
    labels = list(scores.keys())
    vals   = [scores[l] * 100 for l in labels]
    colors_list = [DIAGNOSES[l]["color"] for l in labels]

    fig, ax = plt.subplots(figsize=(7, 3.5), facecolor=BG)
    ax.set_facecolor(BG)

    bars = ax.barh(labels, vals, color=colors_list, height=0.6, alpha=0.85)
    for bar, v in zip(bars, vals):
        if v > 2:
            ax.text(v + 0.5, bar.get_y() + bar.get_height() / 2,
                    f"{v:.1f}%", va="center", color=TEXT, fontsize=8)

    ax.set_xlim(0, 100)
    ax.set_xlabel("Puntaje relativo (%)", color=TEXT, fontsize=9)
    ax.tick_params(colors=TEXT, labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    fig.tight_layout()
    b64 = _fig_to_b64(fig)
    plt.close(fig)
    return b64


def plot_frequency_analysis(f: np.ndarray, Sxx: np.ndarray,
                            features: dict | None = None) -> str:
    """
    Izq.: PSD del ECG (0–40 Hz, contenido de la onda).
    Der.: PSD de la HRV sobre el tacograma RR con bandas VLF/LF/HF.
    """
    features = features or {}
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 3.2), facecolor=BG)

    # ── PSD del ECG ──
    psd = np.mean(Sxx, axis=1)
    mask = f <= 40
    ax.set_facecolor(BG)
    ax.fill_between(f[mask], psd[mask], alpha=0.3, color=ACCENT)
    ax.plot(f[mask], psd[mask], color=ACCENT, linewidth=1.2)
    ax.set_title("Espectro del ECG (STFT promedio)", color=TEXT, fontsize=9, pad=4)
    ax.set_xlabel("Frecuencia (Hz)", color=TEXT, fontsize=9)
    ax.set_ylabel("PSD", color=TEXT, fontsize=9)

    # ── PSD de la HRV ──
    ax2.set_facecolor(BG)
    fh, ph = features.get("_hrv_psd_f"), features.get("_hrv_psd")
    if fh is not None and len(fh) > 2:
        m = fh <= 0.5
        ax2.plot(fh[m], ph[m], color=TEXT, linewidth=1.0)
        for name, lo, hi, c in [("VLF", 0.0033, 0.04, "#f59e0b"),
                                ("LF", 0.04, 0.15, "#22d3ee"),
                                ("HF", 0.15, 0.40, "#a78bfa")]:
            mb = (fh >= lo) & (fh <= hi)
            if mb.any():
                ax2.fill_between(fh[mb], ph[mb], alpha=0.45, color=c, label=name)
        ax2.legend(fontsize=8, facecolor=BG, labelcolor=TEXT, framealpha=0.7)
        dur = features.get("hrv_duration_sec", 0)
        warn = "" if features.get("hrv_lf_valid") else f"  ⚠ {dur:.0f} s < 120 s: LF/HF no fiable"
        ax2.set_title(f"HRV — tacograma RR (Welch){warn}", color=TEXT, fontsize=9, pad=4)
    else:
        ax2.text(0.5, 0.5, "Latidos insuficientes para HRV espectral",
                 ha="center", va="center", color=TEXT, transform=ax2.transAxes)
    ax2.set_xlabel("Frecuencia (Hz)", color=TEXT, fontsize=9)
    ax2.set_ylabel("PSD (ms²/Hz)", color=TEXT, fontsize=9)

    for a_ in (ax, ax2):
        a_.tick_params(colors=TEXT, labelsize=8)
        for sp in a_.spines.values():
            sp.set_edgecolor(GRID)
    fig.tight_layout()
    b64 = _fig_to_b64(fig)
    plt.close(fig)
    return b64


# ─── 7. FUNCIÓN PRINCIPAL ────────────────────────────────────────────────────
def classify_signal(x: np.ndarray, fs: float):
    """
    Clasificación rápida (sin figuras ni CWT) para validación masiva.
    Usa exactamente el mismo preprocesamiento, detector, features y reglas
    que analyze_ecg. Retorna (diagnóstico, confianza, features, picos).
    """
    ecg = preprocess_ecg(np.asarray(x, float), fs)
    f, _t, _Sxx_db, Sxx = ecg_to_spectrogram(ecg, fs)
    features, peaks = extract_features(ecg, fs, f, Sxx)
    dx, conf, _notes, _scores = classify_ecg(features)
    return dx, conf, features, peaks


def analyze_ecg(filepath: str, fs: float | None = None,
                original_name: str | None = None) -> dict:
    """
    Pipeline completo. Retorna dict JSON-serializable.
    fs: frecuencia de muestreo indicada por el usuario (opcional).
    original_name: nombre original del archivo subido (para inferir fs).
    """
    try:
        ecg_raw, fs, fs_source = load_ecg(filepath, fs)
        if fs_source.startswith("ASUMIDA") and original_name:
            fs_n, src_n = _fs_from_filename(original_name)
            if fs_n:
                fs, fs_source = (int(fs_n) if fs_n == int(fs_n) else fs_n), src_n
        if len(ecg_raw) < fs * 2:
            raise ValueError("La señal es demasiado corta (mín. 2 segundos).")

        ecg = preprocess_ecg(ecg_raw, fs)
        f, t, Sxx_db, Sxx = ecg_to_spectrogram(ecg, fs)
        features, peaks = extract_features(ecg, fs, f, Sxx)
        diagnosis, confidence, notes, scores = classify_ecg(features)
        if fs_source.startswith("ASUMIDA"):
            notes.insert(0, f"⚠ Frecuencia de muestreo {fs_source}. Si no es la real, "
                            "FC, intervalos RR y frecuencias quedan mal escalados: "
                            "indíquela en el campo 'fs'.")
        if features.get("num_peaks", 0) >= 4 and not features.get("hrv_lf_valid"):
            notes.append(f"Registro de {features.get('hrv_duration_sec', 0):.0f} s: "
                         "LF/HF requiere ≥ 2 min (Task Force, 1996); se reporta "
                         "como referencia y no se usa para diagnosticar.")
        # CWT: solo visualización (opción 1). NO alimenta al clasificador.
        cw_f, cw_t, cw_p, cw_coi = ecg_to_cwt(ecg, fs)
        cache = {"ecg": ecg, "fs": fs, "peaks": peaks, "f": f, "t": t,
                 "Sxx_db": Sxx_db, "Sxx": Sxx, "cwt": (cw_f, cw_t, cw_p, cw_coi),
                 "scores": scores, "features": features}
        analysis_id = _cache_put(cache)

        return {
            "status":    "ok",
            "diagnosis": diagnosis,
            "confidence": round(confidence * 100, 1),
            "risk":      DIAGNOSES[diagnosis]["risk"],
            "icon":      DIAGNOSES[diagnosis]["icon"],
            "color":     DIAGNOSES[diagnosis]["color"],
            "notes":     notes,
            "features":  {k: (round(v, 4) if isinstance(v, float) else v)
                          for k, v in features.items() if not k.startswith("_")},
            "scores":    {k: round(v * 100, 2) for k, v in scores.items()},
            "signal_info": {
                "duration_sec": round(len(ecg) / fs, 2),
                "fs_hz": fs,
                "fs_source": fs_source,
                "n_samples": len(ecg),
            },
            "analysis_id": analysis_id,
            "plots": _render_plots(cache, "dark"),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def generate_demo_ecg(condition: str = "normal", fs: int = 500,
                       duration: float = 10.0) -> np.ndarray:
    """
    Genera una señal ECG sintética para demostración.
    condition: 'normal' | 'tachy' | 'brady' | 'afib' | 'block'
    """
    t = np.linspace(0, duration, int(fs * duration))
    ecg = np.zeros_like(t)

    params = {
        "normal": {"bpm": 72,  "rr_noise": 0.02},
        "tachy":  {"bpm": 130, "rr_noise": 0.02},
        "brady":  {"bpm": 42,  "rr_noise": 0.02},
        "afib":   {"bpm": 90,  "rr_noise": 0.18},
        "block":  {"bpm": 80,  "rr_noise": 0.01},   # frecuencia auricular
    }
    p = params.get(condition, params["normal"])
    bpm, rr_noise = p["bpm"], p["rr_noise"]

    rr_base = 60.0 / bpm
    beat_times = []
    blocked_p = []   # ondas P no conducidas (solo demo de bloqueo AV)
    current = 0.0
    if condition == "block":
        # Bloqueo AV de 2.º grado: aurícula a 80 lpm; tramos alternos de
        # conducción 1:1 y 2:1 (una P de cada dos no genera QRS).
        pp = 60.0 / 80
        k = 0
        while current < duration:
            two_to_one = (k // 6) % 2 == 1
            if two_to_one and k % 2 == 1:
                blocked_p.append(current)
            else:
                beat_times.append(current)
            current += pp * (1 + np.random.randn() * rr_noise)
            k += 1
    else:
        while current < duration:
            beat_times.append(current)
            rr = rr_base * (1 + np.random.randn() * rr_noise)
            current += max(0.3, rr)

    # Forma del latido PQRST simplificada
    def pqrst(t_local):
        p  =  0.15 * np.exp(-((t_local - 0.10) ** 2) / (2 * 0.008 ** 2))
        q  = -0.10 * np.exp(-((t_local - 0.18) ** 2) / (2 * 0.005 ** 2))
        r  =  1.00 * np.exp(-((t_local - 0.20) ** 2) / (2 * 0.006 ** 2))
        s  = -0.25 * np.exp(-((t_local - 0.22) ** 2) / (2 * 0.005 ** 2))
        tp =  0.25 * np.exp(-((t_local - 0.35) ** 2) / (2 * 0.030 ** 2))
        return p + q + r + s + tp

    for bt in beat_times:
        local_t = t - bt
        mask = (local_t >= -0.05) & (local_t <= 0.55)
        ecg[mask] += pqrst(local_t[mask])
    for bt in blocked_p:   # P sin QRS
        local_t = t - bt
        mask = (local_t >= -0.05) & (local_t <= 0.25)
        ecg[mask] += 0.15 * np.exp(-((local_t[mask] - 0.10) ** 2) / (2 * 0.008 ** 2))

    # Ruido
    ecg += np.random.randn(len(t)) * 0.03
    return ecg


if __name__ == "__main__":
    import sys, tempfile
    print("=== Test con señal sintética ===")
    for cond in ["normal", "tachy", "afib"]:
        ecg_demo = generate_demo_ecg(cond)
        # guardar como CSV temporal
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f_tmp:
            for v in ecg_demo:
                f_tmp.write(f"{v}\n")
            fname = f_tmp.name
        result = analyze_ecg(fname)
        os.unlink(fname)
        if result["status"] == "ok":
            print(f"  [{cond:8s}] → {result['diagnosis']:25s} | "
                  f"Conf: {result['confidence']}% | HR: {result['features'].get('heart_rate',0):.0f} lpm")
        else:
            print(f"  [{cond}] ERROR: {result['message']}")
