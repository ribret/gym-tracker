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
Feiertag als gelerntes Feature (nur ~2 Feiertage im Datensatz, nicht lernbar), externe Feeds
(Ausfallfläche > Signal).

### Feiertage: Domänen-Prior statt Feature
Berliner Feiertage (openHolidays API) werden in Training **und** Prognose wie ein **Sonntag**
behandelt (`features.effective_dow`). Das Sonntagsprofil kennt das Modell aus rund 20 Tagen,
ein eigener Feiertagseffekt wäre aus 2 Beispielen nicht schätzbar. Test vom 03.10.2026:
Pfingstmontag MAE 12,6 als Montag gegenüber 7,7 als Sonntag; Feiertag am Samstag neutral
(6,7 zu 6,5). Evidenz n = 2, Richtung deckt sich mit dem Standardvorgehen der Lastprognose.

### Live-Nowcast (seit 04.10.2026)
Sonderereignisse (Marathon, verkaufsoffene Sonntage) sind mit 1 bis 4 Beispielen je Typ nicht
lernbar; Marathon-Wochenende 26./27.09. lag in Charlottenburg 8 bis 9 Punkte unter Prognose,
ein normales Wochenende (29.08.) aber ebenso. Statt Ereigniskalender korrigiert die Seite die
Prognose deshalb **live**: mittlere Abweichung der Messungen der letzten 60 Min wird voll
uebernommen und klingt mit exp(-dt/120 Min) ab. Backtest (Parameter auf der ersten Haelfte
gewaehlt, geprueft auf 61 spaeteren Tagen): Fehler naechste Stunde 8,4 -> 6,0, 1-3 h 8,2 -> 7,3,
ab 3 h kein Effekt; besser an 59/61 Tagen. Faengt jedes Ereignis ab, auch unbekannte.
Umsetzung: `gym_tracker.write_today_json` schreibt je Runde `data/today.json`, die Seite laedt
sie von raw.githubusercontent.com (max. 5 Min Cache) und rechnet im Browser (`nowcast()`).

### Nacht-Snapshot der Stundentabelle (seit 08.10.2026)
Die API liefert je Studio eine Tabelle aller Stunden des Tages: abgeschlossene Stunden als
Stundenmittel (Abgleich 04.10. Charlottenburg, 18 Stunden: MAE 0,7 zu den eigenen
20-Min-Messungen), laufende Stunde live, kuenftige 0. Reset kurz nach Mitternacht, je Studio
um Minuten versetzt (07.10. 00:03: 3 von 7 noch mit Vortag); der Vortag ist danach weg.
Die erste Messrunde zwischen 23:30 und 23:59 sichert deshalb alle 7 Studios, Stunden 0-22,
in `data/hourly_snapshot.csv` (Stunde 23 fehlt; betrifft praktisch nur Prenzlauer Berg, 24 h).
Noch **nicht** im Training: Stundenmittel sind glatter als Punktwerte, Einbindung erst nach
Backtest (z.B. als Punkt um HH:30 mit Quellenflag).

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
