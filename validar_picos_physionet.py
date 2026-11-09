"""
Valida el detector de picos R de CardioScan AI contra las anotaciones de
cardiólogos de PhysioNet (archivos .atr).

Métricas (ANSI/AAMI EC57): Sensibilidad (Se) y Valor Predictivo Positivo (+P),
con tolerancia de 150 ms entre pico detectado y latido anotado.

Requiere internet y wfdb (pip install wfdb).

Uso:
    python validar_picos_physionet.py                 # registros por defecto, 5 min
    python validar_picos_physionet.py --minutos 30    # registro completo de mitdb
    python validar_picos_physionet.py --registros mitdb/100 mitdb/203 afdb/04015
"""
import argparse
import numpy as np
import wfdb

from ecg_pipeline import preprocess_ecg, detect_r_peaks

# Símbolos de anotación que corresponden a latidos (AAMI)
BEAT_SYMBOLS = set("NLRBAaJSVrFejnE/fQ?")

DEFAULT = ["mitdb/100", "mitdb/101", "mitdb/103", "mitdb/105", "mitdb/119",
           "mitdb/200", "mitdb/203", "mitdb/208", "mitdb/221",
           "afdb/04015", "afdb/04043", "nsrdb/16265", "nsrdb/16272"]


def evaluar(det, ref, fs, tol_s=0.150):
    tol = int(round(tol_s * fs))
    det = np.sort(det)
    usados = np.zeros(len(det), bool)
    tp = 0
    for r in ref:
        i = np.searchsorted(det, r)
        cand = [j for j in (i - 1, i) if 0 <= j < len(det) and not usados[j]
                and abs(det[j] - r) <= tol]
        if cand:
            j = min(cand, key=lambda j: abs(det[j] - r))
            usados[j] = True
            tp += 1
    fn = len(ref) - tp
    fp = len(det) - tp
    return tp, fn, fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registros", nargs="*", default=DEFAULT)
    ap.add_argument("--minutos", type=float, default=5.0)
    ap.add_argument("--canal", type=int, default=0)
    a = ap.parse_args()

    print(f"{'registro':14s} {'fs':>5s} {'latidos':>8s} {'TP':>6s} {'FN':>5s} "
          f"{'FP':>5s} {'Se %':>7s} {'+P %':>7s}")
    TP = FN = FP = 0
    for rid in a.registros:
        db, rec = rid.split("/")
        try:
            hdr = wfdb.rdheader(rec, pn_dir=db)
            n = min(hdr.sig_len, int(a.minutos * 60 * hdr.fs))
            r = wfdb.rdrecord(rec, pn_dir=db, sampto=n, channels=[a.canal])
            ann = wfdb.rdann(rec, "atr", pn_dir=db, sampto=n)
        except Exception as e:
            print(f"{rid:14s} ERROR: {e}")
            continue
        fs = r.fs
        x = np.nan_to_num(r.p_signal[:, 0])
        ref = np.array([s for s, sym in zip(ann.sample, ann.symbol)
                        if sym in BEAT_SYMBOLS])
        if len(ref) == 0:
            print(f"{rid:14s} sin anotaciones de latido (.atr solo de ritmo)")
            continue
        # Ignorar primer y último segundo (efecto de borde de los filtros)
        ref = ref[(ref > fs) & (ref < n - fs)]
        det = detect_r_peaks(preprocess_ecg(x, fs), fs)
        det = det[(det > fs) & (det < n - fs)]
        tp, fn, fp = evaluar(det, ref, fs)
        TP, FN, FP = TP + tp, FN + fn, FP + fp
        se = 100 * tp / max(1, tp + fn)
        pp = 100 * tp / max(1, tp + fp)
        print(f"{rid:14s} {fs:5.0f} {len(ref):8d} {tp:6d} {fn:5d} {fp:5d} "
              f"{se:7.2f} {pp:7.2f}")

    if TP:
        print("-" * 62)
        print(f"{'TOTAL':14s} {'':5s} {TP + FN:8d} {TP:6d} {FN:5d} {FP:5d} "
              f"{100 * TP / (TP + FN):7.2f} {100 * TP / (TP + FP):7.2f}")
        print("\nReferencia: Pan-Tompkins original reporta Se 99.75 % y +P 99.54 % "
              "en MIT-BIH completa.")


if __name__ == "__main__":
    main()
