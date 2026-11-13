# Calidad de trip_id por línea

## Conclusión

Con estos umbrales **ninguna de las 15 líneas queda como usable**; todas salen *roto* por al menos un criterio. Dos fallas son generales: (1) el mismo trip_id aparece en dos coches a la vez en el 24-50 % de los trip_ids de toda línea (el trip_id es un viaje del horario asignado a varios coches, no un identificador único por coche); (2) menos de la mitad de los viajes v2b coinciden con un cambio de trip_id en casi todas las líneas (máx. 64 % en la 39). Además la 124 y la 151 tienen 43 % y 56 % de pings sin trip_id (la 151 ya estaba confirmada rota). Las menos malas, para un subset de prueba, son la 39, 26, 132, 168 y 92 (vacío 10-12 %, cambios en cabecera 57-91 %, coincidencia con v2b 40-64 %), pero ni siquiera ellas cumplen el umbral de usable; usarlas sería aceptar un trip_id parcialmente confiable. Salvedad de la métrica de inversión: cuenta viajes v2b que arrancan dentro de una corrida con otra dirección, y el v2b también parte por huecos y esperas, así que es una cota alta. Una sola muestra de 10 días; sin pesos por día.

Medición (sin usar trip_id en el pipeline): 15 líneas de v2b, 10 días: 2026-04-08, 2026-04-18, 2026-05-12, 2026-06-07, 2026-07-14, 2026-08-12, 2026-09-12, 2026-09-16, 2026-10-07, 2026-10-11. Línea identificada solo por el sufijo del label (LABEL_LINE_MAP vigente por fecha). Generado por `prediccion/scripts/diag_trip_id.py`. Los coches de cada línea se toman tal como salen del NDJSON (un ping por cambio de `ts`).

Definiciones. *Corrida* = secuencia maximal de pings con el mismo trip_id no vacío de un coche en un día; *cambio* = inicio de una corrida que no es la primera del coche-día. Duración y largo de corrida excluyen la primera y la última del coche-día (truncadas por el corte del día); largo = suma de distancias entre pings consecutivos. *Cabecera*: el cambio cae a ≤500 m de un extremo de algún recorrido de la línea (se toma el mínimo entre el último ping de la corrida anterior y el primero de la nueva). *Inversión sin cambio*: % de corridas (>6 min, con algún viaje v2b adentro) que contienen un viaje v2b que arranca ≥3 min después del inicio y ≥3 min antes del fin con dirección distinta a la del viaje v2b anterior. *Duplicado*: % de (línea, trip_id)-día que aparece en dos coches con solapamiento >2 min. *v2b→cambio*: % de viajes v2b (excluidos los que arrancan en el primer ping del día) cuyo inicio está a ±3 min de un cambio de trip_id del mismo coche; *cambio→v2b*: % de cambios con un inicio de viaje v2b del mismo coche a ±3 min.

## 1. Vacío, cambios y duración

| línea | pings | vacío % | coche-días | cambios/coche-día p50 (media) | dur p10/p50/p90 (min) | largo p10/p50/p90 (km) | <10 min % | >4 h % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 12 | 400110 | 16.0 | 594 | 16 (14.7) | 4/47/71 | 0.9/7.9/11.7 | 18.8 | 0.0 |
| 15 | 415761 | 15.7 | 807 | 6 (5.6) | 15/77/154 | 3.7/16.5/52.1 | 7.0 | 0.2 |
| 26 | 242308 | 11.2 | 372 | 11 (11.0) | 3/64/82 | 0.4/12.9/13.9 | 15.5 | 0.0 |
| 39 | 461998 | 10.1 | 789 | 12 (11.2) | 9/59/80 | 2.0/12.3/16.1 | 11.9 | 0.0 |
| 42 | 277792 | 21.2 | 421 | 10 (9.5) | 14/71/88 | 2.9/16.2/20.2 | 8.2 | 0.0 |
| 50 | 307154 | 15.8 | 540 | 9 (12.9) | 5/29/88 | 1.3/6.3/19.5 | 23.9 | 0.0 |
| 92 | 409463 | 11.7 | 680 | 8 (7.8) | 9/69/128 | 2.8/18.9/31.4 | 11.4 | 0.0 |
| 106 | 592359 | 14.5 | 847 | 12 (18.8) | 3/29/80 | 0.9/6.7/18.7 | 38.1 | 0.0 |
| 107 | 243569 | 11.6 | 402 | 11 (10.8) | 2/70/101 | 0.3/17.7/21.1 | 30.0 | 0.0 |
| 108 | 240066 | 9.3 | 362 | 9 (9.3) | 5/85/120 | 0.4/21.6/24.6 | 14.9 | 0.0 |
| 124 | 235979 | 43.3 | 421 | 8 (8.0) | 13/82/96 | 3.0/17.3/19.2 | 8.5 | 0.0 |
| 128 | 191647 | 16.3 | 335 | 10 (8.9) | 47/61/69 | 9.5/12.3/12.9 | 2.2 | 0.0 |
| 132 | 461954 | 10.9 | 718 | 14 (13.4) | 3/54/76 | 0.7/11.9/13.7 | 25.5 | 0.0 |
| 151 | 417154 | 56.1 | 616 | 6 (5.6) | 6/69/80 | 0.9/12.2/16.2 | 12.2 | 0.0 |
| 168 | 332995 | 10.0 | 547 | 10 (9.8) | 4/56/112 | 0.9/11.3/28.5 | 12.4 | 0.0 |

## 2. Coherencia con la geometría y con v2b

