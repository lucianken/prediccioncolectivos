# Consistencia temporal del ETA anunciado (ARQUITECTURA.md §11 ítem 4a)

Medido el 2026-11-16/17. Experimento de medición: no se entrenó nada, no se tocó la app, `pinned/`, `geo_assign.py`, `metrics.py` ni proyectoconsola. Pregunta: si la app anuncia «viene en 5 min», un minuto después debería decir ~4; si el anuncio sube, la predicción anterior era mala. ¿Qué tan seguido pasa?

## Método (spec)

- **Modelo y lógica:** `data/ml/export/path_v3_l1_s1`, lógica de la app fijada en `prediccion/replay/pinned/` (variante `base`: ramal y sentido desconocidos), presentación de la app (`core.build_list`: top 5, «seguro» primero). Sin ajuste de anuncio (a = 0). El ETA anunciado es `eta0` (hora común, como la vara); el que muestra la app es 60 s menor (constante), no cambia ningún Δ.
- **Consultas:** cada 60 s dentro de una ventana de 2 h por (línea, día), con los pings disponibles hasta cada instante (historial de 15 min, ping de a lo sumo 10 min de antigüedad), como el refresco de la app. Se registran los coches *listados* (top 5) en cada consulta.
- **Muestra (semilla fija 20261116, `prediccion/replay/consistencia.py`):**
  - Días: 12 al azar entre 2026-09-15 y 2026-10-14 (período de validación con grabación), 4 de fin de semana: 09-15, 09-18, 09-20 (dom), 09-25, 09-26 (sáb), 10-03 (sáb), 10-05, 10-06, 10-09, 10-11 (dom), 10-12, 10-13.
  - Paradas: por línea, 150 al azar de las paradas de `ramales[].stops` (tras el descarte de paradas a < 300 m del inicio de sus shapes); las mismas todos los días. Las líneas con menos paradas usan todas: 39, 42 y 50 ≈ 108-110, 124 = 126, 151 = 127, 132 = 79, 26 = 79. Total 1 488 paradas distintas.
  - Ventana: 2 h con inicio al azar por (línea, día) entre las 6 y las 21 h (hash de semilla, día y línea). Una secuencia ya listada al abrir la ventana se sigue desde ahí (no se ve su comienzo).
  - Línea 26: en la muestra solo tiene datos el 15 de septiembre; pesa 0,8 % de los pasos de la banda 3-7 y no permite hablar de dispersión día a día.
  - Total: 8,19 M listados (coche, parada, consulta), 477 719 pares (parada, coche), 710 198 secuencias, 7,29 M pasos entre consultas consecutivas; 1,37 M con anuncio 3-7 min.
- **Secuencia:** racha de consultas consecutivas (60 s) en que el coche está listado en la parada, hasta su paso real (se descartan las filas desde el paso y las de coches que ya pasaron entre su último ping y t). Un paso es el par de consultas (t, t + 60 s) de una secuencia; se clasifica por el ETA anunciado en t.
- **Δ** = ETA anunciado (t + 60 s) − ETA anunciado (t); ideal −60 s. «Sube» = Δ > 0. «Baja más que el reloj» = Δ < −120 s. «Ping nuevo» = el último ping del coche cambió entre t y t + 60 s.
- **Resultado:** verdad corregida vigente (`core.truth_at`: próximo cruce firme en (t, t + 40 min], con el filtro por recorrido ex post del viaje: un cruce cuenta solo si el viaje del coche tiene la parada en su lista). «Llega antes / después» > 60 s de lo anunciado (error = paso real − ETA anunciado en t). El «error al final» de una secuencia se mide en su último paso. Los bondi fantasma (listados que no pasan) y los pasos no verificables no tienen resultado: entran en las tablas de Δ pero no en las de resultado.
- **Proceso (verdad):** los ETA no dependen de la verdad. La verdad del replay cambió dos veces durante la corrida (se retiró la asociación parada↔recorrido por geometría; después se exige el recorrido ex post). Se descartó la primera extracción parcial (22 archivos, verdad con geometría). Los ETA salen de `consistencia/run` (corrida única, verdad sin filtro ex post, no usada) y la verdad vigente se recalculó sobre esos crudos, sin volver a predecir, con `prediccion/replay/consistencia_verdad.py` → `consistencia/run_xp`. Todas las tablas salen de `run_xp` (`prediccion/replay/report_consistencia.py`, copia en `consistencia/tablas.md`).
- Cuando el top 5 cambia por otro coche, un coche aparece o desaparece de la lista: ese corte no es un paso de la secuencia.

