# Grabador de CuandoSubo: estado (2026-11-22 15:53) y plan del primer experimento

Medido leyendo `\\192.168.0.18\buffer\grabaciones_cuandosubo` (la unidad `Z:` figura "No disponible" en esta sesión; la ruta UNC funciona). Sin SSH al NUC (`laek@192.168.0.18` rechaza la clave: no hay `docker ps` ni logs). Solo lectura; no se tocó el grabador. Análisis con proceso en prioridad Idle.

## 1. Estado del grabador

**Corriendo.** `health`, `state.json` y `stats.json` se escribieron a las 15:48:58 del 2026-11-22. Último despliegue: 2026-11-14 18:24 BA (`stats.started_at`; los contadores se reinician ahí). Primer dato: 2026-11-13 23:03 BA.

### Días disponibles

Todas las horas son de Buenos Aires. Posiciones = frames de 45 s. Arribos = consultas por parada (18 paradas, 3 por línea). Día completo = 1920 frames y 5760 consultas.

| Día | Posiciones (MB, frames) | Arribos (MB, consultas) | Horarios (MB) | Huecos de posiciones (> 5 min) | Huecos de arribos |
|---|---|---|---|---|---|
| 11-13 (jue) | 0,3 / 75 | 0,14 / 225 | 0,15 | parcial: arranca 23:03 | parcial: arranca 23:04 |
| 11-14 (sáb) | 9,8 / 1874 | 4,06 / 5620 | 2,17 | 02:19–03:02 y 18:23–18:58 (reinicio por despliegue; registro `gap` restart, 2149 s) | 18 paradas con corte > 20 min (el mismo reinicio) |
| 11-15 (dom) | 7,8 / 1920 | 3,58 / 5760 | 1,14 | ninguno | ninguno |
| 11-16 (lun) | 14,4 / 1919 | 5,40 / 5760 | 2,79 | 02:31–03:03 | ninguno |
| 11-17 (mar) | 14,8 / 1916 | 5,47 / 5748 | 1,16 | 02:20–03:03 | ninguno |
| 11-18 (mié) | 14,8 / 1920 | 5,49 / 5760 | 0,89 | ninguno | ninguno |
| 11-19 (jue) | 14,9 / 1920 | 5,51 / 5760 | 0,76 | ninguno | ninguno |
| 11-20 (vie) | 14,5 / 1920 | 5,44 / 5760 | 0,71 | 02:21–03:01 | ninguno |
| 11-21 (sáb) | 9,8 / 1921 | 4,13 / 5759 | 0,61 | ninguno | ninguno |
| 11-22 (dom, parcial) | 2,1 / 510 | 1,26 / 1984 | 0,18 | **00:26–09:54 (9,5 h, `gap` outage, 34.071 s)** | sin consultas 00:30–07:00; parciales 07 y 08 h |

- **Días completos útiles: 8** (14 al 21), todos con los 3 flujos. El 14 tiene el reinicio de 35 min. Con el 22 parcial (10:00 en adelante) y el 13 (desde las 23:03) suman casi 9 días.
- **Corte del 2026-11-22 00:26–09:54: afecta también a la API CABA.** El grabador CABA tiene el mismo hueco (1795318006 → 1795352074, 9,5 h). Es una caída del NUC, no del grabador de CuandoSubo. Causa no determinada: sin SSH no vi el log. Ambos volvieron solos.
- **Corte nocturno de posiciones ~02:20–03:03 (40 min):** 14, 16, 17 y 20. Los arribos siguen en esas horas (240 consultas/h), así que no es el grabador entero. Posible causa: WAF o servidor de OBA a esa hora; sin confirmar. Impacto casi nulo (madrugada).
- Los 4 flujos graban: posiciones (A+C), arribos (B), horarios (D); `paradas.json` y `horarios_index.json` se actualizan (`horarios_index` 1,4 MB).

### Salud (stats.json acumulado desde 2026-11-14 18:24, 14.549 ciclos)

