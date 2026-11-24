### train (12 líneas)

| corrida | global | sesgo | subest.>60 s global | MAE 0–5 / 5–10 / 10–20 / 20+ | subest. 0–5 | por distancia | inicio | resto | sin inicio | detenido | en mov. |
|---|---:|---:|---:|---|---:|---|---:|---:|---:|---:|---:|
| a3_lr1e-3_s0 | 106.5 | -24.1 | 30.6 | 44 / 69 / 113 / 184 | 3.7 | 56 / 74 / 105 / 177 | 131.2 | 98.4 | 98.4 | 109.7 | 104.3 |
| a3_lr2e-3_s0 | 107.1 | -21.4 | 30.0 | 46 / 70 / 114 / 183 | 3.1 | 60 / 75 / 105 / 176 | 132.7 | 98.7 | 98.7 | 111.0 | 104.5 |
| path_lr1e-3_s0 | 102.6 | -15.4 | 28.7 | 42 / 70 / 112 / 172 | 4.7 | 56 / 73 / 103 / 166 | 127.2 | 94.6 | 94.6 | 106.4 | 100.0 |
| path_lr2e-3_s0 | 101.6 | -14.9 | 28.5 | 41 / 69 / 111 / 170 | 4.5 | 55 / 72 / 102 / 164 | 125.9 | 93.6 | 93.6 | 105.5 | 99.0 |
| a3_lr1e-3_s1 | 109.3 | -29.7 | 32.4 | 43 / 71 / 117 / 190 | 4.5 | 57 / 76 / 107 / 182 | 135.8 | 100.7 | 100.7 | 113.5 | 106.5 |
| path_lr2e-3_s1 | 102.2 | -10.0 | 27.5 | 42 / 70 / 111 / 171 | 4.2 | 56 / 72 / 102 / 165 | 126.1 | 94.4 | 94.4 | 106.2 | 99.5 |

- **a3** (LR 1e-3): global semillas 106.5 / 109.3, media 107.9, diferencia entre semillas 2.9; sin inicio 99.6; 20+ min 186.9
- **path** (LR 2e-3): global semillas 101.6 / 102.2, media 101.9, diferencia entre semillas 0.6; sin inicio 94.0; 20+ min 170.6
- ventaja del modelo por tramos sobre A3 (media de 2 semillas): 6.0 s (5.6 %); mayor diferencia entre semillas: 2.9 s; ventaja / diferencia = 2.1

### control (12, 15, 128)

| corrida | global | sesgo | subest.>60 s global | MAE 0–5 / 5–10 / 10–20 / 20+ | subest. 0–5 | por distancia | inicio | resto | sin inicio | detenido | en mov. |
|---|---:|---:|---:|---|---:|---|---:|---:|---:|---:|---:|
| a3_lr1e-3_s0 | 298.6 | 5.6 | 30.3 | 83 / 172 / 313 / 566 | 9.4 | 77 / 156 / 327 / 602 | 355.2 | 278.7 | 278.7 | 295.8 | 300.8 |
| a3_lr2e-3_s0 | 284.2 | -5.3 | 30.8 | 92 / 169 / 287 / 533 | 8.2 | 86 / 152 / 302 / 571 | 326.4 | 269.4 | 269.4 | 276.9 | 289.7 |
| path_lr1e-3_s0 | 221.2 | -19.9 | 45.8 | 59 / 122 / 197 / 457 | 11.0 | 65 / 110 / 188 / 517 | 260.1 | 207.5 | 207.5 | 203.2 | 234.6 |
| path_lr2e-3_s0 | 211.1 | -32.6 | 46.5 | 57 / 116 / 185 / 440 | 9.6 | 65 / 107 / 178 / 490 | 254.6 | 195.8 | 195.8 | 195.8 | 222.6 |
| a3_lr1e-3_s1 | 287.6 | -14.7 | 32.4 | 79 / 165 / 301 / 546 | 10.5 | 76 / 151 / 313 / 581 | 333.0 | 271.7 | 271.7 | 281.4 | 292.3 |
| path_lr2e-3_s1 | 229.8 | -33.2 | 49.5 | 58 / 121 / 196 / 491 | 10.3 | 64 / 108 / 189 / 557 | 270.1 | 215.7 | 215.7 | 208.4 | 245.9 |

- **a3** (LR 1e-3): global semillas 298.6 / 287.6, media 293.1, diferencia entre semillas 11.0; sin inicio 275.2; 20+ min 556.0
- **path** (LR 2e-3): global semillas 211.1 / 229.8, media 220.4, diferencia entre semillas 18.7; sin inicio 205.7; 20+ min 465.7
- ventaja del modelo por tramos sobre A3 (media de 2 semillas): 72.7 s (24.8 %); mayor diferencia entre semillas: 18.7 s; ventaja / diferencia = 3.9
