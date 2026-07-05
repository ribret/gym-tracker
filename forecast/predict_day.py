"""
Tagesprognose der Auslastung fuer ein oder alle JOHN-REED-Berlin-Studios.

Trainiert das Modell auf dem gesamten CSV, holt die Open-Meteo-Wetterprognose fuer
den Zieltag und gibt die Stundenkurve mit 80%-Band aus (Tabelle + PNG-Chart).

Beispiele:
  OMP_NUM_THREADS=1 python3 forecast/predict_day.py --studio charlottenburg
  python3 forecast/predict_day.py --date 2026-07-07 --studio all --out /tmp/prognose.png
"""
from __future__ import annotations
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys, json, argparse, urllib.request, datetime as dt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import STUDIOS, build_predict_frame
from model import ForecastModel, LookupBaseline, load_training_frame

BERLIN_LAT, BERLIN_LON = 52.52, 13.40


def fetch_weather(date_str: str):
    """Stuendliche Temp + Niederschlag fuer Berlin (Open-Meteo). Fallback: NaN."""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={BERLIN_LAT}"
           f"&longitude={BERLIN_LON}&hourly=temperature_2m,precipitation"
           f"&timezone=Europe%2FBerlin&start_date={date_str}&end_date={date_str}")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            h = json.load(r)["hourly"]
        return {int(t[11:13]): (te, pr) for t, te, pr in
                zip(h["time"], h["temperature_2m"], h["precipitation"])}
    except Exception as e:
        print(f"[warn] Wetterabruf fehlgeschlagen ({e}); Prognose ohne Wetter.", file=sys.stderr)
        return {}


def predict_studio(fm, studio, date_str, weather, hours):
    dts = pd.DatetimeIndex([pd.Timestamp(f"{date_str} {h:02d}:00") for h in hours])
    temp = np.array([weather.get(h, (np.nan, np.nan))[0] for h in hours], float)
    prec = np.array([weather.get(h, (np.nan, np.nan))[1] for h in hours], float)
    frame = build_predict_frame(studio, dts, temp=temp, precip=prec, schulferien=0)
    pt, lo, hi = fm.predict(frame)
    return pt, lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--studio", default="charlottenburg", help="Studio-Schluessel oder 'all'")
    ap.add_argument("--csv", default="data/gym_utilization.csv")
    ap.add_argument("--out", default="", help="PNG-Pfad (optional)")
    ap.add_argument("--from-hour", type=int, default=6)
    ap.add_argument("--to-hour", type=int, default=23)
    args = ap.parse_args()

    hours = list(range(args.from_hour, args.to_hour + 1))
    df = load_training_frame(args.csv)
    last = df["date"].max().date()
    print(f"Training: {df['date'].nunique()} Tage bis {last} | {len(df)} Zeilen")
    fm = ForecastModel().fit(df)

    weather = fetch_weather(args.date)
    wd = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][pd.Timestamp(args.date).dayofweek]
    if weather:
        tmax = max(v[0] for v in weather.values())
        rain = sum(v[1] for v in weather.values())
        print(f"Wetter {args.date}: Tmax {tmax:.0f}C, Regen {rain:.1f}mm")

    studios = STUDIOS if args.studio == "all" else [args.studio]
    results = {}
    for s in studios:
        pt, lo, hi = predict_studio(fm, s, args.date, weather, hours)
        results[s] = (pt, lo, hi)

    # Tabelle (Fokus-Studio bzw. erstes)
    focus = studios[0]
    pt, lo, hi = results[focus]
    print(f"\nPrognose {focus}  {wd} {args.date}  (Punkt [80%-Band])")
    peak_i = int(np.argmax(pt))
    for i, h in enumerate(hours):
        bar = "#" * int(round(pt[i] / 3))
        star = "  <- Peak" if i == peak_i else ""
        print(f"  {h:02d}:00  {pt[i]:4.0f}% [{lo[i]:3.0f}-{hi[i]:3.0f}]  {bar}{star}")
    print(f"  Tages-Peak: {pt[peak_i]:.0f}% um {hours[peak_i]:02d}:00")

    if args.studio == "all":
        print("\nPeak je Studio:")
        for s in studios:
            p = results[s][0]
            j = int(np.argmax(p))
            print(f"  {s:16s} {p[j]:4.0f}% um {hours[j]:02d}:00  | Tagesmittel {p.mean():.0f}%")

    if args.out:
        make_chart(results, hours, args.date, wd, args.out, focus)
        print(f"\nChart gespeichert: {args.out}")


def make_chart(results, hours, date_str, wd, out, focus):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = np.array(hours)
    if len(results) == 1:
        fig, ax = plt.subplots(figsize=(10, 5.5))
        pt, lo, hi = results[focus]
        ax.fill_between(x, lo, hi, alpha=0.18, color="#2a9d8f", label="80%-Band")
        ax.plot(x, pt, "-o", color="#264653", lw=2, ms=4, label="Prognose")
        ax.set_title(f"JOHN REED {focus} — {wd} {date_str}")
    else:
        fig, ax = plt.subplots(figsize=(11, 6))
        cmap = plt.get_cmap("tab10")
        for i, (s, (pt, lo, hi)) in enumerate(results.items()):
            ax.plot(x, pt, "-o", ms=3, lw=1.8, color=cmap(i), label=s)
        ax.set_title(f"JOHN REED Berlin — Auslastungsprognose {wd} {date_str}")
    ax.set_xlabel("Uhrzeit"); ax.set_ylabel("Auslastung %")
    ax.set_ylim(0, 100); ax.set_xticks(x[::1] if len(x) <= 20 else x[::2])
    ax.grid(alpha=0.25); ax.legend(fontsize=8, ncol=2)
    fig.tight_layout(); fig.savefig(out, dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
