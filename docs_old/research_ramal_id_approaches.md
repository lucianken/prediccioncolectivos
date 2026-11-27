# Research: Tres enfoques para identificación de ramal (Phase 1)

*Escrito post análisis empírico de 62 días, 7 líneas. Fecha: 2026-05-31.*

---

## El problema real que estamos resolviendo

Antes de comparar los enfoques, conviene enunciarlo con precisión después del análisis:

**Input disponible en tiempo real:** `route_id`, `direction_id`, posición GPS, `label` (→ línea)

**Lo que aprendimos del análisis de 62 días:**
- `route_id` mapea 1:1 a un shape físico dentro de un período (2-3 semanas)
- `direction_id` es redundante con `route_id` pero divide el espacio de búsqueda a la mitad
- El problema NO es clasificar GPS en tiempo real — es **construir y mantener la lookup table `route_id → shape`** que se resetea cada 2-3 semanas

Esta re-formulación cambia qué enfoque tiene sentido.

---

## Enfoque A — Fleet-level Transformer (plan original)

### Qué hace

Un transformer en dos capas:

1. **PerVehicleEncoder**: toma los últimos 40 puntos GPS de un vehículo (20 minutos de trayectoria) y produce un embedding de 128 dimensiones que captura el patrón de movimiento.

2. **CrossFleetTransformer**: toma los embeddings de todos los vehículos activos simultáneamente y aplica self-attention cross-flota. La idea: si el vehículo A (con route_id desconocido) tiene un embedding similar al vehículo B (ya identificado como ramal 39A), A probablemente también es 39A.

Los inputs por vehículo son: trayectoria GPS, `route_id_rank` (posición relativa del route_id en el período actual, no el valor absoluto), `direction_id`.

### Ventajas

- **Inferencia por asociación de flota**: cuando un vehículo está en zona compartida y no es identificable solo por geografía, la señal de otros vehículos del mismo route_id que sí están en zona única puede propagarse. El modelo aprende que "todos los vehículos con route_id_rank=2 son ramal 39A" después de ver un solo vehículo confirmado.

- **Inferencia por trayectoria temprana**: puede aprender que ciertos patrones de velocidad + dirección en los primeros 5 km predicen qué ramal viene, incluso antes de la zona de divergencia.

- **Maneja fraccionados naturalmente**: si 39D y 39A comparten track pero tienen route_ids distintos, el modelo aprende a separarlos por route_id_rank + trayectoria de inicio (el fraccionado nunca pasa por Barracas).

### Desventajas

**El problema de los labels:** El transformer necesita ejemplos `(snapshot_flota, ramal_por_vehículo)` para entrenarse. Estos labels tienen que venir de algún lado — del algoritmo geográfico como oráculo. Si el oráculo falla para el 67% de los casos (como vimos), el training set es escaso y sesgado.

**Cold start post-rotación:** En el día 1 de un nuevo período, el `route_id_rank` es nuevo. El modelo no tiene embeddings para esos ranks. Necesita fine-tuning con los datos del período nuevo, lo cual requiere días de observación + pipeline de reentrenamiento. Durante ese tiempo, sin fine-tuning, la inferencia degrada.

**Complejidad operacional:** Requiere pipeline de entrenamiento, validación, deploy de ONNX, monitoreo de drift. Un error en cualquier parte deja el sistema sin ramal ID.

**Overkill para el sub-problema:** El transformer fue diseñado para el caso donde la geografía no alcanza. Pero si la geografía + direction_id alcanzan para el 95% de los casos, el transformer agrega complejidad sin proporcional ganancia en accuracy.

**Dependencia circular:** El plan usa el algoritmo geográfico como oráculo para generar labels. Si el algoritmo geográfico ya funciona, ¿para qué el transformer?

### Cuándo tiene sentido

Cuando el algoritmo geográfico resuelve menos del 60% de los trips y el 40% restante es crítico para la cobertura. En ese caso, el transformer agrega valor real en la zona compartida de los primeros kilómetros de cada viaje.

---

## Enfoque B — Eliminación iterativa (implementación actual)

### Qué hace

Construye offline la lookup `route_id → shape` usando el siguiente algoritmo:

1. Para cada shape, calcula "zonas únicas": puntos del shape que están a >40m de todos los otros shapes del mismo período.
2. Acumula GPS de todos los vehículos de un route_id y cuenta cuántos caen en cada zona única.
3. El route_id con >95% de sus hits en las zonas únicas de un shape se resuelve a ese shape, que luego se elimina del conjunto competing. Las zonas únicas de los shapes restantes se expanden.
4. Repite hasta convergencia.

