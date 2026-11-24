# Vara de producto: v3 (48 líneas) contra v2c en producción

> **Registro (2026-11-16):** las falsas alarmas, la omisión y el «viene» vacío de este informe usan la definición anterior de la vara de producto. Siguen válidos como comparaciones relativas; las falsas alarmas absolutas están infladas (≈ 24,5 contra ≈ 14,7 % con la vara corregida) y la omisión y el «viene» vacío absolutos algo subestimados. Ver `VARA_CORREGIDA.md` y `ARQUITECTURA.md` §5.

Replay en condiciones de producción (`prediccion/replay/`, vara de producto de `ARQUITECTURA.md` §5) del modelo en producción desde 2026-11-15 (`data/ml/export/path_v3_l1_s1`, contrato 2.2, 48 líneas en el modelo, 46 habilitadas en la app: todas menos 61 y 88) contra el anterior (`path_v2c_l1_s1`, contrato 2.1, 12 líneas). Comandos: `python -m prediccion.replay.run --model <export> --variants base --workers 2 --out data/ml/replay/v3prod/{v2c,v3}` (v3 con las 48 líneas del manifest, v2c con las 12 de producción) y `python -m prediccion.replay.report_v3 ...`. Datos crudos: `data/ml/replay/v3prod/{v2c,v3}/`; tablas generadas: `data/ml/replay/v3prod/tablas.md`; las 34 líneas nuevas en `data/ml/replay/V3_PRODUCCION.nuevas.csv`.

## Método

- **Mismas muestras que `ORACULO_RAMAL.md`:** 40 paradas por línea (mitad tronco compartido, mitad tramo exclusivo; líneas de un solo recorrido por sentido, «únicas»), instantes cada 10 min de 6 a 23 h, 10 días (15, 16, 17, 18, 19, 20 de sep. y 3, 4, 6, 8 de oct.; la línea 26 solo tiene datos 15–17 de sep.). Variante `base` (producción: ramal y sentido por historial y geometría). Verdad: cruce de la parada con pings futuros compatibles, interpolado entre dos pings a lo sumo 10 min separados; horizonte 40 min. Las 465.560 parejas (parada, t) de las 12 líneas son idénticas para los dos modelos; la comparación es pareada.
- **Re-pin (2026-11-15) de `prediccion/replay/pinned/`:** copia de `prediccion/inference/path_reference.py` actual (sha256 3f23cb3c665eb4d0…; contrato 2.2 con paradas por tramo `seg_stop_n`/`seg_stop_next` y el desempate de proyección `PROJECT_TIE_M` = 1e-6 m, primer segmento ante empate) y de `prediccion/v2/geo_assign.py` (sin cambios respecto del pin anterior; `models/stops.py` se importa del árbol, sha256 131f100f11275a72…). Antes estaba fijado el commit e7479f7 (contrato 2.1). Chequeo: v2c con el pin nuevo reproduce los números base de `ORACULO_RAMAL.md` (MAE 107 s, falsas alarmas 24,0 %, omisión 17,0 %, «viene» vacío 13,7 %): el re-pin no movió la vara. Detalle de las adaptaciones en `pinned/__init__.py`.
- **Port de la app:** `predict_from_raw` del pin acepta `snapshot_ts` y `ts_offset_s` como `core.js` (`predictFromRaw`): `ts_age` = hora de la foto (máximo `ts` de los coches de la línea en t) menos `ts` del ping, y ETA anunciado = máx(0, ETA del modelo − (t − ts) − `CABA_TS_OFFSET_S` = 60 s). Defaults = comportamiento anterior. Igual para los dos modelos.
- **Corrección de hora de CABA:** el sello `ts` de CABA se estima 60 s adelantado respecto de la hora real del GPS. En el replay los pings y el paso real están en la misma hora del sello, así que el descuento de 60 s se cancela (la app, con reloj real, lo resta porque la antigüedad del ping le sale subestimada). Las tablas principales miden el ETA en esa hora común (columna `ann0` del replay), equivalente a lo que muestra la app corregida contra la hora real. **Sensibilidad:** si el ETA se descuenta 60 s contra el paso medido en la hora del sello (fórmula de la app sin cambiar de reloj), el coche llega después de lo anunciado en más de 60 s en 53–56 % de los casos de la banda y el MAE sube a 125–128 s: es un artefacto del reloj, no un efecto del modelo (tabla de sensibilidad). La validez del corrimiento de 60 s en sí no se mide acá (necesita verdad de campo).
- **Métricas:** banda de tiempo real al próximo coche 3–7 min. Próximo coche anunciado = primero del grupo «viene» y, si no hay, primero de «puede venir» o provisional. MAE en s; «llega antes» = el coche llega más de 60 s antes de lo anunciado; «llega después» = más de 60 s después. Falsas alarmas: coches listados que no pasan en 40 min. Omisión: coches con ping vigente que pasan en ≤10 min y no están en la lista de 5. «Viene» vacío: instantes sin ningún «viene» aunque un coche pasa en ≤10 min.
- **Días extra:** no se extendió (el replay de 48 líneas × 10 días tomó ~5,5 h con 2 workers a baja prioridad).


