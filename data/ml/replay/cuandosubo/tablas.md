Corrida `data\ml\replay\cuandosubo\run`: días 2026-11-14, 2026-11-15, 2026-11-16, 2026-11-17, 2026-11-18, 2026-11-19, 2026-11-20, 2026-11-21; líneas 39, 42, 92, 152, 168.

### A. ETA por coche, banda de ETA real 3–7 min

Todos los coches que cada fuente lista y que cruzan firme la parada con ETA real 3–7 min.

| línea / fuente | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| línea 39: CuandoSubo | 6305 | 71 | 147 | 23.8 | 23.8 | 66 |
| línea 39: modelo `path_v4_l1_s1` | 6356 | 55 | 116 | 21.6 | 15.0 | 52 |
| línea 42: CuandoSubo | 3042 | 76 | 159 | 31.9 | 13.8 | 49 |
| línea 42: modelo `path_v4_l1_s1` | 3198 | 52 | 108 | 15.7 | 17.6 | 49 |
| línea 92: CuandoSubo | 2998 | 84 | 172 | 29.5 | 26.9 | 87 |
| línea 92: modelo `path_v4_l1_s1` | 3520 | 59 | 131 | 13.9 | 21.8 | 65 |
| línea 152: CuandoSubo | 7491 | 76 | 160 | 8.8 | 43.3 | 92 |
| línea 152: modelo `path_v4_l1_s1` | 7373 | 47 | 100 | 13.0 | 17.5 | 49 |
| línea 168: CuandoSubo | 2093 | 105 | 191 | 1.7 | 70.4 | 111 |
| línea 168: modelo `path_v4_l1_s1` | 2806 | 52 | 107 | 14.5 | 19.8 | 54 |
| agregado: CuandoSubo | 21929 | 78 | 163 | 18.5 | 33.9 | 84 |
| agregado: modelo `path_v4_l1_s1` | 23253 | 52 | 111 | 16.1 | 17.8 | 53 |

Solo coches listados por las dos fuentes en el mismo (parada, instante).

| línea / fuente | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| línea 39: CuandoSubo | 5989 | 69 | 145 | 23.0 | 24.0 | 66 |
| línea 39: modelo | 5989 | 54 | 114 | 22.1 | 14.1 | 49 |
| línea 42: CuandoSubo | 3015 | 75 | 157 | 31.5 | 13.8 | 49 |
| línea 42: modelo | 3015 | 50 | 104 | 14.6 | 17.8 | 49 |
| línea 92: CuandoSubo | 2970 | 83 | 171 | 29.3 | 26.9 | 87 |
| línea 92: modelo | 2970 | 51 | 111 | 15.8 | 16.1 | 51 |
| línea 152: CuandoSubo | 7121 | 76 | 161 | 8.9 | 43.1 | 93 |
| línea 152: modelo | 7121 | 47 | 98 | 13.3 | 16.6 | 47 |
| línea 168: CuandoSubo | 2006 | 105 | 191 | 1.5 | 70.6 | 111 |
| línea 168: modelo | 2006 | 52 | 108 | 15.6 | 18.1 | 52 |
| agregado: CuandoSubo | 21101 | 78 | 162 | 18.3 | 33.9 | 83 |
| agregado: modelo | 21101 | 50 | 106 | 16.5 | 16.1 | 49 |

### B. Próximo coche anunciado, instantes con paso real en 3–7 min

| línea | n instantes | CuandoSubo: sin anuncio (%) | CuandoSubo MAE (s) | antes (%) | después (%) | modelo (cualquier grupo): sin anuncio (%) | MAE (s) | antes (%) | después (%) | modelo («Viene»): MAE (s) | antes (%) | después (%) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| línea 39 | 1451 | 0.0 | 70 | 20.7 | 24.3 | 0.0 | 85 | 10.8 | 31.6 | 85 | 10.8 | 31.6 |
| línea 42 | 1623 | 2.2 | 84 | 31.4 | 15.4 | 0.4 | 67 | 11.4 | 25.8 | 66 | 11.1 | 25.9 |
| línea 92 | 1641 | 0.0 | 132 | 34.0 | 25.7 | 0.0 | 87 | 11.9 | 30.5 | 87 | 11.9 | 30.5 |
| línea 152 | 1444 | 0.0 | 70 | 9.7 | 39.0 | 0.0 | 86 | 5.2 | 34.8 | 86 | 5.2 | 34.8 |
| línea 168 | 1465 | 0.5 | 194 | 29.6 | 43.8 | 0.4 | 176 | 25.4 | 23.3 | 175 | 25.3 | 23.3 |
| agregado | 7624 | 0.6 | 110 | 25.4 | 29.3 | 0.2 | 99 | 12.9 | 29.1 | 99 | 12.8 | 29.2 |

### C. Bondi fantasma

| línea | CuandoSubo: listados ≤ 40 min | evaluados | no verificables | ya pasó | bondi fantasma (%) | modelo: listados | evaluados | bondi fantasma (%) |
|---|---|---|---|---|---|---|---|---|
| línea 39 | 49281 | 49149 | 132 | 125 | 6.0 | 25407 | 25186 | 2.2 |
| línea 42 | 28364 | 28185 | 179 | 81 | 19.1 | 21121 | 20281 | 5.3 |
| línea 92 | 36703 | 36555 | 148 | 42 | 22.3 | 26233 | 25100 | 5.1 |
| línea 152 | 59088 | 58964 | 124 | 66 | 18.4 | 25722 | 25713 | 1.2 |
| línea 168 | 40182 | 40060 | 122 | 13 | 38.2 | 22458 | 20904 | 4.3 |
| agregado | 213618 | 212913 | 705 | 327 | 20.0 | 120941 | 117184 | 3.5 |

