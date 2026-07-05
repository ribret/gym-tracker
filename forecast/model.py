"""
Prognosemodell: HistGradientBoostingRegressor (full pooling) + kalibrierte Baender.

Architektur (aus dem verifizierten Modellauswahl-Lauf):
- Punktprognose: HGB loss="squared_error" auf ALLEN Trainingsdaten (beste Punktguete).
- Baender: HGB loss="quantile" (0.1/0.9) auf einem frueheren fit-Teil + Split-Conformal-
  Nachkalibrierung auf einem zeitlich HINTEREN Kalibrier-Slice (Austauschbarkeit gewahrt:
  die Quantilmodelle sehen die Kalibrierzeilen NICHT).
- Band-Methode wird per gemessener Coverage gewaehlt (backtest.py), nicht per Theorie.

Determinismus: random_state=0, OMP_NUM_THREADS=1 (in CLI gesetzt).
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from features import (FEATURES, CAT_FEATURES, MONOTONIC_CST,
                      make_X, add_target_features)

# Gewinner-Config aus dem full-pooling+ Bake-off.
PARAMS = dict(
    max_iter=250,
    learning_rate=0.05,
    max_leaf_nodes=15,
    min_samples_leaf=25,
    l2_regularization=1.0,
    random_state=0,
    early_stopping=False,
)
PHASES = ["Nacht", "Morgen", "Mittag", "Abend"]


def _make_hgb(loss, quantile=None):
    kw = dict(PARAMS)
    kw["loss"] = loss
    if quantile is not None:
        kw["quantile"] = quantile
    return HistGradientBoostingRegressor(
        categorical_features=CAT_FEATURES,
        monotonic_cst=MONOTONIC_CST,
        **kw,
    )


def _fit(X, y, loss, quantile=None):
    m = _make_hgb(loss, quantile)
    m.fit(X, y)
    return m


def _calib_split(df_feat, calib_frac=0.2, min_calib_days=5):
    """Trainingsdaten zeitlich teilen: frueher fit-Teil vs. hinterer Kalibrier-Slice."""
    dates = np.sort(df_feat["date"].unique())
    n_cal = max(min_calib_days, int(round(len(dates) * calib_frac)))
    n_cal = min(n_cal, len(dates) - min_calib_days) if len(dates) > 2 * min_calib_days else 0
    if n_cal <= 0:
        return df_feat, None
    cutoff = dates[len(dates) - n_cal]
    fit_part = df_feat[df_feat["date"] < cutoff]
    cal_part = df_feat[df_feat["date"] >= cutoff]
    return fit_part, cal_part


class ForecastModel:
    """Trainiert Punktmodell + Residuen-basierte Baender, prognostiziert (point, lo, hi) auf [0,100].

    Baender: NICHT ueber HGB-Quantilregression (die kollabiert am unteren Rand bei diesen
    kleinen, null-lastigen Daten auf 0). Stattdessen SIGNIERTE Residuen-Quantile auf einem
    zeitlich hinteren Kalibrier-Slice, STRATIFIZIERT nach Tagesphase (Streuung nachts ~0,
    im Peak breit). Band = point + resid_q(alpha/2 .. 1-alpha/2). Coverage wird in
    backtest.py empirisch gemessen (nicht dem Nominalwert vertraut)."""

    def __init__(self, alpha=0.2, band_method="resid_phase"):
        self.alpha = alpha                # 1-alpha = nominale Coverage (0.8)
        self.band_method = band_method    # resid_phase | resid_global
        self.point = None
        self.dlo_global = 0.0
        self.dhi_global = 0.0
        self.dlo_phase = {p: 0.0 for p in PHASES}
        self.dhi_phase = {p: 0.0 for p in PHASES}

    def _resid_quantiles(self, resid):
        lo = float(np.percentile(resid, 100 * self.alpha / 2))
        hi = float(np.percentile(resid, 100 * (1 - self.alpha / 2)))
        return lo, hi

    def fit(self, df_feat: pd.DataFrame):
        # Deploytes Punktmodell: alle Daten (beste Punktguete)
        self.point = _fit(make_X(df_feat), df_feat["y"].values, "squared_error")

        # Band-Kalibrierung: Residuen eines fit-Teil-Modells auf hinterem Kalibrier-Slice
        fit_part, cal_part = _calib_split(df_feat)
        if cal_part is not None and len(cal_part) >= 20:
            pfit = _fit(make_X(fit_part), fit_part["y"].values, "squared_error")
            resid = cal_part["y"].values - pfit.predict(make_X(cal_part))
            self.dlo_global, self.dhi_global = self._resid_quantiles(resid)
            for p in PHASES:
                r = resid[cal_part["phase"].values == p]
                if len(r) >= 10:
                    self.dlo_phase[p], self.dhi_phase[p] = self._resid_quantiles(r)
                else:  # duenne Phase (Nacht) -> globaler Fallback
                    self.dlo_phase[p], self.dhi_phase[p] = self.dlo_global, self.dhi_global
        else:  # zu wenig Daten fuer Kalibrierung -> grobes symmetrisches Notband
            self.dlo_global, self.dhi_global = -12.0, 12.0
            for p in PHASES:
                self.dlo_phase[p], self.dhi_phase[p] = -12.0, 12.0
        return self

    def predict(self, Xframe: pd.DataFrame):
        """Xframe = build_predict_frame(...) ODER add_target_features-Output.
        Gibt (point, lo, hi) zurueck, sortiert lo<=point<=hi und auf [0,100] geclippt."""
        point = self.point.predict(make_X(Xframe))
        if self.band_method == "resid_global":
            dlo = np.full(len(point), self.dlo_global)
            dhi = np.full(len(point), self.dhi_global)
        else:  # resid_phase
            ph = Xframe["_phase"].values if "_phase" in Xframe else Xframe["phase"].values
            dlo = np.array([self.dlo_phase.get(p, self.dlo_global) for p in ph])
            dhi = np.array([self.dhi_phase.get(p, self.dhi_global) for p in ph])
        point = np.clip(point, 0, 100)
        lo = np.clip(np.minimum(point + dlo, point), 0, 100)
        hi = np.clip(np.maximum(point + dhi, point), 0, 100)
        return point, lo, hi


# ---- Referenz-Baseline (Guardrail): lookup(studio, dow, hour) ----
class LookupBaseline:
    def fit(self, df_feat):
        d = df_feat.copy()
        d["hour"] = (d["minutes"] // 60).astype(int)
        self.tab = d.groupby(["Studio", "dow_num", "hour"], observed=True)["y"].mean()
        self.tab_sd = d.groupby(["Studio", "dow_num"], observed=True)["y"].mean()
        self.gm = d["y"].mean()
        return self

    def predict_rows(self, studios, dows, hours):
        out = []
        for s, dw, h in zip(studios, dows, hours):
            if (s, dw, h) in self.tab.index:
                out.append(self.tab.loc[(s, dw, h)])
            elif (s, dw) in self.tab_sd.index:
                out.append(self.tab_sd.loc[(s, dw)])
            else:
                out.append(self.gm)
        return np.array(out)


def load_training_frame(csv_path="data/gym_utilization.csv"):
    from features import load_raw
    return add_target_features(load_raw(csv_path))
