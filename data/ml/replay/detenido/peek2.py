import pandas as pd
pd.set_option("display.width", 300)
p = pd.read_csv("out/pareado.csv").set_index("cfg")
for c in ["N5_A50_b2_all","N5_A50_b2_mid","N5_A50_b2_cab","N5_A50_a_mid","N5_A50_a_all","N5_A100_b2_mid","N5_A20_b2_mid"]:
    print(c, " | ".join(f"{m} {p.loc[c,m]:+.2f}±{p.loc[c,m+'_sd']:.2f} (+{p.loc[c,m+'_pos']}/-{p.loc[c,m+'_neg']})" for m in ["fa","faC","om","om_b","om_1","vac","mae","antes","desp"]))
