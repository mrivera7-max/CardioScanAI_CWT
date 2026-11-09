# CardioScan AI (CWT) — Estado del proyecto

**Autora:** Ing. María Fernanda Rivera Sanclemente — 2025, Ficha de Desafío.

Este repositorio es la línea de desarrollo activa. La versión STFT
([CardioScanAI_STFT](https://github.com/mrivera7-max/CardioScanAI_STFT), commit `f133ac8`)
queda **congelada como referencia** y no recibe estas correcciones.

## Historial
| Commit | Cambio |
|---|---|
| `3367eb3` | v2: `ecg_to_cwt()` reimplementada (Morlet compleja, sin `scipy.signal.cwt`) + pestañas Escalograma CWT y STFT vs CWT |
| `4e60697` | Pie de página y reporte: solo el año |
| `c809d06` | v2.1: correcciones metodológicas (fs, picos R tipo Pan-Tompkins, HRV sobre tacograma RR, regla de flutter, ventana STFT 0.5 s) |

| `4d5ea37` | v2.2: sección **Importar PhysioNet (WFDB)** — carga directa de .zip/.hea/.dat con referencia de cardiólogos |
| `13cb724` | v2.3: **Reporte PDF** con diagnóstico, métricas, referencia y las 7 gráficas con guía de lectura |
| `950d60d` | v2.4: **separación de pacientes** (Operador vs Paciente/ID, botón Nuevo paciente, borrado automático al cambiar de señal, reportes con ID y sin escritura en disco) |
| _(este)_ | **Validación BUT PDB** (`validar_but_pdb.py`, resultados en `docs/validacion_but_pdb/`): detección Se 94.4 % / +P 99.1 %; diagnóstico 27.3 % estricta / 38.6 % aceptable; FA Se 10/10 pero VPP 32 % |

Detalle técnico y resultados: ver `README.md`.

## Ejecución local
```powershell
cd "<carpeta del proyecto>"
python run.py          # → http://localhost:5050
```

## Pendientes
- [x] Validación BUT PDB (50 registros) — ver `docs/validacion_but_pdb/resumen.md`.
- [ ] Rediseñar reglas FA / Extrasístoles / Bloqueo AV (BUT PDB = desarrollo).
- [ ] Prueba independiente: AFDB (FA) + INCART (extrasístoles). MIT-BIH NO es independiente (BUT PDB 01–38 sale de mitdb).
- [ ] Correr `python validar_picos_physionet.py` y registrar Se / +P contra anotaciones de cardiólogos.
- [ ] Regla de Bloqueo AV: hoy equivale a bradicardia < 50 lpm (RR > 1200 ms regular). Reformular.
- [ ] Opción 3: features wavelet al clasificador + validación cruzada sobre bases PhysioNet completas.
- [ ] Detección de flutter por ondas F (hoy solo diferencial de taquicardia regular 140–160 lpm).
