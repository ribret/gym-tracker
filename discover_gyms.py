#!/usr/bin/env python3
"""
Discover John Reed Berlin gym IDs — v5.
KEY FINDING: Each club page contains mlStudioID (Magicline numeric ID).
Strategy: test if RSG API accepts mlStudioID as gym ID, or find mapping endpoint.

Known mlStudioIDs from __NEXT_DATA__:
  3818598990  → Charlottenburg (Firebase: mL6O8ISwlk5tQt7mnwjo)
  1404492860  → Prenzlauer Berg
  3946841990  → Friedrichshain
  1414215390  → Kreuzberg
  1414770410  → Gesundbrunnen
  ???         → Bötzow        (need to scrape)
  ???         → Women's Club  (need to scrape)
"""

import os, json, re, requests

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID  = "johnreed"
BASE      = "https://app-api.rsg.mamba-app.one-member.com"
KNOWN_FIREBASE_ID = "mL6O8ISwlk5tQt7mnwjo"

# Known from __NEXT_DATA__ scraping
STUDIOS = {
    "berlin-charlottenburg":   {"mlId": "3818598990", "firebase": KNOWN_FIREBASE_ID},
    "berlin-prenzlauer-berg":  {"mlId": "1404492860", "firebase": None},
    "berlin-friedrichshain":   {"mlId": "3946841990", "firebase": None},
    "berlin-kreuzberg":        {"mlId": "1414215390", "firebase": None},
    "berlin-gesundbrunnen":    {"mlId": "1414770410", "firebase": None},
    "berlin-boetzow":          {"mlId": None,          "firebase": None},
    "berlin-womens-prenzlauer-berg": {"mlId": None,    "firebase": None},
}

EXTRA_SLUGS = [
    "berlin-boetzow", "berlin-bötzow",
    "berlin-womens-prenzlauer-berg", "berlin-women-prenzlauer-berg",
    "berlin-prenzlauer-berg-women", "berlin-prenzlauer-berg-womens-club",
    "berlin-womens-club-prenzlauer-berg", "berlin-damen-prenzlauer-berg",
    "berlin-womens", "berlin-women",
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Accept": "text/html,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
}

def get_id_token():
    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        json={"grantType": "refresh_token", "refreshToken": FIREBASE_REFRESH_TOKEN},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id_token"]

def api_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "X-HERO-APP-PLATFORM": "iPhone",
        "X-HERO-BRAND-ID": BRAND_ID,
        "X-HERO-APP-IDENTIFIER": "com.heroworkout.mamba.johnreed",
        "X-HERO-APP-VERSION": "1.20.0",
        "X-HERO-API-VERSION": "v1",
        "Accept": "application/json",
        "User-Agent": "ktor-client",
    }

def try_api(token, path):
    url = BASE + path
    try:
        r = requests.get(url, headers=api_headers(token), timeout=8)
        print(f"  {r.status_code}  {url}")
        if r.status_code == 200:
            data = r.json()
            print(f"    → {json.dumps(data)[:300]}")
        return r
    except Exception as e:
        print(f"  ERR  {url}: {e}")
        return None

def get_studio_id_from_page(slug):
    """Fetch club page and extract studioId from __NEXT_DATA__."""
    url = f"https://johnreed.fitness/clubs/{slug}"
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        if r.status_code != 200:
            return None, r.status_code
        m = re.search(r'"studioId"\s*:\s*"?(\d+)"?', r.text)
        if m:
            return m.group(1), 200
        return None, 200
    except Exception as e:
        return None, f"ERR:{e}"

def main():
    print("=== Firebase Token ===")
    token = get_id_token()
    print("OK\n")

    # ── 1. Bötzow + Women's Club mlStudioID holen ─────────────────────────
    print("=== Bötzow & Women's Club: mlStudioID suchen ===")
    for slug in EXTRA_SLUGS:
        ml_id, status = get_studio_id_from_page(slug)
        print(f"  {status}  {slug}  →  mlStudioID={ml_id}")
        if ml_id:
            STUDIOS[slug] = {"mlId": ml_id, "firebase": None}
    print()

    # ── 2. mlStudioID direkt als Gym-ID in RSG API testen ─────────────────
    print("=== RSG API: mlStudioID als Gym-ID testen ===")
    print("(Charlottenburg als Kontrolle: mlId=3818598990, Firebase=mL6O8ISwlk5tQt7mnwjo)")

    for slug, info in STUDIOS.items():
        ml_id = info["mlId"]
        if not ml_id:
            continue
        print(f"\n  [{slug}] mlId={ml_id}")
        for path_template in [
            f"/gyms/{BRAND_ID}/gym/{ml_id}/utilization",
            f"/gyms/{BRAND_ID}/gym/{ml_id}",
        ]:
            r = try_api(token, path_template)
            if r and r.status_code == 200:
                print(f"    ✓ TREFFER mit mlId!")
    print()

    # ── 3. Mapping-Endpoints testen ───────────────────────────────────────
    print("=== Mapping-Endpoints: mlId → Firebase-ID ===")
    test_ml_id = "3818598990"  # Charlottenburg
    mapping_paths = [
        f"/gyms/{BRAND_ID}/gym/by-magicline-id/{test_ml_id}",
        f"/gyms/{BRAND_ID}/gym/by-ml-id/{test_ml_id}",
        f"/gyms/{BRAND_ID}/gym/magicline/{test_ml_id}",
        f"/gyms/{BRAND_ID}/gym/external/{test_ml_id}",
        f"/gyms/{BRAND_ID}/studio/{test_ml_id}",
        f"/magicline/gym/{test_ml_id}",
        f"/gyms/{BRAND_ID}/gym?mlId={test_ml_id}",
        f"/gyms/{BRAND_ID}/gym?externalId={test_ml_id}",
        f"/gyms/{BRAND_ID}/gym?studioId={test_ml_id}",
    ]
    for path in mapping_paths:
        try_api(token, path)
    print()

    # ── 4. Zusammenfassung ─────────────────────────────────────────────────
    print("=== VOLLSTÄNDIGE STUDIO-LISTE ===")
    print(f"{'Slug':<40} {'mlStudioID':<15} {'Firebase-ID'}")
    print("-" * 85)
    for slug, info in STUDIOS.items():
        firebase = info['firebase'] or '❓'
        ml_id    = info['mlId'] or '❓'
        print(f"  {slug:<40} {ml_id:<15} {firebase}")

if __name__ == "__main__":
    main()
