# ¿A qué velocidad andan realmente los colectivos en la Ciudad de Buenos Aires?

**Medición sobre julio de 2026 · 25 líneas porteñas · 1.529 coches · medio millón de viajes**

---

## El resultado en una línea

Un colectivo en la Ciudad de Buenos Aires avanza, en promedio, a **15 kilómetros
por hora**.

No es la velocidad a la que pisa el acelerador: es la velocidad a la que
efectivamente se traslada de un punto a otro, contando los semáforos, las
paradas, el tránsito y las esquinas. Es el número que siente el pasajero, y el
que determina cuánto tarda en llegar.

Para tener una referencia: **una bicicleta urbana promedia entre 15 y 18 km/h.**

---

## De dónde salen estos datos

La Ciudad publica, a través de su API de transporte público, la posición de cada
colectivo en circulación. Cada coche reporta dónde está aproximadamente **una vez
por minuto**, junto con su velocidad instantánea y la lectura de su odómetro.

Se registró ese flujo de forma continua y se analizó **el mes completo de julio
de 2026**: 28 días útiles (se descartaron tres jornadas con fallas de registro).
El resultado son casi **15 millones de mediciones** de movimiento, sobre 259.840
horas de colectivo en servicio.

No es una muestra ni una estimación: es el registro de lo que hicieron todos los
coches de esas líneas, todos los días, todo el mes.

---

## Qué líneas se midieron

Se analizaron las líneas cuyo recorrido está **enteramente dentro de la Ciudad**
—las que administra el Gobierno porteño—, porque son las que quedarían
alcanzadas por una norma de velocidad municipal.

> **7 · 12 · 26 · 34 · 39 · 42 · 44 · 47 · 50 · 61 · 62 · 64 · 65 · 68 · 76 ·
> 84 · 102 · 106 · 107 · 108 · 109 · 115 · 118 · 132 · 151**

Dos líneas porteñas más, la **4** y la **25**, no pudieron incluirse: sus
empresas no publican la información de viajes que hace falta para separar el
tiempo en servicio del tiempo estacionado en cabecera.

---

## Cómo se mide la velocidad de un colectivo

El desafío es simple de enunciar: si sé dónde estaba un colectivo a las 14:03 y
dónde estaba a las 14:04, ¿cuánto recorrió en ese minuto?

Se usaron **dos maneras independientes** de responderlo, y se contrastaron entre
sí. Que dos métodos que no comparten ningún supuesto lleguen al mismo número es
lo que da confianza en el resultado.

### Método 1 — El odómetro del coche

Cada colectivo informa su cuentakilómetros. La diferencia entre dos lecturas
consecutivas es, directamente, lo que recorrió. Es la medición más fiel: sigue
el camino real, con sus curvas y sus vueltas.

El problema es que **no todos los odómetros funcionan bien**. Algunos se quedan
clavados y no suman kilómetros aunque el coche esté andando.

Por eso se revisó unidad por unidad, comparando cada odómetro contra el
movimiento observado por GPS a lo largo de todo el mes. Un coche que declara
"no me moví" mientras el GPS lo muestra avanzando cuadras tiene el odómetro
fallado, y se lo deja afuera.

**De 1.528 coches revisados, 1.323 tienen el odómetro confiable (87 %) y 188
quedaron descartados.** La falla típica no es un desastre total sino una pérdida
intermitente: unidades que "se olvidan" de contar uno de cada ocho minutos.

### Método 2 — La distancia en línea recta

Se toman las dos posiciones GPS y se mide la distancia directa entre ellas. No
requiere confiar en ningún equipo del vehículo, sólo en el GPS.

Tiene una imprecisión conocida y sistemática: si el colectivo dobló en una
esquina, la línea recta se "come" ese desvío. Por eso subestima siempre un poco
—alrededor de un 5 %— y de manera predecible.

### Los dos coinciden

| | Velocidad promedio medida |
|---|---|
| Odómetro (con las unidades falladas excluidas) | **15,0 km/h** |
| Distancia en línea recta | 14,1 km/h |