| línea | cambios | cambio en cabecera % | corridas con inversión % | trip_ids | trip_id en 2 coches % | viajes v2b | v2b→cambio % | (v2b sin start_unknown) | cambio→v2b % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 12 | 8563 | 40.7 | 57.8 | 4932 | 47.7 | 7078 | 45.9 | 49.5 | 38.1 |
| 15 | 4256 | 52.6 | 6.3 | 2906 | 37.0 | 3681 | 30.4 | 36.5 | 26.6 |
| 26 | 3964 | 90.6 | 30.5 | 2894 | 31.1 | 3659 | 50.5 | 50.7 | 48.8 |
| 39 | 8524 | 68.6 | 68.9 | 5095 | 46.4 | 6953 | 64.0 | 67.7 | 53.2 |
| 42 | 3718 | 57.3 | 71.0 | 2318 | 45.6 | 3462 | 28.1 | 18.2 | 26.3 |
| 50 | 6830 | 31.6 | 64.7 | 3572 | 48.9 | 3754 | 25.1 | 21.9 | 14.0 |
| 92 | 5202 | 80.2 | 48.8 | 3304 | 44.3 | 5043 | 40.5 | 44.2 | 39.3 |
| 106 | 15490 | 46.1 | 25.9 | 7412 | 49.6 | 8311 | 35.3 | 35.0 | 19.1 |
| 107 | 4204 | 58.3 | 44.9 | 3159 | 25.1 | 2786 | 46.5 | 45.8 | 34.0 |
| 108 | 3280 | 81.7 | 44.0 | 2217 | 37.1 | 2793 | 43.0 | 44.1 | 37.4 |
| 124 | 2010 | 57.1 | 10.1 | 1420 | 37.3 | 2684 | 19.9 | 19.0 | 26.5 |
| 128 | 2855 | 71.9 | 68.8 | 2488 | 23.8 | 3071 | 20.9 | 18.5 | 22.5 |
| 132 | 9413 | 78.7 | 26.4 | 6388 | 35.6 | 7456 | 51.8 | 53.3 | 42.5 |
| 151 | 3280 | 72.5 | 4.0 | 2711 | 26.7 | 4831 | 11.0 | 11.1 | 16.2 |
| 168 | 5271 | 57.1 | 32.3 | 3098 | 41.0 | 3250 | 50.7 | 50.9 | 31.7 |

## 3. Clasificación

**Usable** si cumple todo: vacío ≤5 %, corridas <10 min o >4 h ≤15 %, cambio en cabecera ≥70 %, v2b→cambio ≥70 %, cambio→v2b ≥70 %, trip_id en 2 coches ≤2 %, inversión sin cambio ≤10 %. **Roto** si falla cualquiera de: vacío >30 %, duración anómala >50 %, cabecera <30 %, v2b→cambio <30 % o cambio→v2b <30 %, duplicado >10 %, inversión >30 %. **Dudoso**: el resto. Los umbrales se fijaron antes de ver los números; son criterios de este informe, no de una norma.

| línea | clase | motivo de roto | vacío | dur. anómala | cabecera | v2b→cambio | cambio→v2b | 2 coches | inversión |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 12 | **roto** | trip_id duplicado, inversión sin cambio | 16.0 | 18.8 | 40.7 | 45.9 | 38.1 | 47.7 | 57.8 |
| 15 | **roto** | no coincide con v2b, trip_id duplicado | 15.7 | 7.1 | 52.6 | 30.4 | 26.6 | 37.0 | 6.3 |
| 26 | **roto** | trip_id duplicado, inversión sin cambio | 11.2 | 15.5 | 90.6 | 50.5 | 48.8 | 31.1 | 30.5 |
| 39 | **roto** | trip_id duplicado, inversión sin cambio | 10.1 | 11.9 | 68.6 | 64.0 | 53.2 | 46.4 | 68.9 |
| 42 | **roto** | no coincide con v2b, trip_id duplicado, inversión sin cambio | 21.2 | 8.2 | 57.3 | 28.1 | 26.3 | 45.6 | 71.0 |
| 50 | **roto** | no coincide con v2b, trip_id duplicado, inversión sin cambio | 15.8 | 23.9 | 31.6 | 25.1 | 14.0 | 48.9 | 64.7 |
| 92 | **roto** | trip_id duplicado, inversión sin cambio | 11.7 | 11.4 | 80.2 | 40.5 | 39.3 | 44.3 | 48.8 |
| 106 | **roto** | no coincide con v2b, trip_id duplicado | 14.5 | 38.1 | 46.1 | 35.3 | 19.1 | 49.6 | 25.9 |
| 107 | **roto** | trip_id duplicado, inversión sin cambio | 11.6 | 30.0 | 58.3 | 46.5 | 34.0 | 25.1 | 44.9 |
| 108 | **roto** | trip_id duplicado, inversión sin cambio | 9.3 | 14.9 | 81.7 | 43.0 | 37.4 | 37.1 | 44.0 |
| 124 | **roto** | vacío, no coincide con v2b, trip_id duplicado | 43.3 | 8.5 | 57.1 | 19.9 | 26.5 | 37.3 | 10.1 |
| 128 | **roto** | no coincide con v2b, trip_id duplicado, inversión sin cambio | 16.3 | 2.2 | 71.9 | 20.9 | 22.5 | 23.8 | 68.8 |
| 132 | **roto** | trip_id duplicado | 10.9 | 25.5 | 78.7 | 51.8 | 42.5 | 35.6 | 26.4 |
| 151 | **roto** | vacío, no coincide con v2b, trip_id duplicado | 56.1 | 12.2 | 72.5 | 11.0 | 16.2 | 26.7 | 4.0 |
| 168 | **roto** | trip_id duplicado, inversión sin cambio | 10.0 | 12.5 | 57.1 | 50.7 | 31.7 | 41.0 | 32.3 |
