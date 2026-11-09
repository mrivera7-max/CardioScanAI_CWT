#!/usr/bin/env python3
"""
Batería de pruebas funcionales y de verificación de CardioScan AI (versión CWT).

Uso (desde la carpeta del proyecto):
    python pruebas/test_cardioscan.py                 # pruebas sin datos externos
    python pruebas/test_cardioscan.py <carpeta_BUT_PDB>  # + registros reales 01, 05, 07, 22

Salida: tabla en consola y docs/pruebas/resultados_pruebas.{md,json}
"""
import io, json, sys, time, zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ecg_pipeline as P          # noqa: E402
import app as appmod              # noqa: E402

RESULTS = []


def case(cid, area, desc):
    def deco(fn):
        def run():
            t0 = time.time()
            try:
                ok, detail = fn()
            except Exception as e:                      # la prueba falla, no el runner
                ok, detail = False, f"excepción: {e}"
            RESULTS.append(dict(id=cid, area=area, prueba=desc, ok=bool(ok),
                                detalle=detail, seg=round(time.time() - t0, 2)))
        run.__name__ = fn.__name__
        return run
    return deco


def strict_json(text):
    """json.loads que rechaza NaN/Infinity (como JSON.parse del navegador)."""
    def bad(c):
        raise ValueError(f"constante no JSON: {c}")
    return json.loads(text, parse_constant=bad)


