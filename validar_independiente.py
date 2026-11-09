"""
Prueba INDEPENDIENTE de CardioScan AI (v2.5 / v2.6) en bases no usadas para ajustar reglas.

    python validar_independiente.py afdb   <carpeta con registros AFDB>   [--salida dir]
    python validar_independiente.py incart <carpeta con registros INCART> [--salida dir]

PROTOCOLO (fijado ANTES de ver resultados; los umbrales del clasificador NO se tocan)
-----------------------------------------------------------------------------------
Unidad de análisis: ventanas consecutivas, sin solapamiento, de 2 min (igual que BUT PDB).

AFDB — MIT-BIH Atrial Fibrillation Database (23 registros de ~10 h, 250 Hz, canal 0)
  · Referencia por ventana desde las anotaciones de ritmo .atr:
      FA      si ≥ 90 % de la ventana está en (AFIB
      NO-FA   si ≥ 90 % está en (N
      FLUTTER si ≥ 90 % está en (AFL     → se reporta aparte
      UNIÓN   si ≥ 90 % está en (J       → se reporta aparte
      mixta   en otro caso               → excluida
  · Se excluyen ventanas con bloques planos (datos ilegibles de la cinta original).
  · Positivo = CardioScan diagnostica "Fibrilación Auricular".
  · Métricas: Se, Esp, VPP, VPN, exactitud (todas las ventanas) y Se/Esp por registro.

INCART — St Petersburg 12-lead Arrhythmia Database (75 registros de 30 min, 257 Hz, derivación II)
  · Detección de latidos vs. .atr (corregido manualmente): Se, +P, tolerancia 150 ms.
  · Referencia por ventana desde .atr:
      CON EXTRASÍSTOLES si ≥ 2 latidos ectópicos prematuros (A, a, J, S, V, r)
      SIN EXTRASÍSTOLES si 0 ectópicos
      1 ectópico        → excluida (ambigua)
  · Positivo = CardioScan diagnostica "Extrasístoles".
  · También se reporta cuántas ventanas SIN extrasístoles se clasifican como FA (falsas alarmas).
  · Advertencia: varias ventanas y registros provienen del mismo paciente (32 pacientes).
"""
import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import wfdb

sys.path.insert(0, str(Path(__file__).parent))
from ecg_pipeline import classify_signal  # noqa: E402

WIN_SEC = 120
BEAT_SYMBOLS = set("NLRBAaJSVrFejnE/fQ?")
ECTOPIC = set("AaJSVr")


def metrics(tp, fp, tn, fn):
    se = tp / (tp + fn) if tp + fn else float("nan")
    sp = tn / (tn + fp) if tn + fp else float("nan")
    ppv = tp / (tp + fp) if tp + fp else float("nan")
    npv = tn / (tn + fn) if tn + fn else float("nan")
    acc = (tp + tn) / max(1, tp + tn + fp + fn)
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn, "Se": se, "Esp": sp,
            "VPP": ppv, "VPN": npv, "Exactitud": acc}


def _num(v, nd=0):
    """Redondeo seguro (NaN/None → cadena vacía)."""
    try:
        return "" if v is None or v != v else round(float(v), nd)
    except (TypeError, ValueError):
        return ""


def pct(v):
    return "—" if v != v else f"{100 * v:.1f} %"


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


def has_flat_block(x, fs):
    n = int(fs)
    for i in range(0, len(x) - n, n):
        if np.ptp(x[i:i + n]) < 1e-6:
            return True
    return False


# ─── AFDB ────────────────────────────────────────────────────────────────────
def rhythm_track(ann, n):
    """Ritmo vigente en cada muestra a partir de las anotaciones de ritmo."""
    lab = np.full(n, "", dtype=object)
    cur, start = "", 0
    for s, aux in zip(ann.sample, ann.aux_note):
        aux = (aux or "").strip().rstrip("\x00")
        if aux.startswith("("):
            lab[start:min(s, n)] = cur
            cur, start = aux, min(s, n)
    lab[start:] = cur
    return lab


