# Validación CardioScan AI — BUT PDB

Registros: 50 · dentro de alcance: 44 · fuera de alcance: 6 · canal 0

## Detección de latidos (vs. anotaciones .qrs)

| Latidos anotados | TP | FN | FP | Sensibilidad | Valor predictivo + |
|---|---|---|---|---|---|
| 7447 | 7163 | 284 | 72 | **96.19 %** | **99.00 %** |

## Diagnóstico

- Exactitud **estricta** (clase principal): **31/44 = 70.5 %**
- Exactitud **aceptable** (cualquier hallazgo presente): **33/44 = 75.0 %**

### Por clase de referencia

| Referencia (principal) | n | Estricta | Aceptable |
|---|---|---|---|
| Normal | 1 | 1/1 | 1/1 |
| Taquicardia | 1 | 0/1 | 0/1 |
| Fibrilación Auricular | 10 | 8/10 | 8/10 |
| Bloqueo AV | 4 | 2/4 | 2/4 |
| Extrasístoles | 27 | 20/27 | 22/27 |
| Flutter Auricular | 1 | 0/1 | 0/1 |

### Matriz de confusión (filas = referencia principal, columnas = CardioScan)

| Ref \ Pred | NOR | TAQ | BRA | FA | BAV | EXT | FL |
|---|---|---|---|---|---|---|---|
| **NOR** | 1 | · | · | · | · | · | · |
| **TAQ** | · | · | · | · | · | 1 | · |
| **FA** | · | · | · | 8 | · | 2 | · |
| **BAV** | 1 | · | · | · | 2 | 1 | · |
| **EXT** | 3 | · | 2 | 2 | · | 20 | · |
| **FL** | · | · | · | 1 | · | · | · |

FA = Fibrilación Auricular · FL = Flutter Auricular · BAV = Bloqueo AV · EXT = Extrasístoles · TAQ = Taquicardia · BRA = Bradicardia · NOR = Normal · ISQ = Isquemia Miocárdica

### Detalle

