# E2 en lineas de control: cobertura de la grilla vs error

Script: `prediccion/v2/diag/heldout_coverage.py`. Resultados crudos: `heldout_cov_results.json`. Mapa: `heldout_cobertura_mapa.png`.
Sin entrenar ni cambiar nada. Train: 1 de cada 3 row groups = 34,7 M filas (filtro de ETADataset), conteos escalados x3.
Grilla: 39.780 vertices (cell 500 m). P y T suman por separado; cada punto cuenta sus 4 vertices vecinos.
Clases por fraccion de peso bilineal: no cubierta = >50 % del peso en vertices con 0 pasadas; poco cubierta = >50 % en vertices con <100; bien cubierta = el resto. Fila "no cubierta" = P o T no cubierto.

## 1. Cobertura de train
- Vertices tocados: 3.164 de 39.780 (8 %); solo 11 de ellos con 1-99 pasadas (el resto con 100+). Los demas 36.616 nunca reciben gradiente.

## 2. Checkpoint (`e2_geo.pt`)
Init: `normal(std=0.1)`, sin semilla -> se compara la distribucion.
| grupo | n | RMS por vertice (media) |
|---|---|---|
| no tocados | 36.616 | 0,092 (std elem 0,093, media 0,0001) = init intacta |
| 1-99 pasadas | 11 | 0,41 |
| 100-9.999 | 459 | 1,19 |
| >=10.000 | 2.694 | 0,71 |
Se confirma: los no tocados conservan la init (0,1) y los tocados se movieron 7-12 veces. La sospecha mecanica es correcta (los embeddings no entrenados son pequenos, no ruido grande).

## 3. Cobertura de eval_heldout (100k filas)
- Peso bilineal medio en vertices no tocados: P 6,9 %, T 7,0 % (con <100: 7,0 % / 7,1 %). Filas con algun peso en no tocados: P 9,0 %, T 9,1 %.
- Filas con P o T en zona no cubierta: 9,95 % (9.954); poco cubierta: 0,05 % (46); bien cubierta: 90 %.

| linea | n | % filas P o T no cubierto | MAE | sesgo (s) | MAE / sesgo solo filas bien cubiertas |
|---|---|---|---|---|---|
| 1 | 3237 | 47 | 276 | +124 | 204 / +85 |
| 87 | 5897 | 44 | 482 | +180 | 405 / +154 |
| 181 | 5200 | 31 | 246 | -74 | 192 / -89 |
| 100 | 7445 | 19 | 193 | +43 | 164 / +44 |
| 21 | 16333 | 14 | 258 | -13 | 228 / -63 |
| 15 | 7294 | 8 | 327 | -158 | 287 / -204 |
| 109, 12, 128, 64, 65, 68 | 5.7-13.5k | 0 | 162 / 190 / 291 / 155 / 174 / 336 | -2 / +104 / +255 / +24 / +55 / +292 | iguales (100 % cubiertas) |

## 4. Error segun cobertura (E2 heldout; MAE (sesgo, %subest>60s) por bucket ETA 0-5/5-10/10-20/20+ min)
| clase | n | MAE | sesgo | % sub>60s | por bucket |
|---|---|---|---|---|---|
| todas | 100.000 | 255 | +75 | 25,7 | 93(+72,6) / 169(+80,26) / 269(+111,31) / 488(+37,40) |
| bien cubierta | 90.000 | 232 | +65 | 25,1 | 80(+61,5) / 141(+55,26) / 241(+85,31) / 469(+58,39) |
| poco cubierta | 46 | 841 | +219 | 28,3 | (n chico, no interpretable) |
| no cubierta | 9.954 | 454 | +168 | 30,9 | 199(+166,10) / 452(+337,33) / 521(+345,32) / 637(-129,49) |
Por punto (bien / no cubierta): P 246 (+75) / 364 (+73); T 245 (+72) / 380 (+125).

- Las filas bien cubiertas mantienen sesgo +65 s y MAE 80 en 0-5 min (vistas: -17 s). **No se parecen a las vistas: la sospecha NO explica el sesgo.**
- Las no cubiertas si son peor (MAE 454 vs 232, sesgo +168 vs +65), pero son el 10 % de las filas. Quitarlas baja el MAE global de 255 a 232 y el sesgo de +75 a +65 (~10 s de 75, ~9 % del MAE).
- Contrafactual: poner en 0 los embeddings de vertices con <100 pasadas deja las predicciones casi igual (MAE 255, sesgo +74). Los embeddings sin entrenar (norma 0,09) casi no aportan ruido; lo que falla en esas zonas es la falta de informacion, no el ruido.
- Las lineas con mayor sesgo (68: +292, 128: +255, 12: +104) tienen 0 % de filas en zona no cubierta.

## 5. Otras causas
- `schedule_dev_norm`: los 242 ramales de las medianas son todos de train; **0 % de los ramales de heldout estan** -> sdn = 0 en todas las filas de control. Contrafactual en vistas: sdn=0 en vez del real cambia MAE 114,6 -> 122,8 y sesgo -17 -> -25 (empuja a subestimar, no a sobreestimar). Entonces sdn=0 por defecto **no explica el +75**; cuesta unos 8 s de MAE a lo sumo.
- La linea en si domina: el sesgo por linea va de -158 (15) a +292 (68) con cobertura total. Lineas largas (15: 50 km, 21: 35 km) subestiman; cortas (68: 11,6 km, 12: 13,4 km, 128: 14,2 km) sobreestiman fuerte. Correlacion con longitud del recorrido (aprox. el nivel de velocidad/frecuencia de la linea), lo que sugiere que el modelo regresa a un nivel de velocidad promedio de train y no capta la velocidad propia de la linea; el sesgo agregado +75 sale de que las lineas cortas/lentas (por numero de filas) pesan mas.
- Solo se observo correlacion con longitud (12 lineas); velocidad/frecuencia no se midieron aca.

## Conclusion
- La cobertura explica una parte menor: ~10 s de los 75 s de sesgo y ~23 s de los 255 s de MAE, concentrada en 1, 87 y 181. El 90 % de las filas esta bien cubierto y igual da +65 s.
- Causa principal: generalizacion entre lineas (nivel de velocidad propio de cada linea no visto en train), con sdn=0 como factor menor y que apunta al lado contrario. Mas lineas de train (diversidad) y/o un descriptor de linea observable (velocidad tipica reciente) serian los candidatos; ampliar la cobertura de la grilla aporta poco.