## Resultado principal (anuncio 3-7 min, 1,37 M pasos)

| métrica | valor |
|---|---|
| Δ mediana (ideal −60 s) | −56 s |
| Δ P5 / P25 / P75 / P95 | −129 / −76 / −33 / +1 s |
| el anuncio sube (Δ > 0) | 5,6 % de los pasos |
| sube > 30 s | 1,7 % |
| sube > 60 s | 0,7 % |
| sube > 120 s | 0,2 % |
| baja más de 60 s más que el reloj (Δ < −120 s) | 6,5 % |
| secuencias con al menos una subida > 0 (pasos en la banda) | 15,5 % |
| secuencias con al menos una subida > 60 s | 2,1 % |
| dispersión día a día de «sube > 60 s» (12 días) | media 0,8 %, desvío 0,3, rango 0,3-1,1 |
| dispersión día a día de «sube > 0» | media 5,5 %, desvío 0,5, rango 4,9-6,8 |
| dispersión entre líneas de «sube > 60 s» | 0,2-1,8 % (mediana 0,6; la mayor, línea 42) |

El anuncio es consistente: baja ~56 s por minuto (mediana) y sube más de 60 s en 7 de cada 1 000 pasos.

## Hallazgos

1. **Casi nunca sube mucho.** En la banda 3-7 sube el 5,6 % de los pasos, pero casi todo son subas chicas; > 60 s son 0,7 %. A nivel secuencia, 15,5 % tiene alguna subida y 2,1 % alguna > 60 s. Parecido en todas las bandas ≥ 2 min; por debajo de 2 min sube más (10,4 %; 2,0 % > 60 s), rango donde la predicción es inviable.
2. **Lo más frecuente son las bajadas bruscas:** 6,5 % de los pasos baja más de 60 s de más (el anuncio estaba largo y se corrige de golpe), 9 veces más seguido que una subida > 60 s. Esos pasos terminan en «llega antes de lo anunciado» el 60,3 % de las veces contra 14,3 % de los pasos normales.
3. **Una subida confirma que el anuncio previo era corto:** tras una subida > 60 s, el coche llega después > 60 s el 81,2 % de las veces (error mediano +288 s); tras una subida de 0-60 s, 55,5 % (mediana +74 s); sin subida, 22,3 % (todos los pasos: 23,2 %). Las subidas casi nunca terminan en arribo temprano (4,6-6,2 %).
4. **Por secuencia (banda 3-7):** con alguna subida > 60 s el 18,9 % termina llegando después > 60 s (4,1 % sin subida). Con alguna bajada rápida el 8,3 % termina llegando antes > 60 s (10,7 % sin bajada): a nivel secuencia la bajada rápida ya no predice «llega antes» (el modelo se corrige en el camino); lo predice a nivel paso.
5. **Ping nuevo.** Con ping nuevo el Δ se aparta más del reloj (|Δ + 60| mediana 25,6 s, P90 66,4 s) que sin ping (12,3 y 52,1 s); suben 6,1 % contra 4,1 %, > 60 s 0,8 % contra 0,4 %, y bajan > 60 s de más 7,3 % contra 3,8 %. El 76 % de los pasos de la banda trae ping nuevo (por día 60-89 %: los pings llegan por lotes con huecos). Sin ping nuevo el anuncio igual se mueve (mediana 12 s) porque depende del tiempo y de los demás coches.
6. **Grupo mostrado:** «seguro» es consistente (sube 4,7 %, > 60 s 0,4 %); «puede venir» sube 9,4 % (> 60 s 1,8 %); «provisional» (sentido sin confirmar) 24,6 % (> 60 s 6,2 %). La inestabilidad se concentra en coches con recorrido incierto.
7. **Línea y día.** «Sube > 60 s» va de 0,2 % (26, 132, 151) a 1,8 % (42). Entre días, 0,3-1,1 %: más alto en fin de semana (0,8-1,0 los cuatro) y el lunes 10-12 (1,1); hábiles 0,3-0,8. Sin día atípico.

