#!/usr/bin/env python3
"""
JOHN REED Berlin Charlottenburg — Auslastungs-Tracker
Holt alle 15 Minuten die aktuelle Auslastung und schreibt sie in data/gym_utilization.csv
"""

import os
import csv
import requests
from datetime import datetime
from pathlib import Path

# ── Konfiguration (via Umgebungsvariablen / GitHub Secrets) ─────────────────

FIREBASE_API_KEY   = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

GYM_ID   = "mL6O8ISwlk5tQt7mnwjo"
BRAND_ID = "johnreed"
ENDPOINT = f"https://app-api.rsg.mamba-app.one-member.com/gyms/{BRAND_ID}/gym/{GYM_ID}/utilization"

CSV_FILE = Path(__file__).parent / "data" / "gym_utilization.csv"

# ── Firebase: frischen ID-Token holen ───────────────────────────────────────

def get_id_token() -> str:
    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    resp = requests.post(url, json={
        "grantType": "refresh_token",
        "refreshToken": FIREBASE_REFRESH_TOKEN,
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()["id_token"]

# ── Auslastung abrufen ───────────────────────────────────────────────────────

def fetch_utilization(id_token: str) -> int:
    headers = {
        "Authorization":          f"Bearer {id_token}",
        "X-HERO-APP-PLATFORM":    "iPhone",
        "X-HERO-BRAND-ID":        BRAND_ID,
        "X-HERO-APP-IDENTIFIER":  "com.heroworkout.mamba.johnreed",
        "X-HERO-APP-VERSION":     "1.20.0",
        "X-HERO-API-VERSION":     "v1",
        "Accept":                 "application/json",
        "Accept-Charset":         "UTF-8",
        "Accept-Language":        "de-DE,de;q=0.9",
        "Content-Type":           "application/json",
        "User-Agent":             "ktor-client",
    }
    resp = requests.get(ENDPOINT, headers=headers, timeout=10)
    resp.raise_for_status()
    utilization = resp.json()["data"]["utilization"]
    current_hour = str(datetime.now().hour)
    return int(utilization.get(current_hour, 0))

# ── In CSV speichern ─────────────────────────────────────────────────────────

def save(value: int):
    now = datetime.now()
    is_new = not CSV_FILE.exists()
    CSV_FILE.parent.mkdir(exist_ok=True)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if is_new:
            w.writerow(["Datum", "Uhrzeit", "Wochentag", "Stunde", "Auslastung_%"])
        w.writerow([
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M"),
            now.strftime("%A"),
            now.hour,
            value,
        ])
    print(f"[{now.strftime('%Y-%m-%d %H:%M')}]  Auslastung: {value}%")

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    id_token = get_id_token()
    value = fetch_utilization(id_token)
    save(value)
