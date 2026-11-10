# Research: Variante débil de ETA sin ramal conocido

## El problema

El pipeline A3 requiere conocer el `shape_id` del vehículo para:
1. Proyectar el trip sobre el shape correcto → obtener `dist_along_shape_m` por punto
2. Normalizar `dist_remaining_m / shape_length_m` → feature escalar para el modelo
3. Generar la `trajectory` (secuencia de `dist_along_norm`, speed, dt)

Este mapeo hoy viene de `ramal_lookup/ramal_map.json` → `(route_id, direction_id) → shape_id`. Solo cubre la línea 39.

### Por qué es intractable construir ramal_map manualmente

**Caso 168 — el bug Darwin (intractable por diseño del API):**  
Desde La Boca, la 168A y la 168C salen juntas por el mismo tramo (~45 min hasta la zona Darwin). El API asigna route_id 1260/1780 a *todos* los vehículos en ese tramo compartido. El route_id solo se resuelve al llegar a Darwin, cuando el API reasigna 1254 (168A) o 1258 (168C). **No es un problema de mapeo — el API genuinamente no sabe el ramal.** El análisis de 66 días y 9341 viajes Darwin probó 10 features distintas sin superar 62% de accuracy. La ambigüedad es inherente a la fuente de datos.

**Caso otras líneas — inmanejable en la práctica:**  
Construir ramal_map requiere identificar todos los route_id activos, verificar a qué ramal físico corresponde cada uno, y repetirlo tras cada rotación del API (~3 semanas). Para la línea 39 fue viable como caso de desarrollo. Para 6 líneas en simultáneo con rotaciones no documentadas es inmanejable. Las 6 líneas restantes quedarían permanentemente sin datos de entrenamiento.

**Consecuencia actual:** todos los vehículos de las líneas 26, 42, 92, 124, 151, 168 (y los Darwin del 168) son skipped en `build_dataset.py:293-295`.

El modelo A3 **no toma ramal_id como input** — lo necesita el pipeline de datos para la proyección, no el forward pass.

---

## Opción A — Proyección geométrica (variante débil)

**Idea:** En vez de lookup por route_id, proyectar el trip sobre todos los shapes de la línea y seleccionar el de menor error perpendicular mediano. No hay ramal_map.

### Por qué las labels de entrenamiento Darwin son válidas

Este es el argumento central que justifica la opción A.

Los training rows son pares `(P, F)` donde `observed_eta_s = F.ts - P.ts` — tiempo real entre dos puntos GPS del mismo viaje. Para que este label sea válido, solo hace falta que tanto P como F estén correctamente proyectados sobre el shape elegido.

El mecanismo que garantiza esto ya existe: `project_trip` filtra puntos con `perp_error > 150m`. Para un vehículo Darwin proyectado sobre el shape incorrecto (ej: va a 168C pero proyectamos sobre 168A):
- En el tramo compartido: `perp_error ≈ 10-20m` → ambos shapes → puntos válidos → F puede estar en el tramo compartido
- Post-fork: el vehículo diverge físicamente de 168A → `perp_error ≈ 300-500m` → puntos filtrados

El resultado: el trip proyectado sobre 168A queda con puntos **solo hasta el fork**. Los pares `(P, F)` generados tienen P y F dentro del tramo compartido, donde ambas shapes son la misma geometría física. El `observed_eta_s` es correcto. **El label es válido independientemente del ramal final del vehículo.**

La variante es "débil" no porque los labels sean incorrectos, sino porque los datos de Darwin solo enseñan al modelo a predecir ETAs dentro del tramo compartido — no cubren el tramo post-fork de esos viajes.

### Ruido de normalización (limitación real)

Hay un problema sutil: dos shapes con perp_error similar dan **normalizaciones diferentes**. Para la misma posición física en el tramo compartido, 168A (longitud ~45km) y 168C (longitud ~35km) producen `dist_remaining_norm` distintos por un factor ≈ 0.78. Si `best_shape_for_trip` elige 168A para algunos viajes Darwin y 168C para otros (perp_errors casi iguales en el tramo compartido), el modelo recibe la misma situación física con codificaciones distintas. Esto es **ruido, no bias** — el modelo promedia sobre ambas normalizaciones sin sesgo sistemático, pero la varianza del error en ese segmento es mayor.

A escala (7 líneas), los viajes Darwin representan una fracción de los datos. Con datos de ramales completos de varias líneas, este ruido se diluye.

### Problema de consistencia train/inferencia

**En training:** `best_shape_for_trip` recibe el trip completo. Para viajes no-Darwin (post-fork), la elección de shape es estable (perp_error muy diferente entre shapes). Para Darwin en el tramo compartido, la elección es arbitraria pero consistente dentro del mismo trip.

**En inferencia:** el predictor tiene el trip parcial (GPS acumulado hasta ahora). Durante el tramo Darwin, ambas shapes tienen perp_error bajo → la elección puede diferir de la que se haría con el trip completo. Esto genera una distribución de entrada levemente distinta a la de entrenamiento.

Mitigación: en cuanto el API resuelve el route_id post-fork, el sistema usa el shape correcto con certeza (`route_shape_map` toma precedencia). El período de inconsistencia es solo durante el tramo Darwin.

