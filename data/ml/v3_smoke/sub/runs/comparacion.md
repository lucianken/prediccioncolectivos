# Comparación sobre el eval de v3, modelo por tramos con pérdida L1

Eval `data/ml/v3/eval` (200 filas por bucket de ETA y por conjunto, asignación geo3). `v2c_l1`: modelo por tramos L1 sin paradas entrenado sobre v2c (12 líneas; su semilla 1 es `path_v2c_l1_s1`, el de producción); `v2c_l1_paradas`: igual con `--stops-feature` (`data/ml/v2c_sub/runs_stops`); `v3_l1_paradas`: este escalado (v3_sub, 48 líneas). Cada celda es la media de las semillas 0 y 1. Banda principal: 3-7 min (principal).

## seen, 12 líneas de producción (las que conocen todos los modelos): ETA real 3-7 min (principal) (n = 66)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 59.5 | 135.8 | 14.4 | 22.7 | 64.2 |
| v2c_l1 | 53.9 | 131.7 | 10.6 | 21.2 | 57.3 |

MAE (s) por banda de ETA real, seen, 12 líneas de producción (las que conocen todos los modelos):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 25.9 | 40.1 | 44.1 | 87.2 | 118.9 | 114.9 | 105.5 |
| v2c_l1 | 21.1 | 41.2 | 40.2 | 72.0 | 82.0 | 92.0 | 85.3 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 59.3 s (13.6 %) ; s1 59.7 s (15.2 %)
- v2c_l1: s1 53.9 s (10.6 %)

## seen, 36 líneas nuevas (no en producción; solo v3): ETA real 3-7 min (principal) (n = 111)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 66.3 | 140.7 | 17.1 | 25.7 | 66.5 |

MAE (s) por banda de ETA real, seen, 36 líneas nuevas (no en producción; solo v3):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 27.9 | 40.0 | 68.3 | 90.9 | 104.6 | 132.8 | 159.6 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 67.3 s (15.3 %) ; s1 65.4 s (18.9 %)

## seen, las 48 líneas de train (solo v3): ETA real 3-7 min (principal) (n = 177)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 63.8 | 141.4 | 16.1 | 24.6 | 65.6 |

MAE (s) por banda de ETA real, seen, las 48 líneas de train (solo v3):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 27.3 | 40.0 | 60.5 | 89.6 | 110.2 | 128.9 | 138.6 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 64.3 s (14.7 %) ; s1 63.3 s (17.5 %)

## heldout, las 3 de control con shapes conocidos por v2c (12, 15, 128; ninguna en train de ningún modelo): ETA real 3-7 min (principal) (n = 34)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 79.0 | 144.5 | 14.7 | 42.6 | 84.1 |
| v2c_l1 | 78.2 | 139.1 | 20.6 | 50.0 | 75.2 |

MAE (s) por banda de ETA real, heldout, las 3 de control con shapes conocidos por v2c (12, 15, 128; ninguna en train de ningún modelo):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 35.3 | 68.4 | 77.8 | 66.9 | 114.4 | 145.2 | 149.8 |
| v2c_l1 | 52.4 | 86.8 | 74.5 | 83.1 | 118.1 | 210.9 | 213.5 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 77.7 s (14.7 %) ; s1 80.4 s (14.7 %)
- v2c_l1: s1 78.2 s (20.6 %)

## heldout, las 12 de control (solo v3; ninguna en train): ETA real 3-7 min (principal) (n = 183)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 82.7 | 175.8 | 20.2 | 32.2 | 86.9 |

MAE (s) por banda de ETA real, heldout, las 12 de control (solo v3; ninguna en train):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 32.8 | 51.8 | 89.9 | 85.8 | 125.4 | 134.8 | 168.6 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 82.3 s (19.7 %) ; s1 83.1 s (20.8 %)

## Desglose por línea (seen)

MAE y % llega antes >60 s en la banda 3-7 min (principal), y MAE global (todas las bandas), media de semillas. Las columnas v2c solo existen para las 12 líneas viejas. n = filas de la banda.

