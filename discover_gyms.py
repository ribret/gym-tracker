#!/usr/bin/env python3
"""
Discover John Reed Berlin gym IDs via RSG API + public sources.
"""

import os
import json
import re
import requests
import xml.etree.ElementTree as ET

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID  = "johnreed"
BASE      = "https://app-api.rsg.mamba-app.one-member.com"
KNOWN_ID  = "mL6O8ISwlk5tQt7mnwjo"  # Charlottenburg

# Berlin John Reed club slugs (from johnreed.fitness/clubs/*)
# Guessing based on naming pattern observed in Charlottenburg URL
BERLIN_SLUGS = [
    "berlin-charlottenburg",   # confirmed
    "berlin-mitte",
    "berlin-prenzlauer-berg",
    "berlin-friedrichshain",
    "berlin-kreuzberg",
    "berlin-tempelhof",
    "berlin-schoeneberg",
    "berlin-schöneberg",
    "berlin-wedding",
    "berlin-gesundbrunnnen",
    "berlin-steglitz",
    "berlin-spandau",
    "berlin-lichtenberg",
    "berlin-neukoelln",
    "berlin-neukölln",
    "berlin-treptow",
    "berlin-koepenick",
]

def get_id_token() -> str:
    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        json={"grantType": "refresh_token", "refreshToken": FIREBASE_REFRESH_TOKEN},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id_token"]

def api_headers(token: str) -> dict:
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

def try_api(token: str, path: str, method="GET", body=None):
    url = BASE + path
    try:
        if method == "GET":
            r = requests.get(url, headers=api_headers(token), timeout=10)
        else:
            r = requests.post(url, headers=api_headers(token), json=body, timeout=10)
        print(f"  {r.status_code}  {url}")
        if r.status_code == 200:
            print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:4000])
        return r
    except Exception as e:
        print(f"  ERR  {url}  → {e}")
        return None

def try_web(url: str, label: str):
    """Fetch a public web URL with a browser-like User-Agent."""
    try:
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9",
        })
        print(f"  [{label}]  {r.status_code}  {url}")
        return r
    except Exception as e:
        print(f"  [{label}]  ERR  → {e}")
        return None

def extract_ids_from_text(text: str) -> list:
    """Find strings that look like Firebase IDs (20 alphanumeric chars)."""
    return list(set(re.findall(r'\b[A-Za-z0-9]{20}\b', text)))

# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=== Firebase Token ===")
    token = get_id_token()
    print("OK\n")

    # ── 1. Koordinatenbasierte Such-Endpoints ─────────────────────────────────
    print("=== Koordinaten-Suche (Berlin Zentrum) ===")
    berlin_lat, berlin_lon = 52.52, 13.40
    coordinate_paths = [
        f"/gyms/{BRAND_ID}/gyms/nearby?lat={berlin_lat}&lon={berlin_lon}&radius=25",
        f"/gyms/{BRAND_ID}/gyms/search?lat={berlin_lat}&lon={berlin_lon}&radius=25",
        f"/gyms/{BRAND_ID}/locations?lat={berlin_lat}&lon={berlin_lon}",
        f"/gyms/{BRAND_ID}/gyms?city=Berlin",
        f"/gyms/{BRAND_ID}/gyms?country=DE",
        f"/gyms/{BRAND_ID}/gyms?lat={berlin_lat}&lon={berlin_lon}&radius=25",
        f"/gyms/search?brandId={BRAND_ID}&lat={berlin_lat}&lon={berlin_lon}",
        f"/gyms/{BRAND_ID}/gym/search",
    ]
    for path in coordinate_paths:
        r = try_api(token, path)
        if r and r.status_code == 200:
            print(">>> TREFFER! Koordinaten-Suche")
            break
    print()

    # ── 2. POST-basierte Suche ────────────────────────────────────────────────
    print("=== POST Suche ===")
    post_candidates = [
        (f"/gyms/{BRAND_ID}/gyms/search", {"lat": berlin_lat, "lon": berlin_lon, "radius": 25}),
        (f"/gyms/{BRAND_ID}/gyms/nearby", {"latitude": berlin_lat, "longitude": berlin_lon}),
        (f"/search/gyms", {"brand": BRAND_ID, "city": "Berlin"}),
    ]
    for path, body in post_candidates:
        r = try_api(token, path, method="POST", body=body)
        if r and r.status_code == 200:
            print(">>> TREFFER! POST-Suche")
    print()

    # ── 3. Slug-basierte Lookups ──────────────────────────────────────────────
    print("=== Slug-basierte API-Lookups ===")
    slug_paths = [
        f"/gyms/{BRAND_ID}/gym/by-slug/berlin-charlottenburg",
        f"/gyms/{BRAND_ID}/gym/slug/berlin-charlottenburg",
        f"/gyms/{BRAND_ID}/club/berlin-charlottenburg",
    ]
    for path in slug_paths:
        r = try_api(token, path)
        if r and r.status_code == 200:
            print(">>> TREFFER! Slug-Lookup")
    print()

    # ── 4. Sitemap ────────────────────────────────────────────────────────────
    print("=== johnreed.fitness Sitemap ===")
    for sitemap_url in [
        "https://johnreed.fitness/sitemap.xml",
        "https://johnreed.fitness/sitemap_index.xml",
        "https://www.johnreed.fitness/sitemap.xml",
    ]:
        r = try_web(sitemap_url, "sitemap")
        if r and r.status_code == 200:
            # Parse XML und finde Berlin-URLs
            try:
                root = ET.fromstring(r.text)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = [loc.text for loc in root.findall(".//sm:loc", ns) if loc.text]
                berlin_urls = [u for u in urls if "berlin" in u.lower()]
                print(f"  Berlin-URLs in Sitemap ({len(berlin_urls)}):")
                for u in berlin_urls:
                    print(f"    {u}")
                # Auch nach Firebase-IDs suchen
                ids = extract_ids_from_text(r.text)
                if ids:
                    print(f"  Mögliche IDs: {ids}")
            except Exception as e:
                print(f"  XML-Parse-Fehler: {e}")
                print(r.text[:2000])
            break
    print()

    # ── 5. Apple App Site Association ─────────────────────────────────────────
    print("=== Apple App Site Association ===")
    r = try_web("https://johnreed.fitness/.well-known/apple-app-site-association", "AASA")
    if r and r.status_code == 200:
        print(r.text[:3000])
        ids = extract_ids_from_text(r.text)
        if ids:
            print(f"  Mögliche IDs: {ids}")
    print()

    # ── 6. Club-Seiten direkt scrapen ─────────────────────────────────────────
    print("=== Club-Seiten scrapen (nach IDs suchen) ===")
    found_slugs = []
    for slug in BERLIN_SLUGS[:8]:  # Erstmal die wahrscheinlichsten
        r = try_web(f"https://johnreed.fitness/clubs/{slug}", slug)
        if r and r.status_code == 200:
            ids = extract_ids_from_text(r.text)
            firebase_ids = [i for i in ids if i != KNOWN_ID]
            print(f"  IDs auf Seite: {ids}")
            found_slugs.append(slug)
    print()

    # ── 7. Gym-Detail mit bekannter ID — nach "siblings" suchen ──────────────
    print("=== Detail-Response auf versteckte Felder prüfen ===")
    r = try_api(token, f"/gyms/{BRAND_ID}/gym/{KNOWN_ID}")
    if r and r.status_code == 200:
        data = r.json()
        # Vollständige Response ausgeben (vorhin nur 3000 Zeichen)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        ids = extract_ids_from_text(json.dumps(data))
        other_ids = [i for i in ids if i != KNOWN_ID]
        if other_ids:
            print(f"\n  Weitere IDs in der Response: {other_ids}")
    print()

    # ── 8. Membership / Home-Gym Endpoint ─────────────────────────────────────
    print("=== Membership-Endpoints (evtl. Home-Gym + andere) ===")
    for path in [
        f"/gyms/{BRAND_ID}/membership",
        f"/gyms/{BRAND_ID}/user/membership",
        f"/membership",
        f"/gyms/{BRAND_ID}/checkins",
        f"/gyms/{BRAND_ID}/user/checkins",
    ]:
        r = try_api(token, path)
        if r and r.status_code == 200:
            print(">>> TREFFER!")

if __name__ == "__main__":
    main()