**Discontinuidad al fork:** si el sistema eligió 168A durante Darwin pero el vehículo va a 168C, el historial de trayectoria tiene una discontinuidad de normalización en el momento del switch de shape. Este es un artefacto de corta duración (el API resuelve el route_id rápido post-fork) pero existe.

### Comportamiento UX resultante

*Tramo compartido (Darwin, ~45 min):*  
El sistema ve al vehículo. Puede dar ETA a paradas del tramo compartido. Para paradas post-fork (ej: Belgrano, solo 168A), el sistema no puede confirmar si el bus las sirve — dice "viene un 168 en X minutos" pero no "viene el 168A". El usuario sabe que hay un bus en camino, no a dónde va.

*Post-fork (API resuelve route_id):*  
La proyección geométrica elige el shape correcto (el bus divergió, perp_error alto en el incorrecto). ETA ramal-específica y precisa. Para paradas post-fork, la predicción solo aparece en los últimos ~15-20 min del viaje.

### Cambios necesarios

- `projector.py`: +`best_shape_for_trip(lats, lons, {sh_id: ShapeIndex}) → (sh_id, median_perp)`
- `build_dataset.py`: precomputo `line_shape_indices` por línea, fallback geométrico si `route_shape_map` no tiene entrada, remoción del skip `if not sh_id`
- Modelo A3: **sin cambios**
- Reentrenamiento: **una vez** con las 7 líneas

---

## Opción B — Doble proyección en inferencia

**Idea:** Para vehículos Darwin, proyectar sobre ambas shapes y correr A3 dos veces. Devolver dos ETAs con el hint de 62% del viaje previo.

**Limitación:** Específico por línea (requiere identificar Darwin manualmente para cada nueva línea). No genera datos de entrenamiento para las 6 líneas sin ramal_map.

---

## A y B son complementarias

El documento las presenta como alternativas pero no lo son. A resuelve el problema de datos de entrenamiento para todas las líneas. B resuelve el problema de UX para el tramo Darwin — en vez de "viene un 168", muestra "168A en X min / 168C en Y min". Se pueden implementar independientemente:

- **Solo A:** mejor modelo, peor UX en Darwin (no dice el ramal)
- **Solo B:** mejor UX en Darwin para la 168, modelo sigue entrenado solo con línea 39
- **A + B:** mejor modelo Y mejor UX en Darwin — este es el objetivo a mediano plazo

---

## Consideraciones de escala

**Volumen de datos actual:** 9165 filas de entrenamiento (solo línea 39). Al agregar 6 líneas, el volumen depende del número de viajes por día por línea y los días grabados. Si algunas líneas tienen 5-10x más viajes que la 39, el modelo puede sobre-representar sus patrones. Considerar muestreo balanceado por línea si el desbalanceo es pronunciado.

**Shapes disponibles hoy:** 7 líneas en `line_shapes.json`. Agregar una nueva línea requiere agregar su shape (proceso descrito en `SHAPES_PIPELINE.md`) — una sola vez, no por rotación.

**Darwin en otras líneas:** el bug Darwin puede existir en otras líneas (cualquier línea con segmento inicial compartido entre ramales). Con proyección geométrica esto se maneja automáticamente sin trabajo adicional.

---

## Comparativa A vs B

| | A (geom, variante débil) | B (doble inferencia) |
|---|---|---|
| Reentrenamiento | 1 vez | No |
| Generalizable | Sí, todas las líneas automáticamente | No (manual por línea) |
| Predicción Darwin | Por línea — ETA hasta fork | Por ramal — dos ETAs con incertidumbre |
| Predicción post-fork | Por ramal (igual que hoy) | Por ramal (igual que hoy) |
| Resuelve las 6 líneas sin ramal_map | Sí | No |
| Cambios modelo | Ninguno | Ninguno |
| Complementarias | Sí — se pueden combinar | Sí |

**Relación con el modelo primario:** A es la degradación aceptable mientras no hay ramal_map para una línea. A medida que se agregan líneas con ramal_map completo, el mismo modelo mejora sin cambios de arquitectura — la proyección geométrica converge al shape correcto con mayor certeza porque los datos de entrenamiento son más limpios.

**Nota — shape virtual (D) es un caso particular de A:** construir el shape del tramo compartido manualmente produce el mismo resultado que A, porque el algoritmo geométrico lo elegiría de todas formas. A lo hace automáticamente.

---

## Recomendación

**Implementar A primero.** Desbloquea las 7 líneas sin cambiar el modelo. Luego evaluar si agregar B para mejorar la UX de Darwin en la 168.

---

## Estado actual del código (referencias)

- `build_dataset.py:268-305` — bloque de resolución shape + skip Darwin
- `build_dataset.py:194-205` — precomputo `shape_indices` y `naive_shape_indices` (el naive es código muerto: `direction=None` en todos los shapes)
- `projector.py:84-146` — `project_many` vectorizado, base para `best_shape_for_trip`
- `projector.py:167-193` — `project_trip` con filtro `perp_error > 150m`
- `a3_eta.py:96-152` — forward del modelo (sin ramal_id como input)
- `168_ramal_analysis.md` — análisis del bug Darwin: mapa de route_ids por período, 10 features testeadas, señal del viaje previo (62%)