El resultado es una tabla `route_id → shape` que persiste hasta la próxima rotación.

### Ventajas

- **Sin entrenamiento**: es puramente geométrico, no necesita labels.
- **Determinístico y explicable**: se puede trazar exactamente por qué un route_id fue asignado a un shape.
- **Acumula evidencia**: cada día agrega más GPS al mismo route_id. La confianza aumenta con el tiempo.

### Desventajas

**Fraccionados destruyen el algoritmo:** 39D es un subset geográfico perfecto de 39A. Las zonas únicas de 39D dentro del conjunto {39A, 39D, ...} son vacías — no existen puntos de 39D que estén a >40m de 39A. El algoritmo produce 0 hits para 39D y nunca converge.

**La expansión no alcanza:** El mecanismo de expansión (eliminar un shape del conjunto competing expande las zonas del resto) no ayuda con fraccionados. Cuando 39C se elimina, las zonas de 39A se expanden respecto a 39B y 39C — pero la ambigüedad entre 39A y 39D persiste porque 39D sigue en el conjunto.

**Sensibilidad al threshold:** `UNIQUE_THRESHOLD_M=40` y `HIT_RADIUS_M=50` son parámetros que funcionan para algunas geometrías y no para otras. No hay garantía de que funcionen para todas las líneas objetivo.

**Complejidad acumulada:** El código creció con cada edge case: pairing de direction, resolución por dirección independiente, corrección del bug de shapes completos/fraccionados. Cada fix introduce el siguiente problema.

**El período de arranque:** En los primeros días post-rotación, hay pocos GPS acumulados. El algoritmo puede hacer resoluciones erróneas si el route_id A tiene un solo vehículo que coincidentemente pasó por la zona única del shape B.

### Por qué dio 0% en la prueba empírica — y por qué eso NO condena el approach

El `analisis_ramal_39_results.json` muestra `geo_hits_breakdown: {}` (vacío) para los 12 route_ids: cero hits totales. `find_unique_hit` devolvió `None` para *todos* los puntos GPS. La causa no es bootstrap lento, es más estructural: con 12 shapes solapados al ~80% y `UNIQUE_THRESHOLD_M=40`, la ronda 1 produce zonas únicas vacías/degeneradas (`< 2 puntos`) para *todos* los shapes a la vez, porque cada punto de cada shape está a <40m de algún otro shape. Si nadie resuelve en ronda 1, nada se elimina, las zonas nunca se expanden, y el `while` corta en `best_rid is None`. La cascada diseñada (eliminar C → expandir las zonas de A/B) nunca arranca porque requiere que alguien resuelva primero.

