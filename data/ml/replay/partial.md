
## Tablas

Días: 2026-09-15, 2026-09-16, 2026-09-17. Líneas: 26, 39. Criterio «seguro»: primer coche del grupo pasa seguro (solo instantes en que hay); «seguro-o-fallback»: primero de pasa seguro y, si no hay, primero de pueden venir/provisional. «Antes»: el coche llega >60 s antes de lo anunciado; «después»: >60 s después.

#### Global

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 24720 | 241728 | 87.4 | 78 (n=6873) | 13.5 / 26.7 | 85 | 14.7 / 26.3 | 92 (n=21605) | 5.6 | 20.8 (7.8 / 55.3 / 40.6) | 14.2 (n=51934) | 17.4 (n=20209) |
| solo sentido conocido | 24720 | 240687 | 87.4 | 77 (n=6873) | 13.6 / 26.3 | 78 | 14.6 / 26.1 | 80 (n=21605) | 5.9 | 20.5 (7.7 / 55.4 / 36.2) | 14.2 (n=51934) | 17.4 (n=20209) |
| oráculo ramal | 24720 | 191173 | 87.4 | 73 (n=6873) | 14.2 / 24.0 | 75 | 15.3 / 23.7 | 75 (n=21605) | 7.0 | 8.3 (8.1 / 100.0 / 17.3) | 15.1 (n=51934) | 7.4 (n=20209) |

#### Línea 39

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 12360 | 163211 | 97.5 | 77 (n=3735) | 12.5 / 25.8 | 88 | 14.1 / 25.6 | 102 (n=12051) | 1.7 | 30.4 (9.1 / 55.3 / 48.9) | 11.9 (n=27751) | 23.2 (n=11066) |
| solo sentido conocido | 12360 | 162445 | 97.5 | 77 (n=3735) | 12.5 / 25.7 | 76 | 13.7 / 25.7 | 82 (n=12051) | 2.1 | 30.0 (9.0 / 55.4 / 43.8) | 11.9 (n=27751) | 23.2 (n=11066) |
| oráculo ramal | 12360 | 112931 | 97.5 | 70 (n=3735) | 13.8 / 21.8 | 72 | 15.0 / 21.5 | 74 (n=12051) | 4.1 | 9.5 (9.2 / 100.0 / 18.2) | 13.6 (n=27751) | 5.0 (n=11066) |

#### Tronco compartido (todas las líneas)

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 6180 | 84999 | 98.3 | 83 (n=1691) | 11.7 / 29.6 | 94 | 13.5 / 28.3 | 84 (n=6076) | 2.7 | 12.5 (9.3 / 33.5 / 25.0) | 14.5 (n=19527) | 8.3 (n=5883) |
| solo sentido conocido | 6180 | 84645 | 98.3 | 82 (n=1691) | 11.7 / 29.5 | 82 | 13.0 / 28.3 | 68 (n=6076) | 3.3 | 12.1 (9.1 / 33.5 / 17.9) | 14.5 (n=19527) | 8.3 (n=5883) |
| oráculo ramal | 6180 | 79808 | 98.3 | 79 (n=1691) | 11.7 / 28.2 | 81 | 12.9 / 27.9 | 69 (n=6076) | 3.8 | 8.8 (8.6 / — / 16.2) | 15.2 (n=19527) | 4.5 (n=5883) |

#### Tramo exclusivo (todas las líneas)

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 6180 | 78212 | 96.7 | 69 (n=2044) | 13.6 / 20.3 | 83 | 14.6 / 23.5 | 120 (n=5975) | 0.9 | 48.4 (8.3 / 58.5 / 65.8) | 5.7 (n=8224) | 40.1 (n=5183) |
| solo sentido conocido | 6180 | 77800 | 96.7 | 69 (n=2044) | 13.6 / 20.3 | 72 | 14.3 / 23.6 | 97 (n=5975) | 1.2 | 48.1 (8.3 / 58.6 / 62.0) | 5.7 (n=8224) | 40.1 (n=5183) |
| oráculo ramal | 6180 | 33123 | 96.7 | 62 (n=2044) | 15.5 / 16.5 | 65 | 16.7 / 16.2 | 79 (n=5975) | 4.4 | 10.3 (9.9 / 100.0 / 21.0) | 9.9 (n=8224) | 5.6 (n=5183) |

