# Descomposición del error del próximo coche anunciado por línea (replay v4, banda de ETA real 3-7 min)

Medido el 2026-11-22 sobre los crudos de `data/ml/replay/v4prod/v4/` (modelo `path_v4_l1_s1`, 10 días, 40 paradas por línea, instantes cada 10 min de 6 a 23 h). Sin volver a predecir. Código: `data/ml/replay/porcoche/descomposicion.py` (cálculo; salidas `descomposicion_lineas.csv`, `descomposicion_fantasma_causas12.csv`) y `data/ml/replay/porcoche/descomposicion_md.py` (este documento). Reusa la lógica de `porcoche/calcula.py` sin modificarlo.

## Definiciones

- **Líneas:** las 126 de `proyectoconsola/public/config/prediccion.json`; la 164 (no habilitada) aparte.
- **MAE modelo (vara vigente, banda de ETA real 3-7 min):** 46 líneas, eval congelado de v3, modelo v4 candidato (`data/ml/v4_sub/runs/no_regresion.md`, tabla por línea); 72 líneas nuevas, eval congelado de v4 (mismo archivo); 8 habilitadas tarde (49, 97, 119, 153, 154, 163, 185, 193) y la 164, `data/ml/v4_eval_ext/resultados.csv` (columnas `mae`, `n`, eval extendido de 25 días). n pequeños en varias nuevas (57-700 filas): el MAE de la vara tiene ruido de ±5 s por línea.
- **MAE por coche replay:** ETA anunciado (`eta0_s`) − tiempo real hasta SU propio paso (`tp2_s`) de cada coche listado con paso firme en 3-7 min; MAE pooled.
- **MAE próximo coche:** ETA anunciado del 1.º de la lista − tiempo real al primer coche en llegar (cualquiera, listado o no), instantes con el próximo paso real en 3-7 min, sin los de paso previo no verificable, solo con anuncio. Coincide con `tablas.md` (diferencia máxima por línea 5.7e-14 s; n de instantes de la banda distinto en 0 líneas de 127).
- **Casos** (excluyentes, por el estado del 1.º anunciado; el aporte en s es la suma de |error| del caso dividida por todos los instantes con anuncio de la línea, y los seis suman el MAE): (a) el 1.º anunciado es el primero en llegar; (b) el 1.º ya había pasado entre su último ping y t; (c) el 1.º es bondi fantasma (no pasa en 40 min); (d) el 1.º llega después y otro coche listado (2.º-5.º) llega primero; (e) el 1.º llega después y llega primero un bondi no anunciado; (f) el 1.º es no verificable (hueco de GPS; no pedido, queda para que sumen). En b y c el primero en llegar puede ser listado o bondi no anunciado.
- Llega antes / después de lo anunciado: error = anunciado − real; > 0 llega antes, < 0 llega después. Sin anuncio = instantes sin ningún ETA anunciado (no es el «sin aviso firme» de `tablas.md`, que es «viene» vacío); fuera del MAE.

## Tabla agregada (126 líneas, ponderada por instantes)

MAE modelo ponderado por instantes de la línea (53.9 s; ponderado por n de cada eval 49.5 s, n 270,907; media simple de líneas 54.0, mediana 54.0). MAE por coche replay 54.8 s (n 2,131,427 coches). MAE próximo coche 116.9 s; llega antes > 60 s 17.6 %, llega después > 60 s 23.0 %; sin anuncio 2.9 % de 1,228,348 instantes de la banda. Cociente próximo coche / modelo 2.17; por coche / modelo 1.02.

| caso (banda real 3-7 min, instantes con anuncio) | n instantes | % de instantes | MAE (s) | aporte al MAE (s) |
|---|---:|---:|---:|---:|
| (a) el 1.º anunciado es el primero en llegar | 933 826 | 78.3 | 49 | 38.7 |
| (b) el 1.º anunciado ya había pasado entre su último ping y t (otro coche llega primero) | 65 161 | 5.5 | 277 | 15.1 |
| (c) el 1.º anunciado es bondi fantasma (otro coche llega primero) | 62 218 | 5.2 | 563 | 29.3 |
| (d) el 1.º anunciado llega después; otro coche listado (2.º-5.º) llega primero | 94 372 | 7.9 | 233 | 18.4 |
| (e) el 1.º anunciado llega después; llega primero un bondi no anunciado | 36 706 | 3.1 | 484 | 14.9 |
| (f) el 1.º anunciado es no verificable (hueco de GPS) | 792 | 0.1 | 649 | 0.4 |
| **Total con anuncio** | 1 193 075 | 100 | 116.9 | 116.9 |

