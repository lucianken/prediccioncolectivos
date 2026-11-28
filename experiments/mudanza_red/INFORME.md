# Equivalencia de nivel 2 de la mudanza a `red` (F1.5)

Spec: `../bondi/docs/specs/red-reglas.md`, «Pruebas», nivel 2. Script: `equivalencia.py` (`corre` y `compara`). Resultado completo: `resultado.json`.

## Qué se comparó (2026-11-28)

- **Antes:** el árbol del tag `pre-red` (commit 2eb811e, exportado con `git archive`). **Después:** el árbol con los imports repuntados a `red` 0.1.0 (tag `red-v0.1.0` de `bondi`), con el replay importando `red` y no `replay/pinned/`, antes de borrar las copias.
- Mismos insumos congelados para los dos lados: copia de `proyectoconsola/data/line_shapes` (commit 087d276), `LABEL_LINE_MAP.json` y el export vigente `path_v4_l1_s1_r20261126` (idéntico al de `proyectoconsola/public/models/`). Grabación `Z:/grabaciones/2026-09-15.ndjson.gz`. Mismo Python 3.13, mismo `onnxruntime-gpu` 1.26.0, misma máquina.
- Día 2026-09-15, líneas 26, 39, 42 y 168. Corridas: pipeline v2 `--segmentation geo2` con `--assign geo3`, con `--assign legacy` y con `--assign geo3 --targets stops`; replay con variantes `base,sentido,ramal,prior_token_ii`; `gen_path_parity_fixture.py` con seed 7.

## Resultado: IGUAL

- 17 parquets (898.342 filas): iguales con `assert_frame_equal(check_exact=True)` y además idénticos byte a byte (mismo sha256).
- 10 json (`meta.json` por día, `manifest.json`, `carry.json`, fixture): iguales salvo `elapsed_s`. `assign_params` igual en geo3.
- Fixture: 19.945 casos iguales; el lado nuevo agrega la clave `eta0_s` (superset de `path_reference`, R4) en 27.958 lugares, contada aparte y excluida de la comparación.

## Tiempos (s)

| corrida | antes | después |
|---|---|---|
| v2 geo3 | 16,8 | 20,1 |
| v2 legacy | 16,1 | 19,3 |
| v2 geo3 + paradas | 20,5 | 23,4 |
| replay | 268,1 | 321,0 |
| fixture | 240,4 | 222,8 |

El después corrió a continuación del antes, con otro agente usando la PC: la diferencia es pareja entre corridas (también en el pipeline, que no usa `memoized()`) y el fixture salió más rápido. No es una medición limpia del costo; si se quiere, repetir solo el replay antes y después con la PC libre.
