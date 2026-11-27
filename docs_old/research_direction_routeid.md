# Research: direction_id y route_id en la API de transporte CABA/GBA

*Basado en análisis empírico de 62 días (29-mar-2026 → 29-may-2026), 7 líneas objetivo.*

---

## 1. Qué es direction_id

`direction_id` es un campo binario (0 o 1) que devuelve la API de posiciones en tiempo real para cada vehículo. Según el estándar GTFS-RT, 0 representa un sentido de circulación y 1 el opuesto. En la práctica para la red CABA/GBA:

- No está documentado cuál es "ida" y cuál es "vuelta" — es una convención interna del operador/concesionario.
- No cambia durante un viaje: si un vehículo tiene `direction_id=0` en un snapshot, lo tendrá en todos los del mismo viaje.
- Es **constante por route_id dentro de un período**: en los 62 días analizados, ningún route_id que tenga volumen significativo de observaciones presentó ambas direcciones. Los pocos casos de `dual_direction` encontrados en línea 151 son noise o vehículos en transición de servicio.

---

## 2. Relación entre route_id y direction_id

### Observación fundamental
Cada route_id mapea a exactamente **una** direction_id dentro de un período de vigencia. No existe un route_id que opere en ambas direcciones con regularidad. Esto implica que `(route_id, direction_id)` es redundante — conocer el route_id es suficiente para determinar la dirección.

### Cantidad por línea y período
La cantidad de route_ids activos por período es fija por línea y se divide en mitades exactas entre direction_id=0 y direction_id=1:

| Línea | route_ids/período | dir=0 | dir=1 |
|-------|------------------|-------|-------|
| 26    | 2                | 1     | 1     |
| 39    | 12               | 6     | 6     |
| 42    | 4                | 2     | 2     |
| 92    | 8                | 4     | 4     |
| 168   | ~8               | ~4    | ~4    |

La simetría es perfecta. Cada shape físico (ramal × dirección) tiene exactamente un route_id asignado en un período dado.

---

## 3. El patrón de numeración y el "pairing"

### Patrón observado desde mayo 2026
En los períodos post-rotación desde el 8 de mayo, los route_ids se asignan en pares consecutivos con direction_ids opuestos:

```
N   → direction_id = 0
N+1 → direction_id = 1
N+2 → direction_id = 0
N+3 → direction_id = 1
...
```

Ejemplos confirmados:
- Línea 39, período 2: 1973(d0) 1974(d1) 1975(d0) 1976(d1) ... 1983(d0) 1984(d1)
- Línea 39, período 3: 1947(d0) 1948(d1) 1949(d0) 1950(d1) ... 1957(d0) 1958(d1)
- Línea 42, período 2: 2041(d0) 2042(d1) 2043(d0) 2044(d1)
- Línea 92, período 2: 1411(d0) 1412(d1) 1413(d0) 1414(d1) ... 1417(d0) 1418(d1)
- Línea 26: 2530(d0) 2531(d1) → 2059(d0) 2060(d1)

### Patrón observado en marzo 2026 (período anterior)
En el primer período del dataset (antes de la rotación de mayo), el patrón era diferente: todos los route_ids de direction_id=1 juntos, seguidos de todos los de direction_id=0. La numeración sigue siendo consecutiva pero el interleaving no existe:

```
Línea 39, período 1: 1329(d1) 1330(d1) 1331(d1) 1332(d1) 1333(d1) 1334(d1)
                     1335(d0) 1336(d0) 1337(d0) 1338(d0) 1339(d0) 1340(d0)

Línea 92, período 1: 2457(d0) 2458(d0) 2459(d0) 2460(d0)
                     2461(d1) 2462(d1) 2463(d1) 2464(d1)
```

Esto indica un **cambio en el generador de route_ids del backend** entre marzo y mayo, probablemente asociado a una actualización del sistema de gestión del operador.

### Consecuencia: el pairing no es estructural
El patrón N/N+1 es una característica del generador vigente, no una garantía del protocolo. Una futura rotación podría volver al patrón agrupado o introducir uno distinto. El pairing es **detectable empíricamente** (si N y N+1 tienen direction_ids opuestos, son un par probable) pero no puede asumirse a priori.

---

## 4. Rotaciones y su efecto en direction_id

