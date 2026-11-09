"""
Importación de registros PhysioNet en formato WFDB (.hea + .dat [+ .atr/.qrs])
directamente en CardioScan AI, sin convertir a CSV por fuera.

Flujo:
  1. save_upload(): recibe un .zip de la base (o archivos sueltos), lo extrae en
     una carpeta temporal de sesión y devuelve los registros encontrados.
  2. read_segment(): lee un canal/tramo de un registro con su fs real.
  3. reference_annotations(): resume las anotaciones de cardiólogos del tramo.
"""
import os
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path

import numpy as np

try:
    import wfdb
except ImportError:  # instalación automática, igual que flask en app.py
    import sys
    os.system(f"{sys.executable} -m pip install wfdb -q")
    import wfdb

SESSION_TTL_SEC = 3 * 3600
ANN_EXTS = ["atr", "qrs", "ecg", "ari", "pwave", "atrb", "pu", "pu0", "pu1", "man"]
ALLOWED_EXTS = {".zip", ".hea", ".dat", ".mat", ".edf", ".atr", ".qrs", ".ecg", ".ari",
                ".pwave", ".atrb", ".pu", ".pu0", ".pu1", ".man", ".xws", ".txt", ""}

BEAT_DESC = {
    "N": "Normal", "L": "Bloqueo de rama izquierda", "R": "Bloqueo de rama derecha",
    "B": "Bloqueo de rama (sin especificar)", "A": "Extrasístole auricular",
    "a": "Extrasístole auricular aberrante", "J": "Extrasístole nodal",
    "S": "Extrasístole supraventricular", "V": "Extrasístole ventricular",
    "r": "Extrasístole ventricular R-sobre-T", "F": "Fusión ventricular+normal",
    "e": "Escape auricular", "j": "Escape nodal", "n": "Escape supraventricular",
    "E": "Escape ventricular", "/": "Marcapasos", "f": "Fusión marcapasos+normal",
    "Q": "No clasificable", "?": "No clasificado",
}
BEAT_SYMBOLS = set(BEAT_DESC)

RHYTHM_DESC = {
    "(N": "Ritmo sinusal normal", "(AFIB": "Fibrilación auricular",
    "(AFL": "Flutter auricular", "(AB": "Bigeminismo auricular",
    "(B": "Bigeminismo ventricular", "(T": "Trigeminismo ventricular",
    "(BII": "Bloqueo AV de 2.º grado", "(BI": "Bloqueo AV de 1.er grado",
    "(BIII": "Bloqueo AV de 3.er grado", "(IVR": "Ritmo idioventricular",
    "(NOD": "Ritmo nodal", "(P": "Ritmo de marcapasos", "(PREX": "Preexcitación (WPW)",
    "(SBR": "Bradicardia sinusal", "(SVTA": "Taquiarritmia supraventricular",
    "(VFL": "Flutter ventricular", "(VT": "Taquicardia ventricular",
    "(SVTA)": "Taquiarritmia supraventricular", "(J": "Ritmo de la unión",
}


