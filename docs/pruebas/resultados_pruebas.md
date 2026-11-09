# Resultados de pruebas — CardioScan AI CWT

**21/21 superadas**

| ID | Área | Prueba | Resultado | Detalle |
|---|---|---|---|---|
| P01 | CWT | Tonos puros 2, 5, 10 y 20 Hz: pico del escalograma en la frecuencia correcta (error < 5 %) | ✓ | error máx. 2.8 % |
| P02 | CWT | Multirresolución: dos impulsos separados 100 ms se separan a 30 Hz y se funden a 2 Hz | ✓ | 30 Hz: 2 máximos; 2 Hz: 1 máximo |
| P10 | Reglas | Demo sintética 'normal' → Normal, FC 72 lpm ± 5 % | ✓ | Normal (95 %), FC 72 lpm |
| P11 | Reglas | Demo sintética 'tachy' → Taquicardia, FC 130 lpm ± 5 % | ✓ | Taquicardia (80 %), FC 130 lpm |
| P12 | Reglas | Demo sintética 'brady' → Bradicardia, FC 42 lpm ± 5 % | ✓ | Bradicardia (80 %), FC 42 lpm |
| P13 | Reglas | Demo sintética 'afib' → Fibrilación Auricular | ✓ | Fibrilación Auricular (83 %), FC 93 lpm |
| P14 | Reglas | Demo sintética 'block' → Bloqueo AV | ✓ | Bloqueo AV (95 %), FC 62 lpm |
| P15 | Detector | Independencia de fs: la misma señal a 250, 360 y 500 Hz da el mismo diagnóstico y FC ± 2 lpm | ✓ | 250 Hz: Normal, 72 lpm; 360 Hz: Normal, 72 lpm; 500 Hz: Normal, 72 lpm |
| P20 | API | GET / sirve la interfaz (200, HTML) | ✓ | HTTP 200 |
| P21 | API | Demo vía API devuelve JSON estricto (sin NaN) con diagnóstico y 7 gráficas | ✓ | Bloqueo AV, 7 gráficas |
| P22 | API | Condición demo inválida → HTTP 400 | ✓ | HTTP 400 |
| P23 | API | Carga de CSV con fs del usuario (/api/analyze) | ✓ | fs=250 Hz (indicada por el usuario), Normal |
| P24 | API | Formato no soportado (.exe) → HTTP 400 | ✓ | HTTP 400 |
| P25 | Reporte | PDF sin Paciente/ID → rechazado (HTTP 400) | ✓ | HTTP 400 |
| P26 | Reporte | PDF con paciente: application/pdf, ≥ 5 páginas, generado en memoria | ✓ | 5 páginas, 1439 kB |
| P27 | Privacidad | Nuevo paciente: /api/forget borra el análisis de la memoria del servidor | ✓ | antes: True, después: False |
| P28 | Seguridad | Zip con ruta maliciosa (../) no escribe fuera de la carpeta de sesión | ✓ | HTTP 400; archivo fuera de sesión: False |
| P30 | Registros reales | BUT PDB 01 (README: Bloqueo AV) vía /api/wfdb/analyze, JSON estricto | ✓ | Bloqueo AV (81.6 %) |
| P31 | Registros reales | BUT PDB 05 (README: Extrasístoles) vía /api/wfdb/analyze, JSON estricto | ✓ | Extrasístoles (81.0 %) |
| P32 | Registros reales | BUT PDB 07 (README: Fibrilación Auricular) vía /api/wfdb/analyze, JSON estricto | ✓ | Fibrilación Auricular (80.8 %) |
| P33 | Registros reales | BUT PDB 22 (README: Bloqueo AV) vía /api/wfdb/analyze, JSON estricto | ✓ | Bloqueo AV (60.0 %) |