La diferencia de 0,9 km/h es exactamente el desvío esperado del segundo método.
Ese margen es el nivel de precisión honesto de todo el estudio: **cuando acá
dice 15 km/h, hay que leer "entre 14 y 15".**

En las pocas líneas donde además se contaba con el trazado exacto del recorrido
—lo que permite una tercera medición, la más precisa posible— el método del
odómetro filtrado acertó **con un error del 0,3 %**.

---

## Los números

### Velocidad promedio: 15,0 km/h

Contando todo: el tiempo andando, el detenido en semáforos, el que pasa en cada
parada subiendo y bajando pasajeros.

### El colectivo está frenado el 38 % del tiempo

De cada hora que un colectivo pasa en servicio, **23 minutos los pasa detenido**.
No en la terminal: en la calle, en un semáforo o en una parada.

Este dato es el corazón del asunto. La velocidad de un colectivo urbano no la
define lo rápido que puede ir, sino la cantidad de veces que tiene que frenar.

### Cuánto tiempo va rápido

Un colectivo porteño supera los 30 km/h durante el **16 % del tiempo**, en
ráfagas cortas entre semáforo y semáforo.

Supera los 50 km/h durante el **1,8 % del tiempo**.

### Línea por línea

Ninguna línea de la Ciudad promedia más de 20 km/h.

| Línea | Velocidad promedio | Tiempo sobre 30 km/h |
|---|---|---|
| 84 | 9,7 km/h ◆ | 9 % |
| 102 | 12,4 km/h ◆ | 10 % |
| 12 | 12,7 km/h | 12 % |
| 26 | 12,8 km/h | 11 % |
| 151 | 12,9 km/h ◆ | 11 % |
| 132 | 13,3 km/h | 13 % |
| 64 | 13,4 km/h | 14 % |
| 65 | 13,5 km/h | 13 % |
| 44 | 13,9 km/h | 15 % |
| 61 | 14,2 km/h | 17 % |
| 118 | 14,3 km/h | 16 % |
| 39 | 14,4 km/h | 15 % |
| 68 | 14,4 km/h | 17 % |
| 62 | 14,6 km/h | 16 % |
| 7 | 15,1 km/h | 16 % |
| 107 | 15,5 km/h | 16 % |
| 108 | 15,6 km/h | 17 % |
| 109 | 15,7 km/h | 14 % |
| 50 | 15,9 km/h | 18 % |
| 106 | 16,0 km/h | 18 % |
| 76 | 16,1 km/h | 18 % |
| 115 | 16,2 km/h | 19 % |
| 42 | 16,2 km/h | 19 % |
| 47 | 18,7 km/h | 21 % |
| 34 | 20,1 km/h | 31 % |

◆ *Menos datos disponibles que el resto; tomar con más cautela.*

La línea 34 encabeza la tabla porque parte de su recorrido va por la autopista
Lugones hasta Ciudad Universitaria. Es un caso atípico dentro del conjunto.

---

## Por qué esto importa para discutir velocidades máximas

Cuando se propone bajar el límite de velocidad en la Ciudad, la objeción más
frecuente es que perjudicaría al transporte público: los colectivos tardarían
más y el servicio empeoraría.

Estos datos permiten poner un número a esa objeción.

### El ejercicio

Se tomó cada minuto de cada viaje en que un colectivo superó determinado
límite, y se recalculó cuánto habría tardado si no hubiera podido pasar de ese
límite.

El escenario es **deliberadamente adverso a la medida**: se asume que cada
segundo de exceso se paga íntegro y que nada lo compensa. Sin menos congestión,
sin mejor coordinación de semáforos, sin ningún efecto de segundo orden. Es el
peor caso imaginable, no una predicción.

### El resultado

Sobre un viaje típico de **41 minutos**:

| Límite | Tiempo adicional del viaje |
|---|---|
| **40 km/h** | entre 8 y 27 segundos |
| **30 km/h** | entre 43 segundos y 2 minutos 10 |

Un tope de 40 km/h es, a efectos prácticos, **gratuito** para el pasajero de
colectivo.

