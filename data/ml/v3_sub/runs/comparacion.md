# Comparación sobre el eval de v3, modelo por tramos con pérdida L1

Eval `data/ml/v3/eval` (15000 filas por bucket de ETA y por conjunto, asignación geo3). `v2c_l1`: modelo por tramos L1 sin paradas entrenado sobre v2c (12 líneas; su semilla 1 es `path_v2c_l1_s1`, el de producción); `v2c_l1_paradas`: igual con `--stops-feature` (`data/ml/v2c_sub/runs_stops`); `v3_l1_paradas`: este escalado (v3_sub, 48 líneas). Cada celda es la media de las semillas 0 y 1. Banda principal: 3-7 min (principal).

## seen, 12 líneas de producción (las que conocen todos los modelos): ETA real 3-7 min (principal) (n = 3915)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 55.9 | 117.3 | 16.2 | 20.1 | 56.0 |
| v2c_l1 | 56.1 | 117.4 | 16.8 | 19.8 | 55.8 |
| v2c_l1_paradas | 56.0 | 118.2 | 15.8 | 19.9 | 55.5 |

MAE (s) por banda de ETA real, seen, 12 líneas de producción (las que conocen todos los modelos):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 22.8 | 38.6 | 55.3 | 69.9 | 78.9 | 96.2 | 115.4 |
| v2c_l1 | 24.4 | 38.5 | 55.3 | 70.2 | 79.0 | 96.4 | 115.7 |
| v2c_l1_paradas | 23.8 | 38.2 | 55.5 | 70.3 | 79.3 | 96.4 | 115.8 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 56.1 s (16.0 %) ; s1 55.7 s (16.5 %)
- v2c_l1: s0 56.0 s (16.3 %) ; s1 56.2 s (17.3 %)
- v2c_l1_paradas: s0 55.7 s (15.9 %) ; s1 56.3 s (15.7 %)

## seen, 36 líneas nuevas (no en producción; solo v3): ETA real 3-7 min (principal) (n = 9483)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 56.2 | 116.6 | 13.8 | 21.2 | 58.2 |

MAE (s) por banda de ETA real, seen, 36 líneas nuevas (no en producción; solo v3):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 22.5 | 39.6 | 56.4 | 70.2 | 80.5 | 99.2 | 130.7 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 56.2 s (13.6 %) ; s1 56.2 s (13.9 %)

## seen, las 48 líneas de train (solo v3): ETA real 3-7 min (principal) (n = 13398)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 56.1 | 116.8 | 14.5 | 20.8 | 57.5 |

MAE (s) por banda de ETA real, seen, las 48 líneas de train (solo v3):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 22.5 | 39.3 | 56.1 | 70.1 | 80.0 | 98.3 | 125.8 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 56.2 s (14.3 %) ; s1 56.1 s (14.7 %)

## heldout, las 3 de control con shapes conocidos por v2c (12, 15, 128; ninguna en train de ningún modelo): ETA real 3-7 min (principal) (n = 3442)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 66.9 | 141.5 | 11.8 | 33.3 | 72.7 |
| v2c_l1 | 90.2 | 177.7 | 18.5 | 33.5 | 79.1 |
| v2c_l1_paradas | 84.0 | 168.4 | 15.5 | 37.3 | 80.2 |

MAE (s) por banda de ETA real, heldout, las 3 de control con shapes conocidos por v2c (12, 15, 128; ninguna en train de ningún modelo):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 23.2 | 43.2 | 68.2 | 82.9 | 100.3 | 124.7 | 148.0 |
| v2c_l1 | 32.9 | 55.7 | 91.7 | 109.9 | 134.7 | 163.4 | 188.9 |
| v2c_l1_paradas | 28.9 | 51.1 | 85.3 | 102.3 | 123.9 | 156.1 | 185.1 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 66.4 s (11.1 %) ; s1 67.5 s (12.4 %)
- v2c_l1: s0 89.9 s (18.4 %) ; s1 90.4 s (18.7 %)
- v2c_l1_paradas: s0 81.5 s (15.7 %) ; s1 86.5 s (15.3 %)

## heldout, las 12 de control (solo v3; ninguna en train): ETA real 3-7 min (principal) (n = 13292)

| modelo | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---:|---:|---:|---:|---:|
| v3_l1_paradas | 74.1 | 156.0 | 17.1 | 30.8 | 74.9 |

MAE (s) por banda de ETA real, heldout, las 12 de control (solo v3; ninguna en train):

| modelo | 0-2 min | 2-4 min | 4-6 min | 6-8 min | 8-10 min | 10-15 min | 15-20 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3_l1_paradas | 24.1 | 47.6 | 75.6 | 93.4 | 117.3 | 141.0 | 165.3 |

Semillas 0 / 1 en 3-7 min (principal) (MAE s; llega antes %):

- v3_l1_paradas: s0 73.8 s (16.6 %) ; s1 74.4 s (17.6 %)

## Desglose por línea (seen)

