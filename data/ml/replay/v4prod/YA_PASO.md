# Regla causal de «ya pasó» sobre el próximo coche anunciado (replay v4, 126 líneas, 10 días)

Medido el 2026-11-23 sobre los crudos de `data/ml/replay/v4prod/v4/` (modelo `path_v4_l1_s1`; sin volver a predecir ni tocar `prediccion/replay`). Código en `data/ml/replay/v4prod/yapaso/`: `extrae.py` (filas listadas con eta0 <= 900 s), `edades.py` (edad del último ping, de los pings grabados, con `porcoche/calcula.py::ping_meta` sin modificar), `evalua.py` (calibración + variantes por línea -> `variantes.csv`, `calibracion.csv`), `informe.py` (tablas -> `tablas.md`). Corridas con prioridad Idle, afinidad 8 núcleos, `keep_awake.py` verificado.

## Regla

- Equivalencia de la app: `eta_consumed` = `eta_model - (edad + 60) <= 0` = `eta_s == 0` = `eta0_s <= 60` (verificado en los crudos: 956 879 filas con `eta_s == 0`, todas con `eta0_s <= 60` y a la inversa). Solo usa el ETA; no usa la edad.
- P(pasó) causal: P(`past` | eta0, edad del último ping en t), `past` = el coche cruzó la parada entre su último ping y t. Tabla de frecuencias empíricas, 10 bins de eta0 (0, 0-15, 15-30, 30-45, 45-60, 60-75, 75-90, 90-120, 120-180, 180-300 s; eta0 > 300 s: P = 0, medido 6e-5) x 5 bins de edad (<30, 30-60, 60-120, 120-240, >= 240 s), suavizado (+0,5/+1) y respaldo a la tabla solo por eta0 si la celda tiene < 300 filas o no hay edad. Se excluyen los coches `unv` (no verificables). Población: coches listados (top 5) de las 126 líneas.
- Sin trampa: validación cruzada por días. Pliegue A = 15-sep, 17-sep, 19-sep, 3-oct, 6-oct; pliegue B = 16-sep, 18-sep, 20-sep, 4-oct, 8-oct. Los días de A se evalúan con la tabla calibrada en B y los de B con la de A. No hay replay de otros días (el replay v4 son esos 10; el dataset de train no tiene `past`). Tablas en `yapaso/calibracion.csv`. Las dos tablas difieren poco salvo en edad >= 240 s (P 0,01-0,06 en A, hasta 0,38 en B): celda chica y ruidosa; no cambia las conclusiones.
- La edad entra porque con eta0 = 0 la P es 0,46-0,49 con edad < 30 s y 0,69-0,74 con edad 30-120 s. P máxima observada 0,74: el umbral 0,9 no mueve a ningún coche (idéntico a la base).
- Variantes: «baja» = el coche con P > umbral (o `eta_s == 0` en la regla de la app) pasa al final de la lista (queda anunciado si es el único); «saca» = sale de la lista. Umbrales 0,3 / 0,5 / 0,7 / 0,9. El anunciado es el primero de la lista en el orden de pantalla (seguros por ETA, luego el resto). En «saca» no entra un 6.º coche (los crudos solo guardan los 5 listados): subestima la ayuda de sacar y sobrestima el bondi no anunciado.
- Métricas: las de la vara vigente (corregida) sobre los mismos 10 días y 126 líneas: MAE del próximo coche en banda 3-7 min, llega antes / después > 60 s (error = anunciado - real; > 60 llega antes), sin anuncio, bondi fantasma (listados sin cruce, sin los ya pasados), bondi no anunciado (coches que pasan <= 10 min con ping vigente y no están en la lista), sin aviso firme, descomposición a-e (lógica de `descomposicion.py`). Chequeo de la base: MAE 116,92 s y n 1 193 075 con anuncio, igual a `DESCOMPOSICION.md`; casos a-f iguales.
- Agregado no pedido pero necesario para el balance: MAE del próximo coche con el real a 0-3 min y a 7-15 min. La vara 3-7 min elige los instantes por el paso real futuro; los coches que la regla baja o saca y que llegan en < 3 min no entran en esa banda, y su costo solo se ve en 0-3.

