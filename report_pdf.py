"""
Reporte PDF de CardioScan AI: diagnóstico, métricas, hallazgos, referencia
PhysioNet (si existe) y TODAS las gráficas con su guía de lectura.

Usa reportlab + la fuente DejaVu Sans que trae matplotlib (soporta ≥, ², ⚠, ω).
"""
import base64
import io
import os
from datetime import datetime
from xml.sax.saxutils import escape

import matplotlib

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (Image, KeepTogether, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)
except ImportError:
    import sys
    os.system(f"{sys.executable} -m pip install reportlab -q")
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (Image, KeepTogether, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

AUTHOR = "Ing. María Fernanda Rivera Sanclemente"
YEAR = "2025"

# ─── Fuentes ─────────────────────────────────────────────────────────────────
_FONT, _FONT_B = "Helvetica", "Helvetica-Bold"
try:
    _ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_ttf, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(_ttf, "DejaVuSans-Bold.ttf")))
    _FONT, _FONT_B = "DejaVu", "DejaVu-Bold"
except Exception:
    pass

# ─── Estilos ─────────────────────────────────────────────────────────────────
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#cbd5e1")
SOFT = colors.HexColor("#f1f5f9")
ACC = colors.HexColor("#0e7490")

S = {
    "title": ParagraphStyle("title", fontName=_FONT_B, fontSize=17, leading=21, textColor=INK),
    "sub": ParagraphStyle("sub", fontName=_FONT, fontSize=9, leading=12, textColor=MUTED),
    "h2": ParagraphStyle("h2", fontName=_FONT_B, fontSize=12, leading=15, textColor=ACC,
                         spaceBefore=10, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName=_FONT_B, fontSize=10.5, leading=13, textColor=INK,
                         spaceBefore=6, spaceAfter=3),
    "body": ParagraphStyle("body", fontName=_FONT, fontSize=9, leading=12.5, textColor=INK),
    "small": ParagraphStyle("small", fontName=_FONT, fontSize=8, leading=10.5, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName=_FONT, fontSize=8.5, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName=_FONT_B, fontSize=8.5, leading=11, textColor=INK),
    "diag": ParagraphStyle("diag", fontName=_FONT_B, fontSize=16, leading=20),
    "center": ParagraphStyle("center", fontName=_FONT, fontSize=8, leading=10,
                             textColor=MUTED, alignment=TA_CENTER),
}

RISK_COLORS = {"Bajo": "#16a34a", "Medio": "#d97706", "Alto": "#dc2626", "Crítico": "#b91c1c"}

# ─── Guía de lectura de cada gráfica ─────────────────────────────────────────
PLOTS = [
    ("ecg", "1. Señal ECG preprocesada con picos R",
     "Primeros 10 s de la señal tras filtrar (pasa-alto 0.5 Hz, pasa-bajo 40 Hz, notch 50/60 Hz) "
     "y normalizar (z-score). Los puntos rojos son los complejos QRS detectados (detector tipo "
     "Pan-Tompkins). Verifique que cada latido tenga su marca y que no haya marcas sobre ondas T "
     "o ruido: de esta detección dependen la FC y toda la HRV."),
    ("spectrogram", "2. Espectrograma STFT",
     "Transformada de Fourier de tiempo corto (ventana Hann de 0.5 s, solape 75 %). Eje x: tiempo; "
     "eje y: frecuencia 0–40 Hz; color: potencia en dB. Cada latido aparece como una franja vertical "
     "de energía 5–25 Hz (QRS). La resolución tiempo-frecuencia es fija para todas las frecuencias."),
    ("cwt", "3. Escalograma CWT (Morlet compleja, ω0 = 6)",
     "Transformada wavelet continua, 0.5–40 Hz en escala logarítmica. A alta frecuencia la ventana es "
     "corta y localiza cada QRS con precisión; a baja frecuencia la ventana es larga y resuelve mejor "
     "las ondas P/T y el ritmo. La zona rayada es el cono de influencia: allí los bordes de la señal "
     "distorsionan el resultado y no debe interpretarse."),
    ("compare", "4. Comparación STFT vs CWT",
     "Ambas representaciones sobre la misma ventana de tiempo. Permite ver la ventaja de la CWT: "
     "latidos más definidos a alta frecuencia sin perder resolución en baja frecuencia. "
     "La CWT es aquí una herramienta de visualización; no interviene en el diagnóstico."),
    ("rr", "5. Intervalos RR y diagrama de Poincaré",
     "Izquierda: duración de cada intervalo entre latidos; la banda sombreada es la media ± 1 DE. "
     "Derecha: cada RR frente al siguiente. Ritmo sinusal: nube compacta y alargada sobre la diagonal. "
     "Fibrilación auricular: nube dispersa sin patrón. Extrasístoles: puntos aislados fuera de la nube."),
    ("psd", "6. Análisis frecuencial: ECG y variabilidad cardíaca",
     "Izquierda: espectro de potencia del ECG (contenido de la onda). Derecha: espectro de la HRV "
     "calculado sobre el tacograma RR (interpolación a 4 Hz + Welch), con las bandas VLF "
     "(< 0.04 Hz), LF (0.04–0.15 Hz) y HF (0.15–0.4 Hz). LF/HF solo es fiable con registros ≥ 2 min "
     "(Task Force ESC/NASPE, 1996)."),
    ("scores", "7. Puntaje por diagnóstico",
     "Puntaje relativo de cada clase según las reglas clínicas del sistema, normalizado a 100 %. "
     "No es una probabilidad calibrada: indica qué hallazgos pesaron más en la decisión."),
]

