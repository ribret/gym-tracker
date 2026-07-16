# forecast/ — Auslastungsprognose für alle 7 JOHN-REED-Berlin-Studios

Prognostiziert die Auslastung (`Auslastung_%`) im Tagesverlauf je Studio, konditioniert
auf Kalender + Wetter, inkl. 80%-Unsicherheitsband. Die Modellwahl wurde in einem
adversarial verifizierten Auswahl-Lauf getroffen (Recherche + empirisches Bake-off von 6
Modellfamilien + Skeptiker-Prüfung), nicht aus dem Bauch.

## Ergebnis der Modellauswahl

Gewinner: **HistGradientBoostingRegressor, ein global gepooltes Modell** (`studio` + `dow`
als native Kategorien). Datengetrieben, nicht aus Prinzip:

| Modell | MAE (pooled) | Peak-MAE 10–21 Uhr |
|---|---|---|
| **HGB full-pooling** ← Wahl | **5,67** | **8,28** |
| RandomForest | 5,80 | 8,52 |
| Smart-Lookup++ | 6,26 | 8,85 |
| Ridge/Fourier | 7,25 | 9,19 |
| Lookup-Baseline (Referenz) | 8,49 | 12,57 |

Backtest: rolling-origin über 30 Kalendertage (`backtest.py`), 28/30 Gewinn-Tage vs.
Lookup, +2,90 MAE (SE 0,43). Kein Leakage (Punktmodell auf `date<d`, Test auf `date==d`).

### Warum diese Wahl
- **Pooling ist der Haupthebel** gegen die kleine Datenmenge (~51 Tage, 7–8 pro Wochentag):
  full-pooling 6,04 schlägt 7 Einzelmodelle (6,89) und z-Norm-Pooling (6,75). Ein Baum lernt
  Niveau *und* Kurvenform je Studio aus `studio_code`-Splits.
- RandomForest ist statistisch **nicht** besser (Δ0,13 MAE < SE 0,40). HGB gewinnt den
  Tie-Break über native Bänder, native NaN-Behandlung und sklearn-only-Deployment.
- Der **Peak (~8,3 MAE) ist der harte, weitgehend irreduzible Kern** (1 Berlin-Wetterpunkt ×
  51 Tage). Die niedrige Gesamt-MAE kommt großteils aus den trivial lernbaren Nacht-Nullen —
  darum wird Peak-MAE immer separat berichtet.

### Bewusst verworfen (kein Out-of-Sample-Lift)
Voller Wetterblock (Wind, Bewölkung, WMO-Codes, temp²) — 0 Lift; nur `Temperatur_C`
(monotone Nebenbedingung: Hitze dämpft) + `is_hot` + `is_rain` bleiben. Fourier-Terme
(Bäume splitten `tod` selbst), Trend `days_since_start` (Bäume extrapolieren nicht),
Ein-Tages-Feiertag (Overfit-Magnet), externe Feeds (Ausfallfläche > Signal).

### Unsicherheitsbänder
**Nicht** über HGB-Quantilregression (kollabiert am unteren Rand bei diesen null-lastigen
Daten auf 0). Stattdessen **signierte Residuen-Quantile, stratifiziert nach Tagesphase**
(nachts eng, Peak breit), kalibriert auf einem zeitlich hinteren Held-out-Slice.
Gemessene Coverage: **78,6 % @ nominal 80 %, mittlere Breite 16,8 pp** (empirisch validiert,
nicht aus Theorie übernommen).

## Dateien
| Datei | Zweck |
|---|---|
| `features.py` | Feature-Aufbau, Loader, rolling-origin-Splitter (self-contained) |
| `model.py` | `ForecastModel` (Punkt + Bänder), `LookupBaseline` (Guardrail) |
| `backtest.py` | ehrlicher rolling-origin-Backtest: MAE, Peak-MAE, Coverage, Gewinnrate |
| `predict_day.py` | CLI: Tagesprognose je Studio mit Wetter-Abruf + Chart |
| `build_site.py` | baut die statische Prognose-Seite (GitHub Pages) aus `site_template.html` |
| `site_template.html` | selbst-enthaltenes Seiten-Template (SVG-Chart clientseitig, Daten als JSON) |

## Nutzung
```bash
cd gym-tracker
# Prognose heute, ein Studio (Tabelle + optional Chart)
OMP_NUM_THREADS=1 python3 forecast/predict_day.py --studio charlottenburg
# alle Studios, bestimmter Tag, mit PNG
python3 forecast/predict_day.py --studio all --date 2026-07-07 --out /tmp/prognose.png
# Modell erneut validieren (nach neuen Daten)
OMP_NUM_THREADS=1 python3 forecast/backtest.py
```
Deps: `forecast/requirements.txt` (pandas, numpy, scikit-learn; matplotlib nur für Chart).
Das Modell trainiert bei jedem Lauf frisch auf dem gesamten CSV (Fit < 1 s), kein Artefakt nötig.

## Prognose-Seite (GitHub Pages)

`.github/workflows/forecast-site.yml` baut mit `build_site.py` eine statische Seite
(Heute + Morgen, alle 7 Studios, 80%-Band, Ist-Messungen des Tages als Punkte) und
deployt sie auf GitHub Pages — 3× täglich per Cron und auf Knopfdruck über
Actions → „Forecast Site" → „Run workflow". Da das Modell je Build frisch auf allen
Daten trainiert, verbessert sich die Seite automatisch mit jedem Datentag.

```bash
# lokal bauen und ansehen
OMP_NUM_THREADS=1 python3 forecast/build_site.py --out-dir _site
python3 -m http.server -d _site 8000
```

Veröffentlicht wird per Force-Push auf den `gh-pages`-Branch (Pages-Quelle; wurde durch
das Anlegen des Branches automatisch aktiviert). Der API-Weg über `actions/deploy-pages`
scheitert an den Token-Rechten — Begründung im Workflow-Kommentar.

## Ehrliche Grenzen
- **Wetter generalisiert kaum** (1 Punkt × 51 Tage). "Hitze dämpft" ist in-sample real,
  one-day-ahead im Baum kaum nutzbar. Peak-MAE ~8,3 ist die Decke ohne mehr Tage oder
  studiospezifisches Wetter.
- **MAE < 5,5 wäre verdächtig, < 5,0 fast sicher Leakage.** Wer die Zahl "verbessert",
  zuerst auf Leakage prüfen.
- **Schulferien inert bis ~09.07.2026** (all-0 im Training) — Ferien-Regime lernt das Modell
  erst nach mehreren Retrain-Zyklen ab Mitte Juli.
- **Kein Extrapolieren** über gesehene Temperatur-/Datumsbereiche (piecewise-constant).
- Bei deutlich mehr Daten HP (`max_leaf_nodes`, `min_samples_leaf`) periodisch im nested
  rolling-origin nachprüfen, nicht einfrieren.
