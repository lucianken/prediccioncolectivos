# Historia de ARQUITECTURA.md

Movido desde `ARQUITECTURA.md` el 2026-11-27: §6.3, §6.4 y §9. Texto original.

### 6.3 Replanteo del 2026-11-12 (historia)
Los modelos A3 (regresión global sobre escalares normalizados, junio 2026) no tenían noción de ubicación, de metros, de generalización a líneas no vistas ni del tránsito del camino. El tiempo de llegada es la **suma del tiempo de cada tramo** del camino entre el coche (P) y el objetivo (T); cada tramo tiene un comportamiento típico (hora, día) más el estado actual. Por eso la tabla A1 (suma por tramos) le ganaba a A3. Se abandonó A3 y se reusaron el pipeline v2, la vara, la tabla de tránsito y la grilla. Pasos (citados en §7 como «Paso 6.2.N»):
1. **Techo y cobertura del tránsito, sin entrenar:** el tránsito no es prioridad (§7, «Paso 6.2.1»).
2. **Infraestructura de iteración:** subconjunto fijo de train de 12 líneas (26, 39, 42, 92, 124, 151, 168, 50, 106, 107, 108, 132) y control 12 (corta), 15 (larga, 54 km) y 128 (corta); ventana de train acotada; presupuesto fijo de épocas con schedule (coseno/onecycle), sin early stopping. Las 48 líneas solo para confirmar al ganador.
3. **Modelo por tramos del camino:** el camino P→T partido en tramos fijos de 250 m; el tiempo de cada tramo se aprende solo con colectivos (incluye paradas, semáforos, regulación). Valor de cada tramo = componente del lugar (compartido entre líneas) + componente de la línea, más hora y día, más el estado del coche (velocidad, antigüedad GPS); salida = suma por tramos + ajuste global. Forma inspirada en DiDi WDR y Uber DeepETA.
4. **Comparación A1 / A3 + grilla / por tramos en el subconjunto:** ganó el modelo por tramos (§7).
5. **Corte de viajes:** segmentador v2b (`--segmentation geo2`): une huecos de datos cuando el avance es físicamente posible, marca `start_unknown` cuando el viaje arranca a mitad de recorrido y separa la espera en cabecera (§7, «Paso 6.2.5»).

Pendiente abierto: las líneas de control son un proxy imperfecto de lo que pasa en producción (no hay líneas nuevas; sí recorridos modificados, ramales nuevos y tramos poco recorridos). Falta una prueba más fiel, por ejemplo dejar afuera un ramal o un tramo de una línea vista.

### 6.4 Escalera anterior (histórica, E0–E2 corridos)

Cada escalón es una corrida nocturna y responde una pregunta. Se corta donde deja de haber mejora.

| # | Corrida | Pregunta | Decide |
|---|---|---|---|
| E0 | Baselines A0/A1/A3-actual en la vara | ¿Cuál es el nivel de partida? | piso a superar |
| E1 | A3 no-fleet, solo 39, pipeline v2, K=64 | ¿El muestreo de pares y la geometría empeoran algo vs A3 actual? | si K=64 alcanza |
| E1c | E1 K=32 + grilla de ciudad (ubicación de P y T), solo 39 | ¿Falta saber *dónde* está el coche? | hecho: sí, le gana a A1 (§7) |
| E2 | A3 no-fleet **+ grilla**, 48 líneas, K=32 | ¿Más líneas mejoran la 39? ¿Generaliza a las líneas de control? | si vale escalar |
| E3a | E1c + tránsito actual en las celdas del camino P→T (todas las líneas de la flota), **solo 39** | ¿El tránsito actual aporta sobre la ubicación? | si vale escalarlo |
| E3b | E2 + lo mismo, **48 líneas** (solo si E3a mejora) | ¿Se sostiene en todas las líneas y en las de control? | modelo candidato |

E3 sigue el mismo escalonado que E1→E2: primero solo la 39 (barato, ~30 min) y después todas. Aun entrenando con la 39, el tránsito de cada celda sale de **todos** los coches de la flota grabada (todas las líneas), porque es la información de la ciudad, no de la línea. Requiere una tabla nueva por snapshot × celda (velocidad media y conteo de coches en movimiento), construida una vez desde el NDJSON. La variante por zona y la flota como lista de vehículos (FleetEncoder) quedan después (§11).

Estimación de costo E2 (medida, 60 líneas, K=32): ~147 M filas de train (~4,7 M solo la 39) y ~27 M de val; ~43 k viajes por día hábil. En la RTX 3080 el trainer actual rinde ~24 k filas/s con `--batch-size 256` y ~98 k filas/s con `--batch-size 1024` (limitado por lanzamiento de kernels, ~95 it/s en ambos): **~100 min por época con batch 256 y ~25 min con batch 1024** (+~2 min de val). Con K=64 serían el doble de filas y de disco. Estimación descartada (~1,5 M viajes, 100 M filas, 12 min/época): contaba ~4× menos viajes que los medidos. La flota con el encoder actual es ~12× más lenta (§9 del plan): por eso va después y en versión liviana. **Comprar compute solo si E3 muestra que la flota vale y no entra en una noche.**

## 9. Inconsistencias conocidas en docs viejos

- Modelo "en producción" en docs viejos: `CLAUDE.md` indica ep24 (72,7 s) y el plan ep21 (72,5 s); ambos son el A3 histórico, sin efecto (`proyectoconsola/lib/eta_predict.js` está roto desde el rediseño). Modelo en producción desde 2026-11-22: `path_v4_l1_s1` (§6).
- `research_a3w_proyeccion_geometrica.md` habla de 9.165 filas; el parquet real tiene 71,5 M.
- Split de validación: el código usa último 20 % de días (`build_dataset.py:423`); `ml_timeline.md` dice últimos 7 días. **Manda §5.**
- `docs_old/INFERENCE_GUIDE.md` (sin efecto; reemplazada por `prediccion/INFERENCIA_PATH.md`) no incluye `schedule_dev_norm` ni `time_since_last_bus_s`, y asume `shape_id` vía ramal_lookup.
- `has_active_bus` es siempre 1 en training (nunca se entrenó el caso sin coche visible).
