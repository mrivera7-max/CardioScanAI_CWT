# 🫀 CardioScan AI (versión CWT) — Clasificación de Enfermedades Cardiovasculares

> Versión derivada de [CardioScanAI_STFT](https://github.com/mrivera7-max/CardioScanAI_STFT) (commit `f133ac8`).
> Añade la **Transformada Wavelet Continua (CWT, Morlet compleja)** como análisis visual complementario.

Sistema de análisis de electrocardiogramas (ECG) mediante procesamiento de
espectrogramas y Machine Learning para detección de anomalías cardíacas.

---

## Arquitectura del sistema

```
Archivo ECG (.csv/.wav/.npy)
        │
        ▼
┌─────────────────────┐
│  1. Carga de señal  │  Soporta: CSV, TXT, WAV, NPY, DAT
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  2. Preprocesamiento│  Filtro paso-alto 0.5 Hz (baseline wander)
│                     │  Filtro paso-bajo 40 Hz (ruido HF)
│                     │  Filtro notch 50/60 Hz (red eléctrica)
│                     │  Normalización Z-score
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  3. Espectrograma   │  STFT (Short-Time Fourier Transform)
│     STFT            │  nperseg=256, overlap=75%
│                     │  Potencia en dB (10·log10)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  4. Extracción de   │  Temporales: amplitud, skewness, kurtosis
│     características │  HRV: SDNN, RMSSD, pNN50, Poincaré
│                     │  Espectrales: VLF/LF/HF bands, LF/HF ratio
│                     │  Detección de picos R
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  5. Clasificación   │  Reglas clínicas basadas en umbrales HRV
│     ML Híbrida      │  + scoring probabilístico multi-clase
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  6. Visualización   │  Señal ECG con picos R marcados
│                     │  Espectrograma (plasma colormap)
│                     │  Diagrama de Poincaré
│                     │  PSD con bandas VLF/LF/HF
│                     │  Barras de probabilidad por diagnóstico
└─────────────────────┘
```

---

## Diagnósticos detectados

| Diagnóstico              | Nivel de riesgo | Criterios principales          |
|--------------------------|-----------------|--------------------------------|
| Normal                   | Bajo            | 60–100 lpm, RR regular         |
| Taquicardia              | Medio           | FC > 100 lpm                   |
| Bradicardia              | Medio           | FC < 60 lpm                    |
| Fibrilación Auricular    | Alto            | CV_RR > 15%, RMSSD > 50 ms     |
| Bloqueo AV               | Alto            | RR medio > 1200 ms, regular    |
| Extrasístoles            | Medio           | CV_RR moderado, pNN50 bajo     |
| Isquemia Miocárdica      | Crítico         | Dominio LF, ratio LF/HF > 4   |
| Flutter Auricular        | Medio           | FC 250–350 lpm, RR regular     |

---

## Instalación y uso

### Requisitos

- Python 3.9+
- numpy, scipy, matplotlib, scikit-learn, flask, pillow

### Inicio rápido

```bash
# Instalar dependencias (automático al ejecutar)
python run.py

# Abrir en el navegador:
# http://localhost:5050
```

### Opciones de línea de comandos

```bash
python run.py                   # Servidor en puerto 5050
python run.py --port 8080       # Puerto personalizado
python run.py --demo            # Solo test del pipeline (sin servidor)
python run.py --debug           # Modo debug de Flask
```

---

## Formatos de archivo ECG aceptados

### CSV / TXT
Una columna de valores numéricos, una muestra por línea:
```
-0.0032
0.1245
0.8901
...
```
O con cabecera:
```
mV
-0.0032
0.1245
```

### WAV
Audio mono o estéreo (se usa canal 0). La frecuencia de muestreo se lee del archivo.

### NPY (NumPy)
Array 1D o 2D. Si es 2D, se usa la primera columna.

### DAT / TXT (formato PhysioBank)
Columnas de texto separadas por espacios; se usa la primera columna numérica.

---

## API REST

| Endpoint             | Método | Descripción                        |
|----------------------|--------|------------------------------------|
| `/`                  | GET    | Interfaz web principal             |
| `/api/analyze`       | POST   | Analizar archivo (multipart/form)  |
| `/api/demo/<cond>`   | GET    | Demo: normal/tachy/brady/afib/block|
| `/api/export_report` | POST   | Exportar reporte en texto          |

### Ejemplo con curl

```bash
curl -X POST http://localhost:5050/api/analyze \
     -F "file=@mi_ecg.csv" \
     | python3 -m json.tool
```

### Respuesta JSON

```json
{
  "status": "ok",
  "diagnosis": "Fibrilación Auricular",
  "confidence": 82.1,
  "risk": "Alto",
  "icon": "⚠",
  "color": "#ef4444",
  "notes": ["Alta variabilidad RR: CV=0.183, RMSSD=61.2 ms"],
  "features": {
    "heart_rate": 89.3,
    "sdnn": 87.2,
    "rmssd": 61.2,
    "pnn50": 28.4,
    "lf_hf_ratio": 1.87,
    "dominant_freq": 1.48
  },
  "scores": {
    "Normal": 5.2,
    "Fibrilación Auricular": 57.3,
    "Taquicardia": 12.1
  },
  "signal_info": {
    "duration_sec": 12.0,
    "fs_hz": 500,
    "n_samples": 6000
  },
  "plots": {
    "ecg": "<base64_png>",
    "spectrogram": "<base64_png>",
    "rr": "<base64_png>",
    "psd": "<base64_png>",
    "scores": "<base64_png>"
  }
}
```

---

## Estructura de archivos

```
cardioscan/
├── run.py           ← Punto de entrada principal
├── app.py           ← Servidor Flask (API REST)
├── ecg_pipeline.py  ← Pipeline completo de análisis
├── templates/
│   └── index.html   ← Interfaz web (HTML/CSS/JS)
└── README.md
```

---

## Notas importantes

> **Este sistema es de apoyo diagnóstico y no reemplaza la evaluación
> de un médico cardiólogo certificado.**

Los umbrales de clasificación están basados en criterios clínicos estándar
de la literatura de HRV y electrocardiografía, pero la precisión depende
de la calidad y duración de la señal ECG proporcionada.

**Señal mínima recomendada:** 10 segundos a 250+ Hz de muestreo.


---

## Novedad de esta versión: CWT (Wavelet continua)

**Qué se hizo**
- `ecg_to_cwt()` reimplementada desde cero (la versión anterior usaba `scipy.signal.cwt`, eliminada en scipy ≥ 1.15).
- Wavelet **Morlet compleja analítica** (ω0 = 6), 80 frecuencias logarítmicas entre 0.5 y 40 Hz.
- Convolución en el dominio de la frecuencia (teorema de convolución), normalización de Torrence & Compo (1998) y corrección de sesgo por escala de Liu et al. (2007).
- **Cono de influencia (COI)** sombreado: la zona rayada está afectada por los bordes y no debe interpretarse.
- Dos pestañas nuevas en la interfaz: **🌊 Escalograma CWT** y **⚖️ STFT vs CWT** (ejes de tiempo alineados).

**Qué NO cambia (decisión metodológica)**
La CWT es **solo visualización** (opción 1). No alimenta al clasificador: los diagnósticos son idénticos a la versión STFT
(verificado con los 4 registros PhysioNet incluidos). Usar features wavelet en la clasificación (opción 3) exige
validación cruzada sobre PhysioNet antes de afirmar cualquier mejora.

**Verificación**
| Prueba | Resultado |
|---|---|
| Tonos puros 1 / 5 / 17 / 30 Hz | pico CWT en 1.03 / 5.14 / 17.41 / 30.31 Hz (error ≤ 2.5 %, resolución de la malla log) |
| Señal 5 Hz → 25 Hz en t = 5 s | energía localizada correctamente en cada mitad |
| Tiempo de cómputo (10 s @ 500 Hz) | ≈ 30 ms |
| Diagnóstico vs. versión STFT | idéntico en los 4 CSV de PhysioNet |

**Por qué CWT además de STFT:** la STFT usa una ventana fija (misma resolución en todas las frecuencias). La CWT adapta
la ventana a la escala: ventanas cortas a alta frecuencia (localiza el complejo QRS) y largas a baja frecuencia
(mejor resolución en ondas P/T y ritmo).
