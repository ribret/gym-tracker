#!/usr/bin/env python3
"""
JOHN REED Berlin Charlottenburg — Auslastungs-Tracker mit Wetter & Kalenderkontext
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

GYM_ID   = "mL6O8ISwlk5tQt7mnwjo"
BRAND_ID = "johnreed"
GYM_LAT  = 52.506   # Wilmersdorfer Str. 126-127, 10627 Berlin
GYM_LON  = 13.306

ENDPOINT = f"https://app-api.rsg.mamba-app.one-member.com/gyms/{BRAND_ID}/gym/{GYM_ID}/utilization"
CSV_FILE = Path(__file__).parent / "data" / "gym_utilization.csv"

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

def fetch_utilization(id_token: str) -> int:
    headers = {
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
    resp = requests.get(ENDPOINT, headers=headers, timeout=10)
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

_holiday_cache = {}

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

_ferien_cache = {}

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

# ── CSV-Migration: altes Schema → neues Schema ──────────────────────────────

def migrate_csv_if_needed():
    if not CSV_FILE.exists():
        return
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
    header = first_line.split(";")
    if header == COLUMNS:
        return  # bereits migriert

    if header[:5] == ["Datum", "Uhrzeit", "Wochentag", "Stunde", "Auslastung_%"]:
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))

        years = set()
        for row in rows[1:]:
            try: years.add(int(row[0][:4]))
            except: pass
        holidays_by_year = {y: fetch_holidays(y) for y in years}
        ferien_by_year   = {y: fetch_school_holidays(y) for y in years}

        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
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
        print("CSV auf neues Schema migriert.")

# ── In CSV speichern ─────────────────────────────────────────────────────────

def save(value: int, weather: dict, holidays: set, ferien: list):
    now = datetime.now(BERLIN)
    today = now.date()

    migrate_csv_if_needed()
    is_new = not CSV_FILE.exists()
    CSV_FILE.parent.mkdir(exist_ok=True)

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

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if is_new:
            w.writerow(COLUMNS)
        w.writerow([row[c] for c in COLUMNS])

    print(
        f"[{now.strftime('%Y-%m-%d %H:%M')}]  "
        f"Auslastung {value}%  |  "
        f"{weather['Temperatur_C']}°C, "
        f"{weather['Niederschlag_mm']}mm Regen, "
        f"Wettercode {weather['Wettercode']}  |  "
        f"FT={row['Ist_Feiertag_BE']} Ferien={row['Ist_Schulferien_BE']}"
    )

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    id_token = get_id_token()
    value    = fetch_utilization(id_token)
    weather  = fetch_weather()
    now      = datetime.now(BERLIN)
    holidays = fetch_holidays(now.year)
    ferien   = fetch_school_holidays(now.year)
    save(value, weather, holidays, ferien)
