# Prueba independiente — CardioScan AI v2.5

Bases **no usadas** para ajustar las reglas (los umbrales se fijaron en BUT PDB y no se modificaron).
Protocolo definido antes de ejecutar: ver docstring de `validar_independiente.py`.
Unidad de análisis: ventanas de 2 min sin solapamiento.

Reproducir:
```
python validar_independiente.py afdb   <carpeta afdb>   --salida resultados --tiempo-max 0
python validar_independiente.py incart <carpeta incart> --salida resultados
```

## Resultados principales (IC 95 % de Wilson)

| Base | Tarea | Ventanas | Sensibilidad | Especificidad | VPP |
|---|---|---|---|---|---|
| **AFDB** (23 registros, 10 h) | Fibrilación auricular | 6 639 (FA 2 630) | **98.7 %** (98.2–99.0) | **97.4 %** (96.9–97.9) | 96.1 % (95.4–96.8) |
| **INCART** (75 registros, 32 pacientes) | Extrasístoles (≥ 2 en la ventana) | 1 044 (con ext. 772) | **69.6 %** (66.2–72.7) | **83.8 %** (79.0–87.7) | 92.4 % (90.0–94.3) |
| **INCART** | Detección de latidos (derivación II) | 172 978 latidos | **94.48 %** | — | **98.97 %** (+P) |

Mediana por registro en AFDB (≥ 5 ventanas): Se 100 %, Esp 98.9 %.

## Hallazgos y limitaciones
1. **FA:** desempeño alto y consistente entre registros. Las ventanas de **flutter** (43) no se reconocen como tal
   (se clasifican como extrasístoles o taquicardia): el flutter requiere análisis de ondas F.
2. **Extrasístoles frecuentes → falsa FA:** 170 de 772 ventanas con extrasístoles se clasificaron como FA. Se
   concentran en registros con ectopia muy frecuente (mediana 45–87 ectópicos por ventana: bigeminismo,
   duplas), donde no existe un ritmo de base regular. Es la principal causa de la sensibilidad de 69.6 %.
   Mejora propuesta: morfología del QRS (ancho/forma de los ectópicos ventriculares) y onda P, p.ej. con la CWT.
3. En ventanas sin extrasístoles, solo 11/272 (4.0 %) se clasificaron como FA (falsa alarma).
4. **Dependencia:** las ventanas de un mismo registro/paciente no son independientes (23 pacientes en AFDB,
   32 en INCART); los IC por ventana son, por tanto, optimistas. Se reporta también la mediana por registro.
5. AFDB usa anotaciones de **ritmo** (manuales); las anotaciones de latidos de AFDB (.qrs) no están auditadas y no
   se usaron. INCART usa anotaciones de latidos corregidas manualmente.

## Comparación con el conjunto de desarrollo (BUT PDB)
FA en BUT PDB: Se 80 %, VPP 73 % (registros de 2 min muy heterogéneos). En AFDB (independiente) la FA se detecta
mejor porque las ventanas de FA/no-FA son más "puras"; en ambos casos los errores dominantes son ectopia frecuente
y flutter.