## Conclusiones

- La inconsistencia del ETA (subidas) no es un problema del producto hoy: 0,7 % de los pasos sube > 60 s en la banda 3-7 min, 2,1 % de las secuencias, estable entre días. No justifica un suavizado propio.
- Lo que sí aparece son bajadas bruscas (6,5 %), asociadas a «llega antes» (60 % de esos pasos): el mismo problema del error grave (anuncio largo), visto en el tiempo.
- Si se quisiera suavizar, el frente son los coches «provisional» y «puede venir» y los pasos con ping nuevo; los «seguro» ya son estables.
- Una subida > 60 s es indicador *ex post* de que el anuncio anterior era corto (81 % llegan después); no sirve para anticipar.
- Limitaciones: ventanas de 2 h (secuencias truncadas al abrir), línea 26 con un solo día, un solo modelo y variante (`base`, a = 0), y las secuencias se cortan cuando el coche sale del top 5 aunque siga con ETA.

---

## Tablas completas (generadas)

### Resumen del dataset

Filas (listados por consulta): 8186863; días 12, líneas 12, paradas distintas 1488, pares (parada, coche) 477719, secuencias (rachas de consultas consecutivas) 710198, pasos entre consultas 7294953 (3-7 min: 1369371).

### Δanuncio entre consultas consecutivas (60 s), por banda de ETA anunciado

Δ = ETA anunciado en t+60 s − ETA anunciado en t, en segundos (ideal −60). «Sube» = Δ > 0.

| banda ETA (min) | pasos | Δ P5 | P25 | P50 | P75 | P95 | Δ medio | sube >0 % | >30 s % | >60 s % | >120 s % | baja >60 s más que el reloj % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0-2 | 378091 | -78 | -55 | -30 | -1 | 14 | -25.2 | 10.4 | 3.3 | 2.0 | 1.2 | 0.0 |
| 2-3 | 333971 | -114 | -74 | -54 | -31 | 0 | -53.1 | 5.1 | 1.4 | 0.6 | 0.2 | 4.0 |
| 3-5 | 689550 | -128 | -76 | -56 | -33 | 1 | -56.6 | 5.4 | 1.7 | 0.7 | 0.2 | 6.4 |
| 5-7 | 679821 | -130 | -76 | -55 | -33 | 2 | -57.2 | 5.8 | 1.8 | 0.7 | 0.2 | 6.6 |
| 7-10 | 929511 | -130 | -77 | -56 | -34 | 2 | -58.5 | 5.7 | 1.6 | 0.7 | 0.2 | 6.7 |
| 10-20 | 2218655 | -131 | -78 | -58 | -35 | 2 | -59.3 | 5.8 | 1.7 | 0.7 | 0.2 | 6.9 |
| 20-40 | 1629981 | -132 | -80 | -59 | -35 | 3 | -59.4 | 6.3 | 1.7 | 0.7 | 0.2 | 7.2 |
| 3-7 (foco) | 1369371 | -129 | -76 | -56 | -33 | 1 | -56.9 | 5.6 | 1.7 | 0.7 | 0.2 | 6.5 |
| todas | 7294953 | -129 | -76 | -56 | -32 | 3 | -56.7 | 6.3 | 1.8 | 0.8 | 0.3 | 6.5 |