### Qué es una rotación
Una rotación es el evento donde el backend reasigna todos los route_ids de una línea simultáneamente. Los route_ids anteriores dejan de usarse y aparecen route_ids nuevos que representan los mismos ramales físicos.

### Comportamiento observado
- **Simultáneas o en 2-3 días**: la mayoría de las líneas rotan todos sus route_ids en un solo día. La línea 39 mostró en su tercer período rotaciones escalonadas (6 el 23-may, 6 más el 26-may).
- **Corte limpio**: en casi todos los casos los route_ids viejos dejan de aparecer antes o el mismo día que aparecen los nuevos. El overlap máximo observado fue de 0 días para las líneas limpias.
- **El conteo por dirección se preserva**: cada rotación produce exactamente el mismo número de route_ids por dirección que el período anterior. No se observaron rotaciones que cambien la cantidad de ramales activos.
- **Los route_ids no se reutilizan**: en 62 días, ningún route_id reapareció en líneas limpias (26, 39, 42, 92, 168). Son identificadores únicos con ciclo de vida de ~2-3 semanas.

---

## 5. Casos anómalos

### Route_ids de bajo volumen
En cada período existen route_ids con `obs_count` muy bajo (< 100 observaciones en todo el período) y `days_active` de 1-3 días. Estos pueden ser:
- Fraccionados que operan esporádicamente
- Vehículos en servicio de prueba o reposicionamiento
- Errores de asignación del sistema

Estos route_ids no deben excluirse a priori: un fraccionado que opera 2 días por semana tendrá bajo obs_count pero es un servicio real con su propio ramal físico.

### Línea 151 — caso especial
La línea 151 presenta 71 route_ids únicos en 62 días, con rotaciones parciales frecuentes (cada 5-10 días), muchos route_ids con obs_count=1 o 2, y algunos con `dual_direction_ids`. Esta línea parece operar bajo un contrato o sistema de asignación diferente. Cualquier análisis sobre la 151 requiere un filtro previo de route_ids por volumen mínimo antes de aplicar cualquier heurística.

### Línea 124 — caótica moderada
La 124 tiene route_ids con gaps frecuentes (desaparecen y reaparecen con gaps de 6-21 días), lo que sugiere servicios que no operan todos los días de la semana o variaciones estacionales. El pairing N/N+1 sí aparece en sus períodos más recientes.

---

## 6. Implicaciones para el algoritmo de identificación de ramal

### Lo que direction_id aporta
Conocer la dirección del vehículo reduce el espacio de búsqueda a la mitad: si `direction_id=0`, solo hay 6 shapes candidatos (de los 12 de la línea 39). El algoritmo de eliminación iterativa puede operar sobre un subconjunto de shapes en vez del conjunto completo.

### Lo que el pairing aporta
Si el pairing N/N+1 se verifica para el período actual (detectable en el primer día de observación), resolver un route_id implica resolver su par automáticamente. Esto es especialmente valioso en los primeros días post-rotación cuando la evidencia geográfica es escasa.

El pairing debe verificarse, no asumirse: comprobar que N+1 existe, está activo, y tiene direction_id opuesto antes de aplicar la inferencia.

### Ventana post-rotación
El único período problemático para el lookup `route_id → ramal` es el día de la rotación y hasta que el algoritmo converge (1-2 días). Durante esa ventana:
- Los route_ids viejos ya no aparecen → el lookup anterior es inútil
- Los nuevos route_ids no están mapeados aún
- La dirección se conoce desde el primer snapshot (direction_id está disponible en tiempo real)

El direction_id permite hacer predicciones parciales durante la ventana (se sabe "este vehículo va en sentido 0") incluso sin saber el ramal exacto.

---

## 7. Resumen ejecutivo

| Propiedad | Observación |
|-----------|-------------|
| route_id → direction_id | Relación 1:1, estable dentro del período |
| Pares N/N+1 (desde mayo 2026) | Confiable, verificable, no garantizado en futuras rotaciones |
| Simetría dir=0/dir=1 | Siempre mitad y mitad por período |
| Duración de un período | ~2-3 semanas |
| Overlap en rotaciones | 0 días en líneas limpias |
| Reutilización de route_ids | No observada en 62 días |
| Líneas "limpias" | 26, 39, 42, 92, 168 |
| Líneas con comportamiento especial | 151 (muy caótica), 124 (gaps frecuentes) |