## Resultado, 126 líneas (1 228 348 instantes en la banda 3-7 min)

| variante | MAE 3-7 (s) | llega antes > 60 s % | llega después > 60 s % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | MAE 0-3 (s) | MAE 0-15 (s) | coches movidos | ya había pasado % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 116,9 | 17,6 | 23,0 | 20,99 | 9,83 | 11,86 | 71,9 | 123,3 | 0 | - |
| app, baja | 106,0 | 19,1 | 18,0 | 20,99 | 9,83 | 11,86 | 215,9 | 167,0 | 988 940 | 25,2 |
| app, saca | 105,4 | 19,1 | 17,7 | 21,53 | 19,66 | 14,67 | 219,9 | 167,2 | 988 940 | 25,2 |
| P > 0,3, baja | 107,7 | 18,7 | 19,1 | 20,99 | 9,83 | 11,86 | 100,0 | 124,8 | 442 140 | 47,3 |
| P > 0,3, saca | 107,3 | 18,7 | 18,9 | 21,10 | 12,13 | 12,69 | 100,3 | 124,2 | 442 140 | 47,3 |
| P > 0,5, baja | 113,6 | 18,0 | 21,6 | 20,99 | 9,83 | 11,86 | 74,3 | 120,9 | 123 605 | 66,5 |
| P > 0,5, saca | 113,4 | 18,0 | 21,6 | 21,02 | 10,10 | 12,05 | 74,4 | 120,7 | 123 605 | 66,5 |
| P > 0,7, baja | 115,5 | 17,7 | 22,4 | 20,99 | 9,83 | 11,86 | 72,6 | 122,1 | 46 889 | 70,1 |
| P > 0,7, saca | 115,5 | 17,7 | 22,4 | 21,01 | 9,94 | 11,93 | 72,6 | 122,1 | 46 889 | 70,1 |
| P > 0,9 (baja o saca) | 116,9 | 17,6 | 23,0 | 20,99 | 9,83 | 11,86 | 71,9 | 123,3 | 0 | - |

MAE 0-15 = MAE pooled de las tres bandas (0-3, 3-7, 7-15 min; 3 808 666 instantes; sin anuncio 3,33 % en la base). «Coches movidos» = filas coche-instante bajadas o sacadas; «ya había pasado %» = precisión de la regla (fracción con `past`).

## Descomposición a-e, 126 líneas (aporte al MAE en s; % de instantes)

| variante | (a) primero | (b) ya había pasado | (c) fantasma | (d) otro listado | (e) no anunciado | total |
|---|---:|---:|---:|---:|---:|---:|
| base | 38,7 (78,3) | 15,1 (5,5) | 29,3 (5,2) | 18,4 (7,9) | 14,9 (3,1) | 116,9 |
| app, baja | 40,8 (82,8) | 1,4 (0,6) | 28,3 (4,7) | 19,3 (8,5) | 15,8 (3,3) | 106,0 |
| app, saca | 40,8 (83,0) | 0,8 (0,4) | 28,2 (4,7) | 18,6 (8,3) | 16,6 (3,5) | 105,4 |
| P > 0,3, baja | 40,5 (82,0) | 3,3 (1,4) | 28,9 (5,0) | 19,0 (8,3) | 15,6 (3,3) | 107,7 |
| P > 0,5, baja | 39,4 (79,6) | 10,7 (3,9) | 29,3 (5,2) | 18,6 (8,1) | 15,1 (3,1) | 113,6 |
| P > 0,7, baja | 39,0 (78,8) | 13,3 (4,8) | 29,4 (5,2) | 18,5 (8,0) | 15,0 (3,1) | 115,5 |

(f) = 0,4 s en todas. Tablas completas por variante y por grupo (12 viejas, 34 de v3, 80 nuevas habilitadas = 72 nuevas + 8 habilitadas tarde, 126) al final.

## Lectura

