# Vara de producto (replay) de `path_v4_l1_s1` y re-evaluación de las líneas sin habilitar

Medido el 2026-11-22. Modelo en producción `data/ml/export/path_v4_l1_s1` (contrato 2.3), 118 líneas habilitadas. Bondi fantasma, bondi no anunciado, sin aviso firme y llega antes / después usan la vara vigente de `ARQUITECTURA.md` §5 (verdad por recorrido ex post; bondi fantasma = coche listado con ETA anunciado ≤ 40 min que no cruza). «Sin aviso firme» es un problema de la app (cómo agrupa los coches que ya encontró), no del modelo. «Llega antes / después» = el próximo coche anunciado llega más de 60 s antes / después de lo anunciado, banda de ETA real 3–7 min.

## Método

- Variante `base`, regla `trailing_run`, lógica de la app fijada en `prediccion/replay/pinned/`; mismos 10 días que `V3_PRODUCCION.md` (2026-09-15 a 20, 10-03, 10-04, 10-06, 10-08), 40 paradas por línea (mitad tronco compartido, mitad tramo exclusivo; menos si la línea tiene menos paradas utilizables, p. ej. 154 con 18), instantes cada 10 min de 6 a 23 h. No se redujeron las paradas.
- v4: 118 habilitadas + 9 sin habilitar (49, 97, 119, 153, 154, 163, 164, 185, 193) = 127 líneas × 10 días (1.263 pares línea-día; la 26 solo tiene 3 días). Crudos: `data/ml/replay/v4prod/v4/`.
- v3 (`path_v3_l1_s1`) con la vara vigente: 12 líneas viejas reusadas de `data/ml/replay/vara/run_base_xp` (9 días) y `run_cs_xp` (3 de oct., variante `base`); las otras 34 de las 46 habilitadas con v3, corridas de nuevo con el pin vigente en `data/ml/replay/v4prod/v3/` (340 pares línea-día).
- Comparación pareada: ambas corridas se restringen a los mismos (línea, día, parada, t). La verdad (`real_next2_s`) es idéntica en todas las filas comunes (0 diferencias) y los coches listados coinciden; por eso bondi fantasma, bondi no anunciado y sin aviso firme son casi idénticos entre v3 y v4 (dependen de la lista de candidatos, no del modelo).
- Corrida: 4 lanzadores con 2 workers (8 procesos), prioridad Idle (también los workers), afinidad 8 núcleos (máscara 0xFF hasta las 16:08 y 0x5555 después: 8 hilos en 8 núcleos físicos distintos); 15:52 a 21:52 (6,0 h de pared). `data/ml/replay/v4prod/run_idle.py` fuerza Idle en los workers (`run.run_day` los deja en BELOW_NORMAL).

## Resultado

### Grupos (v4)