| Contador | Valor |
|---|---|
| requests | 150.033 (A 87.294, arribos 43.647, trips 18.985, C 0) |
| waf | **213** (~27/día; cada uno = pausa de 120 s) |
| fetch_errors | 373 (último: ReadTimeout a `vehicles-for-agency/12`) |
| cycle_overrun | 17 |
| empty_cycles | 203 |
| gaps (registros) | 2 (restart del 14 y outage del 22) |
| artifacts | 384 |
| shared_ts | 2.185.027 (con falsos positivos, README §10) |
| identity.conflicts | **0** |
| trips_queue | 3 (prioritarios 0), `trips_missing` 0, `horario_cambiado_total` 0 |

- **C = 0 requests:** la rotación del resto de AMBA no corre nunca (tier A + arribos + horarios copan el ciclo). Las posiciones cubren solo las agencias de `RECORD_LINES` (39 26 42 92 152 168); `lines_seen` = 7 porque la 132 aparece en la agencia de la 92.
- El grabador no se rompió: ningún dato malo encontrado. Pendientes a anotar: el corte nocturno de posiciones y el outage del 22.
- Volumen: ~15 MB/día de posiciones en día hábil (7,8–9,8 en fin de semana), ~5,5 MB de arribos, ~1 MB de horarios.

## 2. Cobertura

### Posiciones

IDs distintos por línea (por label, día hábil 18): 152: 120, 39: 93, 132: 91, 92: 86, 168: 77, 26: 60, 42: 47. En stats (15:48 del 22) coches con reporte < 3 min: 39: 21 de 45, 26: 8/21, 42: 12/19, 92: 27/37, 152: 54/70, 168: 8/21.

### Arribos: paradas

`arrival_stops.json`: 18 paradas, 3 por línea (generado 2026-11-13). Paradas de las líneas 39, 26, 42, 92, 168 y 152, listadas en README §11 (inicio, medio y final). 152 no validado contra `line_shapes.json` legacy; sí existe en `proyectoconsola/data/line_shapes/152.json` (fuente única del pipeline).

Por día hábil (11-18): 960 consultas por línea (cada parada cada ~4,5 min), ~108.700 entradas de arribo, de las cuales **46 % sin coche** (solo horario, `predicted: false`) y 54 % con tiempo real (58.400). Todo coche con tiempo real trae `pred_arr`; `lag` t − `veh_ts` mediano 123 s (p10 94, p90 155; el 22: mediana 82). 16 % de las entradas con tiempo real (9.621 de 58.391) tienen `stops_away < 0` (ya pasó, según OBA).

Entradas con tiempo real y coche de la línea del panel (por label, `veh_line` = línea de la parada), por día:

| Día | 39 | 42 | 92 | 168 | 152 | 26 |
|---|---|---|---|---|---|---|
| 11-14 | 6991 | 4026 | 5965 | 4952 | 7260 | 0 |
| 11-15 | 5202 | 2973 | 4423 | 2537 | 5817 | 0 |
| 11-16 | 10212 | 5290 | 7134 | 7770 | 12045 | 0 |
| 11-17 | 10611 | 5682 | 7247 | 8326 | 12366 | 0 |
| 11-18 | 10458 | 5750 | 7222 | 8213 | 12445 | 0 |
| 11-19 | 10769 | 5847 | 7294 | 8037 | 12495 | 0 |
| 11-20 | 10712 | 5610 | 7313 | 7808 | 12178 | 0 |
| 11-21 | 6710 | 3791 | 6485 | 5077 | 7030 | 0 |

**Hallazgo: línea 26 sin coche.** En las 3 paradas del 26 (11-18), las 11.222 entradas con ruta 26A son solo horario (ningún coche asignado) y los pocos coches con tiempo real son de las líneas 8, 56 y 91. El 26 sí aparece en posiciones (60 ids), pero OBA no les asigna el trip del 26 ni los lista en esas paradas. **El 26 no sirve para el experimento** y queda fuera.

Otras líneas aparecen en las 18 paradas (suma 11-15 al 11-21 de entradas con tiempo real): 65 (20.348), 59 (16.710), 145 (13.934), 161 (12.620), 180 (10.047), 8 (4.110), 184 (1.909), 130 (1.082). Todas habilitadas en el modelo. Son incidentales (calles compartidas con las líneas del panel): sin cobertura sistemática y no se las elige a propósito (ver §4). Hay que verificar, con las paradas OSM de su relación, si esos coches sirven la parada (regla de paradas).