def run_afdb(folder: Path, out: Path, time_budget: float = 0):
    recs = sorted(p.stem for p in folder.glob("*.hea") if (folder / f"{p.stem}.dat").exists()
                  and p.stem[0].isdigit())
    rows, t0 = [], time.time()
    cache = out / "afdb_cache"          # reanudable: un JSON por registro
    cache.mkdir(exist_ok=True)
    for rid in recs:
        cf = cache / f"{rid}.json"
        if cf.exists():
            rows.extend(json.loads(cf.read_text(encoding="utf-8")))
            continue
        if time_budget and time.time() - t0 > time_budget:
            print(f"Tiempo agotado: faltan registros desde {rid}. Vuelva a ejecutar para continuar.")
            return
        rec_rows = []
        h = wfdb.rdheader(str(folder / rid))
        fs, n = h.fs, h.sig_len
        ann = wfdb.rdann(str(folder / rid), "atr")
        track = rhythm_track(ann, n)
        win = int(WIN_SEC * fs)
        sig = wfdb.rdrecord(str(folder / rid), channels=[0]).p_signal[:, 0]
        sig = np.nan_to_num(sig)
        for k, a in enumerate(range(0, n - win + 1, win)):
            lab = track[a:a + win]
            ref = None
            for code, name in (("(AFIB", "FA"), ("(N", "NO-FA"), ("(AFL", "FLUTTER"),
                               ("(J", "UNION")):
                if np.mean(lab == code) >= 0.90:
                    ref = name
                    break
            row = {"registro": rid, "ventana": k, "inicio_s": round(a / fs, 1), "ref": ref or "mixta"}
            rec_rows.append(row)
            x = sig[a:a + win]
            if ref is None:
                row["pred"] = ""
            elif has_flat_block(x, fs):
                row["ref"], row["pred"] = "excluida_plana", ""
            else:
                dx, conf, f, _ = classify_signal(x, fs)
                row.update(pred=dx, conf=round(conf, 3), fc=round(f.get("heart_rate", 0), 1),
                           nrmssd=round(f.get("nrmssd_clean", 0), 3),
                           reg=round(f.get("reg_frac", 0), 3), nprem=f.get("n_prem", 0),
                           half=round(f.get("half_frac", 0), 2), pr=_num(f.get("pr_ms")))
        cf.write_text(json.dumps(rec_rows), encoding="utf-8")
        rows.extend(rec_rows)
        done = [r for r in rows if r["registro"] == rid and r.get("pred")]
        print(f"{rid}: {len(done)} ventanas evaluadas · {time.time() - t0:.0f} s", flush=True)

    with open(out / "afdb_ventanas.csv", "w", newline="", encoding="utf-8-sig") as fh:
        keys = ["registro", "ventana", "inicio_s", "ref", "pred", "conf", "fc", "nrmssd", "reg", "nprem", "half", "pr"]
        w = csv.DictWriter(fh, fieldnames=keys, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    ev = [r for r in rows if r["ref"] in ("FA", "NO-FA") and r.get("pred")]
    tp = sum(r["ref"] == "FA" and r["pred"] == "Fibrilación Auricular" for r in ev)
    fn = sum(r["ref"] == "FA" and r["pred"] != "Fibrilación Auricular" for r in ev)
    fp = sum(r["ref"] == "NO-FA" and r["pred"] == "Fibrilación Auricular" for r in ev)
    tn = sum(r["ref"] == "NO-FA" and r["pred"] != "Fibrilación Auricular" for r in ev)
    m = metrics(tp, fp, tn, fn)

    per = []
    for rid in recs:
        e = [r for r in ev if r["registro"] == rid]
        pos = [r for r in e if r["ref"] == "FA"]
        neg = [r for r in e if r["ref"] == "NO-FA"]
        se = np.mean([r["pred"] == "Fibrilación Auricular" for r in pos]) if pos else float("nan")
        sp = np.mean([r["pred"] != "Fibrilación Auricular" for r in neg]) if neg else float("nan")
        per.append((rid, len(pos), se, len(neg), sp))

    other = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["ref"] in ("FLUTTER", "UNION") and r.get("pred"):
            other[r["ref"]][r["pred"]] += 1
    excl = {k: sum(r["ref"] == k for r in rows) for k in ("mixta", "excluida_plana")}

    L = ["# Prueba independiente — AFDB (fibrilación auricular)\n",
         f"Registros: {len(recs)} · ventanas de {WIN_SEC} s · evaluadas FA/NO-FA: {len(ev)} "
         f"(FA {tp + fn}, NO-FA {fp + tn}) · excluidas: mixtas {excl['mixta']}, "
         f"con bloques planos {excl['excluida_plana']}\n",
         "## Detección de FA (ventanas)\n",
         "| Se | Esp | VPP | VPN | Exactitud | TP | FP | TN | FN |",
         "|---|---|---|---|---|---|---|---|---|",
         f"| **{pct(m['Se'])}** | **{pct(m['Esp'])}** | {pct(m['VPP'])} | {pct(m['VPN'])} | "
         f"{pct(m['Exactitud'])} | {tp} | {fp} | {tn} | {fn} |\n",
         "## Por registro\n", "| Registro | Ventanas FA | Se | Ventanas NO-FA | Esp |",
         "|---|---|---|---|---|"]
    for rid, npos, se, nneg, sp in per:
        L.append(f"| {rid} | {npos} | {pct(se)} | {nneg} | {pct(sp)} |")
    ses = [p[2] for p in per if p[1] >= 5]
    sps = [p[4] for p in per if p[3] >= 5]
    L.append(f"\nMediana por registro (≥ 5 ventanas): Se {pct(np.median(ses)) if ses else '—'} · "
             f"Esp {pct(np.median(sps)) if sps else '—'}\n")
    fl = [r for r in rows if r["ref"] == "FLUTTER" and r.get("pred")]
    if fl:
        L.append("\n## Flutter por registro (04936 = desarrollo; resto = prueba)\n")
        L.append("| Registro | Ventanas flutter | Detectadas como flutter | Rol |\n|---|---|---|---|")
        for rid in sorted(set(r["registro"] for r in fl)):
            e = [r for r in fl if r["registro"] == rid]
            k = sum(r["pred"] == "Flutter Auricular" for r in e)
            L.append(f"| {rid} | {len(e)} | {k} | {'desarrollo' if rid == '04936' else 'prueba'} |")
        L.append("")
    nf = [r for r in ev if r["ref"] == "NO-FA"]
    for dxn in ("Flutter Auricular", "Bloqueo AV"):
        k = sum(r["pred"] == dxn for r in nf)
        L.append(f"Ventanas NO-FA clasificadas como {dxn}: {k}/{len(nf)} ({pct(k / max(1, len(nf)))})")
    L.append("")
    for k, d in other.items():
        tot = sum(d.values())
        L.append(f"**Ventanas {k} ({tot}):** " + ", ".join(f"{p} {c}" for p, c in
                                                          sorted(d.items(), key=lambda kv: -kv[1])))
    (out / "afdb_resumen.md").write_text("\n".join(L), encoding="utf-8")
    (out / "afdb_metricas.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    print("\n".join(L[:7]))


# ─── INCART ──────────────────────────────────────────────────────────────────
def run_incart(folder: Path, out: Path, lead: str = "II"):
    recs = sorted(p.stem for p in folder.glob("I*.hea"))
    rows, T, t0 = [], [0, 0, 0], time.time()
    for rid in recs:
        h = wfdb.rdheader(str(folder / rid))
        ch = h.sig_name.index(lead) if lead in h.sig_name else 0
        fs, n = h.fs, h.sig_len
        sig = np.nan_to_num(wfdb.rdrecord(str(folder / rid), channels=[ch]).p_signal[:, 0])
        ann = wfdb.rdann(str(folder / rid), "atr")
        beats = np.array([s for s, y in zip(ann.sample, ann.symbol) if y in BEAT_SYMBOLS])
        syms = np.array([y for y in ann.symbol if y in BEAT_SYMBOLS])
        win = int(WIN_SEC * fs)
        edge = int(fs)
        for k, a in enumerate(range(0, n - win + 1, win)):
            m = (beats >= a) & (beats < a + win)
            n_ect = int(np.isin(syms[m], list(ECTOPIC)).sum())
            ref = "CON_EXT" if n_ect >= 2 else ("SIN_EXT" if n_ect == 0 else "ambigua")
            dx, conf, f, det = classify_signal(sig[a:a + win], fs)
            rb = beats[m] - a
            rb = rb[(rb > edge) & (rb < win - edge)]
            db = det[(det > edge) & (det < win - edge)]
            tp, fn, fp = match_beats(db, rb, fs)
            T = [T[0] + tp, T[1] + fn, T[2] + fp]
            rows.append({"registro": rid, "ventana": k, "ectopicos_ref": n_ect, "ref": ref,
                         "pred": dx, "conf": round(conf, 3), "fc": round(f.get("heart_rate", 0), 1),
                         "nprem": f.get("n_prem", 0), "nrmssd": round(f.get("nrmssd_clean", 0), 3),
                         "pr": _num(f.get("pr_ms")), "p_bloq": f.get("n_blocked_p", 0),
                         "TP": tp, "FN": fn, "FP": fp})
        print(f"{rid}: {sum(r['registro'] == rid for r in rows)} ventanas · {time.time() - t0:.0f} s",
              flush=True)

    with open(out / "incart_ventanas.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
        w.writeheader()
        w.writerows(rows)

    ev = [r for r in rows if r["ref"] != "ambigua"]
    P = "Extrasístoles"
    tp = sum(r["ref"] == "CON_EXT" and r["pred"] == P for r in ev)
    fn = sum(r["ref"] == "CON_EXT" and r["pred"] != P for r in ev)
    fp = sum(r["ref"] == "SIN_EXT" and r["pred"] == P for r in ev)
    tn = sum(r["ref"] == "SIN_EXT" and r["pred"] != P for r in ev)
    m = metrics(tp, fp, tn, fn)
    neg = [r for r in ev if r["ref"] == "SIN_EXT"]
    fa_false = sum(r["pred"] == "Fibrilación Auricular" for r in neg)
    dist = defaultdict(lambda: defaultdict(int))
    for r in ev:
        dist[r["ref"]][r["pred"]] += 1
    se_b = 100 * T[0] / max(1, T[0] + T[1])
    pp_b = 100 * T[0] / max(1, T[0] + T[2])

    L = ["# Prueba independiente — INCART (extrasístoles)\n",
         f"Registros: {len(recs)} (32 pacientes) · derivación {lead} · ventanas de {WIN_SEC} s · "
         f"evaluadas: {len(ev)} (con extrasístoles {tp + fn}, sin {fp + tn}) · "
         f"ambiguas excluidas: {len(rows) - len(ev)}\n",
         "## Detección de latidos (vs. .atr corregido manualmente)\n",
         f"| Latidos | TP | FN | FP | Sensibilidad | Valor predictivo + |\n|---|---|---|---|---|---|\n"
         f"| {T[0] + T[1]} | {T[0]} | {T[1]} | {T[2]} | **{se_b:.2f} %** | **{pp_b:.2f} %** |\n",
         "## Detección de extrasístoles (ventanas)\n",
         "| Se | Esp | VPP | VPN | Exactitud | TP | FP | TN | FN |",
         "|---|---|---|---|---|---|---|---|---|",
         f"| **{pct(m['Se'])}** | **{pct(m['Esp'])}** | {pct(m['VPP'])} | {pct(m['VPN'])} | "
         f"{pct(m['Exactitud'])} | {tp} | {fp} | {tn} | {fn} |\n",
         f"Ventanas SIN extrasístoles clasificadas como FA: **{fa_false}/{len(neg)} "
         f"({pct(fa_false / max(1, len(neg)))})**\n",
         f"Ventanas clasificadas como Flutter: {sum(r['pred'] == 'Flutter Auricular' for r in ev)}/{len(ev)} · "
         f"como Bloqueo AV: {sum(r['pred'] == 'Bloqueo AV' for r in ev)}/{len(ev)} "
         "(INCART incluye 3 registros con BAV 2.º grado Mobitz I: I09–I11)\n",
         "## Distribución de diagnósticos\n"]
    for ref, d in dist.items():
        L.append(f"- **{ref}** ({sum(d.values())}): " + ", ".join(
            f"{p} {c}" for p, c in sorted(d.items(), key=lambda kv: -kv[1])))
    (out / "incart_resumen.md").write_text("\n".join(L), encoding="utf-8")
    (out / "incart_metricas.json").write_text(json.dumps(
        {**m, "latidos_Se": se_b, "latidos_PP": pp_b, "FA_falsas": fa_false,
         "ventanas_sin_ext": len(neg)}, indent=2), encoding="utf-8")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("base", choices=["afdb", "incart"])
    ap.add_argument("carpeta")
    ap.add_argument("--salida", default="resultados_independiente")
    ap.add_argument("--tiempo-max", type=float, default=0,
                    help="AFDB: segundos máximos por ejecución (0 = sin límite); es reanudable")
    a = ap.parse_args()
    out = Path(a.salida)
    out.mkdir(exist_ok=True, parents=True)
    if a.base == "afdb":
        run_afdb(Path(a.carpeta), out, a.tiempo_max)
    else:
        run_incart(Path(a.carpeta), out)