| Reg | Códigos | Referencia | CardioScan | FC ref | FC det | CV RR | Se % | ✓ |
|---|---|---|---|---|---|---|---|---|
| 01 | BII,R | Bloqueo AV | Bloqueo AV | 60.1 | 51.5 | 0.276 | 100.0 | ✓ |
| 02 | V,B | Extrasístoles | Fibrilación Auricular | 64.7 | 68.6 | 0.376 | 100.0 | ✗ |
| 03 | BIII | Bloqueo AV | Extrasístoles | 70.8 | 70.6 | 0.072 | 99.29 | ✗ |
| 04 | A | Extrasístoles | Extrasístoles | 58.9 | 58.3 | 0.119 | 100.0 | ✓ |
| 05 | A,V | Extrasístoles | Extrasístoles | 69.5 | 70.0 | 0.111 | 100.0 | ✓ |
| 06 | NOD,J | FUERA DE ALCANCE | Extrasístoles | 56.0 | 56.1 | 0.132 | 94.64 | — |
| 07 | AFIB,NOD,J | Fibrilación Auricular | Fibrilación Auricular | 59.8 | 55.1 | 0.442 | 95.58 | ✓ |
| 08 | AFIB,AFL | Fibrilación Auricular | Fibrilación Auricular | 94.3 | 81.3 | 0.479 | 82.2 | ✓ |
| 09 | E,A,SVTA | Extrasístoles | Extrasístoles | 64.9 | 68.0 | 0.259 | 91.18 | ✓ |
| 10 | V,T | Extrasístoles | Extrasístoles | 108.0 | 103.0 | 0.243 | 97.57 | ✓ |
| 11 | SVTA | Taquicardia | Extrasístoles | 93.9 | 95.4 | 0.092 | 100.0 | ✗ |
| 12 | PREX | FUERA DE ALCANCE | Normal | 64.1 | 64.7 | 0.057 | 100.0 | — |
| 13 | BII,R | Bloqueo AV | Bloqueo AV | 37.1 | 44.3 | 0.266 | 100.0 | ✓ |
| 14 | V,B | Extrasístoles | Extrasístoles | 100.9 | 101.3 | 0.244 | 100.0 | ✓ |
| 15 | J | Extrasístoles | Normal | 91.9 | 96.2 | 0.134 | 100.0 | ✗ |
| 16 | A | Extrasístoles | Normal | 62.1 | 62.1 | 0.035 | 100.0 | ✗ |
| 17 | A | Extrasístoles | Extrasístoles | 86.4 | 85.9 | 0.05 | 100.0 | ✓ |
| 18 | A | Extrasístoles | Extrasístoles | 67.7 | 66.3 | 0.16 | 97.73 | ✓ |
| 19 | P,F,V | FUERA DE ALCANCE | Bradicardia | 73.7 | 51.6 | 0.631 | 69.66 | — |
| 20 | V | Extrasístoles | Extrasístoles | 87.8 | 88.5 | 0.128 | 98.26 | ✓ |
| 21 | L,V | Extrasístoles | Extrasístoles | 81.2 | 81.4 | 0.057 | 100.0 | ✓ |
| 22 | L,BI | Bloqueo AV | Normal | 70.5 | 70.5 | 0.045 | 100.0 | ✗ |
| 23 | a | Extrasístoles | Normal | 60.8 | 61.6 | 0.092 | 100.0 | ✗ |
| 24 | NA | Normal | Normal | 66.9 | 64.6 | 0.114 | 100.0 | ✓ |
| 25 | V,VP | Extrasístoles | Extrasístoles | 82.4 | 82.6 | 0.099 | 100.0 | ✓ |
| 26 | R,A | Extrasístoles | Extrasístoles | 69.7 | 70.0 | 0.133 | 100.0 | ✓ |
| 27 | V,B,T | Extrasístoles | Extrasístoles | 67.9 | 66.7 | 0.312 | 100.0 | ✓ |
| 28 | A,V | Extrasístoles | Extrasístoles | 59.4 | 59.3 | 0.076 | 100.0 | ✓ |
| 29 | V | Extrasístoles | Bradicardia | 49.1 | 49.5 | 0.106 | 98.98 | ✓ |
| 30 | P,IVR,T,V,F | FUERA DE ALCANCE | Bradicardia | 51.4 | 49.6 | 0.196 | 96.08 | — |
| 31 | V,F,VT | Extrasístoles | Extrasístoles | 82.0 | 85.4 | 0.18 | 98.82 | ✓ |
| 32 | V,F,VT | Extrasístoles | Extrasístoles | 92.7 | 95.5 | 0.161 | 98.43 | ✓ |
| 33 | V,VFL | FUERA DE ALCANCE | Fibrilación Auricular | 60.5 | 52.8 | 0.65 | 63.92 | — |
| 34 | R | FUERA DE ALCANCE | Normal | 88.2 | 86.8 | 0.075 | 100.0 | — |
| 35 | V,A | Extrasístoles | Extrasístoles | 105.9 | 105.4 | 0.1 | 99.52 | ✓ |
| 36 | V,L | Extrasístoles | Extrasístoles | 76.3 | 76.2 | 0.199 | 100.0 | ✓ |
| 37 | A,FIB | Fibrilación Auricular | Fibrilación Auricular | 70.0 | 63.7 | 0.313 | 98.43 | ✓ |
| 38 | NOD,AFL,A | Flutter Auricular | Fibrilación Auricular | 86.1 | 71.9 | 0.399 | 87.12 | ✗ |
| 39 | V,A | Extrasístoles | Extrasístoles | 102.4 | 52.9 | 0.3 | 52.82 | ✓ |
| 40 | V,A | Extrasístoles | Extrasístoles | 50.2 | 50.8 | 0.117 | 100.0 | ✓ |
| 41 | L,A,V | Extrasístoles | Extrasístoles | 67.4 | 67.6 | 0.08 | 100.0 | ✓ |
| 42 | V | Extrasístoles | Fibrilación Auricular | 81.7 | 87.3 | 0.262 | 100.0 | ✗ |
| 43 | A,SVTA | Extrasístoles | Bradicardia | 52.8 | 53.6 | 0.203 | 100.0 | ✓ |
| 44 | AFIB | Fibrilación Auricular | Extrasístoles | 60.5 | 66.8 | 0.199 | 100.0 | ✗ |
| 45 | AFIB | Fibrilación Auricular | Extrasístoles | 89.3 | 91.4 | 0.169 | 99.44 | ✗ |
| 46 | AFIB | Fibrilación Auricular | Fibrilación Auricular | 132.4 | 121.0 | 0.281 | 100.0 | ✓ |
| 47 | AFIB | Fibrilación Auricular | Fibrilación Auricular | 97.2 | 94.6 | 0.292 | 95.34 | ✓ |
| 48 | AFIB | Fibrilación Auricular | Fibrilación Auricular | 80.0 | 69.8 | 0.291 | 100.0 | ✓ |
| 49 | AFIB | Fibrilación Auricular | Fibrilación Auricular | 65.1 | 79.5 | 0.337 | 100.0 | ✓ |
| 50 | AFIB | Fibrilación Auricular | Fibrilación Auricular | 139.6 | 112.8 | 0.55 | 100.0 | ✓ |

> BUT PDB se usa como conjunto de **desarrollo**: cualquier ajuste de reglas basado en esta tabla debe evaluarse después en una base independiente.