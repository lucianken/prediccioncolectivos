"""
Construye data/ml/schedule_dev_medians.json desde data/ml/training/eta_train.parquet.

Uso:
  python -m prediccion.pipeline.build_schedule_dev_table

Requiere DuckDB. El parquet tiene ~70M filas — se usa DuckDB para no cargar en RAM.
Deduplica antes de calcular la mediana para eliminar el sesgo por pares (P, F).

Output JSON: {ramal_id: {dist_bucket_str: expected_time_s}}
  ramal_id    — OSM shape_id (ej: "382202")
  dist_bucket — str(round(dist_along_norm * 20) / 20.0), misma fórmula que el lookup
  expected_time_s — mediana de time_since_start en ese bucket
"""

import json
import sys
from pathlib import Path


def main() -> None:
    parquet_path = Path("data/ml/training/eta_train.parquet")
    out_path = Path("data/ml/schedule_dev_medians.json")

    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
        n_ramales = len(existing)
        n_buckets_total = sum(len(v) for v in existing.values())
        avg_buckets = n_buckets_total / n_ramales if n_ramales else 0
        print(f"schedule_dev_medians.json ya existe — saltando recálculo.")
        print(f"  Ramales: {n_ramales}, buckets promedio por ramal: {avg_buckets:.1f}")
        return

    if not parquet_path.exists():
        print(f"ERROR: {parquet_path} no encontrado.", file=sys.stderr)
        print("  Correr primero: python -m prediccion.pipeline.build_dataset", file=sys.stderr)
        sys.exit(1)

    try:
        import duckdb
    except ImportError:
        print("ERROR: duckdb no instalado. pip install duckdb", file=sys.stderr)
        sys.exit(1)

    print(f"Leyendo {parquet_path} con DuckDB (dedup + median)...")
    con = duckdb.connect()
    rows = con.execute(f"""
        WITH deduped AS (
            SELECT DISTINCT ramal_id, dist_along_norm, time_since_start
            FROM read_parquet('{str(parquet_path).replace(chr(92), '/')}')
        )
        SELECT
            ramal_id,
            CAST(round(dist_along_norm * 20) / 20.0 AS DOUBLE) AS dist_bucket,
            median(time_since_start) AS expected_time_s,
            count(*) AS n_obs
        FROM deduped
        GROUP BY 1, 2
        ORDER BY 1, 2
    """).fetchall()
    con.close()
    print(f"  {len(rows)} filas resultado (ramal × bucket)")

    # Construir dict — keys son enteros "0".."20" (bucket_idx = round(dist * 20))
    medians: dict[str, dict[str, float]] = {}
    for ramal_id, dist_bucket, expected_time_s, n_obs in rows:
        if ramal_id is None:
            continue
        bucket_str = str(round(float(dist_bucket) * 20))
        medians.setdefault(str(ramal_id), {})[bucket_str] = float(expected_time_s)

    # Validación de monotonicidad por ramal (tolerancia: máx 5% de buckets pueden violar)
    n_warnings = 0
    for ramal_id, buckets in medians.items():
        sorted_items = sorted(buckets.items(), key=lambda x: float(x[0]))
        violations = []
        prev_val = None
        for bucket_str, val in sorted_items:
            if prev_val is not None and val < prev_val * 0.95:
                violations.append((bucket_str, prev_val, val))
            prev_val = val
        tol = max(1, int(len(sorted_items) * 0.05))
        if len(violations) > tol:
            n_warnings += 1
            print(f"WARN: ramal {ramal_id} — {len(violations)} violaciones de monotonicidad:")
            for b, p, v in violations[:5]:
                print(f"  bucket={b}: {p:.1f}s -> {v:.1f}s (caida {p-v:.1f}s)")
            if len(violations) > 5:
                print(f"  ... y {len(violations)-5} más")

    if n_warnings == 0:
        print(f"  Monotonicidad OK en todos los {len(medians)} ramales.")
    else:
        print(f"  {n_warnings} ramal(es) con violaciones — guardando igual.")

    # Sample del primer ramal
    if medians:
        first_ramal = next(iter(medians))
        first_buckets = sorted(medians[first_ramal].items(), key=lambda x: int(x[0]))
        print(f"\nSample ramal {first_ramal} ({len(first_buckets)} buckets):")
        for b, v in first_buckets[:5]:
            print(f"  bucket={int(b):2d} (dist={int(b)/20:.2f})  expected={v:8.1f}s")
        if len(first_buckets) > 10:
            print(f"  ...")
        for b, v in first_buckets[-5:]:
            print(f"  bucket={int(b):2d} (dist={int(b)/20:.2f})  expected={v:8.1f}s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(medians, f, indent=2)
    print(f"\nGuardado: {out_path}  ({len(medians)} ramales)")


if __name__ == "__main__":
    main()