- El caso (b) vale 15,1 s de los 116,9. La regla de la app (`eta_s == 0`) lo reduce a 1,4 s (baja) o 0,8 s (saca) y el MAE 3-7 baja a 106,0 / 105,4 s (-10,9 / -11,5 s), pero mueve 988 940 coches-instante, de los cuales solo el 25,2 % ya había pasado y el 58,4 % pasa en <= 10 min. Costo: MAE con el real a 0-3 min sube de 71,9 a 215,9 s (llega antes > 60 s en 0-3 min: 12,4 % -> 44,5 %) y el MAE 0-15 pooled de 123,3 a 167,0 s; empeora en las 126 líneas. Sacar suma bondi no anunciado 9,83 % -> 19,66 % y sin aviso firme 11,86 % -> 14,67 %.
- Regla con P > 0,5, baja: MAE 3-7 -3,3 s (116,9 -> 113,6), MAE 0-3 +2,4 s, MAE 0-15 -2,4 s (120,9); mejora 117 de 126 líneas en 0-15 (empeora 9, mediana -2,5 s); precisión 66,5 %. P > 0,7: -1,4 s, sin costo apreciable en 0-3 (+0,7 s). P > 0,3 se parece a la app: -9,2 s en 3-7 pero MAE 0-3 +28 s y 0-15 +1,5 s (mejora 51 líneas, empeora 75).
- «Saca» contra «baja»: 0,2-0,6 s menos de MAE 3-7, pero con P > 0,5 el bondi no anunciado sube 9,83 -> 10,10 %, con P > 0,3 a 12,13 % y con la app a 19,66 %. «Baja» deja la lista idéntica: bondi fantasma, bondi no anunciado y sin aviso firme no cambian.
- Ninguna variante toca (c), (d), (e): (c) 29,3 -> 28,2-29,4 s. El techo de una regla de «ya pasó» es el caso (b) de 15,1 s; P > 0,5 recupera 4,4 s de ellos (alta precisión, baja cobertura).
- Por grupo, MAE 3-7 base -> app baja / P > 0,5 baja: 12 viejas 94,6 -> 79,8 / 90,4; 34 de v3 129,0 -> 118,8 / 125,8; 80 nuevas 115,3 -> 104,7 / 112,0. Misma dirección en los tres. MAE 0-3 con la app: 44 -> 164 s (12), 88 -> 235 (34), 70 -> 218 (80).

## Límites

- 10 días, 2 pliegues; P depende de eta0 y edad, no de la línea. El pliegue B tiene celdas de edad >= 240 s con P distinto al A.
- «Saca» no repone el 6.º coche (no está en los crudos).
- La vara condiciona por el paso real futuro: el MAE 3-7 premia bajar coches que en producción serían el próximo en llegar; por eso se informa 0-3 y 0-15.
- La regla de la app es hoy solo presentación (texto «llegando o recién pasó»); lo medido acá es usarla para reordenar o sacar.

## Tablas completas por grupo

### 12 viejas (n banda 3-7 min: 128,757)

| variante | MAE 3-7 (s) | llega antes > 60 s % | llega despues > 60 s % | sin anuncio % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | MAE 0-3 (s) | antes/despues 0-3 % | MAE 7-15 (s) | coches movidos | % que ya habia pasado | % que pasa en <= 10 min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| base (sin regla) | 94.6 | 14.3 | 26.2 | 2.29 | 17.08 | 9.53 | 9.76 | 44.2 | 9.8 / 6.9 | 183.6 | 0 | - | - |
| app: ETA consumido, baja | 79.8 | 15.9 | 20.0 | 2.29 | 17.08 | 9.53 | 9.76 | 163.6 | 44.4 / 1.5 | 149.8 | 129,698 | 24.8 | 59.1 |
| app: ETA consumido, saca | 79.0 | 16.0 | 19.7 | 2.67 | 17.45 | 19.53 | 12.61 | 165.5 | 45.0 / 1.4 | 147.3 | 129,698 | 24.8 | 59.1 |
| P > 0.3, baja | 82.4 | 15.5 | 21.4 | 2.29 | 17.08 | 9.53 | 9.76 | 67.8 | 18.2 / 3.2 | 156.4 | 58,754 | 46.3 | 32.1 |
| P > 0.3, saca | 81.9 | 15.5 | 21.2 | 2.55 | 17.10 | 11.99 | 10.76 | 67.9 | 18.3 / 3.1 | 154.6 | 58,754 | 46.3 | 32.1 |
| P > 0.5, baja | 90.4 | 14.7 | 24.6 | 2.29 | 17.08 | 9.53 | 9.76 | 45.9 | 10.8 / 5.6 | 174.4 | 16,230 | 65.8 | 13.0 |
| P > 0.5, saca | 90.2 | 14.7 | 24.5 | 2.38 | 17.07 | 9.80 | 9.99 | 45.9 | 10.9 / 5.6 | 173.9 | 16,230 | 65.8 | 13.0 |
| P > 0.7, baja | 92.8 | 14.4 | 25.5 | 2.29 | 17.08 | 9.53 | 9.76 | 44.8 | 10.2 / 6.4 | 179.4 | 6,459 | 70.0 | 14.5 |
| P > 0.7, saca | 92.7 | 14.4 | 25.5 | 2.33 | 17.09 | 9.65 | 9.86 | 44.8 | 10.2 / 6.3 | 179.2 | 6,459 | 70.0 | 14.5 |
| P > 0.9, baja | 94.6 | 14.3 | 26.2 | 2.29 | 17.08 | 9.53 | 9.76 | 44.2 | 9.8 / 6.9 | 183.6 | 0 | - | - |
| P > 0.9, saca | 94.6 | 14.3 | 26.2 | 2.29 | 17.08 | 9.53 | 9.76 | 44.2 | 9.8 / 6.9 | 183.6 | 0 | - | - |

