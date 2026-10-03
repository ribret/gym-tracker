"""
Feature-Aufbau fuer die JOHN-REED-Auslastungsprognose.

Self-contained (keine Abhaengigkeit auf externe Pfade), damit forecast/ direkt in
GitHub Actions laeuft. Feature-Set und Konventionen stammen aus dem adversarial
verifizierten Modellauswahl-Lauf (siehe forecast/README.md):

  Punktmodell = HistGradientBoostingRegressor (full pooling), studio+dow als native
  Kategorien. Bewusst schlankes Feature-Set: was OOS keinen Lift bringt, fliegt raus
  (voller Wetterblock, Fourier-Terme, Trend, Ein-Tages-Feiertag). Behalten wird nur,
  was mechanistisch belegt oder forward-kompatibel ist.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

STUDIOS = ["boetzow", "charlottenburg", "friedrichshain", "gesundbrunnen",
           "kreuzberg", "prenzlauer_berg", "womens_club"]
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
               "Freitag", "Samstag", "Sonntag"]

# Feature-Reihenfolge ist VERBINDLICH (monotonic_cst + categorical_features haengen dran).
NUM_FEATURES = ["tod", "Temperatur_C", "is_hot", "is_rain", "is_weekend", "Ist_Schulferien_BE"]
CAT_FEATURES = ["studio", "dow"]
FEATURES = NUM_FEATURES + CAT_FEATURES

# monotone Nebenbedingung: Auslastung faellt mit Temperatur (Hitze daempft). Sonst frei.
MONOTONIC_CST = [0, -1, 0, 0, 0, 0, 0, 0]  # aligned to FEATURES

CSV_DEFAULT = "data/gym_utilization.csv"


def load_raw(csv_path: str = CSV_DEFAULT) -> pd.DataFrame:
    """Roh-CSV laden, Typen setzen, datetime bauen, zeitlich sortieren."""
    df = pd.read_csv(csv_path, sep=";", decimal=".")
    df["dt"] = pd.to_datetime(df["Datum"] + " " + df["Uhrzeit"], format="%Y-%m-%d %H:%M")
    df["date"] = pd.to_datetime(df["Datum"], format="%Y-%m-%d")
    for c in ["Auslastung_%", "Temperatur_C", "Niederschlag_mm", "Wettercode",
              "Bewoelkung_%", "Wind_kmh", "Ist_Wochenende", "Ist_Feiertag_BE",
              "Ist_Schulferien_BE"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # exakte Dubletten (gleiches Studio + Minute) verwerfen; entstehen bei Doppellaeufen,
    # z.B. an Lauf-Grenzen der Workflow-Kette. Roh-CSV bleibt unveraendert (Protokoll).
    df = df.drop_duplicates(subset=["Studio", "Datum", "Uhrzeit"], keep="first")
    return df.sort_values("dt").reset_index(drop=True)


def _phase(minutes: np.ndarray) -> np.ndarray:
    """Tagesphase-Label fuer die (optionale) Band-Stratifizierung."""
    h = minutes // 60
    out = np.where((h >= 23) | (h <= 4), "Nacht",
          np.where(h <= 11, "Morgen",
          np.where(h <= 16, "Mittag", "Abend")))
    return out


# Feiertag = Sonntag (Domaenen-Prior statt gelerntem Feature): Im Datensatz liegen nur
# ~2 Berliner Feiertage, ein eigenes Feiertags-Feature waere nicht lernbar. Ein Feiertag
# wird deshalb als Sonntag behandelt, das Sonntagsprofil kennt das Modell aus ~20 Tagen.
# Test 03.10.2026: Pfingstmontag MAE 12,6 (als Montag) -> 7,7 (als Sonntag); Feiertag am
# Samstag neutral (6,7 -> 6,5). Gilt identisch in Training und Prognose.
HOLIDAY_DOW = 6


def effective_dow(dow, feiertag):
    """Wochentag fuer das Modell: an Feiertagen Sonntag (6), sonst der echte Wochentag."""
    return np.where(np.asarray(feiertag, float) == 1, HOLIDAY_DOW, np.asarray(dow))


def add_target_features(df: pd.DataFrame) -> pd.DataFrame:
    """Trainings-DataFrame: alle Modell-Features + y + Hilfsspalten (date, phase, minutes)."""
    df = df.copy()
    df["minutes"] = df["dt"].dt.hour * 60 + df["dt"].dt.minute
    df["tod"] = df["minutes"] / 1440.0
    df["dow_num"] = df["dt"].dt.dayofweek          # echter Wochentag (Lookup-Baseline)
    df["dow_eff"] = effective_dow(df["dow_num"], df["Ist_Feiertag_BE"].fillna(0))
    df["is_weekend"] = (df["dow_eff"] >= 5).astype(float)
    # Wetter-Ableitungen: NaN bleibt NaN (HGB routet nativ), kein Zwangs-Impute.
    temp = df["Temperatur_C"]
    df["is_hot"] = np.where(temp.isna(), np.nan, (temp >= 28).astype(float))
    prec = df["Niederschlag_mm"]
    df["is_rain"] = np.where(prec.isna(), np.nan, (prec > 0.1).astype(float))
    df["Ist_Schulferien_BE"] = df["Ist_Schulferien_BE"].astype(float)
    # native Kategorien
    df["studio"] = pd.Categorical(df["Studio"], categories=STUDIOS)
    df["dow"] = pd.Categorical(df["dow_eff"], categories=list(range(7)))
    df["phase"] = _phase(df["minutes"].values)
    df["y"] = df["Auslastung_%"].astype(float)
    return df


def make_X(df: pd.DataFrame) -> pd.DataFrame:
    """Modell-Feature-Matrix in verbindlicher Spaltenreihenfolge & dtypes."""
    X = df[FEATURES].copy()
    X["studio"] = pd.Categorical(X["studio"], categories=STUDIOS)
    X["dow"] = pd.Categorical(X["dow"], categories=list(range(7)))
    return X


def build_predict_frame(studio: str, dts: pd.DatetimeIndex,
                        temp=None, precip=None, schulferien=0, feiertag=0) -> pd.DataFrame:
    """Feature-Frame fuer Prognose bauen (ein Studio, viele Zeitpunkte).
    temp/precip: Arrays gleicher Laenge wie dts (oder Skalar/None)."""
    n = len(dts)
    minutes = dts.hour * 60 + dts.minute
    temp = np.full(n, np.nan) if temp is None else np.asarray(temp, float)
    precip = np.full(n, np.nan) if precip is None else np.asarray(precip, float)
    dow = effective_dow(dts.dayofweek, np.full(n, float(feiertag)))
    df = pd.DataFrame({
        "tod": minutes / 1440.0,
        "Temperatur_C": temp,
        "is_hot": np.where(np.isnan(temp), np.nan, (temp >= 28).astype(float)),
        "is_rain": np.where(np.isnan(precip), np.nan, (precip > 0.1).astype(float)),
        "is_weekend": (dow >= 5).astype(float),
        "Ist_Schulferien_BE": float(schulferien) if np.isscalar(schulferien)
                              else np.asarray(schulferien, float),
        "studio": pd.Categorical([studio] * n, categories=STUDIOS),
        "dow": pd.Categorical(dow, categories=list(range(7))),
    })
    df["_minutes"] = np.asarray(minutes)
    df["_phase"] = _phase(np.asarray(minutes))
    return df


def rolling_origin_splits(df: pd.DataFrame, min_train_days: int = 21, step: int = 1):
    """Backtest-Splitter: train = date<d, test = date==d (ganzer kuenftiger Tag)."""
    dates = np.sort(df["date"].unique())
    for i in range(min_train_days, len(dates), step):
        d = dates[i]
        tr = df.index[df["date"] < d]
        te = df.index[df["date"] == d]
        if len(tr) and len(te):
            yield tr, pd.Timestamp(d), te
