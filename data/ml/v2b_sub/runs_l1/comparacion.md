# Comparación de pérdidas, modelo por tramos (media de semillas 0 y 1)

llega antes / después = % de filas con |error| > 60 s; espera extra = media de (real - pred) cuando llega después.

## seen

| pérdida | MAE (s) | 0-5 min: llega antes (%) | 0-5 min: llega después (%) | 0-5 min: espera extra (s) | <500 m: llega antes (%) | <500 m: llega después (%) | <500 m: espera extra (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| pinball | 103.1 | 17.7 | 4.4 | 31.2 | 13.1 | 9.2 | 91.8 |
| l1 | 102.7 | 10.5 | 7.6 | 34.6 | 3.9 | 14.0 | 77.8 |
| pinball_inv | 103.4 | 8.0 | 12.4 | 37.0 | 1.2 | 21.6 | 71.3 |

## heldout

| pérdida | MAE (s) | 0-5 min: llega antes (%) | 0-5 min: llega después (%) | 0-5 min: espera extra (s) | <500 m: llega antes (%) | <500 m: llega después (%) | <500 m: espera extra (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| pinball | 215.2 | 21.4 | 9.7 | 43.2 | 13.0 | 13.6 | 112.4 |
| l1 | 208.6 | 14.2 | 14.1 | 46.0 | 3.9 | 19.4 | 97.3 |
| pinball_inv | 217.0 | 12.0 | 19.3 | 47.0 | 1.6 | 27.0 | 87.0 |