Un tope de 30 km/h cuesta, en el peor de los escenarios, **entre el 2 % y el 5 %
del tiempo de viaje**.

Los dos métodos de medición llegan al mismo resultado, lo que indica que la
conclusión no depende de decisiones técnicas del análisis.

### Cómo leer esto

**Las velocidades efectivas en la Ciudad ya son lo bastante bajas como para que
reducir el límite no tenga impacto real sobre el transporte público.**

Un colectivo que promedia 15 km/h no está limitado por el techo de velocidad
permitido. Está limitado por la cantidad de veces que tiene que detenerse. El
techo casi nunca es lo que lo frena, así que bajarlo no cambia esa aritmética.

Los números lo confirman por dos caminos que se refuerzan:

**Primero, el costo directo es marginal.** Incluso en el escenario construido
para ser lo más desfavorable posible a la medida, la pérdida es del orden de un
minuto sobre un viaje de 41. Ese es el techo del perjuicio, no el valor esperado.

**Segundo, ese cálculo omite todo lo que juega a favor.** Un límite más bajo
reduce la cantidad de siniestros y, sobre todo, su gravedad: la energía de un
impacto crece con el cuadrado de la velocidad. Y la experiencia internacional
muestra que una circulación más pareja —con menos acelerones y frenadas— tiende
a mejorar la velocidad efectiva del conjunto del corredor, no a empeorarla. Nada
de eso está contabilizado acá. Este informe mide únicamente el costo.

---

## Qué no dicen estos datos

**No distinguen el tipo de vía.** Un colectivo circulando por una calle angosta
de Boedo, por una avenida de doble mano y por la autopista Lugones son, para
esta medición, exactamente lo mismo. Todos los kilómetros pesan igual.

Esto importa mucho para una discusión de límites de velocidad, porque un tope
urbano no se aplicaría a una autopista. En las líneas que combinan ambos tipos
de vía —la 34 y la 42 son los casos claros— el promedio mezcla situaciones que
en la práctica se regularían distinto. Separar el análisis por corredor requiere
saber por qué calles pasa exactamente cada línea, y ese trabajo no está hecho
todavía.

**Tampoco distinguen dónde se pierde el tiempo.** El dato dice que el colectivo
está detenido el 38 % del tiempo, pero no si es en un semáforo mal sincronizado,
en una parada con mucha demanda o en un embotellamiento.

**El costo del tope se expresa como un rango, y no puede ser de otro modo.** La
velocidad promedio es un dato exacto: sale de dividir la distancia total por el
tiempo total, y no depende de con qué frecuencia se tomen las mediciones. Pero
para calcular cuánto costaría un límite hace falta saber cuántos segundos exactos
pasó cada coche por encima de ese valor, y eso sí depende de la resolución. Con
una posición por minuto, una punta de quince segundos puede quedar registrada
como un minuto entero a esa velocidad, o pasar desapercibida. Por eso el costo
aparece siempre acotado entre un mínimo y un máximo, calculados con los dos
criterios opuestos.

**Es un mes.** Julio, en invierno y con vacaciones escolares de por medio. Un
año completo daría el ciclo estacional.

---

## Resumen

| | |
|---|---|
| Velocidad promedio de un colectivo porteño | **15,0 km/h** |
| Proporción del tiempo detenido | **38 %** |
| Línea más lenta / más rápida | 9,7 km/h (84) / 20,1 km/h (34) |
| Tiempo por encima de 30 km/h | 16 % |
| Costo máximo de un tope de 40 km/h | menos de 30 segundos por viaje |
| Costo máximo de un tope de 30 km/h | poco más de 2 minutos por viaje |

Las velocidades efectivas de la Ciudad ya son lo bastante bajas como para que
reducir el límite no tenga impacto real sobre el transporte público. El costo
máximo es de alrededor de un minuto por viaje, y ese cálculo no incluye ninguno
de los beneficios esperados en siniestralidad ni en fluidez del corredor.

**Fuente:** registro histórico propio de la API de transporte público de la
Ciudad de Buenos Aires, julio de 2026.