# ─── Sesiones temporales ─────────────────────────────────────────────────────
def _cleanup(base: Path):
    now = time.time()
    for d in base.glob("wfdb_*"):
        try:
            if now - d.stat().st_mtime > SESSION_TTL_SEC:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def _safe_extract(zf: zipfile.ZipFile, dest: Path):
    """Extrae evitando rutas fuera de dest (zip slip)."""
    dest = dest.resolve()
    for m in zf.infolist():
        target = (dest / m.filename).resolve()
        if dest not in target.parents and target != dest:
            raise ValueError(f"Ruta no permitida dentro del zip: {m.filename}")
        if m.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if Path(m.filename).suffix.lower() not in ALLOWED_EXTS:
            continue  # ignorar ejecutables, html, etc.
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(m) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def session_dir(base: Path, token: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        raise ValueError("Sesión WFDB no válida.")
    d = base / f"wfdb_{token}"
    if not d.is_dir():
        raise ValueError("La sesión expiró. Vuelve a cargar el archivo.")
    return d


def save_upload(base: Path, files) -> dict:
    """files: lista de werkzeug FileStorage. Devuelve {token, records}."""
    base.mkdir(exist_ok=True)
    _cleanup(base)
    token = uuid.uuid4().hex
    d = base / f"wfdb_{token}"
    d.mkdir()
    try:
        _save_files(d, files)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    records = list_records(d)
    if not records:
        shutil.rmtree(d, ignore_errors=True)
        raise ValueError("No se encontraron registros WFDB (archivos .hea) en lo cargado.")
    return {"token": token, "records": records}


def _save_files(d: Path, files):
    for f in files:
        name = Path(f.filename or "").name
        if not name:
            continue
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTS:
            continue
        path = d / name
        f.save(str(path))
        if ext == ".zip":
            with zipfile.ZipFile(path) as zf:
                _safe_extract(zf, d)
            path.unlink()


# ─── Registros ───────────────────────────────────────────────────────────────
def list_records(d: Path) -> list[dict]:
    out = []
    for hea in sorted(d.rglob("*.hea")):
        rel = hea.relative_to(d).with_suffix("")
        try:
            h = wfdb.rdheader(str(hea.with_suffix("")))
        except Exception:
            continue
        if getattr(h, "n_sig", 0) in (0, None) or getattr(h, "sig_len", 0) in (0, None):
            continue  # cabeceras multisegmento vacías o sin señal
        fs = float(h.fs)
        anns = [e for e in ANN_EXTS if hea.with_suffix("." + e).exists()]
        out.append({
            "id": rel.as_posix(),
            "name": rel.name,
            "folder": rel.parent.as_posix() if rel.parent.as_posix() != "." else "",
            "fs": int(fs) if fs == int(fs) else fs,
            "n_sig": int(h.n_sig),
            "sig_name": list(h.sig_name or [f"ch{i}" for i in range(h.n_sig)]),
            "duration_sec": round(h.sig_len / fs, 1),
            "annotations": anns,
            "comments": [c for c in (h.comments or [])][:4],
        })
    # ordenar por nombre natural (01, 02, … 100, 101)
    out.sort(key=lambda r: [int(t) if t.isdigit() else t
                            for t in re.split(r"(\d+)", r["id"])])
    return out


def _record_path(d: Path, rec_id: str) -> Path:
    p = (d / rec_id).resolve()
    if d.resolve() not in p.parents:
        raise ValueError("Registro no válido.")
    if not p.with_suffix(".hea").exists():
        raise ValueError(f"No existe el registro {rec_id}.")
    return p


def read_segment(d: Path, rec_id: str, channel: int = 0,
                 start_sec: float = 0.0, duration_sec: float | None = None):
    """Lee un tramo de un canal. Retorna (señal mV, fs, info)."""
    p = _record_path(d, rec_id)
    h = wfdb.rdheader(str(p))
    fs = float(h.fs)
    if not 0 <= channel < h.n_sig:
        raise ValueError(f"Canal {channel} no existe (el registro tiene {h.n_sig}).")
    sampfrom = max(0, int(round(start_sec * fs)))
    if sampfrom >= h.sig_len:
        raise ValueError("El inicio supera la duración del registro.")
    sampto = h.sig_len if not duration_sec else min(h.sig_len,
                                                   sampfrom + int(round(duration_sec * fs)))
    r = wfdb.rdrecord(str(p), sampfrom=sampfrom, sampto=sampto, channels=[channel])
    x = r.p_signal[:, 0].astype(float)
    if np.isnan(x).any():  # huecos de señal en algunos registros
        idx = np.arange(len(x))
        ok = ~np.isnan(x)
        if ok.sum() < 2:
            raise ValueError("El canal seleccionado no tiene datos válidos.")
        x = np.interp(idx, idx[ok], x[ok])
    info = {"record": rec_id, "channel": channel,
            "lead": (h.sig_name or [f"ch{channel}"])[channel],
            "sampfrom": sampfrom, "sampto": sampto,
            "start_sec": round(sampfrom / fs, 2),
            "duration_sec": round((sampto - sampfrom) / fs, 2)}
    fs_out = int(fs) if fs == int(fs) else fs
    return x, fs_out, info


def reference_annotations(d: Path, rec_id: str, sampfrom: int, sampto: int) -> dict | None:
    """Resumen de anotaciones de cardiólogos dentro del tramo analizado."""
    p = _record_path(d, rec_id)
    for ext in ANN_EXTS:
        if not p.with_suffix("." + ext).exists():
            continue
        try:
            ann = wfdb.rdann(str(p), ext, sampfrom=sampfrom, sampto=sampto)
        except Exception:
            continue
        beats, rhythms = {}, []
        for sym, aux in zip(ann.symbol, ann.aux_note or [""] * len(ann.symbol)):
            if sym in BEAT_SYMBOLS:
                beats[sym] = beats.get(sym, 0) + 1
            aux = (aux or "").strip().rstrip("\x00")
            if aux.startswith("("):
                desc = RHYTHM_DESC.get(aux, aux)
                if desc not in rhythms:
                    rhythms.append(desc)
        # ritmo vigente al inicio del tramo (anotado antes de sampfrom)
        if not rhythms and sampfrom > 0:
            try:
                prev = wfdb.rdann(str(p), ext, sampto=sampfrom)
                for aux in reversed(prev.aux_note or []):
                    aux = (aux or "").strip().rstrip("\x00")
                    if aux.startswith("("):
                        rhythms.append(RHYTHM_DESC.get(aux, aux) + " (vigente)")
                        break
            except Exception:
                pass
        if not beats and not rhythms:
            continue
        total = sum(beats.values())
        beat_list = [{"symbol": s, "desc": BEAT_DESC.get(s, s), "count": c,
                      "pct": round(100 * c / total, 1) if total else 0}
                     for s, c in sorted(beats.items(), key=lambda kv: -kv[1])]
        return {"source": f".{ext}", "n_beats": total,
                "beats": beat_list, "rhythms": rhythms}
    return None


def segment_to_csv(x: np.ndarray, fs, info: dict, path: Path):
    np.savetxt(str(path), x, fmt="%.6f",
               header=f"fs={fs:g} Hz | {info['record']} canal {info['channel']} "
                      f"({info['lead']}) | inicio {info['start_sec']} s",
               comments="# ")