| grupo | líneas | n banda | MAE (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % |
|---|---:|---:|---|---|---|---|---|---|
| 12 viejas | 12 | 128757 | 94 | 14.3 | 26.2 | 16.3 | 8.6 | 9.7 |
| 34 de v3 | 34 | 343323 | 129 | 18.7 | 22.9 | 21.0 | 9.2 | 12.1 |
| 72 nuevas | 72 | 701483 | 119 | 17.5 | 23.0 | 19.2 | 8.7 | 12.1 |
| 118 habilitadas | 118 | 1173563 | 119 | 17.5 | 23.3 | 19.4 | 8.8 | 11.9 |
| 9 sin habilitar | 9 | 59113 | 95 | 20.8 | 15.9 | 16.3 | 7.1 | 8.8 |

(Promedio de las tasas por línea ponderado por n de la banda; no es una tasa agregada recalculada.)

### v4 contra v3, pareado (46 líneas habilitadas con v3)

Diferencia de MAE por línea (v4 − v3): mediana -0.9 s, rango -10.9 a +1.3 s; v4 mejor en 37 de 46 líneas.

| línea | n banda | MAE v3 → v4 (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % |
|---|---:|---|---|---|---|---|---|
| 26 | 3108 | 76 → 77 | 12.3 → 12.9 | 28.7 → 29.5 | 2.6 → 2.6 | 5.9 → 5.9 | 2.0 → 2.0 |
| 39 | 12900 | 89 → 78 | 10.2 → 9.8 | 30.8 → 27.6 | 29.8 → 29.7 | 6.5 → 6.4 | 22.6 → 22.6 |
| 42 | 10591 | 190 → 184 | 16.7 → 15.9 | 33.2 → 32.4 | 32.2 → 32.1 | 8.6 → 8.6 | 12.5 → 12.5 |
| 50 | 10318 | 79 → 79 | 16.4 → 16.0 | 23.2 → 24.0 | 24.9 → 25.0 | 6.7 → 6.8 | 12.9 → 12.9 |
| 92 | 12307 | 67 → 67 | 14.2 → 14.2 | 20.5 → 21.8 | 6.7 → 6.8 | 4.9 → 4.9 | 2.8 → 2.8 |
| 106 | 11684 | 148 → 145 | 14.8 → 14.8 | 29.5 → 29.8 | 14.2 → 14.2 | 15.7 → 15.8 | 5.4 → 5.4 |
| 107 | 10148 | 106 → 106 | 21.0 → 21.7 | 22.0 → 22.0 | 9.0 → 9.0 | 10.4 → 10.4 | 11.9 → 11.9 |
| 108 | 11104 | 74 → 71 | 13.7 → 13.6 | 23.9 → 23.2 | 11.7 → 11.7 | 6.6 → 6.6 | 3.6 → 3.6 |
| 124 | 14313 | 72 → 70 | 13.0 → 13.2 | 21.9 → 21.9 | 4.3 → 4.3 | 4.0 → 4.0 | 2.6 → 2.6 |
| 132 | 11691 | 83 → 83 | 11.3 → 11.0 | 30.8 → 31.6 | 20.8 → 20.8 | 13.1 → 13.1 | 15.7 → 15.7 |
| 151 | 11142 | 83 → 82 | 13.6 → 13.0 | 30.1 → 30.3 | 7.5 → 7.5 | 12.8 → 12.8 | 7.9 → 7.9 |
| 168 | 9451 | 94 → 93 | 16.4 → 16.4 | 22.6 → 22.9 | 26.7 → 26.8 | 7.2 → 7.2 | 12.1 → 12.1 |
| 4 | 11617 | 71 → 70 | 14.1 → 14.0 | 21.3 → 21.6 | 26.3 → 26.5 | 4.5 → 4.5 | 14.0 → 14.0 |
| 7 | 7945 | 129 → 129 | 24.7 → 25.5 | 17.5 → 17.8 | 39.3 → 39.3 | 14.9 → 14.9 | 26.0 → 26.0 |
| 9 | 11999 | 112 → 114 | 18.6 → 18.6 | 22.6 → 23.4 | 8.1 → 8.8 | 9.1 → 9.1 | 8.4 → 8.4 |
| 20 | 8639 | 75 → 74 | 18.8 → 18.0 | 20.7 → 21.2 | 19.4 → 19.4 | 6.2 → 6.2 | 7.9 → 7.9 |
| 25 | 11120 | 81 → 80 | 19.5 → 18.8 | 19.1 → 20.0 | 11.3 → 11.4 | 6.8 → 6.8 | 6.2 → 6.2 |
| 28 | 8774 | 187 → 185 | 30.4 → 30.0 | 25.8 → 26.2 | 44.7 → 44.5 | 22.8 → 22.4 | 17.3 → 17.3 |
| 29 | 11326 | 331 → 328 | 34.0 → 33.7 | 17.6 → 17.6 | 21.3 → 21.5 | 21.7 → 21.7 | 18.0 → 18.0 |
| 33 | 10720 | 134 → 134 | 18.2 → 17.3 | 23.1 → 23.8 | 27.7 → 27.7 | 10.1 → 10.0 | 17.7 → 17.7 |
| 34 | 9578 | 102 → 95 | 7.1 → 7.1 | 44.7 → 43.0 | 39.9 → 39.6 | 17.2 → 16.1 | 14.3 → 14.3 |
| 41 | 12778 | 74 → 70 | 11.9 → 11.4 | 24.7 → 24.2 | 4.5 → 4.4 | 1.9 → 1.9 | 0.4 → 0.4 |
| 44 | 12249 | 73 → 73 | 14.6 → 14.4 | 22.5 → 23.6 | 5.1 → 5.2 | 6.2 → 6.2 | 2.2 → 2.2 |
| 46 | 9527 | 104 → 104 | 19.5 → 18.7 | 19.1 → 19.3 | 28.5 → 28.6 | 3.6 → 3.6 | 24.7 → 24.7 |
| 47 | 8074 | 68 → 67 | 13.1 → 13.4 | 20.7 → 21.2 | 31.5 → 31.6 | 5.5 → 5.5 | 12.5 → 12.5 |
| 62 | 5747 | 106 → 107 | 25.1 → 25.3 | 25.0 → 24.4 | 21.6 → 21.6 | 18.5 → 18.5 | 20.6 → 20.6 |
| 74 | 8712 | 70 → 70 | 14.3 → 14.1 | 18.4 → 19.2 | 5.1 → 5.1 | 5.1 → 5.1 | 5.0 → 5.0 |
| 76 | 12313 | 71 → 70 | 15.6 → 15.1 | 22.0 → 22.1 | 4.3 → 4.3 | 5.2 → 5.2 | 5.0 → 5.0 |
| 84 | 13382 | 67 → 67 | 15.4 → 15.1 | 20.0 → 20.4 | 3.8 → 3.9 | 4.9 → 4.9 | 3.2 → 3.2 |
| 85 | 9563 | 141 → 137 | 18.6 → 18.6 | 22.5 → 21.9 | 28.3 → 28.2 | 3.6 → 3.5 | 8.2 → 8.2 |
| 98 | 10503 | 224 → 224 | 24.2 → 23.9 | 20.7 → 20.8 | 28.7 → 28.8 | 17.0 → 17.0 | 12.9 → 12.9 |
| 102 | 12789 | 86 → 85 | 16.0 → 15.4 | 27.4 → 27.7 | 8.3 → 8.3 | 23.7 → 23.7 | 15.5 → 15.5 |
| 110 | 12230 | 79 → 78 | 13.4 → 13.4 | 24.5 → 24.9 | 19.3 → 19.3 | 1.3 → 1.3 | 11.0 → 11.0 |
| 113 | 10247 | 73 → 72 | 14.7 → 14.2 | 21.7 → 22.7 | 25.7 → 25.7 | 2.9 → 2.9 | 10.5 → 10.5 |
| 114 | 9362 | 110 → 110 | 19.4 → 20.5 | 22.4 → 22.0 | 9.2 → 9.2 | 8.2 → 8.2 | 7.2 → 7.2 |
| 115 | 10141 | 127 → 126 | 14.3 → 13.9 | 27.9 → 28.4 | 17.7 → 17.7 | 15.3 → 15.3 | 9.4 → 9.4 |
| 118 | 12583 | 192 → 190 | 23.3 → 23.3 | 24.1 → 24.0 | 17.8 → 17.8 | 17.9 → 17.9 | 4.2 → 4.2 |
| 123 | 11353 | 80 → 79 | 17.2 → 17.2 | 18.3 → 17.6 | 8.5 → 8.5 | 7.7 → 7.7 | 6.7 → 6.7 |
| 127 | 8897 | 71 → 70 | 14.6 → 15.4 | 21.0 → 20.8 | 32.3 → 32.4 | 0.9 → 0.9 | 26.0 → 26.0 |
| 143 | 8341 | 72 → 72 | 13.5 → 14.2 | 21.2 → 21.3 | 15.8 → 15.8 | 2.7 → 2.7 | 2.3 → 2.3 |
| 169 | 9734 | 127 → 126 | 22.2 → 20.9 | 20.7 → 22.3 | 26.6 → 26.6 | 7.8 → 7.8 | 17.8 → 17.8 |
| 180 | 6939 | 150 → 149 | 22.5 → 23.0 | 28.0 → 27.9 | 58.3 → 58.3 | 9.4 → 9.4 | 42.2 → 42.2 |
| 184 | 12594 | 76 → 74 | 14.2 → 14.8 | 18.2 → 17.6 | 11.0 → 10.9 | 3.7 → 3.7 | 0.7 → 0.7 |
| 188 | 8406 | 569 → 567 | 42.1 → 42.6 | 19.0 → 18.2 | 39.5 → 39.5 | 12.2 → 12.2 | 27.0 → 27.0 |
| 194 | 8353 | 276 → 275 | 26.7 → 27.3 | 35.3 → 33.4 | 34.4 → 35.8 | 15.9 → 15.8 | 23.3 → 23.3 |
| 197 | 6788 | 285 → 284 | 21.3 → 23.3 | 25.9 → 22.5 | 48.9 → 48.8 | 5.5 → 5.5 | 21.8 → 21.8 |
| **12 líneas viejas** | 128757 | 97.0 → 94.6 | 14.4 → 14.3 | 26.3 → 26.2 | 17.1 → 17.1 | 9.5 → 9.5 | 9.8 → 9.8 |
| **34 líneas (v3 nuevas)** | 343323 | 130.2 → 129.0 | 18.8 → 18.7 | 22.9 → 22.9 | 23.1 → 23.2 | 10.5 → 10.4 | 12.2 → 12.2 |
| **46 líneas** | 472080 | 121.0 → 119.6 | 17.6 → 17.5 | 23.8 → 23.8 | 21.4 → 21.5 | 10.2 → 10.1 | 11.5 → 11.5 |

Lectura: v4 no cambia el producto en las 46 líneas habilitadas (MAE 121,0 → 119,6 s; llega antes 17,6 → 17,5 %; llega después 23,8 → 23,8 %). Bondi fantasma, bondi no anunciado y sin aviso firme coinciden dentro de 0,1 pp en el agregado. La mejora mayor es la 39 (89 → 78 s); la peor diferencia por línea es +1,3 s. Las 12 líneas viejas reproducen la referencia de §5 (97 → 95 s).

## Líneas nuevas: propuesta de aviso `quality: "baja"`

Criterio idéntico al usado con v3 (`V3_PRODUCCION.md`, conclusión 4) con la vara vigente. Para cada una de 6 métricas (MAE 3–7 min, llega antes, llega después, bondi fantasma, bondi no anunciado, sin aviso firme) umbral = mediana + 1,5 × (MAD × 1,4826), calculado sobre las 72 líneas nuevas. Una línea se marca si supera el umbral en el MAE o en 2 o más métricas.

Umbrales (72 líneas): MAE 136 s, llega antes 25,8 %, llega después 28,9 %, bondi fantasma 46,0 %, bondi no anunciado 15,1 %, sin aviso firme 30,3 % (mediana de MAE 89 s; MAD×1,4826 = 32 s).

| línea | n banda | MAE (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | marca |
|---|---:|---:|---|---|---|---|---|---|
| 8 | 8652 | 464 | 30.8 | 30.9 | 39.3 | 15.9 | 18.7 | **BAJA** MAE,llega antes,llega después,bondi no anunciado |
| 45 | 10616 | 380 | 33.9 | 19.6 | 24.2 | 13.3 | 6.0 | **BAJA** MAE,llega antes |
| 80 | 10821 | 376 | 31.8 | 20.2 | 25.3 | 26.0 | 15.8 | **BAJA** MAE,llega antes,bondi no anunciado |
| 182 | 8272 | 323 | 26.6 | 22.4 | 38.0 | 20.2 | 28.2 | **BAJA** MAE,llega antes,bondi no anunciado |
| 145 | 7484 | 319 | 24.5 | 22.2 | 37.9 | 5.6 | 15.7 | **BAJA** MAE |
| 136 | 2463 | 255 | 26.6 | 17.3 | 65.7 | 7.8 | 35.8 | **BAJA** MAE,llega antes,bondi fantasma,sin aviso firme |
| 166 | 9754 | 253 | 20.9 | 19.2 | 17.9 | 8.6 | 5.5 | **BAJA** MAE |
| 21 | 9909 | 239 | 28.2 | 26.3 | 43.2 | 28.8 | 20.6 | **BAJA** MAE,llega antes,bondi no anunciado |
| 96 | 5681 | 225 | 20.2 | 29.6 | 57.1 | 7.4 | 24.5 | **BAJA** MAE,llega después,bondi fantasma |
| 100 | 11807 | 202 | 24.7 | 22.6 | 24.4 | 11.0 | 14.9 | **BAJA** MAE |
| 160 | 9201 | 199 | 19.8 | 23.5 | 17.7 | 7.0 | 6.0 | **BAJA** MAE |
| 95 | 11299 | 195 | 24.6 | 21.7 | 27.6 | 3.4 | 16.3 | **BAJA** MAE |
| 55 | 10003 | 186 | 20.9 | 23.4 | 32.9 | 10.3 | 29.5 | **BAJA** MAE |
| 159 | 4223 | 163 | 26.0 | 31.3 | 38.9 | 39.0 | 15.4 | **BAJA** MAE,llega antes,llega después,bondi no anunciado |
| 57 | 5694 | 159 | 19.9 | 25.8 | 54.7 | 8.9 | 34.1 | **BAJA** MAE,bondi fantasma,sin aviso firme |
| 178 | 8157 | 156 | 20.2 | 20.2 | 44.9 | 6.9 | 25.7 | **BAJA** MAE |
| 15 | 9021 | 149 | 24.7 | 21.8 | 22.0 | 8.0 | 14.2 | **BAJA** MAE |
| 195 | 5768 | 139 | 19.1 | 18.7 | 48.5 | 11.2 | 7.7 | **BAJA** MAE,bondi fantasma |
| 60 | 9642 | 132 | 24.3 | 21.7 | 36.9 | 19.3 | 16.2 | bondi no anunciado |
| 51 | 5406 | 129 | 22.7 | 16.0 | 43.9 | 12.0 | 22.9 |  |
| 86 | 5415 | 127 | 20.1 | 26.7 | 55.8 | 8.9 | 34.1 | **BAJA** bondi fantasma,sin aviso firme |
| 91 | 7770 | 125 | 22.2 | 19.2 | 24.4 | 15.1 | 6.3 | bondi no anunciado |
| 174 | 9781 | 122 | 21.8 | 18.1 | 31.0 | 8.0 | 12.5 |  |
| 176 | 7978 | 112 | 19.8 | 21.9 | 44.7 | 10.4 | 20.3 |  |
| 63 | 10738 | 111 | 11.1 | 25.8 | 31.4 | 4.2 | 28.0 |  |
| 87 | 7820 | 111 | 20.3 | 18.4 | 24.5 | 8.7 | 2.1 |  |
| 68 | 9706 | 111 | 7.1 | 37.0 | 5.1 | 25.2 | 52.8 | **BAJA** llega después,bondi no anunciado,sin aviso firme |
| 161 | 11403 | 108 | 20.5 | 19.7 | 16.2 | 16.9 | 9.5 | bondi no anunciado |
| 31 | 10420 | 105 | 17.6 | 29.5 | 17.6 | 8.9 | 13.7 | llega después |
| 105 | 12843 | 105 | 14.8 | 27.9 | 29.5 | 12.1 | 21.9 |  |
| 177 | 3685 | 97 | 14.1 | 22.3 | 12.3 | 30.9 | 21.9 | bondi no anunciado |
| 129 | 6435 | 96 | 23.8 | 22.7 | 42.1 | 7.3 | 18.3 |  |
| 32 | 7266 | 92 | 23.3 | 16.1 | 4.5 | 6.5 | 7.9 |  |
| 12 | 11267 | 91 | 9.3 | 31.4 | 7.2 | 15.2 | 6.2 | **BAJA** llega después,bondi no anunciado |
| 64 | 12588 | 91 | 10.9 | 34.2 | 17.2 | 7.9 | 13.2 | llega después |
| 53 | 11292 | 89 | 16.5 | 26.7 | 16.0 | 7.5 | 1.3 |  |
| 1 | 9988 | 88 | 18.2 | 15.4 | 11.2 | 5.5 | 3.0 |  |
| 37 | 9252 | 85 | 16.8 | 25.3 | 43.4 | 11.7 | 17.9 |  |
| 101 | 10846 | 84 | 16.9 | 23.8 | 20.5 | 4.4 | 10.7 |  |
| 158 | 1826 | 84 | 10.9 | 31.9 | 2.8 | 17.7 | 9.7 | **BAJA** llega después,bondi no anunciado |
| 24 | 12552 | 83 | 17.8 | 22.1 | 5.4 | 5.2 | 1.2 |  |
| 117 | 9801 | 83 | 16.7 | 22.2 | 13.5 | 9.5 | 5.3 |  |
| 59 | 11154 | 82 | 11.7 | 27.5 | 24.5 | 11.0 | 20.5 |  |
| 130 | 11364 | 81 | 14.3 | 27.9 | 19.7 | 3.7 | 9.5 |  |
| 56 | 9921 | 80 | 15.1 | 22.4 | 10.0 | 8.0 | 16.1 |  |
| 22 | 10885 | 78 | 20.6 | 16.5 | 4.8 | 5.2 | 3.6 |  |
| 152 | 11057 | 77 | 4.7 | 31.7 | 4.2 | 15.7 | 11.2 | **BAJA** llega después,bondi no anunciado |
| 65 | 12412 | 77 | 13.9 | 24.3 | 4.0 | 6.2 | 2.7 |  |
| 2 | 11872 | 77 | 18.4 | 21.6 | 8.3 | 6.9 | 3.6 |  |
| 79 | 1783 | 76 | 8.5 | 36.5 | 11.0 | 1.9 | 2.2 | llega después |
| 133 | 12376 | 75 | 19.2 | 18.5 | 6.5 | 5.4 | 2.2 |  |
| 126 | 13458 | 73 | 10.7 | 25.0 | 8.7 | 3.1 | 15.9 |  |
| 150 | 11465 | 73 | 12.8 | 26.3 | 9.9 | 6.3 | 6.9 |  |
| 140 | 12175 | 73 | 17.9 | 21.0 | 7.0 | 2.6 | 2.0 |  |
| 93 | 5492 | 72 | 15.9 | 22.8 | 31.3 | 3.7 | 25.1 |  |
| 109 | 12108 | 72 | 11.1 | 25.9 | 7.7 | 4.3 | 2.8 |  |
| 128 | 14110 | 72 | 17.3 | 19.9 | 4.9 | 6.2 | 5.3 |  |
| 111 | 10535 | 70 | 19.4 | 19.5 | 4.9 | 2.1 | 2.9 |  |
| 134 | 12861 | 69 | 17.1 | 18.3 | 3.3 | 2.8 | 1.6 |  |
| 146 | 13029 | 69 | 15.5 | 21.1 | 4.4 | 9.8 | 8.6 |  |
| 78 | 11715 | 68 | 10.3 | 24.2 | 26.6 | 6.8 | 15.6 |  |
| 172 | 10214 | 68 | 14.1 | 17.8 | 25.6 | 7.0 | 17.8 |  |
| 103 | 11179 | 67 | 15.9 | 20.0 | 7.7 | 2.3 | 3.3 |  |
| 10 | 12499 | 67 | 14.3 | 20.5 | 3.5 | 2.3 | 2.2 |  |
| 17 | 12791 | 67 | 9.8 | 23.3 | 4.0 | 3.1 | 0.6 |  |
| 71 | 10812 | 67 | 11.2 | 25.2 | 32.9 | 1.2 | 20.9 |  |
| 70 | 11616 | 67 | 16.4 | 18.7 | 7.1 | 7.3 | 7.7 |  |
| 19 | 12474 | 66 | 13.9 | 20.6 | 8.6 | 1.8 | 2.4 |  |
| 67 | 13535 | 66 | 9.8 | 23.8 | 5.0 | 2.3 | 0.6 |  |
| 181 | 10376 | 65 | 13.7 | 20.3 | 29.1 | 3.5 | 22.9 |  |
| 135 | 13447 | 65 | 15.8 | 19.2 | 1.3 | 8.0 | 7.0 |  |
| 179 | 8223 | 64 | 20.4 | 16.5 | 29.2 | 9.3 | 31.6 | sin aviso firme |
| **mediana** | | 89 | 17.7 | 22.2 | 18.8 | 7.6 | 11.9 | |
| **MAD×1,4826** | | 32 | 5.4 | 4.5 | 18.1 | 4.9 | 12.3 | |
| **umbral (mediana + 1,5·MAD)** | | 136 | 25.8 | 28.9 | 46.0 | 15.1 | 30.3 | |

**Propuesta (23 líneas):** 8, 12, 15, 21, 45, 55, 57, 68, 80, 86, 95, 96, 100, 136, 145, 152, 158, 159, 160, 166, 178, 182, 195.

- 18 por MAE > 136 s: 8 (464 s), 45, 80, 182, 145, 136, 166, 21, 96, 100, 160, 95, 55, 159, 57, 178, 15, 195 (139 s).
- 5 por 2 o más métricas sin MAE alto: 12, 68, 86, 152, 158. Son marginales: en 12, 152 y 158 la métrica más baja pasa el umbral por 3 pp o menos.
- Con la mediana de las 118 líneas como referencia (MAE 129 s) se agrega la 60 y el resto no cambia (24 líneas).
- Muestras chicas (n de la banda < 4.000): 136 (2.463), 158 (1.826), 79 (1.783), 177 (3.685). La marca de 136 y 158 es menos firme.
- Las 72 pasaron el criterio de habilitación en la vara del modelo (MAE ≤ 71,1 s en el eval congelado); en el replay el MAE del próximo coche de varias es 2 a 6 veces mayor. La diferencia viene de qué coche se anuncia como próximo (ramal / sentido desconocido, §5), no del ETA por coche.

Solo propuesta: no se aplicó en `proyectoconsola`.

### Las 8 líneas con aviso actual, medidas con v4

| línea | MAE v4 (s) | marcas con v4 (referencia: las 34 líneas de v3) | marca |
|---|---:|---|---|
| 7 | 129 | sin aviso firme | ya no |
| 28 | 185 | MAE,llega antes,bondi no anunciado | BAJA |
| 29 | 328 | MAE,llega antes,bondi no anunciado | BAJA |
| 98 | 224 | MAE,bondi no anunciado | BAJA |
| 180 | 149 | llega después,bondi fantasma,sin aviso firme | BAJA |
| 188 | 567 | MAE,llega antes,sin aviso firme | BAJA |
| 194 | 275 | MAE,llega antes,llega después,bondi no anunciado | BAJA |
| 197 | 284 | MAE,bondi fantasma | BAJA |

Umbrales (34 líneas, v4): MAE 164, llega antes 25.5, llega después 26.5, bondi fantasma 45.4, bondi no anunciado 15.6, sin aviso firme 25.4. Líneas de esas 34 que hoy serían BAJA: 28, 29, 34, 98, 102, 118, 180, 188, 194, 197.

Con v4, 7 queda sin marca (su único motivo restante es sin aviso firme, problema de la app) y las otras 7 siguen marcadas. Con los umbrales de las 34 líneas de v3 también quedarían marcadas 34, 102 y 118, que hoy no tienen aviso (34: llega después 43,0 %; 102: bondi no anunciado 23,7 %; 118: MAE 190 s); no se propone cambiarlas en este informe.

## Experimento 2: líneas sin habilitar (49, 97, 119, 153, 154, 163, 185, 193 y 164)

Eval ampliado (no toca `data/ml/v4/eval`): todas las filas válidas de los 25 días de val de `data/ml/v4/daily` (los de `eval_meta.json`, 2026-09-15 a 10-14) con ETA real 3–7 min, de las 9 líneas, evaluadas con el checkpoint de `path_v4_l1_s1` (`data/ml/v4_sub/runs/path_lr2e-3_s1/path_eta_best.pt`). 323245 filas, de las cuales 927 ya estaban en el eval congelado. Carpeta: `data/ml/v4_eval_ext/` (`ext_seen.parquet`, `ext_pred.npy`, `resultados.csv`, `build_and_eval.py`, `analisis.py`). Criterio de habilitación de §7: n ≥ 100 y MAE ≤ 71,1 s (1,3 × la mediana de 54,7 s de las 46 habilitadas; el umbral no se recalculó). Las filas de un mismo viaje están correlacionadas: el IC principal es un bootstrap de 2.000 réplicas remuestreando clusters (día, línea, recorrido, ventana de 30 min de `ts_p`); el IC iid es optimista. La muestra es la población de la banda, no la estratificada por ETA del eval congelado, así que el MAE difiere un poco del congelado.

| línea | n filas (3–7 min) | clusters | MAE (s) | IC 95 % (bootstrap por cluster) | IC 95 % (iid) | MAE solo filas del eval congelado (n) | MAE solo filas adicionales | llega antes % | llega después % | start_unknown % | pasa (n ≥ 100, MAE ≤ 71,1) |
|---|---:|---:|---:|---|---|---|---|---|---|---|---|
| 49 | 29779 | 1794 | 44.5 | 43.9–45.1 | 44.1–44.9 | 51.0 (97) | 44.5 | 11.3 | 15.0 | 8 | sí |
| 153 | 26631 | 2267 | 45.1 | 44.4–45.8 | 44.6–45.6 | 48.4 (70) | 45.1 | 10.7 | 15.5 | 9 | sí |
| 154 | 22248 | 1685 | 47.2 | 46.5–47.9 | 46.6–47.7 | 45.0 (68) | 47.2 | 14.8 | 14.5 | 6 | sí |
| 185 | 34898 | 3512 | 47.6 | 47.0–48.1 | 47.1–48.0 | 53.6 (92) | 47.5 | 11.4 | 18.1 | 9 | sí |
| 119 | 40676 | 2251 | 49.1 | 48.5–49.7 | 48.7–49.5 | 42.2 (97) | 49.1 | 14.1 | 17.1 | 7 | sí |
| 97 | 42834 | 1987 | 49.9 | 49.2–50.6 | 49.4–50.4 | 48.6 (99) | 49.9 | 12.4 | 18.4 | 39 | sí |
| 193 | 25972 | 1860 | 53.4 | 52.5–54.4 | 52.9–54.0 | 47.6 (71) | 53.5 | 12.9 | 20.3 | 12 | sí |
| 163 | 13748 | 2077 | 54.6 | 53.7–55.5 | 53.8–55.4 | 53.7 (57) | 54.6 | 13.8 | 21.2 | 43 | sí |
| 164 | 86459 | 7410 | 67.6 | 66.2–69.0 | 66.6–68.5 | 72.3 (276) | 67.5 | 15.5 | 20.6 | 74 | sí |

- Pasan las 9 el criterio de la vara del modelo. 164: 67,6 s (IC 66,2–69,0; el límite superior queda debajo de 71,1 s). Las otras 8: 44,5 a 54,6 s con límite superior del IC ≤ 55,5 s. El MAE en las filas adicionales coincide con el del pool completo; el 72,4 s de la 164 se reproduce en las filas congeladas (72,3 s, 276 filas).
- `start_unknown`: 164 74 %, 163 43 %, 97 39 %.

### Esas líneas en el replay (vara de producto, v4, mismos 10 días)

| línea | n banda | MAE (s) | llega antes % | llega después % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | n días / paradas |
|---|---:|---:|---|---|---|---|---|---|
| 49 | 8884 | 59 | 16.7 | 12.3 | 5.1 | 2.0 | 2.3 | 10 / 40 |
| 97 | 7463 | 82 | 18.5 | 20.3 | 19.5 | 10.7 | 9.1 | 10 / 40 |
| 119 | 10955 | 77 | 22.8 | 14.8 | 6.6 | 7.6 | 6.0 | 10 / 40 |
| 153 | 7048 | 58 | 17.5 | 12.6 | 12.0 | 3.4 | 4.6 | 10 / 40 |
| 154 | 3376 | 70 | 22.4 | 17.1 | 22.4 | 13.1 | 15.6 | 10 / 18 |
| 163 | 2920 | 75 | 20.8 | 17.2 | 21.3 | 4.6 | 10.4 | 10 / 40 |
| 185 | 6211 | 78 | 16.6 | 17.9 | 25.6 | 6.0 | 13.3 | 10 / 40 |
| 193 | 7928 | 66 | 21.0 | 16.2 | 8.9 | 6.4 | 7.7 | 10 / 40 |
| 164 | 4328 | 404 | 37.9 | 18.2 | 58.0 | 16.6 | 24.8 | 10 / 40 |

- 49, 97, 119, 153, 154, 163, 185 y 193: MAE del próximo coche 58–82 s, llega antes 16,6–22,8 %, bondi fantasma 5–26 %, bondi no anunciado 2–13 %, sin aviso firme 2–16 %; dentro de lo mejor de las líneas habilitadas (mediana de MAE de las 72 nuevas: 89 s). Las muestras más chicas: 154 (n = 3.376, 18 paradas) y 163 (n = 2.920).
- 164 no pasa en el replay: MAE 404 s, llega antes 37,9 %, bondi fantasma 58,0 %. Pasa la vara del modelo y falla la de producto (coincide con su `start_unknown` de 74 %). No se propone habilitarla.

## Conclusiones

1. v4 equivale a v3 en producto en las 46 líneas habilitadas: MAE 121,0 → 119,6 s, mediana de la diferencia por línea −0,9 s, v4 mejor en 37 de 46.
2. Propuesta de `quality: "baja"` para 23 de las 72 líneas nuevas (18 por MAE > 136 s, 5 por 2 o más métricas).
3. Líneas a habilitar: 49, 97, 119, 153, 154, 163, 185, 193. 164: no.

## Salvedades

Una corrida por modelo (sin semillas); 10 días; 40 paradas por línea muestreadas; los huecos de GPS afectan igual a v3 y v4; la propuesta de calidad compara cada línea con la dispersión del grupo de 72, no con un valor absoluto.

## Comandos

Desde `prediccion colectivos/`, Python `C:\Users\LK\AppData\Local\Programs\Python\Python313\python.exe`, `PYTHONPATH=.`:
```powershell
# replay: 3 lanzadores v4 (data/ml/replay/v4prod/lines_v4_{0,1,2}.txt) y 1 de v3 (lines_v3_34.txt), 2 workers c/u, Idle
powershell -File data/ml/replay/v4prod/lanzar.ps1 -Out data/ml/replay/v4prod/v4 -Model data/ml/export/path_v4_l1_s1 -Lines <lista> -Days <10 días> -Workers 2 -Tag v4_0
powershell -File data/ml/replay/v4prod/lanzar.ps1 -Out data/ml/replay/v4prod/v3 -Model data/ml/export/path_v3_l1_s1 -Lines <34 líneas> -Days <10 días> -Workers 2 -Tag v3_34
#   lanzar.ps1: python -u data/ml/replay/v4prod/run_idle.py --model .. --variants base --lines .. --days .. --stops 40 --out .. --workers 2  (+ keep_awake.py <pid>)
# tablas
powershell -File data/ml/replay/v4prod/rep.ps1        # reporte.py -> resumen.pkl
python data/ml/replay/v4prod/tablas_md.py             # tablas.md
python data/ml/replay/v4prod/informe.py               # este informe
# experimento 2
powershell -File data/ml/v4_eval_ext/lanzar.ps1       # build_and_eval.py (~50 s)
python data/ml/v4_eval_ext/analisis.py                # resultados.csv
```
