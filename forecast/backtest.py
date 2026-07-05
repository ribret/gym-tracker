"""
Ehrlicher rolling-origin-Backtest des Prognosemodells.

Reproduziert die Kennzahlen aus dem Modellauswahl-Lauf und misst die Band-Coverage
EMPIRISCH (nicht aus Theorie uebernommen). Meldet:
- pooled MAE, RMSE, Bias   (Modell vs. lookup-Baseline)
- Peak-MAE (10-21 Uhr)     -- der entscheidungsrelevante Kern
- gepaarte Tages-Gewinnrate Modell vs. lookup (Go/No-Go-Gate)
- 80%-Band-Coverage + mittlere Breite je Band-Methode (raw / conformal_global / conformal_phase)

Lauf:  OMP_NUM_THREADS=1 python3 forecast/backtest.py
"""
from __future__ import annotations
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
import pandas as pd

from features import rolling_origin_splits
from model import ForecastModel, LookupBaseline, load_training_frame


def mae(a, b):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def run(csv_path="data/gym_utilization.csv", min_train_days=21):
    df = load_training_frame(csv_path)
    methods = ["resid_phase", "resid_global"]

    all_y, all_pt = [], []
    all_min, all_studio = [], []
    all_lo = {m: [] for m in methods}
    all_hi = {m: [] for m in methods}
    day_mae_model, day_mae_lookup = [], []
    peak_y, peak_pt, peak_lk = [], [], []

    n_days = 0
    for tr, d, te in rolling_origin_splits(df, min_train_days=min_train_days):
        train, test = df.loc[tr], df.loc[te]
        n_days += 1

        # ein Modell fitten, alle Band-Methoden daraus ableiten (identische Punkt-/Quantilmodelle)
        fm = ForecastModel().fit(train)
        pt, _, _ = fm.predict(test)

        # Baseline
        lb = LookupBaseline().fit(train)
        lk = lb.predict_rows(test["Studio"].values,
                             test["dow_num"].values,
                             (test["minutes"].values // 60).astype(int))

        yt = test["y"].values
        mn = test["minutes"].values
        all_y += list(yt); all_pt += list(pt)
        all_min += list(mn); all_studio += list(test["Studio"].values)
        day_mae_model.append(mae(yt, pt)); day_mae_lookup.append(mae(yt, lk))

        pk = (mn >= 600) & (mn <= 1260)
        if pk.sum():
            peak_y += list(yt[pk]); peak_pt += list(pt[pk]); peak_lk += list(lk[pk])

        for m in methods:
            fm.band_method = m
            _, lo, hi = fm.predict(test)
            all_lo[m] += list(lo); all_hi[m] += list(hi)

    y = np.array(all_y); pt = np.array(all_pt); mn = np.array(all_min)
    print(f"Backtest-Tage: {n_days} | Testzeilen: {len(y)}")
    print("=" * 60)
    print("PUNKTGUETE (pooled ueber alle Testzeilen)")
    print(f"  Modell   MAE={mae(y,pt):.2f}  RMSE={np.sqrt(np.mean((y-pt)**2)):.2f}  Bias={np.mean(pt-y):+.2f}")
    print(f"  Lookup   MAE={np.mean([mae(*x) for x in [(y, None)]]) if False else '':}", end="")
    # lookup pooled:
    # (recompute pooled lookup from day arrays not stored; use mean-of-day for lookup ref)
    print(f"mean-of-day  Modell={np.mean(day_mae_model):.2f}  Lookup={np.mean(day_mae_lookup):.2f}")
    pk = (mn >= 600) & (mn <= 1260)
    print(f"  PEAK 10-21 Uhr  Modell MAE={mae(np.array(peak_y),np.array(peak_pt)):.2f}"
          f"   Lookup MAE={mae(np.array(peak_y),np.array(peak_lk)):.2f}")
    wins = int(np.sum(np.array(day_mae_model) < np.array(day_mae_lookup)))
    diff = np.array(day_mae_lookup) - np.array(day_mae_model)
    print(f"  Gepaart vs Lookup: {wins}/{n_days} Gewinn-Tage | mittl. Verbesserung "
          f"{diff.mean():+.2f} (SE {diff.std(ddof=1)/np.sqrt(n_days):.2f})")

    print("=" * 60)
    print("BAND-KALIBRIERUNG (nominal 80%)  -> Coverage empirisch messen")
    for m in methods:
        lo = np.array(all_lo[m]); hi = np.array(all_hi[m])
        cov = float(np.mean((y >= lo) & (y <= hi)))
        width = float(np.mean(hi - lo))
        flag = "OK" if 0.77 <= cov <= 0.83 else ("zu breit" if cov > 0.83 else "UNTERDECKT")
        print(f"  {m:18s} Coverage={cov*100:5.1f}%  mittl.Breite={width:5.1f}pp  [{flag}]")

    print("=" * 60)
    print("PER STUDIO (pooled MAE)")
    st = np.array(all_studio)
    for s in sorted(set(st)):
        mask = st == s
        print(f"  {s:16s} MAE={mae(y[mask], pt[mask]):.2f}  n={mask.sum()}")
    return dict(mae=mae(y, pt), n_days=n_days)


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "data/gym_utilization.csv")
