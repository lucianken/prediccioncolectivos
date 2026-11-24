# Diagnóstico: viajes de v2c_stops contra v2c (2026-11-17)

El chequeo original comparaba trips.parquet entero con DataFrame.equals (sensible al orden de filas) y marcó 43 de 71 días.
Comparando por (vehicle_id, start_ts): 17 días con diferencias reales (el resto solo difiere en el orden de filas o en n_rows por el cambio de T).

- Viajes v2c 562.757; solo en v2c 900 (0,16 %); solo en nuevo 1.357 (0,24 %); mismos viajes con otro shape_id: 0.
- Filas (n_rows) de los viajes que difieren: 27.772 de v2c (0,16 %) y 42.614 del nuevo (0,24 %).
- Por línea (viajes distintos / viajes): 168 0,78 %, 39 0,60 %, 42 0,54 %, 92 0,48 %, 106 0,46 %, resto 0,10-0,42 %.
- Causa confirmada con meta.json: en los 11 días con diferencias grandes (07-20, 07-30, 08-06, 08-13, 08-20, 08-27, 09-03, 09-18, 09-25, 10-07, 10-14: primer día de cada bloque de v2c) v2c tiene carry_in=False y el nuevo carry_in=True (carry sembrado). Los otros 6 días con 1-6 viajes distintos tienen carry_in True en ambos: deriva menor de assign_params (el meta de v2c no tiene direction_rule/heading_tol_deg, el actual sí). Ninguna depende del cambio de T.
- Decisión: despreciable (< 0,5 % de viajes y de filas), se sigue. Validación del lanzador cambiada a comparar por clave con umbral 0,5 %.