| línea | grupo | n banda | v3_l1_paradas MAE banda | llega antes % | MAE global | v2c_l1 MAE banda | v2c_l1_paradas MAE banda |
|---|---|---:|---:|---:|---:|---:|---:|
| 26 | vieja | 7 | 57.1 | 14.3 | 107.3 | 63.4 | nan |
| 39 | vieja | 12 | 54.5 | 16.7 | 88.7 | 55.2 | nan |
| 42 | vieja | 4 | 49.2 | 25.0 | 110.5 | 25.4 | nan |
| 92 | vieja | 2 | 27.5 | 0.0 | 176.7 | 40.5 | nan |
| 124 | vieja | 3 | 28.9 | 0.0 | 102.0 | 31.0 | nan |
| 151 | vieja | 5 | 55.4 | 10.0 | 71.3 | 64.3 | nan |
| 168 | vieja | 4 | 43.2 | 0.0 | 75.4 | 43.7 | nan |
| 50 | vieja | 5 | 81.0 | 20.0 | 94.0 | 58.0 | nan |
| 106 | vieja | 13 | 75.2 | 23.1 | 134.1 | 64.3 | nan |
| 107 | vieja | 1 | 165.9 | 0.0 | 259.7 | 133.8 | nan |
| 108 | vieja | 1 | 49.2 | 0.0 | 295.3 | 31.0 | nan |
| 132 | vieja | 9 | 54.2 | 11.1 | 137.9 | 43.2 | nan |
| 4 | nueva | 2 | 18.8 | 0.0 | 65.9 |  |  |
| 7 | nueva | 4 | 80.5 | 37.5 | 160.0 |  |  |
| 9 | nueva | 1 | 5.6 | 0.0 | 72.0 |  |  |
| 20 | nueva | 4 | 56.8 | 25.0 | 79.3 |  |  |
| 25 | nueva | 0 | nan | nan | 63.2 |  |  |
| 28 | nueva | 5 | 107.9 | 20.0 | 187.7 |  |  |
| 29 | nueva | 6 | 84.5 | 16.7 | 83.7 |  |  |
| 33 | nueva | 3 | 32.9 | 0.0 | 101.6 |  |  |
| 34 | nueva | 7 | 96.7 | 0.0 | 81.5 |  |  |
| 41 | nueva | 4 | 59.4 | 0.0 | 132.3 |  |  |
| 44 | nueva | 5 | 48.2 | 20.0 | 69.5 |  |  |
| 46 | nueva | 1 | 21.9 | 0.0 | 131.9 |  |  |
| 47 | nueva | 1 | 55.1 | 0.0 | 242.0 |  |  |
| 61 | nueva | 2 | 24.3 | 0.0 | 236.2 |  |  |
| 62 | nueva | 2 | 56.0 | 0.0 | 123.0 |  |  |
| 74 | nueva | 0 | nan | nan | 118.3 |  |  |
| 76 | nueva | 3 | 65.3 | 33.3 | 169.8 |  |  |
| 84 | nueva | 5 | 94.3 | 40.0 | 97.8 |  |  |
| 85 | nueva | 5 | 52.5 | 0.0 | 96.9 |  |  |
| 88 | nueva | 0 | nan | nan | 233.5 |  |  |
| 98 | nueva | 5 | 69.4 | 10.0 | 117.7 |  |  |
| 102 | nueva | 1 | 68.1 | 0.0 | 221.8 |  |  |
| 110 | nueva | 7 | 58.4 | 14.3 | 80.6 |  |  |
| 113 | nueva | 4 | 25.8 | 25.0 | 166.1 |  |  |
| 114 | nueva | 0 | nan | nan | 60.6 |  |  |
| 115 | nueva | 4 | 70.4 | 37.5 | 126.8 |  |  |
| 118 | nueva | 5 | 51.7 | 20.0 | 93.0 |  |  |
| 123 | nueva | 4 | 71.1 | 62.5 | 252.1 |  |  |
| 127 | nueva | 1 | 131.3 | 0.0 | 111.2 |  |  |
| 143 | nueva | 2 | 44.0 | 0.0 | 94.7 |  |  |
| 169 | nueva | 2 | 137.9 | 50.0 | 206.5 |  |  |
| 180 | nueva | 6 | 74.0 | 33.3 | 74.3 |  |  |
| 184 | nueva | 1 | 25.6 | 0.0 | 62.7 |  |  |
| 188 | nueva | 3 | 16.6 | 0.0 | 157.7 |  |  |
| 194 | nueva | 2 | 141.3 | 0.0 | 147.0 |  |  |
| 197 | nueva | 4 | 62.9 | 0.0 | 95.5 |  |  |
