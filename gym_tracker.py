#!/usr/bin/env python3
"""
JOHN REED Berlin — Auslastungs-Tracker für alle 7 Studios mit Wetter & Kalenderkontext
"""

import os
import csv
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

BERLIN = ZoneInfo("Europe/Berlin")

# ── Konfiguration ────────────────────────────────────────────────────────────

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID = "johnreed"
BASE_URL = "https://app-api.rsg.mamba-app.one-member.com"

GYM_LAT = 52.52   # Berlin Mitte — einheitlich für alle 7 Studios
GYM_LON = 13.40

DATA_DIR = Path(__file__).parent / "data"

GYMS = {
    "charlottenburg": {
        "id":   "mL6O8ISwlk5tQt7mnwjo",
        "name": "JOHN REED Berlin Charlottenburg",
    },
    "kreuzberg": {
        "id":   "EbbAsfOAYjJK7frGwSQc",
        "name": "JOHN REED Berlin Kreuzberg",
    },
    "prenzlauer_berg": {
        "id":   "QDsORQIS4OlDuDDs9BMD",
        "name": "JOHN REED Berlin Prenzlauer Berg",
    },
    "boetzow": {
        "id":   "0B2lUvpIWFeuHJOIOXFi",
        "name": "JOHN REED Berlin-Bötzow",
    },
    "friedrichshain": {
        "id":   "rUN5RetcHHWRWEl978s7",
        "name": "JOHN REED Berlin-Friedrichshain",
    },
    "womens_club": {
        "id":   "K2cAluM4mcXVbfSDPPdB",
        "name": "JOHN REED Women's Club",
    },
    "gesundbrunnen": {
        "id":   "zChJkIuvStyOUunjqMW1",
        "name": "JOHN REED Berlin Gesundbrunnen",
    },
}

COLUMNS = [
    "Datum", "Uhrzeit", "Wochentag", "Stunde", "Tagesphase",
    "Auslastung_%",
    "Temperatur_C", "Niederschlag_mm", "Wettercode", "Bewoelkung_%", "Wind_kmh",
    "Ist_Wochenende", "Ist_Feiertag_BE", "Ist_Schulferien_BE",
]

WOCHENTAGE_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WOCHENTAGE_EN_TO_DE = {
    "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag", "Friday": "Freitag",
    "Saturday": "Samstag", "Sunday": "Sonntag",
}

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def tagesphase(hour: int) -> str:
    if 5 <= hour <= 11:  return "Morgen"
    if 12 <= hour <= 16: return "Mittag"
    if 17 <= hour <= 22: return "Abend"
    return "Nacht"

def csv_path(key: str) -> Path:
    return DATA_DIR / f"{key}.csv"

# ── Firebase: frischen ID-Token holen ───────────────────────────────────────