## Conclusión

1. **12 líneas de producción: v3 no empeora ni mejora el producto.** MAE del próximo coche en 3–7 min 107 s con los dos modelos; llega antes >60 s 18,4 % (v2c) → 17,0 % (v3); llega después >60 s 23,1 % → 24,5 %. Falsas alarmas, omisión y «viene» vacío son idénticas (24,0 / 17,0 / 13,7 %): dependen de la elección de candidatos (geometría, historial), no del modelo. Por línea el MAE se mueve ≤2 s; v3 baja el llega antes en las 12 líneas (más en 124: 15,9 → 13,4 %, 151: 18,9 → 16,2 %) y sube el llega después en casi todas: un desplazamiento del anuncio hacia más tarde, no una ganancia de precisión. Coincide con la vara del modelo (55,9 vs 56,1 s).
2. **Las líneas de producción más flojas lo siguen siendo:** 107 (MAE 202 s, omisión 32,8 %), 42 (165 s, falsas alarmas 39,9 %), 168, 132 y 106 (115–118 s). Mismo cuadro que `ORACULO_RAMAL.md` (ramal desconocido, no modelo).
3. **Las 34 líneas nuevas quedan algo peor que las 12 viejas, con mucha dispersión:** agregado MAE 124 s (llega antes 19,9 %, después 22,0 %, falsas alarmas 31,7 %, omisión 18,4 %, «viene» vacío 15,9 %) contra 107 s de las 12 viejas. Mediana por línea 105 s (MAD×1,4826 = 43 s) contra 90 s en las 12 viejas; 13 de las 34 líneas están en ≤80 s, a la par de las mejores viejas.
4. **Candidatas a deshabilitar (claramente peor que la mediana de las 34; criterio: MAE, o ≥2 métricas, a más de 1,5 desvíos robustos de la mediana):**
   - **188** (MAE 455 s, llega antes 36,6 %), **29** (236 s, 29,0 %), **197** (241 s, falsas alarmas 55,5 %), **28** (184 s, omisión 37,6 %), **98** (201 s, 28,9 %) y **194** (190 s, llega después 35,5 %): peores en MAE.
   - **7** (164 s, llega antes 29,2 %, «viene» vacío 37,4 %) y **180** (158 s, falsas alarmas 59,4 %, «viene» vacío 41,6 %): peores en confiabilidad de la lista.
   - 188 es el único muy por fuera; 29, 197, 98 y 194 duplican la mediana. Marginales sin marca (MAE 128–158 s): 25, 33, 85, 114, 118. Ninguna tiene muestra chica (≥6.800 parejas en banda).
   - Cuáles deshabilitar es decisión de producto; el replay no mide el costo de ocultar una línea.
5. **Líneas 61 y 88 (no habilitadas): en el replay no son atípicas.** 61: MAE 97 s, llega antes 16,9 %, llega después 31,0 %, falsas alarmas 16,3 %. 88: 112 s, 19,6 %, 22,0 %, falsas alarmas 55,6 %. Ambas dentro de la dispersión de las 34 (mediana 105 s). Los 133 s (61) y 92 s (88) de la vara del modelo salen de 82 y 180 filas de eval: muestras chicas. No hay evidencia de defecto del modelo; sí datos escasos (61: 38 coches en 10 días, 68 % de los instantes con paso ≤20 min, 2,7 coches evaluados por instante; 88: 79 % de `start_unknown` en el dataset, falsas alarmas altas). La razón para mantenerlas fuera es la cobertura y la lista poco confiable (88), no el error del modelo.
6. **Salvedades:** una corrida por modelo (sin semillas); 10 días sin extensión; los huecos de GPS sobrestiman falsas alarmas y omisiones por igual en ambos modelos; la omisión no cuenta coches sin ping vigente; los números por línea dependen de 40 paradas muestreadas por línea.