# ── 1. CWT ─────────────────────────────────────────────────────────────────
@case("P01", "CWT", "Tonos puros 2, 5, 10 y 20 Hz: pico del escalograma en la frecuencia correcta (error < 5 %)")
def t_cwt_tones():
    fs, errs = 250, []
    t = np.arange(0, 10, 1 / fs)
    for f0 in (2, 5, 10, 20):
        fr, _, pw, coi = P.ecg_to_cwt(np.sin(2 * np.pi * f0 * t), fs)
        mid = pw[:, len(t) // 2]
        errs.append(abs(fr[np.argmax(mid)] - f0) / f0 * 100)
    return max(errs) < 5, "error máx. " + f"{max(errs):.1f} %"


@case("P02", "CWT", "Multirresolución: dos impulsos separados 100 ms se separan a 30 Hz y se funden a 2 Hz")
def t_cwt_time():
    from scipy.signal import find_peaks
    fs = 500
    x = np.zeros(10 * fs); x[2500] = 1; x[2550] = 1
    fr, _, pw, _ = P.ecg_to_cwt(x, fs)
    def npk(f):
        row = pw[np.argmin(abs(fr - f))][2300:2750]
        return len(find_peaks(row, prominence=0.05 * row.max())[0])
    a, b = npk(30), npk(2)
    return a >= 2 and b == 1, f"30 Hz: {a} máximos; 2 Hz: {b} máximo"


# ── 2. Detector y reglas con señales sintéticas ────────────────────────────
EXP = {"normal": ("Normal", 72), "tachy": ("Taquicardia", 130), "brady": ("Bradicardia", 42),
       "afib": ("Fibrilación Auricular", None), "block": ("Bloqueo AV", None)}

for k, (dx_exp, hr_exp) in EXP.items():
    def mk(k=k, dx_exp=dx_exp, hr_exp=hr_exp):
        @case(f"P1{list(EXP).index(k)}", "Reglas", f"Demo sintética '{k}' → {dx_exp}"
              + (f", FC {hr_exp} lpm ± 5 %" if hr_exp else ""))
        def t():
            x = P.generate_demo_ecg(k, fs=500, duration=30.0)
            dx, conf, feat, _ = P.classify_signal(x, 500)
            ok = dx == dx_exp
            hr = feat.get("heart_rate", 0)
            if hr_exp:
                ok = ok and abs(hr - hr_exp) / hr_exp < 0.05
            return ok, f"{dx} ({conf * 100:.0f} %), FC {hr:.0f} lpm"
        return t
    globals()[f"t_demo_{k}"] = mk()


@case("P15", "Detector", "Independencia de fs: la misma señal a 250, 360 y 500 Hz da el mismo diagnóstico y FC ± 2 lpm")
def t_fs():
    from scipy.signal import resample
    x = P.generate_demo_ecg("normal", fs=500, duration=30.0)
    out = []
    for fs in (250, 360, 500):
        y = resample(x, int(len(x) * fs / 500))
        dx, _, feat, _ = P.classify_signal(y, fs)
        out.append((fs, dx, feat["heart_rate"]))
    ok = len({o[1] for o in out}) == 1 and max(o[2] for o in out) - min(o[2] for o in out) <= 2
    return ok, "; ".join(f"{fs} Hz: {dx}, {hr:.0f} lpm" for fs, dx, hr in out)


# ── 3. API (cliente de pruebas Flask, sin servidor) ────────────────────────
client = appmod.app.test_client()


@case("P20", "API", "GET / sirve la interfaz (200, HTML)")
def t_home():
    r = client.get("/")
    return r.status_code == 200 and b"<html" in r.data[:500].lower(), f"HTTP {r.status_code}"


@case("P21", "API", "Demo vía API devuelve JSON estricto (sin NaN) con diagnóstico y 7 gráficas")
def t_api_demo():
    r = client.get("/api/demo/block")
    d = strict_json(r.get_data(as_text=True))
    n = len(d.get("plots", {}))
    return r.status_code == 200 and d["status"] == "ok" and n >= 7, f"{d['diagnosis']}, {n} gráficas"


@case("P22", "API", "Condición demo inválida → HTTP 400")
def t_api_bad():
    r = client.get("/api/demo/xyz")
    return r.status_code == 400, f"HTTP {r.status_code}"


@case("P23", "API", "Carga de CSV con fs del usuario (/api/analyze)")
def t_api_csv():
    x = P.generate_demo_ecg("normal", fs=250, duration=20.0)
    buf = io.BytesIO("\n".join(f"{v:.5f}" for v in x).encode())
    r = client.post("/api/analyze", data={"file": (buf, "senal.csv"), "fs": "250"},
                    content_type="multipart/form-data")
    d = strict_json(r.get_data(as_text=True))
    si = d["signal_info"]
    return d["status"] == "ok" and si["fs_hz"] == 250, f"fs={si['fs_hz']} Hz ({si['fs_source']}), {d['diagnosis']}"


@case("P24", "API", "Formato no soportado (.exe) → HTTP 400")
def t_api_ext():
    r = client.post("/api/analyze", data={"file": (io.BytesIO(b"MZ"), "x.exe")},
                    content_type="multipart/form-data")
    return r.status_code == 400, f"HTTP {r.status_code}"


@case("P25", "Reporte", "PDF sin Paciente/ID → rechazado (HTTP 400)")
def t_pdf_nopat():
    d = strict_json(client.get("/api/demo/normal").get_data(as_text=True))
    d["patient_id"] = ""
    r = client.post("/api/export_pdf", json=d)
    return r.status_code == 400, f"HTTP {r.status_code}"


@case("P26", "Reporte", "PDF con paciente: application/pdf, ≥ 5 páginas, generado en memoria")
def t_pdf_ok():
    d = strict_json(client.get("/api/demo/afib").get_data(as_text=True))
    d.update(patient_id="PRUEBA-01", operator_name="Pruebas")
    r = client.post("/api/export_pdf", json=d)
    from pypdf import PdfReader
    n = len(PdfReader(io.BytesIO(r.data)).pages) if r.data[:4] == b"%PDF" else 0
    return r.status_code == 200 and r.mimetype == "application/pdf" and n >= 5, f"{n} páginas, {len(r.data) // 1024} kB"


@case("P27", "Privacidad", "Nuevo paciente: /api/forget borra el análisis de la memoria del servidor")
def t_forget():
    d = strict_json(client.get("/api/demo/normal").get_data(as_text=True))
    aid = d["analysis_id"]
    before = P.render_plots_for_report(aid) is not None
    client.post("/api/forget", json={"analysis_id": aid})
    after = P.render_plots_for_report(aid) is not None
    return before and not after, f"antes: {before}, después: {after}"


@case("P28", "Seguridad", "Zip con ruta maliciosa (../) no escribe fuera de la carpeta de sesión")
def t_zipslip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../fuera_cardioscan.txt", "x")
        z.writestr("ok/100.hea", "100 1 360 3600\n100.dat 212 200 11 1024 0 0 0 MLII\n")
    buf.seek(0)
    r = client.post("/api/wfdb/upload", data={"files": (buf, "malicioso.zip")},
                    content_type="multipart/form-data")
    escaped = any(p.exists() for p in [appmod.UPLOAD_DIR.parent / "fuera_cardioscan.txt",
                                       appmod.UPLOAD_DIR.parent.parent / "fuera_cardioscan.txt"])
    return not escaped, f"HTTP {r.status_code}; archivo fuera de sesión: {escaped}"


# ── 4. Registros reales (opcional) ─────────────────────────────────────────
REAL = {"01": "Bloqueo AV", "05": "Extrasístoles", "07": "Fibrilación Auricular", "22": "Bloqueo AV"}


def real_cases(folder):
    import wfdb
    for rec, exp in REAL.items():
        @case(f"P3{list(REAL).index(rec)}", "Registros reales",
              f"BUT PDB {rec} (README: {exp}) vía /api/wfdb/analyze, JSON estricto")
        def t(rec=rec, exp=exp):
            files = [(open(Path(folder) / f"{rec}{e}", "rb"), f"{rec}{e}") for e in (".hea", ".dat", ".qrs")
                     if (Path(folder) / f"{rec}{e}").exists()]
            r = client.post("/api/wfdb/upload", data={"files": files}, content_type="multipart/form-data")
            tok = r.get_json()["token"]
            r = client.post("/api/wfdb/analyze", json={"token": tok, "record": rec, "channel": 0})
            d = strict_json(r.get_data(as_text=True))
            return d["diagnosis"] == exp, f"{d['diagnosis']} ({d['confidence']} %)"
        t()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("t_") and callable(fn):
            fn()
    if len(sys.argv) > 1:
        real_cases(sys.argv[1])
    RESULTS.sort(key=lambda r: r["id"])
    ok = sum(r["ok"] for r in RESULTS)
    print(f"\n{'ID':4} {'Área':16} {'OK':3} Detalle")
    for r in RESULTS:
        print(f"{r['id']:4} {r['area']:16} {'✓' if r['ok'] else '✗':3} {r['prueba']}\n{'':25}→ {r['detalle']}")
    print(f"\n{ok}/{len(RESULTS)} pruebas superadas")
    out = ROOT / "docs" / "pruebas"; out.mkdir(parents=True, exist_ok=True)
    (out / "resultados_pruebas.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Resultados de pruebas — CardioScan AI CWT", "", f"**{ok}/{len(RESULTS)} superadas**", "",
          "| ID | Área | Prueba | Resultado | Detalle |", "|---|---|---|---|---|"]
    md += [f"| {r['id']} | {r['area']} | {r['prueba']} | {'✓' if r['ok'] else '✗'} | {r['detalle']} |" for r in RESULTS]
    (out / "resultados_pruebas.md").write_text("\n".join(md), encoding="utf-8")
    sys.exit(0 if ok == len(RESULTS) else 1)
