Corrida `data\ml\replay\cuandosubo\run`: días 2026-11-18; líneas 39.

### A. ETA por coche, banda de ETA real 3–7 min

Todos los coches que cada fuente lista y que cruzan firme la parada con ETA real 3–7 min.

| línea / fuente | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| línea 39: CuandoSubo | 914 | 72 | 143 | 24.2 | 23.9 | 66 |
| línea 39: modelo `path_v4_l1_s1` | 902 | 56 | 116 | 22.6 | 15.5 | 52 |
| agregado: CuandoSubo | 914 | 72 | 143 | 24.2 | 23.9 | 66 |
| agregado: modelo `path_v4_l1_s1` | 902 | 56 | 116 | 22.6 | 15.5 | 52 |

Solo coches listados por las dos fuentes en el mismo (parada, instante).

| línea / fuente | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| línea 39: CuandoSubo | 844 | 69 | 137 | 23.3 | 24.3 | 65 |
| línea 39: modelo | 844 | 54 | 112 | 23.6 | 13.6 | 47 |
| agregado: CuandoSubo | 844 | 69 | 137 | 23.3 | 24.3 | 65 |
| agregado: modelo | 844 | 54 | 112 | 23.6 | 13.6 | 47 |

### B. Próximo coche anunciado, instantes con paso real en 3–7 min

| línea | n instantes | CuandoSubo: sin anuncio (%) | CuandoSubo MAE (s) | antes (%) | después (%) | modelo (cualquier grupo): sin anuncio (%) | MAE (s) | antes (%) | después (%) | modelo («Viene»): MAE (s) | antes (%) | después (%) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| línea 39 | 160 | 0.0 | 73 | 15.0 | 35.0 | 0.0 | 87 | 11.2 | 38.1 | 87 | 11.2 | 38.1 |
| agregado | 160 | 0.0 | 73 | 15.0 | 35.0 | 0.0 | 87 | 11.2 | 38.1 | 87 | 11.2 | 38.1 |

### C. Bondi fantasma

| línea | CuandoSubo: listados ≤ 40 min | evaluados | no verificables | ya pasó | bondi fantasma (%) | modelo: listados | evaluados | bondi fantasma (%) |
|---|---|---|---|---|---|---|---|---|
| línea 39 | 7369 | 7369 | 0 | 22 | 4.7 | 3326 | 3302 | 2.1 |
| agregado | 7369 | 7369 | 0 | 22 | 4.7 | 3326 | 3302 | 2.1 |

### D. Bondi no anunciado (coches que pasan en ≤ 10 min)

| línea | pasan | CuandoSubo no anunciado (%) | modelo no anunciado (%) | pasan con ping vigente | CuandoSubo (%) | modelo (%) |
|---|---|---|---|---|---|---|
| línea 39 | 2610 | 15.6 | 13.9 | 2602 | 15.3 | 13.6 |
| agregado | 2610 | 15.6 | 13.9 | 2602 | 15.3 | 13.6 |

### E. Sensibilidad de CuandoSubo al corrimiento del sello de CABA (agregado, banda 3–7 min)

| fuente / corrimiento | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| CuandoSubo, por coche, corrimiento 0 s | 914 | 89 | 173 | 10.6 | 51.5 | 96 |
| CuandoSubo, por coche, corrimiento 60 s | 914 | 72 | 143 | 24.2 | 23.9 | 66 |
| CuandoSubo, por coche, corrimiento 120 s | 914 | 86 | 181 | 48.5 | 6.8 | 45 |
| modelo, por coche (no depende del corrimiento) | 902 | 56 | 116 | 22.6 | 15.5 | 52 |

| próximo coche, agregado | n | MAE (s) | antes (%) | después (%) |
|---|---|---|---|---|
| CuandoSubo, corrimiento 0 s | 160 | 104 | 7.5 | 65.6 |
| CuandoSubo, corrimiento 60 s | 160 | 73 | 15.0 | 35.0 |
| CuandoSubo, corrimiento 120 s | 160 | 72 | 34.4 | 9.4 |
| modelo (cualquier grupo) | 160 | 87 | 11.2 | 38.1 |

### F. Por parada, banda 3–7 min (MAE por coche)

| línea | parada OBA → OSM | n CuandoSubo | MAE CuandoSubo (s) | n modelo | MAE modelo (s) |
|---|---|---|---|---|---|
| 39 | 14_206600 → n1493476757 | 251 | 67 | 266 | 69 |
| 39 | 14_203270 → n2719439787 | 348 | 72 | 336 | 53 |
| 39 | 14_201063 → n3909887526 | 315 | 75 | 300 | 48 |

### G. Por tipo de día (agregado, por coche, banda 3–7 min)

| tipo de día / fuente | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| hábiles (lun–vie): CuandoSubo | 914 | 72 | 143 | 24.2 | 23.9 | 66 |
| hábiles (lun–vie): modelo | 902 | 56 | 116 | 22.6 | 15.5 | 52 |

### H. Contexto de CuandoSubo en las paradas

Entradas de arribo con coche: 10458; de otra línea (por label): 0; sin línea (label desconocido): 0; solo horario (sin tiempo real, sin coche): 6147.

Entradas de coches de la línea con tiempo real y `stops_away ≥ 0`: 7632; de ellas, coche presente en CABA ese día: 7632.
Antigüedad del GPS de CuandoSubo (t − `veh_ts`): P50 124 s, P90 158 s.