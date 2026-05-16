#!/usr/bin/env python3
"""
Discover John Reed Berlin gym IDs — v3.
Confirmed Berlin clubs on website: charlottenburg, prenzlauer-berg, friedrichshain, kreuzberg
Strategy: find Firebase IDs in embedded page JSON (Next.js/__NEXT_DATA__, Yext API keys, script tags)
"""

import os, json, re, requests, xml.etree.ElementTree as ET

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID = "johnreed"
BASE     = "https://app-api.rsg.mamba-app.one-member.com"
KNOWN_ID = "mL6O8ISwlk5tQt7mnwjo"  # Charlottenburg

# All Berlin slugs to test (expanded list)
BERLIN_SLUGS = [
    "berlin-charlottenburg",
    "berlin-prenzlauer-berg",
    "berlin-friedrichshain",
    "berlin-kreuzberg",
    "berlin-mitte",
    "berlin-wedding",
    "berlin-gesundbrunnen",
    "berlin-neukoelln",
    "berlin-neukölln",
    "berlin-tempelhof",
    "berlin-schoeneberg",
    "berlin-schöneberg",
    "berlin-steglitz",
    "berlin-spandau",
    "berlin-lichtenberg",
    "berlin-treptow",
    "berlin-pankow",
    "berlin-reinickendorf",
    "berlin-wilmersdorf",
    "berlin-zehlendorf",
    "berlin-koepenick",
    "berlin-marzahn",
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
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

def fetch_page(url):
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        return r
    except Exception as e:
        print(f"  ERR {url}: {e}")
        return None

def validate_gym_id(token, gym_id):
    """Returns gym name if ID is valid, else None."""
    try:
        r = requests.get(
            f"{BASE}/gyms/{BRAND_ID}/gym/{gym_id}",
            headers=api_headers(token),
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            return data.get("name", "?")
    except:
        pass
    return None

def extract_json_blobs(html):
    """Extract all JSON objects/arrays from HTML."""
    blobs = []
    # Next.js __NEXT_DATA__
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        blobs.append(("__NEXT_DATA__", m.group(1)))
    # Nuxt __NUXT__
    m = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\})\s*;', html, re.DOTALL)
    if m:
        blobs.append(("__NUXT__", m.group(1)[:5000]))
    # Generic window.* assignments with objects
    for match in re.finditer(r'window\.(\w+)\s*=\s*(\{[^;]{20,500}\})\s*;', html):
        blobs.append((f"window.{match.group(1)}", match.group(2)))
    # application/json script tags
    for match in re.finditer(r'<script[^>]+type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL):
        blobs.append(("application/json", match.group(1)[:2000]))
    # application/ld+json (structured data — often contains location IDs)
    for match in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
        blobs.append(("ld+json", match.group(1)[:2000]))
    return blobs

def find_firebase_ids(text):
    """Firebase Firestore IDs: 20 alphanumeric chars, not pure camelCase."""
    candidates = re.findall(r'["\']([A-Za-z0-9]{20})["\']', text)
    # Filter out obvious camelCase variable names (contain no digits)
    return [c for c in set(candidates) if re.search(r'\d', c)]

def find_yext_keys(html):
    """Look for Yext API keys (format: api_key=XXXX or similar)."""
    patterns = [
        r'api[_-]?key["\s:=]+([a-zA-Z0-9_\-]{20,60})',
        r'yext["\s:=]+([a-zA-Z0-9_\-]{20,60})',
        r'liveapi\.yext\.com[^"]*api_key=([^&"]+)',
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, html, re.IGNORECASE))
    return list(set(found))

# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=== Firebase Token ===")
    token = get_id_token()
    print("OK\n")

    valid_gyms = {}  # slug → (id, name)

    # ── 1. Alle Berlin-Slugs testen + Deep-Scrape ──────────────────────────
    print("=== Berlin-Slugs: Seiten abrufen und auf IDs analysieren ===")
    working_slugs = []
    for slug in BERLIN_SLUGS:
        url = f"https://johnreed.fitness/clubs/{slug}"
        r = fetch_page(url)
        status = r.status_code if r else "ERR"
        print(f"  {status}  {url}")
        if r and r.status_code == 200:
            working_slugs.append((slug, r.text))

    print(f"\nAktive Slugs: {[s for s, _ in working_slugs]}\n")

    # ── 2. Jeden aktiven Slug deep-analysen ──────────────────────────────
    print("=== Deep-Analyse der aktiven Club-Seiten ===")
    all_candidate_ids = set()

    for slug, html in working_slugs:
        print(f"\n--- {slug} ---")

        # Yext-Keys
        yext_keys = find_yext_keys(html)
        if yext_keys:
            print(f"  Yext-Keys: {yext_keys}")

        # Firebase-ID-Kandidaten aus dem HTML
        fb_ids = find_firebase_ids(html)
        if fb_ids:
            print(f"  Firebase-ID-Kandidaten: {fb_ids}")
            all_candidate_ids.update(fb_ids)
        else:
            print(f"  Keine Firebase-ID-Kandidaten im Raw-HTML")

        # JSON-Blobs
        blobs = extract_json_blobs(html)
        if blobs:
            for name, blob in blobs:
                print(f"  JSON-Blob gefunden: [{name}] (erste 500 Zeichen):")
                print(f"    {blob[:500]}")
                blob_ids = find_firebase_ids(blob)
                if blob_ids:
                    print(f"    IDs im Blob: {blob_ids}")
                    all_candidate_ids.update(blob_ids)
        else:
            print(f"  Keine JSON-Blobs gefunden")

        # Roh-Suche nach dem Muster der bekannten ID im HTML
        # (suche nach Strings ähnlich zu mL6O8ISwlk5tQt7mnwjo)
        raw_ids = re.findall(r'[A-Z][a-zA-Z0-9]{18}[a-zA-Z0-9]', html)
        non_camel = [x for x in set(raw_ids) if re.search(r'\d', x) and not x[0:3].isupper()]
        if non_camel:
            print(f"  Weitere ID-Kandidaten (unquoted): {non_camel[:10]}")
            all_candidate_ids.update(non_camel)

    # ── 3. Alle Kandidaten gegen die API validieren ──────────────────────
    print(f"\n=== API-Validierung von {len(all_candidate_ids)} ID-Kandidaten ===")
    # Bekannte ID ausschließen
    candidates_to_test = all_candidate_ids - {KNOWN_ID}
    if not candidates_to_test:
        print("  Keine neuen Kandidaten zum Testen.")
    else:
        for cid in sorted(candidates_to_test):
            name = validate_gym_id(token, cid)
            if name:
                print(f"  ✓ TREFFER: {cid} → {name}")
                valid_gyms[cid] = name
            else:
                print(f"  ✗ {cid}")

    # ── 4. Yext Knowledge Graph (falls Key gefunden) ──────────────────────
    print("\n=== Yext-Suche nach Berlin-Gyms ===")
    # Versuche die Yext-CDN-URL-Struktur zu nutzen, um den Yext Account zu finden
    # a.mktgcdn.com URLs enthalten Account-IDs im Pfad
    if working_slugs:
        sample_html = working_slugs[0][1]
        # Extrahiere Account-ID aus mktgcdn URLs
        mktg_ids = re.findall(r'a\.mktgcdn\.com/p/([A-Za-z0-9_\-]{20,60})/', sample_html)
        if mktg_ids:
            print(f"  mktgcdn Bild-IDs (erste 3): {mktg_ids[:3]}")

    # Versuche Yext Live API ohne Key (manchmal öffentlich)
    yext_urls = [
        "https://liveapi.yext.com/v2/accounts/me/entities/geosearch?radius=25&unit=mi&latitude=52.52&longitude=13.40&entityTypes=location&limit=50&v=20231201",
        "https://cdn.yextapis.com/v2/accounts/me/answers/vertical/query?experienceKey=john-reed&api_key=&v=20220511&input=berlin&verticalKey=locations",
    ]
    for url in yext_urls:
        try:
            r = requests.get(url, timeout=8)
            print(f"  {r.status_code}  {url[:80]}")
            if r.status_code == 200:
                print(r.text[:1000])
        except Exception as e:
            print(f"  ERR: {e}")

    # ── 5. Zusammenfassung ────────────────────────────────────────────────
    print("\n=== ZUSAMMENFASSUNG ===")
    print(f"Bekannte Studios:")
    print(f"  mL6O8ISwlk5tQt7mnwjo → JOHN REED Berlin Charlottenburg (Referenz)")
    for gym_id, name in valid_gyms.items():
        print(f"  {gym_id} → {name}")
    print(f"\nWebsite-aktive Slugs ohne bestätigte ID: {[s for s, _ in working_slugs if s != 'berlin-charlottenburg']}")

if __name__ == "__main__":
    main()