#### Línea 39, tronco compartido

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 6180 | 84999 | 98.3 | 83 (n=1691) | 11.7 / 29.6 | 94 | 13.5 / 28.3 | 84 (n=6076) | 2.7 | 12.5 (9.3 / 33.5 / 25.0) | 14.5 (n=19527) | 8.3 (n=5883) |
| solo sentido conocido | 6180 | 84645 | 98.3 | 82 (n=1691) | 11.7 / 29.5 | 82 | 13.0 / 28.3 | 68 (n=6076) | 3.3 | 12.1 (9.1 / 33.5 / 17.9) | 14.5 (n=19527) | 8.3 (n=5883) |
| oráculo ramal | 6180 | 79808 | 98.3 | 79 (n=1691) | 11.7 / 28.2 | 81 | 12.9 / 27.9 | 69 (n=6076) | 3.8 | 8.8 (8.6 / — / 16.2) | 15.2 (n=19527) | 4.5 (n=5883) |

#### Línea 39, tramo exclusivo

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 6180 | 78212 | 96.7 | 69 (n=2044) | 13.6 / 20.3 | 83 | 14.6 / 23.5 | 120 (n=5975) | 0.9 | 48.4 (8.3 / 58.5 / 65.8) | 5.7 (n=8224) | 40.1 (n=5183) |
| solo sentido conocido | 6180 | 77800 | 96.7 | 69 (n=2044) | 13.6 / 20.3 | 72 | 14.3 / 23.6 | 97 (n=5975) | 1.2 | 48.1 (8.3 / 58.6 / 62.0) | 5.7 (n=8224) | 40.1 (n=5183) |
| oráculo ramal | 6180 | 33123 | 96.7 | 62 (n=2044) | 15.5 / 16.5 | 65 | 16.7 / 16.2 | 79 (n=5975) | 4.4 | 10.3 (9.9 / 100.0 / 21.0) | 9.9 (n=8224) | 5.6 (n=5183) |

#### Líneas con un solo recorrido por sentido (paradas «únicas»)

| variante | n (parada,t) | coches evaluados | % con paso ≤20 min | próx. seguro: MAE 3–7 min (s) | antes / después >60 s | próx. seguro-o-fallback: MAE 3–7 min | antes / después | MAE ≤20 min (fallback) | sin anuncio 3–7 min % | falsas alarmas % (seguro / viene / prov.) | omisión ≤10 min % | seguro vacío % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base (ramal y sentido desconocidos) | 12360 | 78517 | 77.3 | 79 (n=3138) | 14.5 / 27.5 | 81 | 15.5 / 27.3 | 79 (n=9554) | 10.2 | 7.0 (6.8 / — / 15.7) | 16.8 (n=24183) | 10.3 (n=9143) |
| solo sentido conocido | 12360 | 78242 | 77.3 | 77 (n=3138) | 14.7 / 26.9 | 79 | 15.7 / 26.5 | 77 (n=9554) | 10.4 | 6.9 (6.7 / — / 15.6) | 16.8 (n=24183) | 10.3 (n=9143) |
| oráculo ramal | 12360 | 78242 | 77.3 | 77 (n=3138) | 14.7 / 26.9 | 79 | 15.7 / 26.5 | 77 (n=9554) | 10.4 | 6.9 (6.7 / — / 15.6) | 16.8 (n=24183) | 10.3 (n=9143) |

#### Por línea: base → oráculo ramal

| línea | n (parada,t) | MAE 3–7 min base → ramal (s) | falsas alarmas % | omisión % | seguro vacío % | MAE 3–7 min en tronco compartido | en exclusivo |
|---|---|---|---|---|---|---|---|
| 26 | 12360 | 81 → 79 | 7.0 → 6.9 | 16.8 → 16.8 | 10.3 → 10.3 | — → — | — → — |
| 39 | 12360 | 88 → 72 | 30.4 → 9.5 | 11.9 → 13.6 | 23.2 → 5.0 | 94 → 81 | 83 → 65 |