## Tablas

Días: 2026-09-15, 2026-09-16, 2026-09-17, 2026-09-18, 2026-09-19, 2026-09-20, 2026-10-03, 2026-10-04, 2026-10-06, 2026-10-08. Cada celda sale de los (parada, t) con coche real en la banda 3–7 min (próximo coche = primero del grupo «viene» y, si no hay, primero de «puede venir»/provisional).

### 1. 12 líneas de producción: v2c vs v3 (mismos días, paradas e instantes)

(parada, t) comunes: 465560 de 465560 (v2c) y 465560 (v3).

#### Agregado (ponderado por n)

| modelo | n (parada,t) en banda | MAE próximo 3–7 min (s) | llega antes >60 s % | llega después >60 s % | falsas alarmas % | omisión ≤10 min % | «viene» vacío % | sin anuncio 3–7 min % |
|---|---|---|---|---|---|---|---|---|
| v2c_l1_s1 (contrato 2.1) | 128566 | 107 | 18.4 | 23.1 | 24.0 | 17.0 | 13.7 | 7.5 |
| v3_l1_s1 (contrato 2.2) | 128566 | 107 | 17.0 | 24.5 | 24.0 | 17.0 | 13.7 | 7.5 |

#### Por línea

| línea | n banda | MAE v2c → v3 (s) | llega antes % v2c → v3 | llega después % v2c → v3 | falsas alarmas % v2c → v3 | omisión % v2c → v3 | «viene» vacío % v2c → v3 |
|---|---|---|---|---|---|---|---|
| 26 | 3138 | 82 → 81 | 14.8 → 14.4 | 28.7 → 28.6 | 7.2 → 7.2 | 16.8 → 16.8 | 10.2 → 10.2 |
| 39 | 12973 | 87 → 87 | 13.9 → 13.7 | 23.7 → 23.9 | 30.4 → 30.4 | 11.6 → 11.6 | 24.6 → 24.6 |
| 42 | 10189 | 163 → 165 | 20.0 → 18.4 | 29.1 → 31.3 | 39.9 → 39.9 | 16.4 → 16.4 | 18.9 → 18.9 |
| 50 | 10253 | 89 → 89 | 17.7 → 17.4 | 22.2 → 22.4 | 32.0 → 32.0 | 16.4 → 16.4 | 20.0 → 20.0 |
| 92 | 12335 | 81 → 81 | 16.9 → 16.7 | 19.5 → 19.7 | 15.0 → 15.0 | 9.1 → 9.1 | 4.1 → 4.1 |
| 106 | 11763 | 115 → 115 | 17.5 → 15.8 | 26.8 → 28.4 | 18.0 → 18.1 | 16.6 → 16.7 | 7.3 → 7.3 |
| 107 | 10088 | 203 → 202 | 32.9 → 30.9 | 17.3 → 18.8 | 17.9 → 17.9 | 32.8 → 32.8 | 18.0 → 18.0 |
| 108 | 10909 | 82 → 81 | 17.6 → 15.7 | 20.3 → 22.0 | 24.1 → 24.1 | 10.9 → 10.9 | 5.9 → 5.9 |
| 124 | 14624 | 77 → 76 | 15.9 → 13.4 | 20.6 → 22.1 | 10.0 → 10.0 | 7.3 → 7.3 | 5.3 → 5.3 |
| 132 | 11754 | 117 → 118 | 16.1 → 14.6 | 27.1 → 29.9 | 25.4 → 25.4 | 23.5 → 23.5 | 22.4 → 22.4 |
| 151 | 11327 | 91 → 91 | 18.9 → 16.2 | 25.4 → 28.8 | 12.7 → 12.7 | 22.1 → 22.1 | 13.3 → 13.3 |
| 168 | 9213 | 117 → 117 | 21.7 → 21.0 | 20.1 → 21.0 | 40.5 → 40.5 | 17.2 → 17.2 | 13.2 → 13.2 |
| **12 líneas (agregado)** | 128566 | **107 → 107** | 18.4 → 17.0 | 23.1 → 24.5 | 24.0 → 24.0 | 17.0 → 17.0 | 13.7 → 13.7 |

#### Sensibilidad a la corrección de hora (12 líneas, agregado)