**Matiz empírico clave:** los fraccionados (39D/E/F) NO están en OSM. Se agregaron a mano a `line_shapes.json` para esta prueba. Fue precisamente al agregarlos que la eliminación pasó a 0/12 — un fraccionado es subset de su completo, no aporta puntos a >40m y además "roba" la zona única del completo. **Sin fraccionados en el set, la eliminación resolvía bien (probado antes, andaba okish).** Esto reordena el diagnóstico: el 0% no condena el approach geométrico per se — condena meter completos y fraccionados en el mismo set de competencia simultánea. Ver la sección [El problema de los fraccionados](#el-problema-de-los-fraccionados-transversal-a-b-y-c).

### Cuándo tiene sentido

Para líneas sin fraccionados, con ramales geográficamente bien separados (zonas únicas amplias). Para la línea 26 (1 ramal), probablemente resuelve perfecto. Para la 39 con sus 12 shapes (incluyendo fraccionados), no es el diseño correcto **sin separar completos de fraccionados** (ver sección dedicada).

---

## Enfoque C — Argmin de error perpendicular medio (propuesto)

### Qué hace

Para cada route_id, construye la lookup usando el siguiente algoritmo:

**Construcción:**
```
Para cada route_id R:
  shapes_candidatos = shapes donde direction == direction_id de R  (6 de 12)
  
  Para cada GPS point de cualquier vehículo con route_id R:
    Para cada shape candidato S:
      perp_error[S] += project(point, S).perp_error
    n_points[S] += 1
  
  mean_perp[S] = perp_error[S] / n_points[S]  # para cada S
  assigned_shape = argmin(mean_perp)
  
  if (second_best_mean - best_mean) / second_best_mean > MARGIN_THRESHOLD:
    lookup[R] = assigned_shape  # confiante
  else:
    lookup[R] = pending         # insuficiente margen, esperar más datos
```

**Fraccionados:** Una vez asignado a un shape S, verificar si es el shape completo o el fraccionado usando el rango de `dist_along` sobre S: si `min(dist_along) / total_length(S) > 0.2`, es un fraccionado (nunca llega al tramo inicial del shape completo). Sin coordenadas hardcodeadas.

**Uso en tiempo real:** dado un vehículo con `route_id=X`, hacer `lookup[X]` → shape asignado. O(1), sin GPS en tiempo real.

### Ventajas

**Funciona con fraccionados:** La media del error perpendicular de 39D sobre el shape 39D-d0 es ~5m. Sobre el shape 39A-d0 también es ~5m (porque comparten el track). El margen entre ambos es cero — el algoritmo reconoce que no puede distinguirlos con este criterio solo, y espera más datos o aplica el criterio de extent. No produce resolución incorrecta.

**Usa direction_id como filtro gratuito:** Reducir de 12 a 6 candidatos directamente. No necesita la lógica de eliminación.

**Más robusto en cold start:** Con pocas observaciones, la media del error tiene alta varianza. El threshold de margen controla cuándo la evidencia es suficiente. El algoritmo simplemente dice "pendiente" hasta tener suficientes datos, en vez de arriesgarse a una resolución errónea.

**Sin parámetros geométricos frágiles:** No hay `UNIQUE_THRESHOLD_M` ni `HIT_RADIUS_M`. Solo un `MARGIN_THRESHOLD` de interpretación directa (porcentaje de ventaja del ganador sobre el segundo).

**Código simple:** ~50 líneas de lógica core, frente a las ~200 del algoritmo de eliminación.

### Desventajas

**Fraccionado vs completo sigue siendo difícil geométricamente:** El criterio de extent del trip (min dist_along / total_length) requiere que el route_id haya acumulado trips completos (no viajes truncados). En los primeros días post-rotación, puede no haber trips completos aún.

**No usa información de flota:** No propaga el conocimiento de "este route_id ya fue identificado como 39A" a los vehículos del mismo route_id que están en zona compartida. Cada trip aporta evidencia individualmente. En la práctica no importa porque la lookup se construye offline acumulando todos los trips.

**La media cruda se diluye en troncales compartidas — y este caso NO es raro.** Los ramales comparten ~80% del recorrido (por algo son ramales). El 39A tiene apenas ~2 cuadras exclusivas frente a {B, C}. Si el route_id pasa el 80-98% de sus puntos sobre el tramo compartido (perp ~5m en todos los shapes) y solo el 2-20% sobre su tramo exclusivo, la **media** sobre todos los puntos diluye la señal discriminante:

```
mean_perp(puntos de A | shape A) ≈ 5m
mean_perp(puntos de A | shape B) ≈ 0.8·5 + 0.2·150 ≈ 34m   (20% exclusivo → margen amplio, OK)
mean_perp(puntos de A | shape B) ≈ 0.98·5 + 0.02·150 ≈ 7.9m (2% exclusivo → margen apretado, ruidoso)
```

Con tramo exclusivo chico (caso 39A vs {B,C}), `5 vs 7.9` es un margen relativo apretado y sensible a ruido. **La media es el estadístico equivocado acá.** Dos alternativas, ambas estrictamente mejores que la media y que el test binario de zonas únicas del Enfoque B:

- **Voto por punto:** para cada punto del route_id, cuál shape candidato ajusta mejor (`argmin perp` entre candidatos); después mayoría sobre todos los puntos. En la zona compartida el "mejor" se reparte como ruido entre los shapes solapados; en la zona exclusiva el correcto gana siempre. Con que los votos del 2% exclusivo superen el ruido del 80% repartido, gana el correcto. Degrada limpio a "empate/pendiente" para subsets puros (fraccionados). Es el discriminador recomendado.
- **Cuantil alto del perp (p90/p95):** en vez del promedio, usar la cola. Ignora el 80% compartido (donde todos empatan bajo) y se queda con la región donde vive la discriminación. Más simple de implementar que el voto, casi igual de robusto.

**Insight clave frente al Enfoque B:** `perp(punto, shape)` es una magnitud intrínseca — no cambia si eliminás otro shape del set. La eliminación iterativa existe para *agrandar* zonas únicas porque su test es binario ("¿el punto cae en una zona >40m?") y necesita zonas grandes. El voto/cuantil usa la magnitud continua del perp, así que las 2 cuadras exclusivas **siguen aportando señal sin necesidad de que sean amplias**. La maquinaria de eliminación resuelve un problema (zonas únicas chicas) que el voto/cuantil no tiene.

### Cuándo tiene sentido

Para el problema específico de construir la lookup `route_id → shape` en un contexto donde:
- `direction_id` está disponible
- Los route_ids son estables dentro del período
- Las shapes candidatas (filtradas por dirección) tienen suficiente diferencia geométrica en alguna parte de su recorrido

Este es exactamente el contexto de las líneas objetivo.

---

## El problema de los fraccionados (transversal a B y C)

Este problema NO está resuelto ni en la eliminación iterativa ni en el voto/cuantil. Lo que sigue es el diseño propuesto para resolverlo, no algo implementado.

### El ejemplo base (número-línea)

Una sola dirección (ida) con dos recorridos, donde el fraccionado D es un pedazo del completo A:

```
COMPLETO (A):   0km ●━━━━━━━━━━━━━━━━━━━━━● 10km
FRACCIONADO(D): 0km ●━━━━━━━● 4km   (pega la vuelta antes)
```

Todo lo que sigue se entiende con este dibujo.

### Por qué el perpendicular solo NO alcanza — y cuál dirección es la peligrosa

Hay dos confusiones posibles, y son asimétricas:

- **Bus ENTERO comparado contra el shape D (dirección fácil):** el bus recorre 0→10km; sus puntos de 4→10km caen FUERA de D y se clampean al extremo de D → perp enorme. **D se descarta solo.** Un entero nunca se confunde con un fraccionado.
- **Bus FRACCIONADO comparado contra el shape A (dirección peligrosa):** el bus recorre 0→4km; todos sus puntos caen ENCIMA de A (porque 0→4km es parte de A) → perp bajo en todos lados. **Encaja perfecto en A.** Acá está el riesgo real: asignar el fraccionado al completo.

Ningún estadístico de perpendicular (media, cuantil, voto) rompe la segunda confusión, porque por definición no existe ningún punto de D que esté lejos de A. **La señal discriminante no es transversal (perp) — es longitudinal (extent):** importa *cuánto del recorrido recorrió* el bus, no qué tan cerca está de la línea.

> **Corrección de fraseo:** "no asignar un viaje entero a un fraccionado" (lo que decía antes este doc) es la dirección **fácil**, se resuelve sola por el desborde. El problema duro es el inverso: **no asignar un fraccionado al entero.** Lo que lo resuelve es `coverage`, abajo.

### Las DOS preguntas — son distintas y hay que medir las dos

Para cada par (route_id, shape candidato) se calculan dos números que responden preguntas diferentes:

**Pregunta 1 — `containment`: "¿el bus se SALE de este recorrido?"**
Fracción de los puntos del bus que caen DENTRO del extent del shape con perp bajo (no clampeados a los extremos).
- Bus entero vs shape D → se sale (≈40% encaja, 60% colgado) → containment **bajo**.
- Bus fraccionado vs shape A → no se sale (todo encaja) → containment **alto**.

**Pregunta 2 — `coverage`: "¿el bus LLENA este recorrido de punta a punta?"**
Fracción del largo del shape que el bus efectivamente recorrió.
- Bus fraccionado vs shape A (0→10km) → solo pisó 0→4km → coverage **bajo (40%)**.
- Bus fraccionado vs shape D (0→4km) → pisó todo → coverage **alto (100%)**.

`containment` mira si **desborda**; `coverage` mira si **llena**. Son ortogonales: un viaje puede encajar sin llenar (fraccionado dentro del entero) o llenar sin encajar no existe. Por eso hacen falta las dos.

### Requisitos previos (se resuelven offline, sin GPS)

**A) Saber qué shapes son fraccionados.** → Para cada par de shapes (S1, S2) de la misma dirección, testear si S1 es subset geométrico de S2 (todos los puntos de S1 a <Xm de S2, y `length(S1) < length(S2)`). Eso etiqueta cada shape como *completo* o *fraccionado-de-Y*. Mapa shape→shape, estable todo el período.