Descomposicion a-e, aporte al MAE en s (% de instantes), 12 viejas:

| variante | (a) | (b) ya habia pasado | (c) fantasma | (d) otro listado | (e) no anunciado | (f) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| base (sin regla) | 37.1 (75.6) | 19.2 (7.0) | 18.4 (5.6) | 9.8 (9.2) | 10.0 (2.6) | 0.2 (0.0) | 94.6 |
| app: ETA consumido, baja | 39.8 (81.3) | 1.7 (0.8) | 16.6 (5.0) | 10.5 (10.0) | 11.0 (2.8) | 0.1 (0.0) | 79.8 |
| app: ETA consumido, saca | 39.8 (81.6) | 1.1 (0.6) | 16.4 (5.0) | 10.0 (9.8) | 11.6 (3.1) | 0.1 (0.0) | 79.0 |
| P > 0.3, baja | 39.4 (80.3) | 4.1 (1.7) | 17.6 (5.4) | 10.2 (9.8) | 10.9 (2.8) | 0.1 (0.0) | 82.4 |
| P > 0.3, saca | 39.4 (80.4) | 3.6 (1.5) | 17.6 (5.4) | 10.0 (9.7) | 11.1 (2.9) | 0.1 (0.0) | 81.9 |
| P > 0.5, baja | 37.9 (77.1) | 13.7 (5.1) | 18.3 (5.6) | 10.0 (9.5) | 10.3 (2.7) | 0.2 (0.0) | 90.4 |
| P > 0.5, saca | 37.9 (77.2) | 13.5 (5.1) | 18.3 (5.6) | 10.0 (9.5) | 10.4 (2.7) | 0.2 (0.0) | 90.2 |
| P > 0.7, baja | 37.4 (76.2) | 16.8 (6.2) | 18.4 (5.6) | 9.9 (9.3) | 10.1 (2.6) | 0.2 (0.0) | 92.8 |
| P > 0.7, saca | 37.4 (76.3) | 16.7 (6.2) | 18.4 (5.6) | 9.9 (9.3) | 10.1 (2.6) | 0.2 (0.0) | 92.7 |
| P > 0.9, baja | 37.1 (75.6) | 19.2 (7.0) | 18.4 (5.6) | 9.8 (9.2) | 10.0 (2.6) | 0.2 (0.0) | 94.6 |
| P > 0.9, saca | 37.1 (75.6) | 19.2 (7.0) | 18.4 (5.6) | 9.8 (9.2) | 10.0 (2.6) | 0.2 (0.0) | 94.6 |

### 34 de v3 (n banda 3-7 min: 343,323)