| criterio | modelo | MAE 3–7 min (s) | llega antes >60 s % | llega después >60 s % |
|---|---|---|---|---|
| con corrección de hora (ann0) | v2c | 107 | 18.4 | 23.1 |
| con corrección de hora (ann0) | v3 | 107 | 17.0 | 24.5 |
| ETA − 60 s contra el paso en la hora del sello (ann) | v2c | 125 | 8.0 | 53.2 |
| ETA − 60 s contra el paso en la hora del sello (ann) | v3 | 128 | 7.5 | 55.7 |

#### Por tipo de parada (12 líneas)

| tipo | modelo | n banda | MAE (s) | llega antes % | llega después % | falsas alarmas % | «viene» vacío % |
|---|---|---|---|---|---|---|---|
| compartido | v2c | 57295 | 124 | 20.3 | 24.1 | 16.0 | 11.0 |
| compartido | v3 | 57295 | 124 | 18.7 | 25.9 | 16.0 | 11.0 |
| exclusivo | v2c | 30265 | 113 | 17.5 | 24.3 | 45.6 | 30.5 |
| exclusivo | v3 | 30265 | 113 | 16.7 | 25.5 | 45.6 | 30.5 |
| unico | v2c | 41006 | 80 | 16.6 | 20.8 | 15.6 | 5.5 |
| unico | v3 | 41006 | 79 | 15.1 | 21.8 | 15.7 | 5.5 |

### 2. Las 34 líneas nuevas habilitadas (solo v3)

| línea | n banda | MAE (s) | llega antes % | llega después % | falsas alarmas % | omisión % | «viene» vacío % | sin anuncio % | marca |
|---|---|---|---|---|---|---|---|---|---|
| 4 | 11709 | 79 | 15.6 | 20.5 | 35.8 | 12.9 | 20.9 | 8.6 |  |
| 7 | 7700 | 164 | 29.2 | 15.5 | 53.3 | 28.8 | 37.4 | 17.3 | PEOR: antes, vacio |
| 9 | 12085 | 88 | 16.2 | 22.8 | 13.9 | 12.6 | 12.8 | 6.9 |  |
| 20 | 8545 | 82 | 20.3 | 20.1 | 30.3 | 18.1 | 15.8 | 14.0 |  |
| 25 | 10742 | 128 | 25.4 | 17.0 | 28.0 | 17.1 | 12.0 | 9.7 |  |
| 28 | 9525 | 184 | 30.2 | 26.1 | 44.5 | 37.6 | 25.7 | 12.6 | PEOR: mae, antes, om |
| 29 | 11356 | 236 | 29.0 | 19.7 | 33.0 | 22.1 | 19.3 | 5.5 | PEOR: mae, antes |
| 33 | 10595 | 130 | 21.7 | 22.3 | 38.5 | 19.0 | 21.7 | 8.4 |  |
| 34 | 9446 | 105 | 9.9 | 42.4 | 47.3 | 29.4 | 19.5 | 5.6 |  |
| 41 | 12849 | 78 | 13.0 | 23.2 | 13.2 | 4.4 | 1.8 | 2.0 |  |
| 44 | 12211 | 78 | 14.8 | 23.5 | 13.1 | 18.7 | 12.9 | 14.8 |  |
| 46 | 9571 | 118 | 22.8 | 17.4 | 38.4 | 9.3 | 22.5 | 1.4 |  |
| 47 | 8025 | 74 | 13.8 | 19.7 | 40.3 | 9.6 | 16.4 | 8.3 |  |
| 62 | 7074 | 106 | 22.6 | 26.4 | 25.5 | 24.4 | 19.7 | 13.8 |  |
| 74 | 8610 | 67 | 14.6 | 17.7 | 20.6 | 8.4 | 8.1 | 8.8 |  |
| 76 | 12354 | 76 | 16.7 | 20.9 | 12.9 | 16.7 | 12.3 | 13.3 |  |
| 84 | 13336 | 68 | 16.2 | 18.6 | 10.6 | 10.6 | 8.5 | 9.3 |  |
| 85 | 9579 | 130 | 18.4 | 21.2 | 36.7 | 6.8 | 8.4 | 1.2 |  |
| 98 | 10374 | 201 | 28.9 | 19.1 | 36.0 | 26.0 | 14.5 | 1.3 | PEOR: mae, antes |
| 102 | 12608 | 107 | 20.0 | 25.5 | 15.5 | 31.0 | 19.9 | 21.1 |  |
| 110 | 12262 | 73 | 12.4 | 24.5 | 22.8 | 1.8 | 10.8 | 1.6 |  |
| 113 | 10220 | 75 | 15.4 | 21.5 | 35.1 | 6.2 | 12.5 | 1.8 |  |
| 114 | 9360 | 158 | 24.6 | 20.2 | 24.6 | 18.6 | 11.1 | 6.8 |  |
| 115 | 10225 | 120 | 17.9 | 24.6 | 18.1 | 26.1 | 17.8 | 18.0 |  |
| 118 | 13024 | 156 | 27.2 | 23.5 | 21.9 | 26.7 | 5.0 | 2.5 |  |
| 123 | 10787 | 70 | 15.5 | 18.3 | 15.3 | 16.9 | 14.4 | 15.4 |  |
| 127 | 8984 | 78 | 16.1 | 20.2 | 42.3 | 3.5 | 26.5 | 1.9 |  |
| 143 | 8391 | 73 | 13.7 | 20.7 | 25.4 | 4.8 | 3.7 | 3.1 |  |
| 169 | 9707 | 89 | 18.3 | 21.4 | 33.3 | 19.6 | 22.9 | 12.2 |  |
| 180 | 6958 | 158 | 25.8 | 24.1 | 59.4 | 19.9 | 41.6 | 3.7 | PEOR: fa, vacio |
| 184 | 11935 | 87 | 16.1 | 17.5 | 22.8 | 11.7 | 5.5 | 6.1 |  |
| 188 | 9204 | 455 | 36.6 | 16.8 | 46.8 | 30.8 | 19.5 | 6.3 | PEOR: mae, antes |
| 194 | 8415 | 190 | 23.0 | 35.5 | 44.8 | 17.3 | 23.8 | 0.7 | PEOR: mae, despues |
| 197 | 6847 | 241 | 24.4 | 20.1 | 55.5 | 9.9 | 21.7 | 3.5 | PEOR: mae, fa |
| **mediana** | | **105** | 18.3 | 20.8 | 31.6 | 17.2 | 16.1 | | |
| **MAD×1,4826** | | 43 | 6.5 | 3.6 | 15.1 | 11.1 | 7.7 | | |