def get_id_token() -> str:
    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    resp = requests.post(url, json={
        "grantType": "refresh_token",
        "refreshToken": FIREBASE_REFRESH_TOKEN,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["id_token"]

# ── Datenquellen ─────────────────────────────────────────────────────────────

def _api_headers(id_token: str) -> dict:
    return {
        "Authorization":         f"Bearer {id_token}",
        "X-HERO-APP-PLATFORM":   "iPhone",
        "X-HERO-BRAND-ID":       BRAND_ID,
        "X-HERO-APP-IDENTIFIER": "com.heroworkout.mamba.johnreed",
        "X-HERO-APP-VERSION":    "1.20.0",
        "X-HERO-API-VERSION":    "v1",
        "Accept":                "application/json",
        "Accept-Charset":        "UTF-8",
        "Accept-Language":       "de-DE,de;q=0.9",
        "Content-Type":          "application/json",
        "User-Agent":            "ktor-client",
    }

def fetch_utilization(id_token: str, gym_id: str) -> int:
    url = f"{BASE_URL}/gyms/{BRAND_ID}/gym/{gym_id}/utilization"
    resp = requests.get(url, headers=_api_headers(id_token), timeout=10)
    resp.raise_for_status()
    utilization = resp.json()["data"]["utilization"]
    current_hour = str(datetime.now(BERLIN).hour)
    return int(utilization.get(current_hour, 0))

def fetch_weather() -> dict:
    """Open-Meteo (kostenlos, kein API-Key, DWD-Daten)"""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={GYM_LAT}&longitude={GYM_LON}"
            "&current=temperature_2m,precipitation,weather_code,cloud_cover,wind_speed_10m"
            "&timezone=Europe%2FBerlin"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        c = resp.json()["current"]
        return {
            "Temperatur_C":    c.get("temperature_2m"),
            "Niederschlag_mm": c.get("precipitation"),
            "Wettercode":      c.get("weather_code"),
            "Bewoelkung_%":    c.get("cloud_cover"),
            "Wind_kmh":        c.get("wind_speed_10m"),
        }
    except Exception as e:
        print(f"⚠️  Wetter-Abruf fehlgeschlagen: {e}")
        return {k: None for k in ["Temperatur_C", "Niederschlag_mm", "Wettercode", "Bewoelkung_%", "Wind_kmh"]}

_holiday_cache: dict = {}

def fetch_holidays(year: int) -> set:
    """Gesetzliche Feiertage Berlin (Bund + Land)"""
    if year in _holiday_cache:
        return _holiday_cache[year]
    try:
        resp = requests.get(f"https://feiertage-api.de/api/?jahr={year}&nur_land=BE", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        dates = {datetime.strptime(v["datum"], "%Y-%m-%d").date() for v in data.values()}
        _holiday_cache[year] = dates
        return dates
    except Exception as e:
        print(f"⚠️  Feiertage-Abruf fehlgeschlagen: {e}")
        return set()

_ferien_cache: dict = {}

def fetch_school_holidays(year: int) -> list:
    """Berliner Schulferien"""
    if year in _ferien_cache:
        return _ferien_cache[year]
    try:
        resp = requests.get(f"https://ferien-api.de/api/v1/holidays/BE/{year}", timeout=10)
        resp.raise_for_status()
        periods = []
        for h in resp.json():
            start = datetime.fromisoformat(h["start"].replace("Z", "+00:00")).date()
            end   = datetime.fromisoformat(h["end"].replace("Z", "+00:00")).date()
            periods.append((start, end))
        _ferien_cache[year] = periods
        return periods
    except Exception as e:
        print(f"⚠️  Schulferien-Abruf fehlgeschlagen: {e}")
        return []

def is_school_holiday(d, periods) -> bool:
    return any(start <= d <= end for start, end in periods)

# ── Migration: gym_utilization.csv → charlottenburg.csv (einmalig) ───────────

def migrate_old_filename():
    old = DATA_DIR / "gym_utilization.csv"
    new = csv_path("charlottenburg")
    if old.exists() and not new.exists():
        old.rename(new)
        print("Migriert: gym_utilization.csv → charlottenburg.csv")

# ── Migration: altes Schema (5 Spalten) → neues Schema (14 Spalten) ──────────

def migrate_schema_if_needed(key: str):
    path = csv_path(key)
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
    header = first_line.split(";")
    if header == COLUMNS:
        return

    if header[:5] != ["Datum", "Uhrzeit", "Wochentag", "Stunde", "Auslastung_%"]:
        return  # unbekanntes Format, nicht anfassen

    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f, delimiter=";"))

    years = set()
    for row in rows[1:]:
        try: years.add(int(row[0][:4]))
        except: pass
    holidays_by_year = {y: fetch_holidays(y) for y in years}
    ferien_by_year   = {y: fetch_school_holidays(y) for y in years}

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUMNS)
        for row in rows[1:]:
            d_str, t, wt, hour_str, util = row
            wt_de = WOCHENTAGE_EN_TO_DE.get(wt, wt)
            try:
                d = datetime.strptime(d_str, "%Y-%m-%d").date()
                h = int(hour_str)
                phase = tagesphase(h)
                is_we = int(d.weekday() >= 5)
                is_ft = int(d in holidays_by_year.get(d.year, set()))
                is_sf = int(is_school_holiday(d, ferien_by_year.get(d.year, [])))
            except Exception:
                phase, is_we, is_ft, is_sf = "", "", "", ""
            w.writerow([
                d_str, t, wt_de, hour_str, phase, util,
                "", "", "", "", "",  # historisches Wetter nicht rekonstruierbar
                is_we, is_ft, is_sf,
            ])
    print(f"Schema migriert: {path.name}")

# ── In CSV speichern ─────────────────────────────────────────────────────────

def save(key: str, value: int, weather: dict, holidays: set, ferien: list):
    now = datetime.now(BERLIN)
    today = now.date()
    path = csv_path(key)
    is_new = not path.exists()
    DATA_DIR.mkdir(exist_ok=True)

    row = {
        "Datum":              now.strftime("%Y-%m-%d"),
        "Uhrzeit":            now.strftime("%H:%M"),
        "Wochentag":          WOCHENTAGE_DE[now.weekday()],
        "Stunde":             now.hour,
        "Tagesphase":         tagesphase(now.hour),
        "Auslastung_%":       value,
        "Temperatur_C":       weather["Temperatur_C"],
        "Niederschlag_mm":    weather["Niederschlag_mm"],
        "Wettercode":         weather["Wettercode"],
        "Bewoelkung_%":       weather["Bewoelkung_%"],
        "Wind_kmh":           weather["Wind_kmh"],
        "Ist_Wochenende":     int(now.weekday() >= 5),
        "Ist_Feiertag_BE":    int(today in holidays),
        "Ist_Schulferien_BE": int(is_school_holiday(today, ferien)),
    }

    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if is_new:
            w.writerow(COLUMNS)
        w.writerow([row[c] for c in COLUMNS])

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    migrate_old_filename()
    for key in GYMS:
        migrate_schema_if_needed(key)

    id_token = get_id_token()
    weather  = fetch_weather()
    now      = datetime.now(BERLIN)
    holidays = fetch_holidays(now.year)
    ferien   = fetch_school_holidays(now.year)

    print(f"\n[{now.strftime('%Y-%m-%d %H:%M')}]  {weather['Temperatur_C']}°C, "
          f"{weather['Niederschlag_mm']}mm, WMO {weather['Wettercode']}\n")

    for key, gym in GYMS.items():
        try:
            value = fetch_utilization(id_token, gym["id"])
            save(key, value, weather, holidays, ferien)
            print(f"  {gym['name']:<40}  {value:3d}%")
        except Exception as e:
            print(f"  ⚠️  {gym['name']}: {e}")
