# v2.6 — Análisis de ondas P / F con CWT (en curso)

Objetivo: detectar lo que los intervalos RR no pueden ver — **bloqueo AV de 1.er grado** (PR largo),
**bloqueo AV de 2.º grado** (P no conducidas), **bloqueo AV completo** (disociación AV) y **flutter auricular 2:1**.

## Método (`ecg_pipeline.py`, sección 4e)
1. **Latido promedio** de los latidos normales; el QRS se borra por interpolación.
2. **Onda P:** CWT *Mexican hat* (σ = 25 ms) → la última onda prominente antes del QRS.
   **PR** = pico de P → inicio del QRS + 45 ms (inicio→pico típico de la P).
3. **P no conducidas:** búsqueda de la forma de la P del propio paciente (correlación ≥ 0.75) en la diástole;
   cuenta solo en pausas de 1.35–2.3 × RR que no siguen a un latido prematuro y sin energía de QRS a P+PR.
4. **Disociación AV:** sin P ligada al QRS + ondas auriculares regulares (CWT en el residuo ECG − QRST promedio)
   a una frecuencia > 1.3 × la ventricular.
5. **Flutter 2:1:** 120–175 lpm regular y dos ondas auriculares iguales (amplitud 0.67–1.5×, ancho por razón CWT
   σ15/σ45 0.5–2×) separadas RR/2 en ≥ 40 % de los ciclos.

## Validación
| Componente | Datos | Resultado |
|---|---|---|
| Localización de la onda P | BUT PDB `.pwave` (22 registros con P clara) | error mediano −1 ms, **MAE 7 ms**, 95 % < 40 ms |
| P no conducidas | BUT PDB registro 01 (BAV 2.º) | 30 detectadas vs 31 de referencia |
| BAV 1.er grado | BUT PDB registro 22 | PR estimado 220 ms → detectado |
| Diagnóstico global | BUT PDB (desarrollo, 44 reg.) | exactitud 70.5 % → **72.7 %**; Bloqueo AV 2/4 → **3/4** (el 4.º tiene marcapasos) |
| Flutter 2:1 | AFDB 04936 (desarrollo, 27 ventanas) | 14/27 detectadas |
| Flutter 2:1 | AFDB 08378, 07910, 04908, 06426 (prueba, 16 ventanas) | **0/16** (08378: sin ondas auriculares visibles en el canal 0; 07910: FC < 120) |
| Falsos positivos de flutter | INCART 69 ventanas de taquicardia; AFDB sin FA | 0 |
| BAV completo | sintéticos (aur 70–75, ven 30–38 lpm) | detectado; **sin casos reales para validar** |
| INCART (v2.6b) | 1 044 ventanas | extrasístoles Se 69.6 % / Esp 83.8 % (= v2.5); Bloqueo AV en 31 ventanas (7 en I09–I10, con Mobitz I real) |
| AFDB (v2.6b) | 23 registros | **pendiente** (se interrumpió la conexión) |

## Transparencia metodológica
- La primera versión (v2.6a) dio **146 ventanas de "Bloqueo AV" en INCART**: tras una extrasístole la P sinusal
  siguiente no se conduce (conducción oculta) y los QRS perdidos por el detector parecían P bloqueadas.
  Se corrigió con criterios fisiológicos (pausa tras latido no prematuro, pausa ≤ 2.3×, sin QRS a P+PR, 2:1 fijo solo
  con FC < 60 y P en el punto medio). **Como la corrección se motivó en INCART, la especificidad del bloqueo AV en
  INCART ya no es una prueba ciega.**
- El flutter funciona en el registro de desarrollo pero **no generaliza** a los registros de prueba: no se reporta como
  resuelto. El análisis multiderivación (las ondas F se ven mejor en II, III, aVF) es la mejora natural.