**B) Saber de qué completo es fracción cada fraccionado.** → Sale del mismo test de (A): el "padre" de D es el completo que lo contiene. Solo geometría, sin datos.

Importante: (A) y (B) clasifican los **shapes**, no los **route_ids**. Saber qué route_id es entero vs fraccionado es lo que resuelve `coverage` (sección siguiente).

### Discriminador unificado: regla de (containment, coverage)

**Regla:** entre los shapes donde el bus NO se sale (containment alto), quedarse con el que MEJOR llena (coverage más alto = el shape más ajustado que el viaje llena sin excederse).

| route_id real | shape A (entero) | shape D (fraccionado) | Asigna |
|---|---|---|---|
| **entero (0→10km)** | containment alto, coverage 100% | containment **bajo** (se sale) ❌ | **A** ✓ |
| **fraccionado (0→4km)** | containment alto, coverage **40%** | containment alto, coverage 100% | **D** ✓ |

- El entero tiene un solo shape donde no se sale (A) → va a A.
- El fraccionado encaja en los dos, pero solo **llena** D → `coverage` desempata a D.

Esto asigna a cada route_id directo, en **una sola pasada**, sin route_id_rank ni pairing. Requiere que el shape fraccionado exista en el set (requisito de datos, no de algoritmo).

### Cómo lo aplica cada enfoque