| variante | MAE 3-7 (s) | llega antes > 60 s % | llega despues > 60 s % | sin anuncio % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | MAE 0-3 (s) | antes/despues 0-3 % | MAE 7-15 (s) | coches movidos | % que ya habia pasado | % que pasa en <= 10 min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| base (sin regla) | 129.0 | 18.7 | 22.9 | 3.04 | 23.20 | 10.39 | 12.16 | 88.3 | 13.9 / 5.8 | 202.5 | 0 | - | - |
| app: ETA consumido, baja | 118.8 | 20.2 | 18.2 | 3.04 | 23.20 | 10.39 | 12.16 | 235.4 | 45.4 / 1.5 | 176.2 | 261,225 | 25.4 | 58.4 |
| app: ETA consumido, saca | 118.2 | 20.3 | 17.9 | 3.38 | 23.84 | 20.14 | 14.93 | 239.6 | 46.4 / 1.4 | 174.0 | 261,225 | 25.4 | 58.4 |
| P > 0.3, baja | 120.5 | 19.8 | 19.2 | 3.04 | 23.20 | 10.39 | 12.16 | 116.4 | 21.1 / 2.9 | 181.2 | 114,006 | 48.6 | 30.0 |
| P > 0.3, saca | 120.1 | 19.9 | 19.0 | 3.27 | 23.37 | 12.58 | 12.94 | 116.8 | 21.1 / 2.9 | 179.6 | 114,006 | 48.6 | 30.0 |
| P > 0.5, baja | 125.8 | 19.1 | 21.6 | 3.04 | 23.20 | 10.39 | 12.16 | 90.8 | 14.9 / 4.8 | 194.8 | 31,179 | 69.7 | 13.1 |
| P > 0.5, saca | 125.7 | 19.1 | 21.6 | 3.11 | 23.25 | 10.65 | 12.33 | 90.9 | 14.9 / 4.8 | 194.4 | 31,179 | 69.7 | 13.1 |
| P > 0.7, baja | 127.7 | 18.9 | 22.4 | 3.04 | 23.20 | 10.39 | 12.16 | 89.1 | 14.2 / 5.4 | 199.2 | 11,536 | 73.5 | 13.1 |
| P > 0.7, saca | 127.7 | 18.9 | 22.4 | 3.06 | 23.22 | 10.49 | 12.22 | 89.1 | 14.2 / 5.4 | 199.1 | 11,536 | 73.5 | 13.1 |
| P > 0.9, baja | 129.0 | 18.7 | 22.9 | 3.04 | 23.20 | 10.39 | 12.16 | 88.3 | 13.9 / 5.8 | 202.5 | 0 | - | - |
| P > 0.9, saca | 129.0 | 18.7 | 22.9 | 3.04 | 23.20 | 10.39 | 12.16 | 88.3 | 13.9 / 5.8 | 202.5 | 0 | - | - |

Descomposicion a-e, aporte al MAE en s (% de instantes), 34 de v3:

| variante | (a) | (b) ya habia pasado | (c) fantasma | (d) otro listado | (e) no anunciado | (f) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| base (sin regla) | 38.2 (77.1) | 14.7 (5.2) | 31.9 (5.6) | 26.1 (8.6) | 17.4 (3.4) | 0.7 (0.1) | 129.0 |
| app: ETA consumido, baja | 40.1 (81.3) | 1.4 (0.6) | 30.9 (5.1) | 27.2 (9.2) | 18.4 (3.7) | 0.8 (0.1) | 118.8 |
| app: ETA consumido, saca | 40.1 (81.5) | 0.8 (0.4) | 30.9 (5.1) | 26.5 (8.9) | 19.1 (3.9) | 0.8 (0.1) | 118.2 |
| P > 0.3, baja | 39.9 (80.6) | 3.3 (1.3) | 31.5 (5.4) | 26.8 (9.0) | 18.2 (3.6) | 0.7 (0.1) | 120.5 |
| P > 0.3, saca | 39.9 (80.7) | 2.9 (1.2) | 31.5 (5.4) | 26.5 (8.9) | 18.5 (3.7) | 0.7 (0.1) | 120.1 |
| P > 0.5, baja | 38.9 (78.4) | 10.2 (3.8) | 31.9 (5.5) | 26.4 (8.8) | 17.7 (3.5) | 0.7 (0.1) | 125.8 |
| P > 0.5, saca | 38.9 (78.4) | 10.1 (3.7) | 31.9 (5.5) | 26.3 (8.7) | 17.8 (3.5) | 0.7 (0.1) | 125.7 |
| P > 0.7, baja | 38.4 (77.6) | 12.9 (4.6) | 32.0 (5.5) | 26.2 (8.7) | 17.5 (3.5) | 0.7 (0.1) | 127.7 |
| P > 0.7, saca | 38.4 (77.6) | 12.8 (4.6) | 32.0 (5.5) | 26.2 (8.7) | 17.5 (3.5) | 0.7 (0.1) | 127.7 |
| P > 0.9, baja | 38.2 (77.1) | 14.7 (5.2) | 31.9 (5.6) | 26.1 (8.6) | 17.4 (3.4) | 0.7 (0.1) | 129.0 |
| P > 0.9, saca | 38.2 (77.1) | 14.7 (5.2) | 31.9 (5.6) | 26.1 (8.6) | 17.4 (3.4) | 0.7 (0.1) | 129.0 |