METHOD = [
    "<b>Carga y frecuencia de muestreo:</b> CSV/TXT/WAV/NPY o registro WFDB de PhysioNet. "
    "La fs se toma de la cabecera del archivo, del nombre o la indica el usuario.",
    "<b>Preprocesamiento:</b> Butterworth pasa-alto 0.5 Hz y pasa-bajo 40 Hz (fase cero), "
    "notch 50/60 Hz, normalización z-score.",
    "<b>Detección QRS:</b> pasa-banda 5–15 Hz, derivada, cuadrado, integración de 150 ms, "
    "umbral adaptativo y periodo refractario de 250 ms (Pan & Tompkins, 1985).",
    "<b>HRV:</b> tiempo (SDNN, RMSSD, pNN50, CV) y frecuencia sobre el tacograma RR "
    "(Task Force ESC/NASPE, 1996).",
    "<b>Tiempo-frecuencia:</b> STFT (Hann 0.5 s) y CWT Morlet compleja (Torrence & Compo, 1998).",
    "<b>Clasificación:</b> reglas clínicas basadas en FC, regularidad RR y HRV, con puntaje por clase.",
]


# ─── Utilidades ──────────────────────────────────────────────────────────────
def _p(text, style="body"):
    return Paragraph(text, S[style])


def _e(x):
    return escape(str(x))


def _img(b64: str, width: float):
    """PNG → JPEG (calidad 88) para que el PDF pese poco sin perder nitidez."""
    raw = base64.b64decode(b64)
    try:
        from PIL import Image as PILImage
        im = PILImage.open(io.BytesIO(raw)).convert("RGB")
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=88, optimize=True, subsampling=0)
        raw = out.getvalue()
    except Exception:
        pass
    iw, ih = ImageReader(io.BytesIO(raw)).getSize()
    return Image(io.BytesIO(raw), width=width, height=width * ih / iw)


def _fmt(v, nd=1, unit=""):
    try:
        return f"{float(v):.{nd}f}{(' ' + unit) if unit else ''}"
    except (TypeError, ValueError):
        return "—"


def _table(rows, col_widths, header=True, zebra=True):
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    st = [("FONT", (0, 0), (-1, -1), _FONT, 8.5),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("FONT", (0, 0), (-1, 0), _FONT_B, 8.5)]
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                st.append(("BACKGROUND", (0, r), (-1, r), SOFT))
    t.setStyle(TableStyle(st))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    w, _h = doc.pagesize
    canvas.setStrokeColor(LINE)
    canvas.line(doc.leftMargin, 1.35 * cm, w - doc.rightMargin, 1.35 * cm)
    canvas.setFont(_FONT, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 0.9 * cm,
                      f"CardioScan AI · {AUTHOR} · {YEAR} · Apoyo diagnóstico, no reemplaza "
                      "al cardiólogo")
    canvas.drawRightString(w - doc.rightMargin, 0.9 * cm, f"Página {doc.page}")
    canvas.restoreState()