## Cantidad de ramales y error

| variable | Spearman con ramales | p | Spearman con shapes | p |
|---|---:|---:|---:|---:|
| aporte c+d | +0.74 | 1.1e-22 | +0.73 | 8.1e-22 |
| aporte c+d+e | +0.67 | 7.7e-18 | +0.66 | 5.3e-17 |
| cociente próx./modelo | +0.57 | 3.0e-12 | +0.56 | 9.5e-12 |
| cociente coche/modelo | -0.17 | 5.1e-02 | -0.17 | 5.8e-02 |
| MAE próximo coche | +0.62 | 7.1e-15 | +0.60 | 7.5e-14 |

| shapes de la línea | líneas | MAE modelo (s) | MAE por coche (s) | MAE próximo coche (s) | cociente | aporte c+d (s) | aporte a (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1-2 shapes | 43 | 52.0 | 54 | 74 | 1.4 | 10 | 41 |
| 3-4 | 43 | 54.8 | 54 | 112 | 2.0 | 42 | 38 |
| 5-6 | 18 | 52.8 | 56 | 157 | 3.0 | 79 | 37 |
| >= 7 | 22 | 57.0 | 56 | 189 | 3.3 | 116 | 36 |

## Bondi fantasma: causa (12 líneas con clasificación)

| causa (clasificación de `FALSAS_ALARMAS.md`) | n instantes (c) | % de (c) | aporte al MAE de esas 12 líneas (s) |
|---|---:|---:|---:|
| R1 otro ramal: no sirve la parada (tramo compartido y diverge) | 2549 | 36.3 | 2.72 |
| C coche en cabecera / sin viaje: arranca despues de 40 min o nunca | 757 | 10.8 | 1.20 |
| S sentido contrario (el recorrido ex post va en el otro sentido) | 755 | 10.8 | 1.21 |
| sin clasificar | 618 | 8.8 | 0.81 |
| T1 el viaje termina antes de la parada, a mitad de recorrido (fraccionado / corta / se pierde) | 473 | 6.7 | 0.84 |
| X2d pasa en 40 min por un shape no asociado a la parada | 469 | 6.7 | 0.57 |
| X0 ETA anunciado > 40 min (fuera del horizonte) | 290 | 4.1 | 9.13 |
| X2c pasa en 40 min con pings no compatibles (> 45 m) en el cruce | 228 | 3.2 | 0.24 |
| T2 el viaje termina antes de la parada, a < 1,5 km del final del recorrido | 153 | 2.2 | 0.22 |
| X3 parada en el ultimo tramo del shape: el coche llega pero el cruce no existe por construccion | 148 | 2.1 | 0.25 |
| X1 pasa despues de 40 min en el mismo viaje (ETA subestimado) | 113 | 1.6 | 0.29 |
| D desvio / fuera de shape cerca de la parada | 105 | 1.5 | 0.19 |
| O otro: sirve la parada, sigue el viaje y no llega en 40 min | 94 | 1.3 | 0.14 |
| G hueco de GPS > 10 min en el horizonte (no se sabe) | 81 | 1.2 | 0.14 |
| P el coche ya cruzo la parada antes de t (ping desactualizado) | 61 | 0.9 | 0.13 |
| X2a pasa en 40 min durante un hueco de GPS > 10 min (la vara no interpola) | 50 | 0.7 | 0.16 |
| X4 alcanza la parada sobre el shape elegido pero ningun par de pings consecutivos compatibles la cruza | 40 | 0.6 | 0.09 |
| X2b pasa en 40 min con salto > 5 km entre pings (la vara lo descarta) | 38 | 0.5 | 0.03 |

## Tabla por línea (ordenada por MAE del próximo coche, descendente)

Columnas a-f: aporte en s al MAE de la línea. n inst. = instantes con anuncio. Ramales (shapes): recorridos distintos y shapes de `proyectoconsola/data/line_shapes`.

| línea | ramales (shapes) | n inst. | sin anuncio % | MAE modelo (s) | MAE por coche replay (s) | MAE próximo coche (s) | cociente próx./modelo | a (s) | b (s) | c (s) | d (s) | e (s) | f (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 188 | 4 (8) | 8177 | 2.7 | 52.5 | 53 | 567 | 10.8 | 26 | 6 | 320 | 190 | 25 | 1.5 |
| 8 | 6 (11) | 8361 | 3.4 | 67.1 | 77 | 464 | 6.9 | 41 | 12 | 337 | 45 | 26 | 1.6 |
| 45 | 2 (4) | 10616 | 0.0 | 53.9 | 54 | 380 | 7.1 | 31 | 10 | 73 | 181 | 85 | 0.8 |
| 80 | 3 (5) | 10589 | 2.1 | 55.7 | 53 | 376 | 6.8 | 29 | 10 | 154 | 48 | 133 | 2.3 |
| 29 | 4 (6) | 11055 | 2.4 | 55.9 | 55 | 328 | 5.9 | 34 | 10 | 128 | 90 | 64 | 1.5 |
| 182 | 4 (8) | 7515 | 9.2 | 55.1 | 59 | 323 | 5.9 | 37 | 10 | 212 | 35 | 27 | 1.9 |
| 145 | 3 (6) | 7445 | 0.5 | 60.0 | 57 | 319 | 5.3 | 39 | 10 | 191 | 59 | 17 | 2.7 |
| 197 | 8 (16) | 6648 | 2.1 | 51.2 | 54 | 284 | 5.5 | 39 | 6 | 131 | 86 | 19 | 1.9 |
| 194 | 3 (6) | 8325 | 0.3 | 67.7 | 70 | 275 | 4.1 | 34 | 14 | 128 | 64 | 33 | 1.5 |
| 136 | 2 (4) | 2345 | 4.8 | 64.3 | 54 | 255 | 4.0 | 42 | 4 | 160 | 35 | 13 | 0.0 |
| 166 | 2 (4) | 9392 | 3.7 | 57.5 | 51 | 253 | 4.4 | 37 | 13 | 179 | 15 | 9 | 0.0 |
| 21 | 8 (16) | 9758 | 1.5 | 60.7 | 58 | 239 | 3.9 | 28 | 16 | 91 | 58 | 45 | 1.2 |
| 96 | 10 (21) | 5584 | 1.7 | 58.4 | 62 | 225 | 3.8 | 42 | 9 | 157 | 11 | 6 | 0.1 |
| 98 | 7 (14) | 10493 | 0.1 | 54.2 | 52 | 224 | 4.1 | 32 | 17 | 63 | 48 | 62 | 0.9 |
| 100 | 3 (6) | 11660 | 1.2 | 46.5 | 53 | 202 | 4.4 | 33 | 18 | 34 | 65 | 51 | 1.5 |
| 160 | 5 (10) | 9091 | 1.2 | 55.3 | 60 | 199 | 3.6 | 45 | 9 | 106 | 6 | 32 | 0.5 |
| 95 | 2 (4) | 11236 | 0.6 | 54.1 | 56 | 195 | 3.6 | 35 | 13 | 29 | 106 | 12 | 0.8 |
| 118 | 2 (4) | 12437 | 1.2 | 55.8 | 59 | 190 | 3.4 | 32 | 22 | 45 | 45 | 37 | 10.1 |
| 55 | 2 (4) | 9908 | 0.9 | 55.1 | 56 | 186 | 3.4 | 36 | 10 | 111 | 7 | 23 | 0.5 |
| 28 | 9 (18) | 8524 | 2.8 | 64.6 | 62 | 185 | 2.9 | 30 | 17 | 50 | 62 | 26 | 0.8 |
| 42 | 3 (6) | 10374 | 2.0 | 59.8 | 61 | 184 | 3.1 | 39 | 13 | 121 | 6 | 4 | 0.2 |
| 159 | 1 (2) | 3828 | 9.4 | 47.4 | 62 | 163 | 3.4 | 33 | 14 | 74 | 4 | 37 | 0.6 |
| 57 | 13 (25) | 5690 | 0.1 | 65.7 | 51 | 159 | 2.4 | 32 | 10 | 60 | 47 | 9 | 1.9 |
| 178 | 4 (8) | 8078 | 1.0 | 48.1 | 50 | 156 | 3.2 | 37 | 10 | 66 | 28 | 14 | 0.7 |
| 15 | 4 (8) | 8941 | 0.9 | 56.1 | 61 | 149 | 2.7 | 36 | 11 | 18 | 61 | 21 | 1.7 |
| 180 | 7 (14) | 6917 | 0.3 | 59.5 | 58 | 149 | 2.5 | 35 | 8 | 57 | 39 | 11 | 0.1 |
| 106 | 2 (4) | 11630 | 0.5 | 54.6 | 53 | 145 | 2.7 | 30 | 28 | 11 | 39 | 36 | 0.4 |
| 195 | 2 (4) | 5715 | 0.9 | 58.4 | 51 | 139 | 2.4 | 34 | 11 | 55 | 12 | 23 | 3.2 |
| 85 | 3 (6) | 9540 | 0.2 | 50.2 | 53 | 137 | 2.7 | 36 | 12 | 25 | 56 | 8 | 0.6 |
| 33 | 5 (10) | 10429 | 2.7 | 50.2 | 51 | 134 | 2.7 | 36 | 15 | 29 | 18 | 34 | 0.5 |
| 60 | 8 (20) | 9385 | 2.7 | 60.9 | 55 | 132 | 2.2 | 36 | 12 | 14 | 17 | 52 | 0.3 |
| 7 | 2 (4) | 7442 | 6.3 | 44.2 | 54 | 129 | 2.9 | 39 | 8 | 36 | 2 | 44 | 0.0 |
| 51 | 2 (4) | 5384 | 0.4 | 49.8 | 50 | 129 | 2.6 | 39 | 6 | 55 | 1 | 27 | 0.0 |
| 86 | 6 (12) | 5290 | 2.3 | 61.4 | 62 | 127 | 2.1 | 46 | 7 | 43 | 22 | 8 | 0.5 |
| 115 | 4 (4) | 9104 | 10.2 | 61.3 | 53 | 126 | 2.1 | 35 | 20 | 14 | 31 | 26 | 0.5 |
| 169 | 3 (6) | 9391 | 3.5 | 42.4 | 55 | 126 | 3.0 | 39 | 10 | 13 | 53 | 11 | 0.1 |
| 91 | 2 (4) | 7597 | 2.2 | 56.3 | 56 | 125 | 2.2 | 39 | 11 | 17 | 19 | 39 | 0.6 |
| 174 | 3 (6) | 9761 | 0.2 | 51.7 | 51 | 122 | 2.4 | 36 | 13 | 12 | 35 | 25 | 0.6 |
| 9 | 3 (6) | 11787 | 1.8 | 50.2 | 56 | 114 | 2.3 | 39 | 21 | 7 | 23 | 24 | 0.2 |
| 176 | 6 (12) | 7908 | 0.9 | 65.1 | 52 | 112 | 1.7 | 37 | 12 | 33 | 17 | 12 | 0.0 |
| 63 | 2 (4) | 10475 | 2.4 | 54.0 | 51 | 111 | 2.1 | 35 | 11 | 55 | 7 | 3 | 0.0 |
| 87 | 2 (4) | 7709 | 1.4 | 55.0 | 52 | 111 | 2.0 | 39 | 10 | 10 | 10 | 42 | 0.3 |
| 68 | 2 (4) | 8755 | 9.8 | 51.5 | 52 | 111 | 2.2 | 30 | 38 | 33 | 8 | 1 | 0.0 |
| 114 | 3 (6) | 9172 | 2.0 | 56.5 | 56 | 110 | 1.9 | 43 | 11 | 12 | 9 | 34 | 0.3 |
| 161 | 2 (4) | 10589 | 7.1 | 53.4 | 53 | 108 | 2.0 | 38 | 12 | 14 | 12 | 32 | 0.1 |
| 62 | 2 (2) | 5093 | 11.4 | 62.2 | 70 | 107 | 1.7 | 44 | 16 | 21 | 11 | 15 | 0.9 |
| 107 | 2 (3) | 9923 | 2.2 | 59.9 | 60 | 106 | 1.8 | 41 | 13 | 11 | 8 | 33 | 0.0 |
| 31 | 4 (8) | 10374 | 0.4 | 56.4 | 54 | 105 | 1.9 | 33 | 24 | 19 | 20 | 10 | 0.2 |
| 105 | 2 (4) | 12574 | 2.1 | 47.4 | 52 | 105 | 2.2 | 33 | 16 | 28 | 5 | 23 | 0.1 |
| 46 | 2 (4) | 9512 | 0.2 | 48.4 | 50 | 104 | 2.1 | 39 | 7 | 15 | 30 | 12 | 0.3 |
| 177 | 1 (2) | 2724 | 26.1 | 45.8 | 45 | 97 | 2.1 | 35 | 21 | 25 | 2 | 14 | 0.0 |
| 129 | 4 (8) | 6166 | 4.2 | 57.4 | 64 | 96 | 1.7 | 54 | 8 | 22 | 5 | 7 | 0.6 |
| 34 | 2 (4) | 9537 | 0.4 | 55.8 | 56 | 95 | 1.7 | 35 | 23 | 29 | 6 | 3 | 0.0 |
| 168 | 2 (4) | 9056 | 4.2 | 52.6 | 53 | 93 | 1.8 | 39 | 13 | 12 | 20 | 8 | 0.1 |
| 32 | 1 (2) | 7146 | 1.7 | 49.2 | 54 | 92 | 1.9 | 47 | 10 | 1 | 10 | 25 | 0.1 |
| 12 | 2 (4) | 10774 | 4.4 | 58.1 | 57 | 91 | 1.6 | 35 | 26 | 18 | 6 | 6 | 0.1 |
| 64 | 3 (3) | 12365 | 1.8 | 58.5 | 58 | 91 | 1.6 | 38 | 27 | 14 | 4 | 8 | 0.0 |
| 53 | 2 (4) | 11268 | 0.2 | 55.3 | 57 | 89 | 1.6 | 44 | 14 | 11 | 7 | 13 | 0.3 |
| 1 | 1 (2) | 9716 | 2.7 | 59.0 | 48 | 88 | 1.5 | 40 | 7 | 2 | 29 | 10 | 0.5 |
| 102 | 1 (2) | 10585 | 17.2 | 61.0 | 59 | 85 | 1.4 | 37 | 26 | 6 | 6 | 11 | 0.0 |
| 37 | 3 (5) | 8934 | 3.4 | 51.3 | 57 | 85 | 1.7 | 38 | 16 | 11 | 6 | 14 | 0.0 |
| 101 | 2 (4) | 10774 | 0.7 | 65.4 | 60 | 84 | 1.3 | 39 | 19 | 8 | 13 | 5 | 0.0 |
| 158 | 1 (2) | 1700 | 6.9 | 49.7 | 56 | 84 | 1.7 | 43 | 33 | 1 | 1 | 7 | 0.0 |
| 24 | 2 (4) | 12386 | 1.3 | 55.3 | 57 | 83 | 1.5 | 40 | 17 | 8 | 5 | 12 | 0.0 |
| 132 | 3 (6) | 11522 | 1.4 | 57.9 | 59 | 83 | 1.4 | 35 | 24 | 16 | 6 | 1 | 0.6 |
| 117 | 2 (4) | 9397 | 4.1 | 56.8 | 57 | 83 | 1.5 | 41 | 13 | 8 | 9 | 13 | 0.0 |
| 151 | 2 (4) | 10553 | 5.3 | 68.4 | 62 | 82 | 1.2 | 40 | 28 | 4 | 6 | 4 | 0.0 |
| 59 | 5 (10) | 11075 | 0.7 | 55.4 | 50 | 82 | 1.5 | 29 | 19 | 18 | 9 | 6 | 0.0 |
| 97 | 1 (2) | 6895 | 7.6 | 49.9 | 57 | 82 | 1.6 | 48 | 5 | 5 | 4 | 19 | 0.0 |
| 130 | 3 (5) | 11217 | 1.3 | 50.9 | 63 | 81 | 1.6 | 44 | 15 | 9 | 6 | 7 | 0.1 |
| 56 | 1 (2) | 9300 | 6.3 | 61.5 | 58 | 80 | 1.3 | 50 | 7 | 2 | 12 | 8 | 0.2 |
| 25 | 1 (2) | 10660 | 4.1 | 58.3 | 53 | 80 | 1.4 | 44 | 10 | 5 | 3 | 17 | 0.1 |
| 50 | 2 (4) | 10158 | 1.6 | 53.1 | 57 | 79 | 1.5 | 38 | 15 | 12 | 7 | 8 | 0.1 |
| 123 | 1 (2) | 10769 | 5.1 | 48.1 | 51 | 79 | 1.6 | 41 | 12 | 2 | 5 | 17 | 0.4 |
| 110 | 2 (4) | 12133 | 0.8 | 51.1 | 52 | 78 | 1.5 | 38 | 16 | 9 | 12 | 3 | 0.1 |
| 185 | 3 (6) | 5871 | 5.5 | 47.6 | 51 | 78 | 1.6 | 44 | 5 | 5 | 20 | 4 | 0.0 |
| 39 | 3 (6) | 12869 | 0.2 | 51.2 | 52 | 78 | 1.5 | 31 | 20 | 17 | 6 | 3 | 0.0 |
| 22 | 1 (2) | 10588 | 2.7 | 48.4 | 60 | 78 | 1.6 | 47 | 10 | 3 | 8 | 10 | 0.0 |
| 152 | 2 (4) | 10713 | 3.1 | 49.6 | 49 | 77 | 1.6 | 29 | 32 | 7 | 7 | 3 | 0.2 |
| 119 | 1 (2) | 10255 | 6.4 | 49.1 | 54 | 77 | 1.6 | 49 | 8 | 2 | 13 | 5 | 0.2 |
| 26 | 1 (2) | 3047 | 2.0 | 62.3 | 62 | 77 | 1.2 | 37 | 26 | 4 | 8 | 1 | 0.0 |
| 65 | 1 (2) | 12192 | 1.8 | 48.3 | 53 | 77 | 1.6 | 38 | 24 | 3 | 4 | 8 | 0.0 |
| 2 | 1 (2) | 11422 | 3.8 | 61.3 | 60 | 77 | 1.3 | 40 | 19 | 6 | 5 | 7 | 0.0 |
| 79 | 1 (2) | 1753 | 1.7 | 51.9 | 64 | 76 | 1.5 | 50 | 6 | 0 | 15 | 6 | 0.3 |
| 163 | 2 (4) | 2800 | 4.1 | 54.6 | 57 | 75 | 1.4 | 55 | 1 | 12 | 0 | 6 | 0.0 |
| 133 | 1 (2) | 12162 | 1.7 | 50.0 | 53 | 75 | 1.5 | 42 | 14 | 4 | 3 | 11 | 0.2 |
| 20 | 2 (4) | 8293 | 4.0 | 51.5 | 57 | 74 | 1.4 | 50 | 8 | 7 | 2 | 7 | 0.2 |
| 184 | 1 (2) | 12552 | 0.3 | 39.6 | 47 | 74 | 1.9 | 39 | 15 | 3 | 2 | 15 | 0.1 |
| 126 | 4 (8) | 13326 | 1.0 | 53.0 | 52 | 73 | 1.4 | 34 | 23 | 6 | 6 | 4 | 0.0 |
| 150 | 2 (4) | 11103 | 3.2 | 55.4 | 53 | 73 | 1.3 | 41 | 18 | 7 | 4 | 4 | 0.0 |
| 140 | 1 (2) | 12093 | 0.7 | 51.9 | 60 | 73 | 1.4 | 47 | 14 | 3 | 5 | 4 | 0.2 |
| 44 | 1 (2) | 11863 | 3.2 | 50.0 | 53 | 73 | 1.5 | 36 | 22 | 7 | 7 | 2 | 0.0 |
| 93 | 2 (4) | 5130 | 6.6 | 57.2 | 56 | 72 | 1.3 | 50 | 4 | 7 | 2 | 10 | 0.0 |
| 113 | 2 (4) | 10218 | 0.3 | 49.4 | 57 | 72 | 1.5 | 42 | 13 | 7 | 5 | 4 | 0.1 |
| 143 | 2 (4) | 8219 | 1.5 | 50.9 | 52 | 72 | 1.4 | 43 | 13 | 6 | 5 | 4 | 0.0 |
| 109 | 1 (2) | 11926 | 1.5 | 53.7 | 55 | 72 | 1.3 | 38 | 18 | 5 | 6 | 5 | 0.2 |
| 128 | 1 (2) | 13550 | 4.0 | 48.7 | 56 | 72 | 1.5 | 42 | 21 | 3 | 3 | 3 | 0.0 |
| 108 | 1 (2) | 10747 | 3.2 | 56.6 | 54 | 71 | 1.3 | 39 | 13 | 5 | 5 | 9 | 0.1 |
| 124 | 1 (2) | 13991 | 2.2 | 53.1 | 52 | 70 | 1.3 | 40 | 24 | 2 | 2 | 3 | 0.1 |
| 127 | 2 (4) | 8858 | 0.4 | 49.4 | 52 | 70 | 1.4 | 42 | 10 | 7 | 8 | 4 | 0.1 |
| 111 | 1 (2) | 10251 | 2.7 | 54.2 | 58 | 70 | 1.3 | 48 | 11 | 1 | 4 | 6 | 0.0 |
| 4 | 2 (4) | 11268 | 3.0 | 64.2 | 52 | 70 | 1.1 | 42 | 14 | 9 | 2 | 3 | 0.3 |
| 154 | 1 (2) | 2985 | 11.6 | 47.2 | 59 | 70 | 1.5 | 55 | 3 | 2 | 3 | 6 | 0.6 |
| 76 | 1 (2) | 12161 | 1.2 | 50.7 | 55 | 70 | 1.4 | 39 | 15 | 1 | 8 | 6 | 0.1 |
| 41 | 1 (2) | 12749 | 0.2 | 59.7 | 52 | 70 | 1.2 | 36 | 21 | 3 | 6 | 4 | 0.1 |
| 74 | 1 (2) | 8326 | 4.4 | 47.8 | 48 | 70 | 1.5 | 41 | 13 | 5 | 3 | 8 | 0.0 |
| 134 | 1 (2) | 12793 | 0.5 | 52.9 | 53 | 69 | 1.3 | 41 | 15 | 1 | 6 | 6 | 0.0 |
| 146 | 1 (2) | 11909 | 8.6 | 49.9 | 55 | 69 | 1.4 | 40 | 19 | 3 | 4 | 3 | 0.0 |
| 78 | 2 (4) | 11351 | 3.1 | 48.7 | 48 | 68 | 1.4 | 34 | 17 | 8 | 4 | 5 | 0.2 |
| 172 | 2 (4) | 9842 | 3.6 | 55.1 | 47 | 68 | 1.2 | 37 | 12 | 6 | 6 | 6 | 0.0 |
| 92 | 2 (4) | 11936 | 3.0 | 54.1 | 53 | 67 | 1.2 | 39 | 14 | 2 | 6 | 6 | 0.0 |
| 103 | 1 (2) | 11062 | 1.0 | 54.1 | 55 | 67 | 1.2 | 44 | 12 | 3 | 3 | 5 | 0.0 |
| 10 | 1 (2) | 12410 | 0.7 | 46.1 | 55 | 67 | 1.5 | 40 | 18 | 2 | 5 | 2 | 0.1 |
| 84 | 1 (2) | 12875 | 3.8 | 51.4 | 53 | 67 | 1.3 | 43 | 18 | 1 | 2 | 2 | 0.1 |
| 17 | 1 (2) | 12726 | 0.5 | 48.1 | 50 | 67 | 1.4 | 34 | 25 | 2 | 4 | 1 | 0.0 |
| 71 | 3 (6) | 10796 | 0.1 | 50.5 | 53 | 67 | 1.3 | 38 | 15 | 9 | 4 | 1 | 0.0 |
| 70 | 1 (2) | 10802 | 7.0 | 52.9 | 54 | 67 | 1.3 | 41 | 15 | 3 | 4 | 3 | 0.0 |
| 47 | 4 (8) | 7765 | 3.8 | 53.0 | 50 | 67 | 1.3 | 40 | 9 | 8 | 4 | 5 | 0.0 |
| 19 | 1 (2) | 12410 | 0.5 | 47.2 | 50 | 66 | 1.4 | 41 | 14 | 3 | 5 | 3 | 0.1 |
| 67 | 1 (2) | 13474 | 0.5 | 55.2 | 51 | 66 | 1.2 | 37 | 19 | 2 | 5 | 3 | 0.1 |
| 193 | 1 (2) | 7383 | 6.9 | 53.4 | 56 | 66 | 1.2 | 52 | 5 | 2 | 3 | 4 | 0.0 |
| 181 | 2 (4) | 10235 | 1.4 | 56.3 | 54 | 65 | 1.2 | 39 | 12 | 8 | 4 | 3 | 0.3 |
| 135 | 1 (2) | 12575 | 6.5 | 58.2 | 53 | 65 | 1.1 | 37 | 20 | 0 | 6 | 2 | 0.0 |
| 179 | 3 (6) | 7484 | 9.0 | 44.6 | 52 | 64 | 1.4 | 44 | 8 | 7 | 2 | 2 | 0.0 |
| 49 | 1 (2) | 8761 | 1.4 | 44.5 | 46 | 59 | 1.3 | 42 | 7 | 2 | 5 | 3 | 0.3 |
| 153 | 1 (2) | 6869 | 2.5 | 45.1 | 48 | 58 | 1.3 | 47 | 1 | 5 | 1 | 4 | 0.0 |

## Línea 164 (aparte)

Línea 164 (no habilitada; 3919 instantes con anuncio): ramales 5 (10 shapes), MAE modelo 67.6 s (n 86459, eval ext (v4_eval_ext)), MAE por coche replay 57 s, MAE próximo coche 404 s, cociente 6.0; aportes a 34 / b 5 / c 124 / d 201 / e 33 / f 7.8 s; sin anuncio 9.5 %.

## Lectura

1. El MAE del próximo coche anunciado de las 126 líneas habilitadas es 117 s (n 1,193,075 instantes con anuncio) contra 54 s de la vara del modelo (ponderada por instantes; 49 s ponderada por n de eval): cociente 2.2. El MAE por coche del replay es 55 s (cociente 1.0); el error de cada coche listado casi coincide con la vara, la diferencia está en qué coche se anuncia primero.
2. Cuando el 1.º anunciado es el primero en llegar (a) hay 78 % de los instantes, con MAE 49 s y aporte 39 s. El otro 22 % de los instantes aporta 78 s (67 % del MAE).
3. Bondi fantasma como 1.º (c): 5.2 % de los instantes, MAE 563 s, aporte 29 s. El 1.º ya había pasado (b): 5.5 %, aporte 15 s. Otro listado llega primero (d): 7.9 %, aporte 18 s. Bondi no anunciado llega primero con el 1.º llegando después (e): 3.1 %, aporte 15 s. No verificable (f): 0.1 %, aporte 0.4 s. Sin anuncio: 2.9 % de los instantes (fuera del MAE).
4. Diferencia con `ERROR_POR_COCHE.md`: allá B5 y B6 (1.º ya pasado o fantasma con bondi no anunciado primero) se cuentan también en la fila del bondi no anunciado; acá cada instante cae en un solo caso, por el estado del 1.º anunciado, y los aportes suman el MAE.
5. Por línea el MAE del próximo coche va de 58 a 567 s (mediana 83 s) y el cociente próximo/modelo de 1.1 a 10.8 (mediana 1.6). Las 5 líneas de mayor cociente: 188 (10.8), 45 (7.1), 8 (6.9), 80 (6.8), 29 (5.9). En 46 de 126 líneas el MAE del próximo coche supera al doble de la vara. En las 25 peores líneas los aportes de b-e suman 223 s en promedio contra 35 s de a (cociente por coche/modelo de esas líneas: 1.01).
6. Cantidad de ramales: Spearman con el aporte de (c)+(d) = +0.74 (p 1.1e-22), con el cociente próximo/modelo = +0.57 (p 3.0e-12), n = 126. Con la cantidad de shapes: +0.73 y +0.56. Ver la tabla por cantidad de shapes.
7. Causas de bondi fantasma: solo hay clasificación (`falsas/clasif.parquet`) para las 12 líneas viejas con el run de v3 de la vara anterior; se cruzó por (día, línea, parada, t, coche) con el 1.º anunciado de v4. Para las otras 114 líneas hace falta el diagnóstico de `falsas_diag.py` (viaje ex post de cada coche; corrida de ~3 h por 12 líneas), por eso se omite. Cruce de las 12: ver tabla.
