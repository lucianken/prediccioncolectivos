# CABA, julio 2026 — velocidad de colectivos sin usar recorridos

Corte sobre **las 27 líneas cuyo recorrido está íntegramente dentro de CABA**
(criterio: `Administración = GCBA` en el listado de Wikipedia — ver
[`lineas_caba.py`](lineas_caba.py)), **mes completo de julio de 2026**.

Reproducir:

```bash
python -m experiments.velocidades.run_month --month 2026-07 \
    --outdir experiments/velocidades/out_caba_202607 --workers 8
python -m experiments.velocidades.trip_id_coverage --month 2026-07 \
    --out experiments/velocidades/out_caba_202607/trip_id_coverage.csv
python -m experiments.velocidades.metrics_sin_recorrido \
    --indir experiments/velocidades/out_caba_202607 \
    --outdir experiments/velocidades/out_caba_202607
```

**144 s** el mes entero con 8 procesos (2,4 min).

## Cobertura

| | |
|---|---|
| días procesados | **28** de 31 |
| días excluidos | 25, 26 y 27/07 — cobertura incompleta (`EXCLUDED_DAYS` en [build_dataset.py:52](../../prediccion/pipeline/build_dataset.py#L52)) |
| líneas medidas | **25** de 27 |
| vehículos | 1.529 |
| viajes | 503.481 |
| intervalos | 14,95 M |
| horas-bondi en servicio | 259.840 (230.331 con el filtro de odómetro) |

**Las líneas 4 y 25 quedaron afuera**: sus operadores (Juan B. Justo y
Riachuelo) reportan `trip_id` vacío en el 100 % de las muestras. Como el
pipeline descarta lo que no tiene `trip_id`, esas dos líneas desaparecen. No se
las mide sin ese filtro a propósito: sin `trip_id` no hay forma de separar el
servicio de las horas que un coche pasa parado en cabecera o en garage, y el
resultado sería una velocidad comercial artificialmente baja.

**Tres líneas quedan marcadas como confianza baja** por cobertura de `trip_id`
menor al 50 %: la **84** (14,5 %), la **102** (33,8 %) y la **151** (44,2 %). Sus
números se apoyan en una fracción chica de su operación real.

---

## Cómo se define "odómetro roto"

El diagnóstico es **por vehículo sobre todo el mes**, no por muestra: un
odómetro sano lo es siempre y uno roto lo es siempre. La referencia es la
**cuerda haversine**, que no necesita recorrido — así que la regla se puede
aplicar a cualquier línea del país.

Un vehículo se marca **roto** si cumple alguna de estas dos:

**1. Pegado.** Más del **5 %** de sus intervalos tienen `Δodo` exactamente 0
mientras la cuerda dice que se movió más de **100 m**. Un odómetro sano
prácticamente no hace eso.

El modo de falla dominante es **intermitente**, no total: entre las 188 unidades
marcadas, la mediana de `frac_cero` es 12 % y el cuartil inferior 8 %. O sea, la
mayoría pierde minutos sueltos, no todos. Hay una cola de unidades clavadas
—máximo 83 %— pero son minoría.

**2. Escala.** La mediana de `Δodo / cuerda` cae fuera de **[0,95 – 1,30]**. El
valor esperado de un odómetro sano es ~1,02: el camino real es un poco más largo
que la recta entre los extremos. Por debajo de 0,95 el odómetro cuenta de menos
— y eso es geométricamente imposible, porque la distancia recorrida no puede ser
menor que la recta entre los dos puntos. Por encima de 1,30 infla.

Además, se exigen **100 intervalos válidos** como mínimo para juzgar. Los
vehículos con menos quedan **sin juzgar** y se excluyen del método filtrado:
es preferible perder cobertura a colar una unidad rota por falta de evidencia.

A nivel de intervalo (previo a todo esto) ya se descartan los `Δodo` negativos
—reseteo del contador— y los mayores a 3.000 m en un minuto.

### Resultado del diagnóstico, julio 2026

| | vehículos |
|---|---|
| con datos | 1.528 |
| sin evidencia suficiente (<100 intervalos) | 17 |
| **rotos: pegados en cero** | **188** |
| **rotos: sólo por escala** | **0** |
| **sanos** | **1.323** (87,6 % de los juzgables) |

Mediana de `Δodo / cuerda` en las unidades sanas: **1,0244**. La distribución es
muy angosta: p1 = 1,011, p99 = 1,047.

Dos cosas que salieron de mirar el diagnóstico:

**Ninguna unidad falla sólo por escala.** Todas las que tienen la escala mal
también están pegadas. El odómetro de la API no se descalibra gradualmente: o
cuenta bien o pierde minutos. Como las unidades sanas caen en una banda de
apenas ±2 %, el criterio de escala [0,95–1,30] es holgadísimo y no está haciendo
trabajo — el que separa es el de pegado. Eso es bueno: el resultado no depende
de dónde se pongan esos bordes.

**El umbral de 5 % es un dial entre cobertura y sesgo**, no una frontera
natural. Medido contra la proyección geométrica en las 4 líneas con recorrido:

| umbral de `frac_cero` | unidades sanas | % de la flota | sesgo vs. proyección | intervalos conservados |
|---|---|---|---|---|
| 1 % | 1.035 | 67,7 % | −0,01 % | 53,2 % |
| 2 % | 1.177 | 77,0 % | −0,13 % | 68,1 % |
| **5 %** | **1.323** | **86,6 %** | **−0,34 %** | **85,1 %** |
| 10 % | 1.395 | 91,3 % | −0,45 % | 90,8 % |
| 20 % | 1.452 | 95,0 % | −0,63 % | 94,9 % |
| sin filtro | 1.468 | 96,1 % | −0,71 % | 96,0 % |

En todo el rango el sesgo se mantiene por debajo del 0,7 %, así que la elección
no es crítica. Tomé 5 % porque conserva el 85 % de los intervalos con un sesgo
de −0,34 %; si te importa más la cobertura que el último medio punto, 10 % o
20 % son igual de defendibles.

---

## Validación de los tres métodos

De las 25 líneas medidas, **4 tienen recorrido** en `line_shapes.json` (26, 39,
42 y 151). Ahí se puede contrastar cada método sin recorrido contra la
proyección geométrica, sobre los mismos intervalos:

| método | v. comercial | sesgo vs. proyección | cobertura de intervalos |
|---|---|---|---|
| proyección sobre el recorrido | 13,99 km/h | — (referencia) | — |
| **odómetro con QC** | **13,94 km/h** | **−0,34 %** | 85,1 % |
| odómetro crudo | 13,74 km/h | −1,74 % | 99,9 % |
| cuerda haversine | 13,22 km/h | −5,48 % | 100 % |

Confirma lo del corte anterior con más de 50× el volumen: **el odómetro filtrado
reproduce la proyección geométrica dentro del 0,3 %**, a cambio de perder el
15 % de los intervalos. El crudo se queda a −1,7 % sin perder nada. La cuerda
subestima consistentemente ~5,5 %, corregible con un factor de 1,058.

---

## Resultados, las 25 líneas de CABA

### Velocidad comercial

| método | v. comercial | intervalos usados |
|---|---|---|
| **odómetro con QC** | **15,02 km/h** | 13,25 M |
| odómetro crudo | 14,74 km/h | 14,94 M |
| cuerda haversine | 14,13 km/h | 14,95 M |

El orden es el esperado y coincide con el sesgo medido arriba: la cuerda tira
para abajo, el odómetro crudo un poco menos, el filtrado da el valor bueno.
**Tomá 15,0 km/h como la cifra.** Los tres métodos coinciden dentro de 0,9 km/h,
que es el margen honesto del análisis.

El bondi está frenado en el **38 %** de los instantes muestreados.

### Exposición: tiempo por encima de 30 km/h

| método | lectura puntual | promedio del minuto |
|---|---|---|
| odómetro con QC | 16,5 % | 7,5 % |
| odómetro crudo | 16,1 % | 7,6 % |
| cuerda haversine | 16,1 % | 5,7 % |

La lectura puntual no depende del método de distancia, por eso las tres
coinciden. La columna del promedio del minuto sí, y ahí se ve el sesgo de la
cuerda otra vez.

### Contrafáctico: costo de un tope de velocidad

Escenario más pesimista: todo el exceso sobre el tope se paga íntegro, sin
ninguna compensación. Cota superior, no predicción. Ver
[README §2](README.md) para los dos estimadores.

| tope | método | sobrecosto bajo | sobrecosto alto |
|---|---|---|---|
| **30 km/h** | odómetro con QC | **+1,73 %** | **+5,28 %** |
| | odómetro crudo | +1,95 % | +5,14 % |
| | cuerda haversine | +1,25 % | +5,15 % |
| **40 km/h** | odómetro con QC | +0,32 % | +1,08 % |
| | odómetro crudo | +0,44 % | +1,04 % |
| | cuerda haversine | +0,21 % | +1,04 % |

**Los tres métodos dan lo mismo.** El contrafáctico es robusto a la elección del
estimador de distancia — que era la pregunta metodológica de fondo.

En el viaje mediano —41 min, 283.698 viajes completos— eso son **+43 s a
+2,2 min** con tope de 30, y **+8 s a +27 s** con tope de 40.

Viajes que tocan cada umbral al menos una vez (lectura puntual / promedio del
minuto): >30 km/h **99,1 % / 86,8 %**, >40 km/h 83,1 % / 40,1 %, >50 km/h
40,8 % / 12,1 %. O sea, el argumento "los bondis no superan 30" es insostenible:
lo que sostiene la discusión es la magnitud del costo, no la frecuencia.

### Por línea (odómetro con QC)

Ordenadas de más lenta a más rápida:

| línea | v. comercial | % tiempo > 30 km/h | vehículos | confianza |
|---|---|---|---|---|
| 84 | 9,70 | 9,5 % | 45 | baja |
| 102 | 12,41 | 10,0 % | 32 | baja |
| 12 | 12,67 | 12,3 % | 45 | ok |
| 26 | 12,78 | 11,2 % | 50 | ok |
| 151 | 12,85 | 10,9 % | 52 | baja |
| 132 | 13,30 | 12,9 % | 83 | ok |
| 64 | 13,41 | 14,3 % | 54 | ok |
| 65 | 13,48 | 13,4 % | 51 | ok |
| 44 | 13,87 | 14,6 % | 46 | ok |
| 61 | 14,24 | 16,5 % | 27 | ok |
| 118 | 14,28 | 15,6 % | 48 | ok |
| 39 | 14,35 | 14,7 % | 82 | ok |
| 68 | 14,40 | 17,4 % | 70 | ok |
| 62 | 14,62 | 16,4 % | 31 | ok |
| 7 | 15,10 | 15,6 % | 39 | ok |
| 107 | 15,51 | 16,3 % | 51 | ok |
| 108 | 15,62 | 16,8 % | 45 | ok |
| 109 | 15,65 | 14,2 % | 39 | ok |
| 50 | 15,86 | 18,0 % | 68 | ok |
| 106 | 15,98 | 17,8 % | 102 | ok |
| 76 | 16,13 | 17,8 % | 53 | ok |
| 115 | 16,16 | 19,4 % | 54 | ok |
| 42 | 16,16 | 19,5 % | 45 | ok |
| 47 | 18,73 | 21,2 % | 43 | ok |
| 34 | 20,12 | 30,5 % | 68 | ok |

**Ninguna línea de CABA promedia más de 20,2 km/h.** La más rápida, la 34, llega
ahí porque corre por Lugones/Cantilo hasta Ciudad Universitaria — donde el
límite urbano no aplicaría de todos modos. La segunda, la 47, está en 18,7.
Sacando esas dos, el rango es **9,7 – 16,2 km/h**.

Es decir: **el tope de 30 km/h está entre 1,5× y 3× por encima de la velocidad
que cualquier línea de CABA logra sostener hoy.**

## Archivos generados

`out_caba_202607/`

| archivo | qué tiene |
|---|---|
| `metrics.json` | todo lo de arriba |
| `odometro_qc.csv` | diagnóstico por vehículo: `n`, `frac_cero`, `ratio_med`, `pegado`, `escala`, `juzgable`, `sano` |
| `trip_id_coverage.csv` | cobertura de `trip_id` por línea |
| `por_linea_{odo_qc,hav,odo}.csv` | resultados por línea con cada método |
| `excedencia_{odo_qc,hav,odo}.csv` | curva de excedencia completa (0–80 km/h) |
| `iv_YYYY-MM-DD.parquet` | intervalos diarios (28 archivos) |
