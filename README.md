# JOHN REED Gym Utilization Tracker

Zeichnet alle 15 Minuten die aktuelle Auslastung des JOHN REED Berlin Charlottenburg auf und speichert sie als CSV.

## Setup (einmalig, ~5 Minuten)

### 1. GitHub Repo anlegen

1. github.com → **New repository**
2. Name: `gym-tracker`
3. Visibility: **Public**
4. Ohne README/gitignore erstellen

### 2. Code hochladen

```bash
cd /Users/richard/Documents/Claude/gym-tracker
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/ribret/gym-tracker.git
git push -u origin main
```

### 3. GitHub Secrets eintragen

GitHub → Repository → **Settings → Secrets and variables → Actions → New repository secret**

| Secret-Name | Wert |
|-------------|------|
| `FIREBASE_API_KEY` | `AIzaSyDPv-q00DmSUpYqFqY43tN03ZezHNJY_eg` |
| `FIREBASE_REFRESH_TOKEN` | den langen Token aus Proxyman (Request-Body) |

### 4. GitHub Actions aktivieren

GitHub → Repository → **Actions → "I understand my workflows, go ahead and enable them"**

Danach läuft der erste Job innerhalb von 15 Minuten automatisch.

## Daten

Die Auslastungsdaten landen in `data/gym_utilization.csv`:

```
Datum;Uhrzeit;Wochentag;Stunde;Auslastung_%
2026-05-16;11:30;Friday;11;50
2026-05-16;11:45;Friday;11;48
...
```

**Download**: Direkt im GitHub-Repo unter `data/gym_utilization.csv` → Raw → in Excel öffnen.

## Token-Ablauf

Der Firebase Refresh Token ist langlebig (Monate bis Jahre) und läuft nur ab, wenn:
- du dich in der One-Member-App abmeldest
- du dein Passwort änderst

Falls der Tracker irgendwann mit Fehler 401 abbricht: Proxyman-Prozedur wiederholen und neuen Refresh Token als Secret eintragen.