### Pasos con ping nuevo del coche contra sin ping nuevo

| banda | paso | pasos | Δ mediana | |Δ+60| mediana | |Δ+60| P90 | sube >0 % | sube >60 s % | baja >60 s más que el reloj % |
|---|---|---|---|---|---|---|---|---|
| 3-7 (foco) | ping nuevo | 1040277 | -57.9 | 25.6 | 66.4 | 6.1 | 0.8 | 7.3 |
| 3-7 (foco) | sin ping nuevo | 329094 | -50.5 | 12.3 | 52.1 | 4.1 | 0.4 | 3.8 |
| todas | ping nuevo | 5629070 | -57.3 | 26.8 | 68.6 | 7.0 | 0.9 | 7.6 |
| todas | sin ping nuevo | 1665883 | -53.0 | 9.8 | 55.3 | 3.6 | 0.4 | 2.8 |

### Secuencias (coche, parada)

| secuencias con ≥1 paso en | n sec. | pasos por sec. | con ≥1 subida >0 % | con ≥1 subida >60 s % | con ≥1 baja >60 s más que el reloj % | con subida: termina llega después >60 s % | sin subida: termina llega después >60 s % | con baja rápida: termina llega antes >60 s % | sin baja rápida: termina llega antes >60 s % |
|---|---|---|---|---|---|---|---|---|---|
| 3-7 (pasos en la banda) | 364003 | 3.8 | 15.5 | 2.1 | 23.3 | 18.9 | 4.1 | 8.3 | 10.7 |
| todas las bandas | 607792 | 12.0 | 41.9 | 6.6 | 45.7 | 19.9 | 14.2 | 13.4 | 15.4 |

### Relación con el resultado (pasos con anuncio 3-7 min)

| paso (anuncio 3-7 min, paso real conocido) | n | llega antes >60 s % | llega después >60 s % | error mediano (s) | MAE (s) |
|---|---|---|---|---|---|
| baja >60 s más que el reloj (Δ < -120) | 78332 | 60.3 | 8.5 | -76.0 | 143.2 |
| baja normal (-120 a 0) | 1096171 | 14.3 | 22.3 | 4.3 | 72.8 |
| sube 0-60 s | 56002 | 6.2 | 55.5 | 73.6 | 188.4 |
| sube > 60 s | 6364 | 4.6 | 81.2 | 287.9 | 445.9 |
| todos los pasos | 1236869 | 16.8 | 23.2 | 3.0 | 84.4 |

### Por línea (anuncio 3-7 min)

| línea | pasos 3-7 | Δ mediana | Δ P5 | Δ P95 | sube >0 % | sube >60 s % | sube >120 s % | baja >60 s más % | con ping nuevo % |
|---|---|---|---|---|---|---|---|---|---|
| 106 | 205648 | -52.6 | -125.3 | 7.7 | 7.3 | 1.0 | 0.3 | 5.8 | 72.5 |
| 107 | 100130 | -57.5 | -127.4 | 1.2 | 5.8 | 0.5 | 0.2 | 6.3 | 81.0 |
| 108 | 88705 | -57.3 | -130.4 | 4.3 | 6.0 | 0.9 | 0.3 | 6.6 | 71.1 |
| 124 | 115336 | -57.4 | -132.9 | -0.0 | 5.0 | 0.6 | 0.2 | 7.1 | 71.4 |
| 132 | 132622 | -57.1 | -126.7 | -3.4 | 3.9 | 0.3 | 0.0 | 6.3 | 82.1 |
| 151 | 135504 | -54.6 | -127.7 | 0.4 | 5.2 | 0.3 | 0.0 | 6.4 | 80.4 |
| 168 | 96949 | -57.0 | -119.3 | -4.1 | 3.7 | 0.4 | 0.1 | 4.9 | 80.4 |
| 26 | 10601 | -55.5 | -131.8 | 0.3 | 5.2 | 0.2 | 0.0 | 7.0 | 90.0 |
| 39 | 152226 | -54.8 | -146.5 | 0.4 | 5.2 | 0.7 | 0.2 | 8.4 | 71.2 |
| 42 | 104986 | -54.6 | -132.2 | 11.0 | 8.2 | 1.8 | 0.8 | 6.9 | 72.6 |
| 50 | 93617 | -54.9 | -130.9 | 0.1 | 5.0 | 0.5 | 0.1 | 6.9 | 75.5 |
| 92 | 133047 | -56.4 | -123.3 | 0.9 | 5.5 | 0.8 | 0.3 | 5.5 | 78.3 |

