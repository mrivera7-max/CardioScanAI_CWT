# Validación en BUT PDB (conjunto de DESARROLLO)

BUT PDB: 50 registros de 2 min (PhysioNet). Referencia: patologías del README de la base.
Reproducir: `python validar_but_pdb.py <ruta>/but-pdb-1.0.0.zip --salida resultados_but_pdb`

| | v1 — reglas originales | v2 — reglas de patrón de ritmo + search-back |
|---|---|---|
| Detección: sensibilidad | 94.39 % | **96.19 %** |
| Detección: valor predictivo + | 99.08 % | 99.00 % |
| Diagnóstico: exactitud estricta (44 reg.) | 27.3 % | **70.5 %** |
| Diagnóstico: exactitud aceptable | 38.6 % | **75.0 %** |
| FA: sensibilidad / VPP | 10/10 · **32 %** | 8/10 · **73 %** |
| Extrasístoles: sensibilidad / VPP | 1/27 · 100 % | **20/27 · 83 %** |
| Bloqueo AV: sensibilidad / VPP | 0/4 | 2/4 · 100 % |

## Cambios v1 → v2
1. **Detector:** *search-back* de Pan-Tompkins (intervalos > 1.66 × RR típico se re-examinan con umbral 50 %).
2. **Reglas por patrón de ritmo** (`rhythm_pattern` en `ecg_pipeline.py`), no solo variabilidad:
   - **FA:** irregularidad de fondo (RMSSD normalizado tras excluir prematuros y pausas) > 0.12 **y** < 80 % de RR regulares.
   - **Extrasístoles:** ≥ 2 latidos prematuros (RR < 85 % de la mediana local) sobre ritmo de base regular.
   - **Bloqueo AV 2.º grado:** RR en dos grupos compactos (CV < 10 %) con razón 1.6–2.3 y grupo minoritario ≥ 15 %.
   - Ritmo tiene prioridad sobre frecuencia (taquicardia/bradicardia pasan a hallazgo secundario).

## Errores residuales v2 y su causa
| Registro | Referencia | CardioScan | Causa |
|---|---|---|---|
| 03 | BAV 3.er grado (marcapasos) | Normal | Bloqueo completo con ritmo regular: indistinguible por RR, requiere ondas P |
| 22 | BAV 1.er grado | Extrasístoles | El BAV 1.er grado solo alarga el PR: invisible para un análisis de RR |
| 44, 45 | FA | Extrasístoles | FA con respuesta ventricular poco variable (2 min, 128 Hz) |
| 38 | Flutter (+ NOD, A) | FA | Flutter con conducción variable: requiere ondas F |
| 11 | Taquiarritmia SV | Extrasístoles | FC 94 lpm en el tramo; la taquiarritmia es paroxística |
| 16, 21, 28 | Extrasístoles aisladas | Normal | Muy pocos prematuros en 2 min |
| 39 | Extrasístoles | Extrasístoles | Acierta, pero el detector pierde ~50 % de latidos (FC 53 vs 102) |

## Advertencia metodológica
Los umbrales de v2 se fijaron mirando estos 50 registros: **estas cifras son optimistas**.
El desempeño reportable debe medirse en bases independientes **sin modificar los umbrales**:
AFDB (FA) e INCART (extrasístoles). MIT-BIH Arrhythmia **no** es independiente (BUT PDB 01–38 proviene de ella).
Los bloqueos AV de 1.er y 3.er grado y el flutter no son detectables solo con intervalos RR: requieren
análisis de ondas P/F (línea futura, donde la CWT puede aportar).
