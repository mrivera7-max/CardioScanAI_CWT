"""
Servidor web Flask para interfaz de análisis ECG.
"""

import os, sys, json, tempfile, base64
from pathlib import Path

# ── Instalar Flask si no está disponible ──────────────────────────────────────
try:
    from flask import Flask, request, jsonify, send_file
except ImportError:
    os.system(f"{sys.executable} -m pip install flask --break-system-packages -q")
    from flask import Flask, request, jsonify, send_file

from ecg_pipeline import analyze_ecg, generate_demo_ecg, render_plots_for_report
import numpy as np
import wfdb_import
import report_pdf

def _get_base_dir():
    """Funciona tanto en ejecución normal como empaquetada con PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

BASE_DIR = _get_base_dir()

app = Flask(__name__,
            static_folder=str(BASE_DIR / "static"),
            template_folder=str(BASE_DIR / "templates"))
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB (zip de bases PhysioNet)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "ecg_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED = {".csv", ".txt", ".wav", ".npy", ".dat"}


@app.route("/")
def index():
    return send_file(str(BASE_DIR / "templates" / "index.html"))


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No se recibió archivo."}), 400

    f = request.files["file"]
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED:
        return jsonify({"status": "error",
                        "message": f"Formato no soportado: {ext}. Use .csv, .txt, .wav, .npy"}), 400

    tmp = UPLOAD_DIR / f"ecg_{os.getpid()}_{f.filename}"
    try:
        f.save(str(tmp))
        fs_user = None
        fs_txt = (request.form.get("fs") or "").strip().replace(",", ".")
        if fs_txt:
            try:
                fs_user = float(fs_txt)
            except ValueError:
                return jsonify({"status": "error",
                                "message": f"fs no válida: '{fs_txt}'"}), 400
        result = analyze_ecg(str(tmp), fs=fs_user, original_name=f.filename)
        result["source"] = f"Archivo: {f.filename}"
        return jsonify(result)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


@app.route("/api/demo/<condition>")
def api_demo(condition: str):
    allowed = {"normal", "tachy", "brady", "afib", "block"}
    if condition not in allowed:
        return jsonify({"status": "error", "message": "Condición no válida."}), 400

    ecg = generate_demo_ecg(condition, fs=500, duration=12.0)
    tmp = UPLOAD_DIR / f"demo_{condition}_{os.getpid()}.csv"
    try:
        np.savetxt(str(tmp), ecg, fmt="%.6f")
        result = analyze_ecg(str(tmp), fs=500)
        result["demo_condition"] = condition
        result["source"] = f"Señal sintética de demostración ({condition})"
        return jsonify(result)
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


# ─── Importación directa de PhysioNet (WFDB) ─────────────────────────────────
def _wfdb_params():
    d = request.get_json(silent=True) or request.values
    token = d.get("token", "")
    rec = d.get("record", "")
    try:
        ch = int(d.get("channel", 0) or 0)
        start = float(d.get("start", 0) or 0)
        dur = d.get("duration", "")
        dur = float(dur) if str(dur).strip() not in ("", "0") else None
    except ValueError:
        raise ValueError("Canal, inicio o duración no válidos.")
    return wfdb_import.session_dir(UPLOAD_DIR, token), rec, ch, start, dur


@app.route("/api/wfdb/upload", methods=["POST"])
def api_wfdb_upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"status": "error", "message": "No se recibieron archivos."}), 400
    try:
        out = wfdb_import.save_upload(UPLOAD_DIR, files)
        return jsonify({"status": "ok", **out})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/wfdb/analyze", methods=["POST"])
def api_wfdb_analyze():
    try:
        d, rec, ch, start, dur = _wfdb_params()
        x, fs, info = wfdb_import.read_segment(d, rec, ch, start, dur)
        tmp = d / f"_seg_{os.getpid()}.csv"
        wfdb_import.segment_to_csv(x, fs, info, tmp)
        try:
            result = analyze_ecg(str(tmp), fs=fs)
        finally:
            tmp.unlink(missing_ok=True)
        if result.get("status") == "ok":
            result["signal_info"]["fs_source"] = f"cabecera WFDB ({rec})"
            result["wfdb"] = info
            result["source"] = f"PhysioNet WFDB: {rec}"
            result["reference"] = wfdb_import.reference_annotations(
                d, rec, info["sampfrom"], info["sampto"])
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/wfdb/csv")
def api_wfdb_csv():
    try:
        d, rec, ch, start, dur = _wfdb_params()
        x, fs, info = wfdb_import.read_segment(d, rec, ch, start, dur)
        name = f"{Path(rec).as_posix().replace('/', '_')}_canal{ch}.csv"
        out = d / name
        wfdb_import.segment_to_csv(x, fs, info, out)
        return send_file(str(out), as_attachment=True, download_name=name,
                         mimetype="text/csv")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.errorhandler(413)
def too_large(_e):
    return jsonify({"status": "error",
                    "message": "Archivo demasiado grande (máx. 500 MB)."}), 413


@app.route("/api/export_report", methods=["POST"])
def export_report():
    """Genera un reporte PDF simple en texto."""
    from datetime import datetime
    data = request.json or {}
    operator = (data.get("operator_name") or "").strip()

    lines = [
        "=" * 60,
        "  REPORTE DE ANÁLISIS ELECTROCARDIOGRÁFICO",
        "  Sistema de Detección de Anomalías Cardíacas",
        "=" * 60,
    ]
    if operator:
        lines.append(f"  Operador / Paciente: {operator}")
    lines.append(f"  Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines += [
        "=" * 60,
        f"  Diagnóstico:   {data.get('diagnosis','N/A')}",
        f"  Confianza:     {data.get('confidence','N/A')}%",
        f"  Nivel de riesgo: {data.get('risk','N/A')}",
        "",
        "  Hallazgos clínicos:",
    ]
    for note in data.get("notes", []):
        lines.append(f"    • {note}")
    lines += [
        "",
        "  Métricas cardíacas:",
        f"    Frecuencia cardíaca : {data.get('features',{}).get('heart_rate',0):.0f} lpm",
        f"    SDNN                : {data.get('features',{}).get('sdnn',0):.1f} ms",
        f"    RMSSD               : {data.get('features',{}).get('rmssd',0):.1f} ms",
        f"    pNN50               : {data.get('features',{}).get('pnn50',0):.1f} %",
        f"    Razón LF/HF         : {data.get('features',{}).get('lf_hf_ratio',0):.2f}",
        "",
        "  NOTA: Este análisis es de apoyo diagnóstico.",
        "  No reemplaza la evaluación de un cardiólogo.",
        "=" * 60,
        "  CardioScan AI",
        "  Diseñado y desarrollado por:",
        "  Ing. María Fernanda Rivera Sanclemente",
        "  2025",
        "=" * 60,
    ]
    text = "\n".join(lines)
    tmp_report = UPLOAD_DIR / "reporte_ecg.txt"
    tmp_report.write_text(text, encoding="utf-8")
    return send_file(str(tmp_report), as_attachment=True,
                     download_name="reporte_ecg.txt", mimetype="text/plain")


@app.route("/api/export_pdf", methods=["POST"])
def export_pdf():
    """Reporte PDF con diagnóstico, métricas, referencia y todas las gráficas."""
    from datetime import datetime
    data = request.get_json(silent=True) or {}
    if data.get("status") != "ok":
        return jsonify({"status": "error", "message": "No hay un análisis para reportar."}), 400
    operator = (data.get("operator_name") or "").strip()
    # Gráficas en tema claro (imprimible) si el análisis sigue en memoria;
    # si no (p. ej. tras reiniciar el servidor), se usan las de la interfaz.
    plots = render_plots_for_report(data.get("analysis_id")) or data.get("plots") or {}
    try:
        pdf = report_pdf.build_report(data, plots, operator)
    except Exception as e:
        return jsonify({"status": "error", "message": f"No se pudo generar el PDF: {e}"}), 500
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe = "".join(c for c in (data.get("diagnosis") or "ECG") if c.isalnum()) or "ECG"
    out = UPLOAD_DIR / f"reporte_cardioscan_{stamp}.pdf"
    out.write_bytes(pdf)
    return send_file(str(out), as_attachment=True,
                     download_name=f"CardioScan_{safe}_{stamp}.pdf",
                     mimetype="application/pdf")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"\n🫀  Servidor ECG iniciado → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
