import pandas as pd
def to_md(df, index=False, nd=1):
    d = df.reset_index() if index else df
    cols = [str(c) for c in d.columns]
    def f(v):
        if isinstance(v, float):
            return "" if v != v else f"{v:.{nd}f}".replace(".", ",")
        return str(v)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in d.itertuples(index=False):
        lines.append("| " + " | ".join(f(v) for v in r) + " |")
    return "\n".join(lines)
