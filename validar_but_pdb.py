"""
Validación de CardioScan AI sobre la base BUT PDB (PhysioNet, 50 registros de 2 min).

    python validar_but_pdb.py <carpeta_o_zip_but_pdb> [--canal 0] [--salida resultados_but_pdb]

Qué mide
--------
1. Detección de latidos vs. anotaciones .qrs de cardiólogos (Se, +P; tolerancia 150 ms).
2. Diagnóstico de CardioScan vs. patología de referencia del README de la base.

Criterio de referencia (definido ANTES de ver resultados)
---------------------------------------------------------
Cada registro tiene uno o más códigos (README.txt). Se asigna una clase PRINCIPAL
con esta prioridad:
    AFIB/FIB → Fibrilación Auricular
    AFL      → Flutter Auricular
    BI/BII/BIII → Bloqueo AV
    P, PREX, IVR, VFL, NOD → FUERA DE ALCANCE (el sistema no modela esos ritmos)
    SVTA/VT  → Taquicardia (si además hay ectópicos, principal = Extrasístoles)
    A, a, V, J, E, B, T, VP, F → Extrasístoles
    NA       → Normal (arritmia sinusal)
    solo L/R (bloqueo de rama) → FUERA DE ALCANCE
Clases ACEPTABLES = principal + las implicadas por los demás códigos
(+ Taquicardia si FC de referencia > 100 lpm, + Bradicardia si < 60 lpm).

Se reportan exactitud ESTRICTA (pred == principal) y ACEPTABLE (pred ∈ aceptables),
solo sobre registros dentro de alcance.

AVISO METODOLÓGICO: si las reglas del clasificador se ajustan mirando estos
resultados, BUT PDB pasa a ser conjunto de DESARROLLO y la exactitud final debe
reportarse en una base independiente no usada para el ajuste.
"""
import argparse
import csv
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import wfdb

sys.path.insert(0, str(Path(__file__).parent))
from ecg_pipeline import analyze_ecg  # noqa: E402

CLASSES = ["Normal", "Taquicardia", "Bradicardia", "Fibrilación Auricular",
           "Bloqueo AV", "Extrasístoles", "Isquemia Miocárdica", "Flutter Auricular"]
ECTOPIC = {"A", "a", "V", "J", "E", "B", "T", "VP", "F"}
OUT_OF_SCOPE = {"P", "PREX", "IVR", "VFL", "NOD"}
BEAT_SYMBOLS = set("NLRBAaJSVrFejnE/fQ?")
ABBR = {"FA": "Fibrilación Auricular", "FL": "Flutter Auricular", "BAV": "Bloqueo AV",
        "EXT": "Extrasístoles", "TAQ": "Taquicardia", "BRA": "Bradicardia",
        "NOR": "Normal", "ISQ": "Isquemia Miocárdica"}
SHORT = {v: k for k, v in ABBR.items()}


# ─── Referencia ──────────────────────────────────────────────────────────────
def parse_readme(path: Path) -> dict:
    """{ '01': {'codes': [...], 'source': 'MIT-BIH ... 231', 'fs': 360} }"""
    ref = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^\s*(\d+)\s+'([^']*)'\s+(.+?)\s+(\d+)\s+\[(\d+),\s*(\d+)\]\s+(\d+)", line)
        if not m:
            continue
        rid = f"{int(m.group(1)):02d}"
        codes = [c.strip() for c in m.group(2).split(",") if c.strip()]
        ref[rid] = {"codes": codes, "source": f"{m.group(3).strip()} {m.group(4)}",
                    "fs": int(m.group(7))}
    return ref


def reference_classes(codes, hr_ref):
    s = set(codes)
    acc = set()
    if s & {"AFIB", "FIB"}:
        primary = "Fibrilación Auricular"
        if "AFL" in s:
            acc.add("Flutter Auricular")
    elif "AFL" in s:
        primary = "Flutter Auricular"
    elif s & {"BI", "BII", "BIII"}:
        primary = "Bloqueo AV"
    elif s & OUT_OF_SCOPE:
        primary = None
    elif s & {"SVTA", "VT"}:
        primary = "Extrasístoles" if s & ECTOPIC else "Taquicardia"
        acc.add("Taquicardia")
    elif s & ECTOPIC:
        primary = "Extrasístoles"
    elif "NA" in s:
        primary = "Normal"
    else:
        primary = None  # solo bloqueo de rama (L/R)
    if primary is None:
        return None, set()
    acc.add(primary)
    if s & ECTOPIC:
        acc.add("Extrasístoles")
    if hr_ref is not None:
        if hr_ref > 100:
            acc.add("Taquicardia")
        elif hr_ref < 60:
            acc.add("Bradicardia")
    return primary, acc