La señal limpia para separar enteros de fraccionados es **`coverage` sobre un shape completo**: un route_id entero llega a ≈100% (recorre el completo de punta a punta); un fraccionado nunca lo logra (siempre parcial). Los dos enfoques usan esto, pero de forma distinta.

**Eliminación iterativa (Enfoque B) — NECESITA las dos etapas explícitas:**
La eliminación se atasca si los fraccionados están en el set (roban las zonas únicas, ver "Por qué dio 0%"). Entonces hay que sacarlos antes:
1. **Etapa 1 — quedarse con los completos.** Los route_ids con `coverage ≈ 100%` sobre algún shape completo son los enteros. Correr la eliminación iterativa SOLO sobre esos (acá las zonas únicas existen y la cascada arranca → recupera el "andaba okish"). Esto te deja los 6 correctos asignados y fuera del set.
2. **Etapa 2 — los que sobran son fraccionados.** Para cada uno, asignarlo al shape fraccionado que llena (`coverage` alto) y donde no se sale (`containment` alto), contra el padre ya conocido por (A)/(B).

**Voto/cuantil (Enfoque C) — NO necesita separar el set:**
El discriminador unificado (containment, coverage) ya asigna entero o fraccionado en una sola pasada (tabla de arriba). El voto-por-punto / cuantil-alto se usa solo como criterio de perp para elegir *entre completos* cuando hay varios candidatos solapados; el extent (containment/coverage) se encarga de la dimensión entero-vs-fraccionado. No hay bootstrap que se trabe porque no depende de zonas únicas. Conviene igual gatear por confianza (margen mínimo) antes de escribir en la lookup, y dejar "pendiente" lo dudoso.

**Resumen:** la eliminación usa coverage como *filtro previo* (dos etapas obligatorias); el voto/cuantil usa coverage como *una de las dos dimensiones del mismo criterio* (una etapa). En ambos, `containment` y `coverage` son las dos preguntas que hay que medir sí o sí.

### Qué queda genuinamente sin resolver

- **Cold start del fraccionado:** con 1-2 días post-rotación un fraccionado puede tener pocos trips y no haber mostrado aún su *extent envelope*. Es indistinguible de un completo mal observado. → queda "pendiente" hasta acumular trips. Degradación aceptable.
- **Fraccionado sin shape propio:** si un fraccionado no tiene shape en `line_shapes.json` (el caso por defecto en OSM hoy), su route_id se asigna al completo padre (containment alto, no hay shape más ajustado disponible). Degradación: la proyección de ETA es correcta en el tramo que recorre, pero el etiquetado de ramal es incorrecto. No es catastrófico para ETA, sí para la identificación.
- **"Completo poco observado" vs "fraccionado":** ambos muestran extent corto. Solo el volumen de trips a lo largo del período desambigua. → gate por número mínimo de trips antes de declarar un route_id como fraccionado.

---

## Comparación directa

