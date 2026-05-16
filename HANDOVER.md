# Handover — gym-tracker

**Zweck:** Eine neue Claude-Session soll dieses Projekt verstehen, ohne dass Richard von vorne erklären muss.

---

## Worum es geht

Richard sammelt seit Mai 2026 die Auslastung aller 7 JOHN REED Berlin Studios im 30-Minuten-Takt — mit dem Ziel, später Prognosen treffen zu können („wie voll wird's am Donnerstag um 18 Uhr bei Sonne?").

Die App des Fitnessstudios (One Member, RSG Group) zeigt die Live-Auslastung nur im iPhone an. Ein Web-Endpoint existiert offiziell nicht. Wir haben den App-Endpoint per Proxyman-MITM identifiziert und automatisieren ihn jetzt.

---

## Architektur in 30 Sekunden

```
GitHub Actions (cron alle 30 min)
  │
  ├── Firebase Refresh Token (GitHub Secret)
  │      ↓ POST securetoken.googleapis.com
  │   ID Token (1h gültig)
  │
  ├── GET Open-Meteo → Wetter (Temp, Regen, Bewölkung, Wind) — einmal pro Run
  ├── GET feiertage-api.de → Berlin-Feiertage
  ├── GET ferien-api.de → Berlin-Schulferien
  │
  └── 7× GET /gyms/johnreed/gym/{ID}/utilization (alle Berliner Studios)
      → je eine neue Zeile in data/gym_utilization.csv
  
  ↓ Auto-Commit zurück ins Repo
```

---

## Live-Links

- **Repo:** https://github.com/ribret/gym-tracker (public)
- **Daten:** https://github.com/ribret/gym-tracker/tree/main/data
- **Actions-Log:** https://github.com/ribret/gym-tracker/actions

---

## Files

| Datei | Zweck |
|-------|-------|
| `gym_tracker.py` | Kernskript — Token-Refresh, Datenabruf für alle 7 Studios, CSV-Schreiben |
| `.github/workflows/collect.yml` | Cron-Definition (alle 30 Min) + Commit-Logik |
| `requirements.txt` | nur `requests` |
| `pyproject.toml` | Projekt-Metadaten für lokale Entwicklung |
| `data/gym_utilization.csv` | alle Studios in einer Datei, wächst pro Run um 7 Zeilen |
| `README.md` | Setup-Anleitung |

---

## Datenmodell (CSV)

Trennzeichen: `;` (für deutsches Excel). 15 Spalten:

```
Studio;Datum;Uhrzeit;Wochentag;Stunde;Tagesphase;Auslastung_%;
Temperatur_C;Niederschlag_mm;Wettercode;Bewoelkung_%;Wind_kmh;
Ist_Wochenende;Ist_Feiertag_BE;Ist_Schulferien_BE
```

- **Studio** = Schlüssel des Studios (z.B. `charlottenburg`, `kreuzberg`, …)
- **Wettercode** = WMO-Standard (0=klar, 3=bedeckt, 51-67=Regen, 71-77=Schnee, 95+=Gewitter)
- **Tagesphase** = Morgen (5-11), Mittag (12-16), Abend (17-22), Nacht (23-4)
- Wetter wird einmal pro Run für alle Studios geteilt (Berlin Mitte, 52.52/13.40)
- Historische Zeilen (vor Phase 1) haben leere Wetter-Spalten; Studio=charlottenburg

**Studio-Schlüssel → Firebase-ID:**

| Studio-Schlüssel | Firebase-ID |
|-----------------|-------------|
| `charlottenburg` | `mL6O8ISwlk5tQt7mnwjo` |
| `kreuzberg` | `EbbAsfOAYjJK7frGwSQc` |
| `prenzlauer_berg` | `QDsORQIS4OlDuDDs9BMD` |
| `boetzow` | `0B2lUvpIWFeuHJOIOXFi` |
| `friedrichshain` | `rUN5RetcHHWRWEl978s7` |
| `womens_club` | `K2cAluM4mcXVbfSDPPdB` |
| `gesundbrunnen` | `zChJkIuvStyOUunjqMW1` |

---

## Secrets (in GitHub: Settings → Secrets → Actions)

| Secret | Wert | Quelle |
|--------|------|--------|
| `FIREBASE_API_KEY` | `AIzaSy...` (im GitHub Secret hinterlegt) | Öffentlich (in App-Bundle eingebettet) |
| `FIREBASE_REFRESH_TOKEN` | langer String, beginnt mit `AMf-vBx0ma...` | Aus Proxyman — siehe Recovery |

Der Refresh Token läuft erst ab, wenn Richard sich in der App abmeldet oder das Passwort ändert.

---

## Recovery — wenn Workflow plötzlich Status 401 zeigt

Token ist abgelaufen. Schritte:

1. iPhone in WLAN, Proxy auf Mac (192.168.x.x:9090), Proxyman CA installiert (Anleitung in Proxyman → Certificate → Install on iOS)
2. Proxyman starten, SSL Proxying für `securetoken.googleapis.com` aktivieren
3. One-Member-App **komplett schließen und neu öffnen** (App Switcher → wegwischen)
4. In Proxyman den POST-Request zu `/v1/token?key=...` öffnen
5. Im Request-Body steht `"refreshToken": "..."` → kopieren
6. In GitHub → Repo → Settings → Secrets → `FIREBASE_REFRESH_TOKEN` → Update value
7. Workflow manuell triggern → muss durchlaufen

---

## Bekannte Stolperfallen

- **GitHub-CLI OAuth-Token** hat oft keinen `workflow`-Scope. Push von Änderungen an `.github/workflows/*` schlägt dann fehl mit „refusing to allow an OAuth App…". Fix: einmalig die Remote-URL mit Personal Access Token (Scopes: `repo` + `workflow`) setzen:
  ```bash
  git remote set-url origin https://ribret:TOKEN@github.com/ribret/gym-tracker.git
  git push
  git remote set-url origin https://github.com/ribret/gym-tracker.git
  ```
- **Workflow-Push-Konflikt**: Der Bot committed regelmäßig die CSV. Vor lokalem Push immer `git pull --rebase`. Der Workflow selbst macht das jetzt auch vor seinem Push.
- **Zeitzone**: GitHub-Runner laufen UTC. Skript nutzt explizit `ZoneInfo("Europe/Berlin")` — sonst werden falsche Stunden aus der `utilization`-Map gelesen.
- **GitHub CSV-Preview-Warnung**: „No commas found" ist nur ein Hinweis, kein Fehler. `;`-Delimiter ist Absicht (deutsches Excel).

---

## Status & nächste Schritte

**Phase 1 (abgeschlossen, 16.05.2026):**
- ✓ Endpoint identifiziert: `GET /gyms/johnreed/gym/{ID}/utilization`
- ✓ Firebase Auth-Flow automatisiert
- ✓ GitHub Actions Cron läuft alle 15 Min
- ✓ Wetter (Open-Meteo), Berlin-Feiertage, Berlin-Schulferien
- ✓ Migration der Bestandsdaten auf neues Schema
- ✓ Alle 7 Berliner Studios per Proxyman + Validation-Script identifiziert
- ✓ Multi-Studio-Tracking: 7 Studios parallel, gemeinsame CSV, 30-Min-Takt

**Was jetzt passiert:**
Mindestens 3 Wochen Daten sammeln lassen — vorher wenig Aussagekraft. Bandbreite an Wetterlagen + ein paar Wochenenden + Werktag-Variation nötig.

**Phase 2 — Backlog (Entscheidung nach 3 Wochen Daten):**
- Hertha BSC Heimspiele (falls Auslastung erkennbar beeinflusst)
- Manuelle Annotation lokaler Großereignisse (Theater des Westens, Deutsche Oper)
- Vorhersagemodell (Gradient Boosting) für Stunde × Wochentag × Wetter
- Heatmap-Auswertung als erstes deskriptives Artefakt

**Methodischer Hinweis von Phase-1-Abschluss:**
Vor Phase 2 zuerst prüfen, ob es überhaupt unerklärte Spitzen gibt, die nicht durch Zeit + Wetter + Feiertage erklärbar sind. Sonst optimiert man auf Faktoren, die wahrscheinlich <5% Varianz erklären.

---

## Tech-Stack-Entscheidungen, die nicht offensichtlich sind

- **GitHub Actions statt VPS**: kostenlos für Public Repos (unbegrenzte Actions-Minuten), keine Server-Wartung
- **Refresh Token statt Email/Passwort**: kein Passwort im System, Token kann jederzeit revoked werden
- **Open-Meteo statt OpenWeatherMap**: kostenlos, kein API-Key, deutsche DWD-Daten
- **CSV statt SQLite/Parquet**: Git diff'bar, direkt in Excel öffenbar, kein zusätzliches Tooling
- **Public Repo**: Auslastungsdaten sind nicht sensibel, Secrets sind in GitHub Secrets (auch in Public Repos unsichtbar)