# ─── Detección ───────────────────────────────────────────────────────────────
def match_beats(det, ref, fs, tol_s=0.150):
    tol = int(round(tol_s * fs))
    det = np.sort(np.asarray(det))
    used = np.zeros(len(det), bool)
    tp = 0
    for r in ref:
        i = np.searchsorted(det, r)
        cand = [j for j in (i - 1, i) if 0 <= j < len(det) and not used[j]
                and abs(det[j] - r) <= tol]
        if cand:
            j = min(cand, key=lambda j: abs(det[j] - r))
            used[j] = True
            tp += 1
    return tp, len(ref) - tp, len(det) - tp


def find_db_dir(src: Path) -> tuple[Path, Path | None]:
    tmp = None
    if src.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="butpdb_"))
        with zipfile.ZipFile(src) as zf:
            zf.extractall(tmp)
        src = tmp
    readmes = list(src.rglob("README.txt"))
    if not readmes:
        raise SystemExit("No se encontró README.txt de BUT PDB.")
    return readmes[0].parent, tmp


# ─── Principal ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fuente", help="Carpeta o .zip de BUT PDB")
    ap.add_argument("--canal", type=int, default=0)
    ap.add_argument("--salida", default="resultados_but_pdb")
    a = ap.parse_args()

    db, tmp = find_db_dir(Path(a.fuente))
    ref = parse_readme(db / "README.txt")
    out = Path(a.salida)
    out.mkdir(exist_ok=True)
    rows = []

    for rid in sorted(ref):
        rec = db / rid
        r = wfdb.rdrecord(str(rec), channels=[a.canal])
        fs = float(r.fs)
        x = np.nan_to_num(r.p_signal[:, 0])
        ann = wfdb.rdann(str(rec), "qrs")
        beats = np.array([s for s, sym in zip(ann.sample, ann.symbol) if sym in BEAT_SYMBOLS])
        hr_ref = (60.0 / np.median(np.diff(beats) / fs)) if len(beats) > 2 else None
        rr_ref = np.diff(beats) / fs if len(beats) > 2 else np.array([])

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            np.savetxt(fh, x, fmt="%.6f", header=f"fs={fs:g}", comments="# ")
            csv_path = fh.name
        res = analyze_ecg(csv_path, fs=fs)
        Path(csv_path).unlink(missing_ok=True)
        if res.get("status") != "ok":
            print(f"{rid}: ERROR {res.get('message')}")
            continue

        f = res["features"]
        # Picos detectados: se recalculan igual que el pipeline para comparar
        from ecg_pipeline import preprocess_ecg, detect_r_peaks
        det = detect_r_peaks(preprocess_ecg(x, fs), fs)
        edge = int(fs)
        refb = beats[(beats > edge) & (beats < len(x) - edge)]
        detb = det[(det > edge) & (det < len(x) - edge)]
        tp, fn, fp = match_beats(detb, refb, fs)

        primary, acceptable = reference_classes(ref[rid]["codes"], hr_ref)
        pred = res["diagnosis"]
        in_scope = primary is not None
        rows.append({
            "registro": rid,
            "codigos": ",".join(ref[rid]["codes"]),
            "origen": ref[rid]["source"],
            "fs": int(fs),
            "fc_ref": round(hr_ref, 1) if hr_ref else "",
            "cv_rr_ref": round(float(np.std(rr_ref) / np.mean(rr_ref)), 3) if len(rr_ref) else "",
            "ref_principal": primary or "FUERA DE ALCANCE",
            "ref_aceptables": "; ".join(sorted(acceptable)),
            "cardioscan": pred,
            "confianza": res["confidence"],
            "fc_cardioscan": round(f.get("heart_rate", 0), 1),
            "cv_rr_cardioscan": round(f.get("rr_cv", 0), 3),
            "rmssd": round(f.get("rmssd", 0), 1),
            "pnn50": round(f.get("pnn50", 0), 1),
            "latidos_ref": len(refb), "latidos_det": len(detb),
            "TP": tp, "FN": fn, "FP": fp,
            "Se_%": round(100 * tp / max(1, tp + fn), 2),
            "PP_%": round(100 * tp / max(1, tp + fp), 2),
            "en_alcance": in_scope,
            "acierto_estricto": in_scope and pred == primary,
            "acierto_aceptable": in_scope and pred in acceptable,
        })
        mark = "—" if not in_scope else ("✓" if pred in acceptable else "✗")
        print(f"{rid} {ref[rid]['codes']!s:28s} ref={SHORT.get(primary, 'fuera'):5s} "
              f"pred={SHORT.get(pred, pred):4s} {mark}  FC ref {rows[-1]['fc_ref']!s:>6} "
              f"det {rows[-1]['fc_cardioscan']:>6}  Se {rows[-1]['Se_%']:6.2f} +P {rows[-1]['PP_%']:6.2f}")

    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── CSV detallado ──
    with open(out / "resultados_por_registro.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)

    # ── Resumen ──
    scope = [r for r in rows if r["en_alcance"]]
    n = len(scope)
    strict = sum(r["acierto_estricto"] for r in scope)
    lenient = sum(r["acierto_aceptable"] for r in scope)
    TP = sum(r["TP"] for r in rows); FN = sum(r["FN"] for r in rows); FP = sum(r["FP"] for r in rows)

    per_class = defaultdict(lambda: [0, 0, 0])  # n, estricto, aceptable
    for r in scope:
        pc = per_class[r["ref_principal"]]
        pc[0] += 1; pc[1] += r["acierto_estricto"]; pc[2] += r["acierto_aceptable"]

    labels = [c for c in CLASSES if any(r["ref_principal"] == c or r["cardioscan"] == c for r in scope)]
    cm = Counter((r["ref_principal"], r["cardioscan"]) for r in scope)

    L = []
    L.append("# Validación CardioScan AI — BUT PDB\n")
    L.append(f"Registros: {len(rows)} · dentro de alcance: {n} · fuera de alcance: {len(rows) - n} · canal {a.canal}\n")
    L.append("## Detección de latidos (vs. anotaciones .qrs)\n")
    L.append(f"| Latidos anotados | TP | FN | FP | Sensibilidad | Valor predictivo + |\n|---|---|---|---|---|---|\n"
             f"| {TP + FN} | {TP} | {FN} | {FP} | **{100 * TP / max(1, TP + FN):.2f} %** | **{100 * TP / max(1, TP + FP):.2f} %** |\n")
    L.append("## Diagnóstico\n")
    L.append(f"- Exactitud **estricta** (clase principal): **{strict}/{n} = {100 * strict / max(1, n):.1f} %**")
    L.append(f"- Exactitud **aceptable** (cualquier hallazgo presente): **{lenient}/{n} = {100 * lenient / max(1, n):.1f} %**\n")
    L.append("### Por clase de referencia\n\n| Referencia (principal) | n | Estricta | Aceptable |\n|---|---|---|---|")
    for c in CLASSES:
        if c in per_class:
            k, s_, l_ = per_class[c]
            L.append(f"| {c} | {k} | {s_}/{k} | {l_}/{k} |")
    L.append("\n### Matriz de confusión (filas = referencia principal, columnas = CardioScan)\n")
    L.append("| Ref \\ Pred | " + " | ".join(SHORT[c] for c in labels) + " |")
    L.append("|---" * (len(labels) + 1) + "|")
    for rc in labels:
        if not any(r["ref_principal"] == rc for r in scope):
            continue
        L.append(f"| **{SHORT[rc]}** | " + " | ".join(str(cm.get((rc, pc), "") or "·") for pc in labels) + " |")
    L.append("\n" + " · ".join(f"{k} = {v}" for k, v in ABBR.items()) + "\n")
    L.append("### Detalle\n\n| Reg | Códigos | Referencia | CardioScan | FC ref | FC det | CV RR | Se % | ✓ |\n|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        ok = "—" if not r["en_alcance"] else ("✓" if r["acierto_aceptable"] else "✗")
        L.append(f"| {r['registro']} | {r['codigos']} | {r['ref_principal']} | {r['cardioscan']} | "
                 f"{r['fc_ref']} | {r['fc_cardioscan']} | {r['cv_rr_cardioscan']} | {r['Se_%']} | {ok} |")
    L.append("\n> BUT PDB se usa como conjunto de **desarrollo**: cualquier ajuste de reglas basado en esta tabla "
             "debe evaluarse después en una base independiente.")
    (out / "resumen.md").write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L[:12]))
    print(f"\nArchivos: {out / 'resultados_por_registro.csv'} · {out / 'resumen.md'}")


if __name__ == "__main__":
    main()