### D. Bondi no anunciado (coches que pasan en ≤ 10 min)

| línea | pasan | CuandoSubo no anunciado (%) | modelo no anunciado (%) | pasan con ping vigente | CuandoSubo (%) | modelo (%) |
|---|---|---|---|---|---|---|
| línea 39 | 17395 | 13.8 | 10.5 | 17345 | 13.6 | 10.2 |
| línea 42 | 8162 | 10.7 | 4.2 | 8155 | 10.6 | 4.1 |
| línea 92 | 9470 | 25.8 | 6.7 | 9461 | 25.7 | 6.6 |
| línea 152 | 19378 | 11.7 | 9.7 | 19374 | 11.7 | 9.6 |
| línea 168 | 9164 | 48.8 | 21.6 | 9149 | 48.7 | 21.5 |
| agregado | 63569 | 19.6 | 10.5 | 63484 | 19.5 | 10.3 |

### E. Sensibilidad de CuandoSubo al corrimiento del sello de CABA (agregado, banda 3–7 min)

| fuente / corrimiento | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| CuandoSubo, por coche, corrimiento 0 s | 21929 | 104 | 207 | 7.0 | 58.8 | 113 |
| CuandoSubo, por coche, corrimiento 60 s | 21929 | 78 | 163 | 18.5 | 33.9 | 84 |
| CuandoSubo, por coche, corrimiento 120 s | 21929 | 83 | 166 | 41.2 | 15.3 | 63 |
| modelo, por coche (no depende del corrimiento) | 23253 | 52 | 111 | 16.1 | 17.8 | 53 |

| próximo coche, agregado | n | MAE (s) | antes (%) | después (%) |
|---|---|---|---|---|
| CuandoSubo, corrimiento 0 s | 7581 | 128 | 14.6 | 52.9 |
| CuandoSubo, corrimiento 60 s | 7581 | 110 | 25.4 | 29.3 |
| CuandoSubo, corrimiento 120 s | 7581 | 121 | 47.1 | 13.3 |
| modelo (cualquier grupo) | 7612 | 99 | 12.9 | 29.1 |

### F. Por parada, banda 3–7 min (MAE por coche)

| línea | parada OBA → OSM | n CuandoSubo | MAE CuandoSubo (s) | n modelo | MAE modelo (s) |
|---|---|---|---|---|---|
| 152 | 14_S00081575 → n3447885521 | 2472 | 126 | 2503 | 54 |
| 152 | 14_S00081644 → n3646859385 | 2526 | 43 | 2475 | 38 |
| 152 | 14_S00081526 → n4911904604 | 2493 | 60 | 2395 | 51 |
| 168 | 14_S00094695 → n3606354766 | 421 | 127 | 504 | 64 |
| 168 | 14_S00094902 → n4704721415 | 1036 | 121 | 1167 | 54 |
| 168 | 14_S00094827 → n7727258306 | 636 | 65 | 1135 | 45 |
| 39 | 14_206600 → n1493476757 | 1871 | 62 | 1929 | 67 |
| 39 | 14_203270 → n2719439787 | 2320 | 77 | 2266 | 56 |
| 39 | 14_201063 → n3909887526 | 2114 | 70 | 2161 | 44 |
| 42 | 14_206135 → n13148755645 | 1042 | 45 | 1055 | 45 |
| 42 | 14_204691 → n2747920157 | 897 | 135 | 1030 | 62 |
| 42 | 14_20796 → n2892599806 | 1103 | 56 | 1113 | 49 |
| 92 | 14_203994 → n3048390056 | 951 | 73 | 1236 | 50 |
| 92 | 14_201704 → n3713013093 | 1197 | 73 | 1243 | 44 |
| 92 | 14_205731 → n5076531539 | 850 | 111 | 1041 | 87 |

### G. Por tipo de día (agregado, por coche, banda 3–7 min)

| tipo de día / fuente | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) | espera extra media (s) |
|---|---|---|---|---|---|---|
| hábiles (lun–vie): CuandoSubo | 15555 | 83 | 171 | 18.1 | 36.8 | 88 |
| hábiles (lun–vie): modelo | 16579 | 53 | 113 | 16.2 | 18.7 | 54 |
| fin de semana: CuandoSubo | 6374 | 67 | 140 | 19.4 | 27.0 | 71 |
| fin de semana: modelo | 6674 | 50 | 105 | 15.8 | 15.5 | 49 |

### H. Contexto de CuandoSubo en las paradas

Entradas de arribo con coche: 386471; de otra línea (por label): 88398; sin línea (label desconocido): 0; solo horario (sin tiempo real, sin coche): 255861.

Entradas de coches de la línea con tiempo real y `stops_away ≥ 0`: 221361; de ellas, coche presente en CABA ese día: 221361.
Antigüedad del GPS de CuandoSubo (t − `veh_ts`): P50 113 s, P90 149 s.