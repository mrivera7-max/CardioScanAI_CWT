# Prueba independiente — INCART (extrasístoles)

Registros: 75 (32 pacientes) · derivación II · ventanas de 120 s · evaluadas: 1044 (con extrasístoles 772, sin 272) · ambiguas excluidas: 81

## Detección de latidos (vs. .atr corregido manualmente)

| Latidos | TP | FN | FP | Sensibilidad | Valor predictivo + |
|---|---|---|---|---|---|
| 172978 | 163432 | 9546 | 1696 | **94.48 %** | **98.97 %** |

## Detección de extrasístoles (ventanas)

| Se | Esp | VPP | VPN | Exactitud | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|---|
| **69.6 %** | **83.8 %** | 92.4 % | 49.2 % | 73.3 % | 537 | 44 | 228 | 235 |

Ventanas SIN extrasístoles clasificadas como FA: **11/272 (4.0 %)**

## Distribución de diagnósticos

- **CON_EXT** (772): Extrasístoles 537, Fibrilación Auricular 170, Normal 20, Bloqueo AV 19, Bradicardia 18, Taquicardia 8
- **SIN_EXT** (272): Normal 106, Bradicardia 98, Extrasístoles 44, Taquicardia 13, Fibrilación Auricular 11