Sube >60 s % entre líneas: mín 0.2, mediana 0.6, máx 1.8.

### Por día (anuncio 3-7 min)

| día | pasos 3-7 | Δ mediana | Δ P5 | Δ P95 | sube >0 % | sube >60 s % | sube >120 s % | baja >60 s más % | con ping nuevo % |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-15 | 153994 | -55.2 | -129.1 | 0.7 | 5.4 | 0.4 | 0.1 | 6.6 | 87.0 |
| 2026-09-18 | 150741 | -57.9 | -141.0 | 7.1 | 6.8 | 0.8 | 0.2 | 7.8 | 59.8 |
| 2026-09-20 | 75357 | -56.1 | -117.0 | 0.3 | 5.7 | 1.0 | 0.4 | 4.5 | 89.2 |
| 2026-09-25 | 99585 | -55.9 | -137.7 | 2.4 | 5.8 | 0.7 | 0.2 | 7.8 | 63.3 |
| 2026-09-26 | 67859 | -56.0 | -114.1 | 0.8 | 5.5 | 1.0 | 0.4 | 3.9 | 85.5 |
| 2026-10-03 | 103379 | -57.4 | -119.0 | -0.0 | 5.0 | 1.0 | 0.3 | 4.8 | 82.5 |
| 2026-10-05 | 148064 | -55.1 | -129.4 | 0.8 | 5.3 | 0.8 | 0.2 | 6.5 | 69.4 |
| 2026-10-06 | 153725 | -52.3 | -129.5 | 0.7 | 5.3 | 0.3 | 0.1 | 6.6 | 79.1 |
| 2026-10-09 | 145481 | -54.3 | -129.2 | 3.5 | 6.1 | 0.8 | 0.2 | 6.4 | 68.8 |
| 2026-10-11 | 66636 | -57.4 | -120.2 | 0.1 | 5.0 | 1.0 | 0.4 | 5.0 | 82.4 |
| 2026-10-12 | 57118 | -60.4 | -139.0 | -0.1 | 4.9 | 1.1 | 0.4 | 9.2 | 86.8 |
| 2026-10-13 | 147432 | -53.1 | -130.6 | 2.1 | 5.8 | 0.5 | 0.2 | 6.9 | 77.1 |

Sube >0 % entre días: media 5.5, desvío 0.5, mín 4.9, máx 6.8. Sube >60 s %: media 0.8, desvío 0.3, mín 0.3, máx 1.1.

### Por grupo mostrado al inicio del paso (anuncio 3-7 min)

| grupo | pasos 3-7 | Δ mediana | Δ P5 | Δ P95 | sube >0 % | sube >60 s % | sube >120 s % | baja >60 s más % | con ping nuevo % |
|---|---|---|---|---|---|---|---|---|---|
| provisional | 22794 | -33.5 | -168.5 | 69.1 | 24.6 | 6.2 | 2.0 | 8.3 | 50.9 |
| puede_venir | 178586 | -50.4 | -143.7 | 17.4 | 9.4 | 1.8 | 0.6 | 7.4 | 68.5 |
| seguro | 1167991 | -56.6 | -127.3 | -0.9 | 4.7 | 0.4 | 0.1 | 6.3 | 77.6 |