### 80 nuevas habilitadas (n banda 3-7 min: 756,268)

| variante | MAE 3-7 (s) | llega antes > 60 s % | llega despues > 60 s % | sin anuncio % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | MAE 0-3 (s) | antes/despues 0-3 % | MAE 7-15 (s) | coches movidos | % que ya habia pasado | % que pasa en <= 10 min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| base (sin regla) | 115.3 | 17.6 | 22.5 | 2.89 | 20.68 | 9.65 | 12.11 | 70.1 | 12.2 / 5.8 | 196.8 | 0 | - | - |
| app: ETA consumido, baja | 104.7 | 19.1 | 17.6 | 2.89 | 20.68 | 9.65 | 12.11 | 217.7 | 44.1 / 1.4 | 170.6 | 598,017 | 25.3 | 58.2 |
| app: ETA consumido, saca | 104.1 | 19.2 | 17.3 | 3.23 | 21.18 | 19.47 | 14.92 | 222.1 | 45.1 / 1.3 | 168.2 | 598,017 | 25.3 | 58.2 |
| P > 0.3, baja | 106.3 | 18.7 | 18.6 | 2.89 | 20.68 | 9.65 | 12.11 | 99.2 | 19.7 / 2.8 | 175.9 | 269,380 | 46.9 | 30.6 |
| P > 0.3, saca | 105.9 | 18.8 | 18.4 | 3.13 | 20.76 | 11.97 | 12.93 | 99.6 | 19.8 / 2.7 | 174.2 | 269,380 | 46.9 | 30.6 |
| P > 0.5, baja | 112.0 | 18.0 | 21.1 | 2.89 | 20.68 | 9.65 | 12.11 | 72.7 | 13.2 / 4.8 | 189.4 | 76,196 | 65.3 | 13.1 |
| P > 0.5, saca | 111.9 | 18.0 | 21.1 | 2.95 | 20.70 | 9.93 | 12.29 | 72.8 | 13.2 / 4.8 | 188.9 | 76,196 | 65.3 | 13.1 |
| P > 0.7, baja | 113.9 | 17.8 | 21.9 | 2.89 | 20.68 | 9.65 | 12.11 | 70.9 | 12.6 / 5.4 | 193.6 | 28,894 | 68.7 | 13.3 |
| P > 0.7, saca | 113.8 | 17.8 | 21.9 | 2.91 | 20.69 | 9.76 | 12.17 | 70.9 | 12.6 / 5.4 | 193.4 | 28,894 | 68.7 | 13.3 |
| P > 0.9, baja | 115.3 | 17.6 | 22.5 | 2.89 | 20.68 | 9.65 | 12.11 | 70.1 | 12.2 / 5.8 | 196.8 | 0 | - | - |
| P > 0.9, saca | 115.3 | 17.6 | 22.5 | 2.89 | 20.68 | 9.65 | 12.11 | 70.1 | 12.2 / 5.8 | 196.8 | 0 | - | - |

Descomposicion a-e, aporte al MAE en s (% de instantes), 80 nuevas habilitadas:

| variante | (a) | (b) ya habia pasado | (c) fantasma | (d) otro listado | (e) no anunciado | (f) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| base (sin regla) | 39.2 (79.3) | 14.7 (5.3) | 30.1 (5.0) | 16.4 (7.4) | 14.6 (3.0) | 0.3 (0.1) | 115.3 |
| app: ETA consumido, baja | 41.2 (83.7) | 1.3 (0.6) | 29.1 (4.5) | 17.3 (7.9) | 15.4 (3.2) | 0.3 (0.1) | 104.7 |
| app: ETA consumido, saca | 41.2 (84.0) | 0.8 (0.4) | 29.0 (4.4) | 16.5 (7.7) | 16.2 (3.4) | 0.3 (0.1) | 104.1 |
| P > 0.3, baja | 40.9 (82.9) | 3.2 (1.3) | 29.6 (4.8) | 17.0 (7.8) | 15.2 (3.2) | 0.3 (0.1) | 106.3 |
| P > 0.3, saca | 40.9 (83.1) | 2.8 (1.2) | 29.6 (4.7) | 16.5 (7.6) | 15.7 (3.3) | 0.3 (0.0) | 105.9 |
| P > 0.5, baja | 39.9 (80.6) | 10.3 (3.8) | 30.0 (5.0) | 16.6 (7.5) | 14.8 (3.1) | 0.3 (0.1) | 112.0 |
| P > 0.5, saca | 39.9 (80.6) | 10.2 (3.8) | 30.0 (5.0) | 16.5 (7.5) | 15.0 (3.1) | 0.3 (0.1) | 111.9 |
| P > 0.7, baja | 39.5 (79.8) | 12.9 (4.7) | 30.1 (5.0) | 16.5 (7.4) | 14.7 (3.0) | 0.3 (0.1) | 113.9 |
| P > 0.7, saca | 39.5 (79.8) | 12.8 (4.7) | 30.1 (5.0) | 16.4 (7.4) | 14.7 (3.0) | 0.3 (0.1) | 113.8 |
| P > 0.9, baja | 39.2 (79.3) | 14.7 (5.3) | 30.1 (5.0) | 16.4 (7.4) | 14.6 (3.0) | 0.3 (0.1) | 115.3 |
| P > 0.9, saca | 39.2 (79.3) | 14.7 (5.3) | 30.1 (5.0) | 16.4 (7.4) | 14.6 (3.0) | 0.3 (0.1) | 115.3 |

### 126 agregado (n banda 3-7 min: 1,228,348)

| variante | MAE 3-7 (s) | llega antes > 60 s % | llega despues > 60 s % | sin anuncio % | bondi fantasma % | bondi no anunciado % | sin aviso firme % | MAE 0-3 (s) | antes/despues 0-3 % | MAE 7-15 (s) | coches movidos | % que ya habia pasado | % que pasa en <= 10 min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|
| base (sin regla) | 116.9 | 17.6 | 23.0 | 2.87 | 20.99 | 9.83 | 11.86 | 71.9 | 12.4 / 6.0 | 197.3 | 0 | - | - |
| app: ETA consumido, baja | 106.0 | 19.1 | 18.0 | 2.87 | 20.99 | 9.83 | 11.86 | 215.9 | 44.5 / 1.5 | 170.5 | 988,940 | 25.2 | 58.4 |
| app: ETA consumido, saca | 105.4 | 19.1 | 17.7 | 3.21 | 21.53 | 19.66 | 14.67 | 219.9 | 45.5 / 1.3 | 168.1 | 988,940 | 25.2 | 58.4 |
| P > 0.3, baja | 107.7 | 18.7 | 19.1 | 2.87 | 20.99 | 9.83 | 11.86 | 100.0 | 19.9 / 2.9 | 175.8 | 442,140 | 47.3 | 30.6 |
| P > 0.3, saca | 107.3 | 18.7 | 18.9 | 3.11 | 21.10 | 12.13 | 12.69 | 100.3 | 20.0 / 2.8 | 174.1 | 442,140 | 47.3 | 30.6 |
| P > 0.5, baja | 113.6 | 18.0 | 21.6 | 2.87 | 20.99 | 9.83 | 11.86 | 74.3 | 13.4 / 4.9 | 189.7 | 123,605 | 66.5 | 13.1 |
| P > 0.5, saca | 113.4 | 18.0 | 21.6 | 2.94 | 21.02 | 10.10 | 12.05 | 74.4 | 13.4 / 4.9 | 189.2 | 123,605 | 66.5 | 13.1 |
| P > 0.7, baja | 115.5 | 17.7 | 22.4 | 2.87 | 20.99 | 9.83 | 11.86 | 72.6 | 12.7 / 5.5 | 194.0 | 46,889 | 70.1 | 13.4 |
| P > 0.7, saca | 115.5 | 17.7 | 22.4 | 2.89 | 21.01 | 9.94 | 11.93 | 72.6 | 12.7 / 5.5 | 193.8 | 46,889 | 70.1 | 13.4 |
| P > 0.9, baja | 116.9 | 17.6 | 23.0 | 2.87 | 20.99 | 9.83 | 11.86 | 71.9 | 12.4 / 6.0 | 197.3 | 0 | - | - |
| P > 0.9, saca | 116.9 | 17.6 | 23.0 | 2.87 | 20.99 | 9.83 | 11.86 | 71.9 | 12.4 / 6.0 | 197.3 | 0 | - | - |