MAE y % llega antes >60 s en la banda 3-7 min (principal), y MAE global (todas las bandas), media de semillas. Las columnas v2c solo existen para las 12 líneas viejas. n = filas de la banda.

| línea | grupo | n banda | v3_l1_paradas MAE banda | llega antes % | MAE global | v2c_l1 MAE banda | v2c_l1_paradas MAE banda |
|---|---|---:|---:|---:|---:|---:|---:|
| 26 | vieja | 42 | 63.4 | 11.9 | 149.9 | 65.3 | 62.8 |
| 39 | vieja | 517 | 51.7 | 15.5 | 89.9 | 51.0 | 52.0 |
| 42 | vieja | 213 | 58.9 | 18.1 | 121.7 | 60.9 | 61.0 |
| 92 | vieja | 375 | 54.0 | 15.7 | 106.8 | 54.9 | 54.5 |
| 124 | vieja | 234 | 51.5 | 13.2 | 83.1 | 50.9 | 50.9 |
| 151 | vieja | 409 | 67.0 | 20.4 | 121.5 | 68.0 | 67.7 |
| 168 | vieja | 246 | 52.5 | 16.3 | 96.7 | 52.8 | 51.5 |
| 50 | vieja | 271 | 52.0 | 14.2 | 90.1 | 53.9 | 52.0 |
| 106 | vieja | 636 | 54.5 | 14.4 | 87.1 | 54.0 | 53.8 |
| 107 | vieja | 224 | 59.2 | 20.8 | 115.9 | 59.3 | 58.6 |
| 108 | vieja | 223 | 57.1 | 14.8 | 105.8 | 56.3 | 55.9 |
| 132 | vieja | 525 | 56.4 | 17.0 | 98.7 | 56.5 | 57.4 |
| 4 | nueva | 236 | 62.5 | 18.0 | 108.3 |  |  |
| 7 | nueva | 149 | 43.1 | 9.7 | 87.5 |  |  |
| 9 | nueva | 277 | 50.8 | 11.7 | 77.2 |  |  |
| 20 | nueva | 151 | 54.8 | 11.9 | 80.3 |  |  |
| 25 | nueva | 149 | 55.9 | 13.4 | 104.0 |  |  |
| 28 | nueva | 842 | 65.4 | 14.1 | 116.6 |  |  |
| 29 | nueva | 282 | 57.0 | 11.5 | 101.6 |  |  |
| 33 | nueva | 327 | 50.7 | 13.3 | 95.1 |  |  |
| 34 | nueva | 482 | 55.9 | 14.1 | 89.5 |  |  |
| 41 | nueva | 289 | 58.2 | 18.3 | 89.5 |  |  |
| 44 | nueva | 291 | 49.3 | 11.9 | 92.6 |  |  |
| 46 | nueva | 165 | 47.6 | 11.8 | 93.0 |  |  |
| 47 | nueva | 174 | 54.8 | 15.2 | 106.2 |  |  |
| 61 | nueva | 82 | 133.3 | 18.3 | 178.9 |  |  |
| 62 | nueva | 104 | 60.1 | 15.4 | 101.7 |  |  |
| 74 | nueva | 116 | 47.4 | 13.4 | 92.4 |  |  |
| 76 | nueva | 225 | 51.2 | 13.6 | 104.5 |  |  |
| 84 | nueva | 205 | 48.9 | 13.9 | 84.2 |  |  |
| 85 | nueva | 287 | 51.4 | 13.1 | 103.8 |  |  |
| 88 | nueva | 180 | 91.8 | 18.3 | 179.0 |  |  |
| 98 | nueva | 566 | 54.1 | 13.5 | 93.5 |  |  |
| 102 | nueva | 329 | 60.7 | 18.8 | 109.3 |  |  |
| 110 | nueva | 288 | 52.8 | 9.4 | 96.6 |  |  |
| 113 | nueva | 221 | 49.6 | 16.5 | 89.9 |  |  |
| 114 | nueva | 181 | 56.5 | 14.4 | 141.7 |  |  |
| 115 | nueva | 313 | 59.4 | 14.2 | 113.8 |  |  |
| 118 | nueva | 445 | 54.4 | 13.6 | 96.5 |  |  |
| 123 | nueva | 153 | 49.2 | 9.2 | 99.7 |  |  |
| 127 | nueva | 172 | 48.9 | 11.9 | 91.9 |  |  |
| 143 | nueva | 140 | 51.7 | 12.9 | 111.9 |  |  |
| 169 | nueva | 176 | 41.1 | 11.6 | 81.2 |  |  |
| 180 | nueva | 445 | 59.6 | 15.3 | 131.1 |  |  |
| 184 | nueva | 120 | 39.5 | 7.5 | 99.7 |  |  |
| 188 | nueva | 339 | 52.0 | 13.1 | 94.8 |  |  |
| 194 | nueva | 302 | 65.5 | 12.7 | 152.4 |  |  |
| 197 | nueva | 280 | 49.5 | 14.5 | 94.4 |  |  |