| Dimensión | Modelo A (Transformer) | Enfoque B (Eliminación iterativa) | Enfoque C (Argmin perp) |
|-----------|----------------------|----------------------------------|------------------------|
| **Tipo de problema** | Clasificación en tiempo real | Construcción offline de lookup | Construcción offline de lookup |
| **Labels necesarios** | Sí (del oráculo geográfico) | No | No |
| **Fraccionados** | Maneja (por route_id_rank) | No maneja sin separar el set (zonas vacías) | No por perp; requiere (containment, coverage) secuencial |
| **Cold start post-rotación** | Días (requiere fine-tuning) | 1-2 días (acumulación de GPS) | 1-2 días (acumulación de GPS) |
| **Complejidad del código** | Alta (entrenamiento, deploy, ONNX) | Media-alta (muchos edge cases) | Baja |
| **Parámetros a tunear** | Muchos (arquitectura, lr, epochs) | Varios (thresholds geométricos) | Uno (margin_threshold) |
| **Explicabilidad** | Baja (caja negra) | Alta (trazable) | Alta (trazable) |
| **Overhead operacional** | Alto (pipeline ML completo) | Bajo | Bajo |
| **Dependencia circular** | Sí (usa el oráculo como label) | No | No |
| **Direction_id como feature** | Sí (embedding) | No (resuelve por separado) | Sí (filtro nativo) |
| **Tiempo de implementación** | Semanas | Ya implementado (parcial) | Horas |

---

## Qué falta resolver en cada enfoque y su impacto

> **Nota sobre el "67%":** el doc cita que el oráculo geométrico falla para el 67% de los trips, pero el experimento real (`analisis_ramal_39_results.json`) midió 0/12 route_ids resueltos = 100% de falla, *con los fraccionados en el set*. No confiar en el "67%" como dato. El número medido depende fuertemente de si los fraccionados están en el set de competencia (ver Enfoque B → "Por qué dio 0%").

### Modelo A
- Definir cómo generar labels de calidad cuando el oráculo geométrico falla (en la prueba: 0% con fraccionados)
- Diseñar el fine-tuning post-rotación sin introducir latencia inaceptable
- Validar que el route_id_rank (posición relativa) transfiere entre períodos
- **Impacto si se resuelve mal:** el modelo puede aprender correlaciones espurias y degradar silenciosamente

### Enfoque B
- Separar completos de fraccionados antes de la eliminación (no es un bug puntual, es el orden de resolución). Ver [sección de fraccionados](#el-problema-de-los-fraccionados-transversal-a-b-y-c)
- El threshold UNIQUE_THRESHOLD_M necesita calibración por línea
- **Impacto si no se resuelve:** se atasca en ronda 1 (0 resueltos) cuando completos y fraccionados compiten juntos

### Enfoque C
- Reemplazar la media de perp por voto-por-punto o cuantil-alto (la media se diluye con ~80% de tramo compartido)
- Implementar el discriminador (containment, coverage) para fraccionados — resuelve los tres requisitos A/B/C de la sección dedicada
- Validar empíricamente el margen real 39A/B/C y el comportamiento en D/E/F (hoy es aritmética de servilleta, no medición)
- **Impacto si no se resuelve:** completos con tramo exclusivo chico quedan en margen apretado/ruidoso; fraccionados quedan "pendientes" en lugar de resolverse incorrectamente

---

## Recomendación

**Para el MVP de ETA:** usar Enfoque C.

El objetivo del MVP no es identificación perfecta de fraccionados — es predecir ETA para los viajes principales. Los ramales A/B/C (completos) representan la mayoría del tráfico y el Enfoque C los resuelve limpiamente en 1-2 días post-rotación usando direction_id como filtro. El overhead de implementación es mínimo.

**El Modelo A:** guardarlo para Phase 2 o para el problema de ETA en la zona compartida de los primeros kilómetros, donde sí agrega valor real. Específicamente, la inferencia por asociación de flota ("todos los vehículos con route_id_rank=2 son 39A, incluyendo los que están en zona ambigua") no requiere el transformer completo — puede hacerse con la lookup del Enfoque C.

**El Enfoque B:** abandonarlo para líneas con fraccionados. Mantenerlo como referencia para líneas simples (26, posiblemente 42) donde funciona sin modificaciones.

---

## La pregunta correcta para el MVP

> ¿Qué porcentaje de trips de las 7 líneas son fraccionados?

Si los fraccionados representan menos del 15% del tráfico, el Enfoque C da cobertura del 85%+ desde el día 2 post-rotación, que es suficiente para lanzar un MVP. Los fraccionados se pueden resolver en iteración siguiente con el criterio de extent.

Este dato se puede obtener directamente del `route_id_explorer_results.json` comparando `obs_count` de los route_ids de alto volumen (A/B/C) contra los de bajo volumen (D/E/F) por período.
