"""
Baut die statische Prognose-Seite fuer GitHub Pages.

Trainiert das Modell frisch auf dem gesamten CSV (dadurch verbessert sich die
Prognose automatisch mit jedem neuen Datentag), prognostiziert Heute + Morgen
fuer alle Studios (inkl. 80%-Band und Open-Meteo-Wetter) und rendert alles in
eine selbst-enthaltene index.html (Template: site_template.html, Daten als
eingebettetes JSON, Chart clientseitig als SVG).

Nutzung (lokal wie in Actions identisch):
  OMP_NUM_THREADS=1 python3 forecast/build_site.py --out-dir _site
"""
from __future__ import annotations
import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
import sys, json, argparse, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import STUDIOS, WEEKDAYS_DE, build_predict_frame, load_raw
from model import ForecastModel, load_training_frame

BERLIN = ZoneInfo("Europe/Berlin")
BERLIN_LAT, BERLIN_LON = 52.52, 13.40

STUDIO_LABELS = {
    "boetzow": "Bötzow",
    "charlottenburg": "Charlottenburg",
    "friedrichshain": "Friedrichshain",
    "gesundbrunnen": "Gesundbrunnen",
    "kreuzberg": "Kreuzberg",
    "prenzlauer_berg": "Prenzlauer Berg",
    "womens_club": "Women's Club",
}


def fetch_weather(start: str, end: str) -> dict:
    """Stuendliche Temp + Niederschlag fuer Berlin, mehrere Tage in einem Call.
    Rueckgabe: {"YYYY-MM-DD": {hour: (temp, precip)}}. Fallback: {} (Prognose ohne Wetter)."""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={BERLIN_LAT}"
           f"&longitude={BERLIN_LON}&hourly=temperature_2m,precipitation"
           f"&timezone=Europe%2FBerlin&start_date={start}&end_date={end}")
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            h = json.load(r)["hourly"]
        out: dict = {}
        for t, te, pr in zip(h["time"], h["temperature_2m"], h["precipitation"]):
            out.setdefault(t[:10], {})[int(t[11:13])] = (te, pr)
        return out
    except Exception as e:
        print(f"[warn] Wetterabruf fehlgeschlagen ({e}); Prognose ohne Wetter.", file=sys.stderr)
        return {}


def fetch_ferien_periods(years) -> list | None:
    """Berliner Schulferien als (start, end)-Liste. None = API nicht erreichbar."""
    periods, ok = [], False
    for y in sorted(set(years)):
        try:
            with urllib.request.urlopen(f"https://ferien-api.de/api/v1/holidays/BE/{y}",
                                        timeout=10) as r:
                for h in json.load(r):
                    s = dt.datetime.fromisoformat(h["start"].replace("Z", "+00:00")).date()
                    e = dt.datetime.fromisoformat(h["end"].replace("Z", "+00:00")).date()
                    periods.append((s, e))
            ok = True
        except Exception as e:
            print(f"[warn] Schulferien-Abruf {y} fehlgeschlagen ({e}).", file=sys.stderr)
    return periods if ok else None


def is_schulferien(d: dt.date, periods: list | None, raw: pd.DataFrame) -> int:
    """Ferien-Flag fuer den Zieltag; Fallback auf den juengsten CSV-Wert."""
    if periods is not None:
        return int(any(s <= d <= e for s, e in periods))
    v = raw["Ist_Schulferien_BE"].dropna()
    return int(v.iloc[-1]) if len(v) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/gym_utilization.csv")
    ap.add_argument("--out-dir", default="_site")
    ap.add_argument("--from-hour", type=int, default=6)
    ap.add_argument("--to-hour", type=int, default=23)
    args = ap.parse_args()

    now = dt.datetime.now(BERLIN)
    today = now.date()
    dates = [today, today + dt.timedelta(days=1)]

    hours = list(range(args.from_hour, args.to_hour + 1))
    raw = load_raw(args.csv)
    df = load_training_frame(args.csv)
    last_dt = raw["dt"].max()
    print(f"Training: {df['date'].nunique()} Tage bis {last_dt} | {len(df)} Zeilen")
    fm = ForecastModel().fit(df)

    weather = fetch_weather(dates[0].isoformat(), dates[-1].isoformat())
    ferien = fetch_ferien_periods({d.year for d in dates})

    days = []
    for di, d in enumerate(dates):
        ds = d.isoformat()
        w = weather.get(ds, {})
        temp = np.array([w.get(h, (np.nan, np.nan))[0] for h in hours], float)
        prec = np.array([w.get(h, (np.nan, np.nan))[1] for h in hours], float)
        sf = is_schulferien(d, ferien, raw)

        forecast = {}
        for s in STUDIOS:
            dts = pd.DatetimeIndex([pd.Timestamp(f"{ds} {h:02d}:00") for h in hours])
            frame = build_predict_frame(s, dts, temp=temp, precip=prec, schulferien=sf)
            pt, lo, hi = fm.predict(frame)
            forecast[s] = {"pt": [round(float(v)) for v in pt],
                           "lo": [round(float(v)) for v in lo],
                           "hi": [round(float(v)) for v in hi]}

        # Ist-Messungen des Tages (nur fuer bereits angebrochene Tage vorhanden)
        day_rows = raw[raw["Datum"] == ds]
        actuals = {}
        for s in STUDIOS:
            r = day_rows[day_rows["Studio"] == s]
            pts = [[int(t.hour * 60 + t.minute), int(v)]
                   for t, v in zip(r["dt"], r["Auslastung_%"]) if pd.notna(v)
                   and args.from_hour * 60 <= t.hour * 60 + t.minute <= args.to_hour * 60 + 59]
            if pts:
                actuals[s] = pts

        day_temp = temp[~np.isnan(temp)]
        day_prec = prec[~np.isnan(prec)]
        days.append({
            "date": ds,
            "label": "Heute" if di == 0 else "Morgen",
            "weekday": WEEKDAYS_DE[d.weekday()],
            "schulferien": sf,
            "tmax": round(float(day_temp.max()), 1) if len(day_temp) else None,
            "rain_mm": round(float(day_prec.sum()), 1) if len(day_prec) else None,
            "forecast": forecast,
            "actuals": actuals,
        })

    payload = {
        "generated": now.strftime("%d.%m.%Y, %H:%M"),
        "train_days": int(df["date"].nunique()),
        "train_rows": int(len(df)),
        "last_data": last_dt.strftime("%d.%m.%Y, %H:%M"),
        "hours": hours,
        "studios": STUDIOS,
        "labels": STUDIO_LABELS,
        "days": days,
    }

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "site_template.html"), encoding="utf-8") as f:
        html = f.read()
    marker = "/*__DATA__*/null"
    assert marker in html, "Daten-Marker im Template nicht gefunden"
    html = html.replace(marker, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    open(os.path.join(args.out_dir, ".nojekyll"), "w").close()
    print(f"Seite gebaut: {args.out_dir}/index.html "
          f"({len(html) // 1024} KB, {len(days)} Tage x {len(STUDIOS)} Studios)")


if __name__ == "__main__":
    main()