### Cruce con las 118 líneas habilitadas

Las seis del panel (26, 39, 42, 92, 152, 168) están en las 118. **Cobertura de predicciones de arribo: 5 de 118 con datos útiles** (39, 42, 92, 152, 168; 26 sin coche). Las otras 113 habilitadas: no hay grabación de arribos con cobertura de paradas propia. Las 65, 59, 145, 161, 180, 8, 184, 130 tienen datos incidentales solo en esas 18 paradas.

El 152 tiene modelo v4 (entre las 72 nuevas, sin vara de producto medida y sin aviso de calidad, §6.1); 39, 42, 92, 168 vienen de v3 y v4.

### Cruce con los datos CABA

Todos los días 13 al 22 existen en `grabaciones\` (89–235 MB por día; 11-22 hasta las 15:49).
Huecos de CABA (> 3 min, BA):

| Día | Huecos |
|---|---|
| 11-13 | 17:58–18:12 (14 min) y restart de 619 s |
| 11-14 | 18:22–18:56 (34 min; coincide con el reinicio de CuandoSubo) |
| 11-15 | ninguno |
| 11-16 | 10:07–10:11, 11:23–11:35 (12 min), restart de 617 s |
| 11-17 | 03:38–04:51 (1 h 13), 09:42–09:45, 21:51–21:55; restart de 4165 s |
| 11-18 | ninguno |
| 11-19 | 02:20–02:24, 05:17–05:20 |
| 11-20 | 08:57–09:14 (17 min) |
| 11-21 | ninguno |
| 11-22 | 00:26–09:54 (el outage común) |

CABA tiene datos todos los días de la ventana; los huecos se esquivan excluyendo las ventanas (±10 min).

## 3. Primer experimento: CuandoSubo contra la llegada real y contra el modelo

**Pregunta:** en las mismas paradas e instantes, ¿qué fuente anuncia mejor el paso del coche (CuandoSubo o `path_v4_l1_s1`)?

### Alcance

- **Líneas:** 39, 42, 92, 168 y 152 (el 26 queda fuera: sin coche en CuandoSubo). 152 se informa aparte (modelo v4 sin vara de producto).
- **Paradas:** las 18 de `arrival_stops.json` menos las 3 del 26 = 15. Cada parada de OBA (`14_…`) se asigna a la parada OSM del `line_shapes` por su identidad (nombre y ubicación), con comprobación de que está en `ramales[].stops`. Los recorridos que la sirven son solo los que la tienen en su lista de paradas (§5); nunca por geometría. Si no hay parada OSM equivalente, se descarta la parada y se informa.
- **Días:** los 8 completos, 2026-11-14 al 21: 5 hábiles (16–20) y 3 de fin de semana (14, 15, 21). Se excluyen ventanas con hueco de CABA o CuandoSubo (±10 min) y 00:00–05:30. Orden de ejecución: 16, 17, 18 primero; si da señal, el resto. Out of sample para el modelo: v4 se entrenó hasta 2026-09-14.
- **Instantes:** cada consulta de arribos (`t` = currentTime del servidor de OBA), ~320 por parada y día, 06:00–23:00.
- **Entrada:** `arribos/YYYY-MM-DD.ndjson.gz`. Solo entradas con `predicted: true`, `pred_arr` no nulo y `stops_away ≥ 0`, de coches con `veh_line` = línea de la parada (línea por label, nunca por ruta ni trip).
- **Tamaño de muestra (banda 3–7 min, un día hábil como el 18, entradas de CuandoSubo):** 39: 1131, 152: 1956, 42: 750, 168: 614, 92: 466 (pares únicos coche-parada-trip: 1020, 1411, 505, 465, 424). Con 5 días hábiles: ~5.600 entradas (39), ~9.800 (152), ~3.700 (42), ~3.100 (168), ~2.300 (92); alcanza para MAE por línea (n de la banda 3–7 min de v4: 100 filas mínimas).

### Cómo se define la llegada real (vara vigente, §5)

Cruce firme de la parada, tal como lo implementa `prediccion/replay/core.py` (`_passes`, vara corregida 2026-11-16):
- par consecutivo de pings CABA compatibles con el shape, separados ≤ 10 min, velocidad media ≤ 25 m/s (+ 50 m), con interpolación lineal del instante;
- cuenta solo si el viaje ex post del coche (segmentador geo2 + asignación geo3) tiene la parada en su lista;
- parada en el último tramo del shape: cruce al llegar a 50 m del final;
- pares de 10–40 min que encierran la parada = no verificable (se informa cuántos y se excluyen del MAE);
- la hora del cruce usa `CABA_TS_OFFSET_S` = 60 s (provisorio, §6.1).

El id de CuandoSubo es el mismo que el de CABA, así que el cruce por coche se une por `vehicle` = `id`.

### Cómo se obtiene cada anuncio

- **CuandoSubo:** `pred_arr − t` de cada coche de la línea listado en la consulta.
- **Modelo:** replay (`prediccion/replay/`, `path_v4_l1_s1`, variante `cs` = producción) en esa parada y en ese `t`, usando solo pings CABA con `ts + offset ≤ t`, con la lógica pinneada y el mismo tope/orden de la app. Adaptación necesaria: el replay elige 40 paradas por línea (`prepare_stops`) e instantes cada 10 min; hay que pasarle las 15 paradas del panel y los `t` de las consultas (cambio chico en `run.py`/`core.instants_for_day`, y se escribe en script aparte para no tocar el replay existente).

### Métricas (misma tabla para las dos fuentes)

1. **Por coche, banda de ETA real 3–7 min** (vara principal §5): MAE, P90 del error absoluto, % llega antes de lo anunciado > 60 s (pred − real > 60 s), % llega después > 60 s, espera extra media. Con n por línea y días. Dos tablas: sobre los coches que listan las dos fuentes (comparación limpia) y sobre todos los de cada fuente.
2. **Próximo coche anunciado** (vara de producto), banda 3–7 min: MAE y % llega antes / después > 60 s.
3. **Bondi fantasma:** coche listado con ETA anunciado ≤ 40 min que no cruza firme la parada en (t, t + 40 min]; no cuenta el que cruzó entre su último ping y t. Para CuandoSubo se cuenta solo si el coche es de la línea del panel (por label). Se informan aparte los coches de otras líneas que OBA lista en la parada.
4. **Bondi no anunciado:** coche que cruza firme en ≤ 10 min y no está en la lista de la fuente. En CuandoSubo cuenta además la causa: coche sin trip (nunca se lista) o con trip de otra línea.
5. **Sin aviso firme:** **no aplica a CuandoSubo** (no tiene grupos "Viene/Puede venir"; es un problema de presentación de la app). No se calcula para la comparación. Se informa el equivalente crudo "instantes con paso en ≤ 10 min y ninguna predicción de la fuente".
6. **Complementarias baratas:** latencia (`t − veh_ts`, solo CuandoSubo), proporción de coches solo-horario (`predicted: false`), `sched_dev` extremo y dos coches con el mismo trip (trip mal asignado), % de coches del modelo que CuandoSubo no ve (sin trip).
7. **Sensibilidad al offset de CABA:** repetir las métricas de CuandoSubo con offset 0, 60 y 120 s. Sin verdad de campo, el sesgo absoluto "llega antes / después" es provisorio; lo robusto es la diferencia entre fuentes con el mismo offset y el MAE.

### Costo estimado (CPU)

- Lectura del día CABA (~230 MB) y segmentación geo2+geo3: ~1 min por (día, línea) (`VARA_CORREGIDA.md`).
- Replay con 3 paradas y ~320 instantes por parada: menos que el run actual (40 paradas × 102 instantes ≈ 700 s por día y línea). Estimo 2–4 min por (día, línea).
- 5 líneas × 8 días = 40 combinaciones ≈ **1,5–2,5 h de CPU en un hilo; ~1 h con 2 workers** a prioridad Idle. Primera pasada (16, 17, 18; 15 combinaciones): ~30–60 min.
- Parte de CuandoSubo (lectura de arribos + unión): minutos. No usa GPU. El `path_v4_l1_s1` corre por ONNX en CPU.
- Es una estimación: no medí el replay con el panel; la primera combinación mide el costo real.

### Riesgos

- **Hora de CABA estampada por lote:** el `ts` CABA es de un lote de ~1/min, no la hora del GPS. La llegada real tiene un error de decenas de segundos y un sesgo (offset 60 s provisorio) que afecta igual a "llega antes/después" de ambas fuentes, pero no por igual si el offset real no es 60 s: el modelo usa pings CABA, CuandoSubo usa reloj propio. Mitigación: sensibilidad (métrica 7) y comparar por diferencia.
- **ts de CuandoSubo no estable:** `lastUpdateTime` con cadencia ~2 min, lotes compartidos (`shared_ts` 2,2 M, con falsos positivos) y artefactos (384). No se usa para la verdad; sí el `t` del servidor. Posible referencia secundaria del cruce con posiciones de CuandoSubo para estimar el offset de CABA, solo como chequeo.
- **Identificación id → label:** CuandoSubo manda label solo con trip; sin trip depende del registro (36.433 ids, abril–octubre) + 4 aprendidos; 0 conflictos. Un id nuevo sin label queda sin línea y se descarta (se cuenta). Línea por sufijo del label con el map vigente a la fecha (el 26 cambia el 2026-09-18).
- **Trips mal asignados:** dos coches colgados del mismo trip con `sched_dev` ± grande (README §2.3). Se miden y se informan, no se filtran de entrada.
- **Paradas OBA ↔ OSM:** identificación por nombre y ubicación entre el GTFS de Nación y OSM; si no coinciden se pierde esa parada. La relación de servicio sale solo de `ramales[].stops`.
- **26 sin datos, 152 sin vara de producto previa y sin validar contra el shape legacy:** se reportan aparte.
- **Días con tráfico atípico:** 16–20 son hábiles normales; 14 y 21 son sábados. Se informa por tipo de día.
- **Posible contaminación:** el replay no debe leer `grabaciones_cuandosubo` (solo la comparación lo hace). El experimento escribe en una carpeta propia bajo `data/ml/replay/` (ej. `cs_vs_modelo/`), nunca en las carpetas de grabación.

## 4. Lo que no se puede medir con lo grabado

- **Hora real de paso con exactitud de segundos:** no hay verdad de campo. El `ts` de CABA es de lote (±~1 min) y el offset de 60 s es provisorio; el sesgo absoluto de "llega antes / después" no es medible. Solo diferencias entre fuentes y MAE.
- **Otras 113 líneas habilitadas:** el grabador solo sigue 6 líneas (`RECORD_LINES`) y 18 paradas. La rotación C (resto de AMBA) está en 0 requests y no hay arribos para esas líneas. No se puede decir nada de CuandoSubo en ellas.
- **Línea 26:** CuandoSubo no asigna coches de la 26 a sus paradas (solo horario). Se puede medir la ausencia, no su ETA.
- **Paradas fuera del panel:** los arribos existen solo en las 18. La predicción de la app en otras paradas se puede reconstruir con `horarios` + `sched_dev` (`ETA = serviceDate + arr(s) + sched_dev`), pero es una reconstrucción de la fórmula, no lo que CuandoSubo mostró; segunda etapa.
- **Coches sin trip:** no se listan en arribos, así que no hay ETA de CuandoSubo para ellos (solo su existencia en posiciones). Se mide como "no anunciado", no como error de ETA.
- **Horizonte > 40 min** y **ETA < 2 min:** fuera de la vara (§5).
- **Sin aviso firme:** no aplica a CuandoSubo (no tiene los grupos de la app).
- **Madrugada, 11-22 00:26–09:54 y huecos listados:** sin datos comunes.
- **Efecto del cambio de mapeo de Nación:** no se puede separar el error de ETA de CuandoSubo del error del trip asignado (el coche corre otro trip): se mide la suma.
- **Fin de semana largo y feriados:** ninguno en la ventana (14–21); no hay otro régimen de servicio.
