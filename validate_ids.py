#!/usr/bin/env python3
"""
Validiert die 7 Firebase-IDs gegen die RSG-API und gibt Name + Adresse aus.
"""

import os, requests

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID = "johnreed"
BASE     = "https://app-api.rsg.mamba-app.one-member.com"

CANDIDATE_IDS = [
    "mL6O8ISwlk5tQt7mnwjo",  # bekannt: Charlottenburg
    "EbbAsfOAYjJK7frGwSQc",
    "QDsORQIS4OlDuDDs9BMD",
    "0B2lUvpIWFeuHJOIOXFi",
    "rUN5RetcHHWRWEl978s7",
    "K2cAluM4mcXVbfSDPPdB",
    "zChJkIuvStyOUunjqMW1",
]

HEADERS = {
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

def get_id_token():
    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        json={"grantType": "refresh_token", "refreshToken": FIREBASE_REFRESH_TOKEN},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id_token"]

def fetch_gym_info(id_token, gym_id):
    url = f"{BASE}/gyms/{BRAND_ID}/gym/{gym_id}"
    headers = {**HEADERS, "Authorization": f"Bearer {id_token}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"  {r.status_code}  {gym_id}  → ", end="")
        if r.status_code == 200:
            d = r.json().get("data", {})
            name    = d.get("name", "?")
            city    = d.get("city", "?")
            street  = d.get("street", "?")
            util_ep = f"/gyms/{BRAND_ID}/gym/{gym_id}/utilization"
            print(f"{name}  |  {street}, {city}  |  ✓ util: {util_ep}")
            return {"id": gym_id, "name": name, "city": city, "street": street}
        else:
            print(r.text[:200])
            return None
    except Exception as e:
        print(f"ERR: {e}")
        return None

def main():
    print("=== Firebase Token ===")
    token = get_id_token()
    print("OK\n")

    print("=== Gym-Info je ID ===")
    results = []
    for gid in CANDIDATE_IDS:
        info = fetch_gym_info(token, gid)
        if info:
            results.append(info)

    print("\n=== Ergebnis-Mapping ===")
    for r in results:
        print(f"  \"{r['name']}\"  →  \"{r['id']}\"")

    print("\n=== Python-Dict für gym_tracker.py ===")
    print("GYMS = {")
    for r in results:
        key = r['name'].lower().replace(" ", "-").replace("ü","ue").replace("ö","oe").replace("ä","ae")
        print(f'    "{key}": {{')
        print(f'        "id":   "{r["id"]}",')
        print(f'        "name": "{r["name"]}",')
        print(f'    }},')
    print("}")

if __name__ == "__main__":
    main()