Agregado v3:

| grupo | n (parada,t) en banda | MAE próximo 3–7 min (s) | llega antes >60 s % | llega después >60 s % | falsas alarmas % | omisión ≤10 min % | «viene» vacío % | sin anuncio 3–7 min % |
|---|---|---|---|---|---|---|---|---|
| 12 líneas de producción | 128566 | 107 | 17.0 | 24.5 | 24.0 | 17.0 | 13.7 | 7.5 |
| 34 líneas nuevas | 344613 | 124 | 19.9 | 22.0 | 31.7 | 18.4 | 15.9 | 7.9 |

### 3. Líneas 61 y 88 (no habilitadas; solo v3)

| línea | n (parada,t) en banda | MAE próximo 3–7 min (s) | llega antes >60 s % | llega después >60 s % | falsas alarmas % | omisión ≤10 min % | «viene» vacío % | sin anuncio 3–7 min % |
|---|---|---|---|---|---|---|---|---|
| 61 | 6882 | 97 | 16.9 | 31.0 | 16.3 | 13.4 | 7.8 | 7.1 |
| 88 | 6512 | 112 | 19.6 | 22.0 | 55.6 | 8.0 | 3.4 | 0.7 |

Contexto de datos de la muestra (v3):

| línea | paradas | coches con ping | instantes (parada,t) | con paso ≤20 min % | coches evaluados por instante |
|---|---|---|---|---|---|
| 61 | 32 | 38 | 32960 | 68.3 | 2.65 |
| 88 | 40 | 64 | 41200 | 63.1 | 5.35 |
| 50 | 40 | 72 | 41200 | 84.9 | 6.54 |
| 39 | 40 | 93 | 41200 | 97.5 | 10.72 |

### Variabilidad por día (agregado v3, 12 líneas / 34 nuevas)

| día | MAE 12 líneas (s) | MAE 34 nuevas (s) |
|---|---|---|
| 2026-09-15 | 109 | 124 |
| 2026-09-16 | 114 | 126 |
| 2026-09-17 | 110 | 123 |
| 2026-09-18 | 128 | 134 |
| 2026-09-19 | 98 | 117 |
| 2026-09-20 | 105 | 117 |
| 2026-10-03 | 93 | 121 |
| 2026-10-04 | 81 | 123 |
| 2026-10-06 | 106 | 123 |
| 2026-10-08 | 121 | 130 |