# ─── Reporte ─────────────────────────────────────────────────────────────────
def build_report(data: dict, plots: dict, operator: str = "") -> bytes:
    """data: resultado de analyze_ecg (dict). plots: base64 PNG por clave."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=1.7 * cm, rightMargin=1.7 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.8 * cm,
                            title="Reporte CardioScan AI", author=AUTHOR,
                            subject="Análisis electrocardiográfico")
    W = doc.width
    f = data.get("features", {}) or {}
    si = data.get("signal_info", {}) or {}
    el = []

    # ── Encabezado ──
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    el.append(_p("CardioScan AI — Reporte de análisis electrocardiográfico", "title"))
    el.append(_p("ECG · STFT + CWT · HRV · Clasificación por reglas clínicas", "sub"))
    el.append(Spacer(1, 8))

    meta = [
        ["Paciente / operador", _e(operator or "—"), "Fecha del reporte", now],
        ["Origen de la señal", _e(data.get("source") or "—"), "Duración analizada",
         _fmt(si.get("duration_sec"), 1, "s")],
        ["Frecuencia de muestreo", f"{_e(si.get('fs_hz', '—'))} Hz", "Fuente de la fs",
         _e(si.get("fs_source", "—"))],
        ["N.º de muestras", f"{si.get('n_samples', 0):,}".replace(",", "."), "ID del análisis",
         _e((data.get("analysis_id") or "—")[:12])],
    ]
    if data.get("wfdb"):
        w = data["wfdb"]
        meta.append(["Registro PhysioNet", _e(w.get("record")), "Canal / tramo",
                     f"{w.get('channel')} ({_e(w.get('lead'))}) · {w.get('start_sec')}–"
                     f"{round(w.get('start_sec', 0) + w.get('duration_sec', 0), 1)} s"])
    meta = [[_p(a, "cellb"), _p(b, "cell"), _p(c, "cellb"), _p(d, "cell")] for a, b, c, d in meta]
    el.append(_table(meta, [3.6 * cm, W / 2 - 3.6 * cm, 3.4 * cm, W / 2 - 3.4 * cm],
                     header=False))
    el.append(Spacer(1, 10))

    # ── Diagnóstico ──
    risk = data.get("risk", "—")
    rc = RISK_COLORS.get(risk, "#334155")
    dcol = data.get("color", "#0f172a")
    diag = Table([[
        Paragraph(f'<font color="{dcol}">{_e(data.get("diagnosis", "—"))}</font>', S["diag"]),
        _p(f'Confianza<br/><b>{_fmt(data.get("confidence"), 1, "%")}</b>', "body"),
        _p(f'Nivel de riesgo<br/><b><font color="{rc}">{_e(risk)}</font></b>', "body"),
    ]], colWidths=[W * 0.52, W * 0.24, W * 0.24])
    diag.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor(dcol)),
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    el.append(_p("Diagnóstico sugerido", "h2"))
    el.append(diag)

    # ── Hallazgos ──
    notes = data.get("notes") or []
    if notes:
        el.append(_p("Hallazgos clínicos", "h2"))
        for n in notes:
            el.append(_p(f"• {_e(n)}", "body"))
            el.append(Spacer(1, 2))

    # ── Métricas ──
    el.append(_p("Métricas", "h2"))
    lf_ok = f.get("hrv_lf_valid")
    lf_flag = "" if lf_ok else " *"
    left = [["Dominio del tiempo", "Valor"],
            ["Frecuencia cardíaca", _fmt(f.get("heart_rate"), 0, "lpm")],
            ["Picos R detectados", str(f.get("num_peaks", "—"))],
            ["RR medio", _fmt(f.get("rr_mean"), 0, "ms")],
            ["SDNN", _fmt(f.get("sdnn"), 1, "ms")],
            ["RMSSD", _fmt(f.get("rmssd"), 1, "ms")],
            ["pNN50", _fmt(f.get("pnn50"), 1, "%")],
            ["CV de RR", _fmt(f.get("rr_cv"), 3)]]
    right = [["Dominio de la frecuencia (HRV)", "Valor"],
             ["Potencia VLF", _fmt(f.get("vlf_power"), 1, "ms²")],
             ["Potencia LF", _fmt(f.get("lf_power"), 1, "ms²")],
             ["Potencia HF", _fmt(f.get("hf_power"), 1, "ms²")],
             [f"Razón LF/HF{lf_flag}", _fmt(f.get("lf_hf_ratio"), 2)],
             ["LF / HF (unid. normalizadas)",
              f'{_fmt(f.get("lf_nu"), 0)} / {_fmt(f.get("hf_nu"), 0)}'],
             ["Duración del tacograma", _fmt(f.get("hrv_duration_sec"), 0, "s")],
             ["Frec. dominante del ECG", _fmt(f.get("dominant_freq"), 2, "Hz")]]
    cw = W / 2 - 0.3 * cm
    t2 = Table([[_table(left, [cw * 0.62, cw * 0.38]), _table(right, [cw * 0.62, cw * 0.38])]],
               colWidths=[W / 2, W / 2])
    t2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    el.append(t2)
    if not lf_ok:
        el.append(Spacer(1, 3))
        el.append(_p("* Registro menor a 2 min: LF/HF se reporta como referencia y no se usa "
                     "para el diagnóstico.", "small"))

    # ── Puntajes ──
    scores = data.get("scores") or {}
    if scores:
        rows = [["Diagnóstico", "Puntaje"]] + [
            [_e(k), _fmt(v, 1, "%")] for k, v in sorted(scores.items(), key=lambda kv: -kv[1])]
        el.append(KeepTogether([_p("Puntaje por diagnóstico", "h2"),
                                _table(rows, [7 * cm, 3 * cm])]))

    # ── Referencia PhysioNet ──
    ref = data.get("reference")
    if data.get("wfdb"):
        blk = [_p("Referencia PhysioNet (anotaciones de cardiólogos)", "h2")]
        if ref:
            if ref.get("rhythms"):
                blk += [_p("<b>Ritmo anotado:</b> " + _e(", ".join(ref["rhythms"])), "body"),
                        Spacer(1, 4)]
            rows = [["Tipo de latido", "Cantidad", "%"]] + [
                [_e(f'{b["symbol"]} · {b["desc"]}'), str(b["count"]), _fmt(b["pct"], 1)]
                for b in ref.get("beats", [])]
            blk += [_table(rows, [9 * cm, 2.5 * cm, 2 * cm]), Spacer(1, 3),
                    _p(f'{ref.get("n_beats", 0)} latidos anotados (archivo {ref.get("source")}) · '
                       f'CardioScan detectó {f.get("num_peaks", "—")}.', "small")]
        else:
            blk.append(_p("El registro no trae anotaciones de referencia (.atr/.qrs).", "small"))
        el.append(KeepTogether(blk))

    # ── Gráficas ──
    first = True
    for key, title, guide in PLOTS:
        b64 = plots.get(key)
        if not b64:
            continue
        width = W * (0.72 if key == "scores" else 1.0)
        block = [_p(title, "h3"), _img(b64, width), Spacer(1, 3), _p(guide, "small"),
                 Spacer(1, 10)]
        if first:
            block = [_p("Gráficas y guía de lectura", "h2")] + block
            first = False
        el.append(KeepTogether(block))

    # ── Método y aviso ──
    blk = [_p("Método", "h2")]
    for m in METHOD:
        blk += [_p("• " + m, "body"), Spacer(1, 2)]
    el.append(KeepTogether(blk))
    el.append(Spacer(1, 8))
    el.append(KeepTogether([_p("Limitaciones y aviso", "h2"), _p(
        "Este reporte es generado automáticamente por un sistema de apoyo diagnóstico en fase de "
        "investigación. La clasificación se basa en reglas clínicas cuyos umbrales aún no han sido "
        "validados en una cohorte independiente. No constituye un diagnóstico médico y no reemplaza "
        "la interpretación de un electrocardiograma por un médico cardiólogo.", "body")]))
    el.append(Spacer(1, 14))
    el.append(_p(f"CardioScan AI · Diseñado y desarrollado por {AUTHOR} · {YEAR}", "center"))

    doc.build(el, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
