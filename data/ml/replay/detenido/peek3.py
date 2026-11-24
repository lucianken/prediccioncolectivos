import pandas as pd
pd.set_option("display.width", 300)
b = pd.read_csv("out/byline.csv", dtype={"line": str})
for c in ["base","N5_A50_b2_mid","N5_A50_b2_all","N5_A50_a_mid"]:
    print(c); print(b[b.cfg==c].set_index("line")[["fa","faC","om","om_b","vac","mae","antes","desp","n_fa"]].round(2).T.to_string())
