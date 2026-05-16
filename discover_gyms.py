#!/usr/bin/env python3
"""
Discover John Reed Berlin gym IDs via RSG API.
Tries various listing endpoints, then brute-force-validates known Firebase-style IDs.
"""

import os
import json
import requests

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID = "johnreed"
BASE     = f"https://app-api.rsg.mamba-app.one-member.com"

KNOWN_ID = "mL6O8ISwlk5tQt7mnwjo"  # Charlottenburg

def get_id_token() -> str:
    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        json={"grantType": "refresh_token", "refreshToken": FIREBASE_REFRESH_TOKEN},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id_token"]

def headers(token: str) -> dict:
    return {
        "Authorization":         f"Bearer {token}",
        "X-HERO-APP-PLATFORM":   "iPhone",
        "X-HERO-BRAND-ID":       BRAND_ID,
        "X-HERO-APP-IDENTIFIER": "com.heroworkout.mamba.johnreed",
        "X-HERO-APP-VERSION":    "1.20.0",
        "X-HERO-API-VERSION":    "v1",
        "Accept":                "application/json",
        "Accept-Language":       "de-DE,de;q=0.9",
        "Content-Type":          "application/json",
        "User-Agent":            "ktor-client",
    }

def try_endpoint(token: str, path: str):
    url = BASE + path
    try:
        r = requests.get(url, headers=headers(token), timeout=10)
        print(f"  {r.status_code}  {url}")
        if r.status_code == 200:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:3000])
        return r
    except Exception as e:
        print(f"  ERR  {url}  → {e}")
        return None

def main():
    print("=== Firebase Token holen ===")
    token = get_id_token()
    print("OK\n")

    print("=== Listing-Endpoints testen ===")
    candidates = [
        f"/gyms/{BRAND_ID}/gyms",
        f"/gyms/{BRAND_ID}",
        f"/gyms/{BRAND_ID}/locations",
        f"/gyms/{BRAND_ID}/studios",
        f"/gyms/{BRAND_ID}/gym",
        f"/gyms/{BRAND_ID}/gym/list",
        f"/gyms/{BRAND_ID}/list",
        f"/brands/{BRAND_ID}/gyms",
        f"/brands/{BRAND_ID}/locations",
        f"/v1/gyms/{BRAND_ID}/gyms",
        f"/gyms",
    ]
    for path in candidates:
        r = try_endpoint(token, path)
        if r and r.status_code == 200:
            break  # Treffer gefunden, Rest überspringen
    print()

    print("=== Profil / Me — evtl. enthält Home-Gym-ID ===")
    for path in ["/user/me", "/user/profile", "/me", f"/gyms/{BRAND_ID}/user/me"]:
        r = try_endpoint(token, path)
        if r and r.status_code == 200:
            break
    print()

    print("=== Bekannte Gym-ID als Referenz validieren ===")
    try_endpoint(token, f"/gyms/{BRAND_ID}/gym/{KNOWN_ID}/utilization")
    print()

    print("=== Gym-Detail-Endpoint testen (enthält evtl. Nachbar-IDs) ===")
    for path in [
        f"/gyms/{BRAND_ID}/gym/{KNOWN_ID}",
        f"/gyms/{BRAND_ID}/gym/{KNOWN_ID}/info",
        f"/gyms/{BRAND_ID}/gym/{KNOWN_ID}/details",
        f"/gyms/{BRAND_ID}/gym/{KNOWN_ID}/nearby",
    ]:
        try_endpoint(token, path)

if __name__ == "__main__":
    main()