Descomposicion a-e, aporte al MAE en s (% de instantes), 126 agregado:

| variante | (a) | (b) ya habia pasado | (c) fantasma | (d) otro listado | (e) no anunciado | (f) | total |
|---|---:|---:|---:|---:|---:|---:|---:|
| base (sin regla) | 38.7 (78.3) | 15.1 (5.5) | 29.3 (5.2) | 18.4 (7.9) | 14.9 (3.1) | 0.4 (0.1) | 116.9 |
| app: ETA consumido, baja | 40.8 (82.8) | 1.4 (0.6) | 28.3 (4.7) | 19.3 (8.5) | 15.8 (3.3) | 0.4 (0.1) | 106.0 |
| app: ETA consumido, saca | 40.8 (83.0) | 0.8 (0.4) | 28.2 (4.7) | 18.6 (8.3) | 16.6 (3.5) | 0.4 (0.1) | 105.4 |
| P > 0.3, baja | 40.5 (82.0) | 3.3 (1.4) | 28.9 (5.0) | 19.0 (8.3) | 15.6 (3.3) | 0.4 (0.1) | 107.7 |
| P > 0.3, saca | 40.5 (82.1) | 2.9 (1.2) | 28.9 (5.0) | 18.6 (8.2) | 16.0 (3.4) | 0.4 (0.1) | 107.3 |
| P > 0.5, baja | 39.4 (79.6) | 10.7 (3.9) | 29.3 (5.2) | 18.6 (8.1) | 15.1 (3.1) | 0.4 (0.1) | 113.6 |
| P > 0.5, saca | 39.4 (79.7) | 10.5 (3.9) | 29.3 (5.2) | 18.5 (8.0) | 15.3 (3.2) | 0.4 (0.1) | 113.4 |
| P > 0.7, baja | 39.0 (78.8) | 13.3 (4.8) | 29.4 (5.2) | 18.5 (8.0) | 15.0 (3.1) | 0.4 (0.1) | 115.5 |
| P > 0.7, saca | 39.0 (78.8) | 13.2 (4.8) | 29.4 (5.2) | 18.5 (8.0) | 15.0 (3.1) | 0.4 (0.1) | 115.5 |
| P > 0.9, baja | 38.7 (78.3) | 15.1 (5.5) | 29.3 (5.2) | 18.4 (7.9) | 14.9 (3.1) | 0.4 (0.1) | 116.9 |
| P > 0.9, saca | 38.7 (78.3) | 15.1 (5.5) | 29.3 (5.2) | 18.4 (7.9) | 14.9 (3.1) | 0.4 (0.1) | 116.9 |

<!-- chequeo base: max dif n_con 0 ; max dif |sum_abs| (s) 554.33 ; MAE 126 desc. 116.92 -->
<!-- p50_dem: MAE por linea delta mediana -3.0, mejora 121 lineas, empeora 5, peor 3.0 -->
<!-- p70_dem: MAE por linea delta mediana -1.1, mejora 118 lineas, empeora 8, peor 1.3 -->
<!-- app_dem: MAE por linea delta mediana -9.5, mejora 118 lineas, empeora 8, peor 14.2 -->
