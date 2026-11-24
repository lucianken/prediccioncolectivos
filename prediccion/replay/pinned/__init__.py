"""Copia fijada de geo_assign.py y path_reference.py: la vara de producto no depende de cambios posteriores.

Re-pin 2026-11-15 (contrato 2.2, paradas por tramo): copia de prediccion/inference/path_reference.py (sha256 3f23cb3c665eb4d0...,
con el desempate de proyección PROJECT_TIE_M) y de prediccion/v2/geo_assign.py (sin cambios respecto del pin anterior).
prediccion/models/stops.py (stop_features_np, sha256 131f100f11275a72...) se importa del árbol, no está copiado.
Cambios respecto del original: (1) path_reference importa geo_assign de este paquete; (2) predict_from_raw acepta
snapshot_ts y ts_offset_s (port de core.js; con los defaults, idéntico) y devuelve eta0_s.
Pin anterior (2026-11-14): commit e7479f7 (contrato 2.1, sin desempate de proyección); referencia: ORACULO_RAMAL.md.
"""
PINNED_COMMIT = "e7479f7"          # pin anterior; el vigente se identifica por los hashes de arriba
PINNED_DATE = "2026-11-15"
