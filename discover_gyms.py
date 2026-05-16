#!/usr/bin/env python3
"""
Discover John Reed Berlin gym IDs — v4.
Confirmed: charlottenburg, prenzlauer-berg, friedrichshain, kreuzberg, gesundbrunnen
New strategies:
- Parse full __NEXT_DATA__ JSON recursively for any ID-like field
- Try Next.js static data routes: /_next/data/{buildId}/clubs/{slug}.json
- Search for mamba-app.one-member.com references in page source
"""

import os, json, re, requests

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID = "johnreed"
BASE     = "https://app-api.rsg.mamba-app.one-member.com"
KNOWN_ID = "mL6O8ISwlk5tQt7mnwjo"  # Charlottenburg

CONFIRMED_SLUGS = [
    "berlin-charlottenburg",
    "berlin-prenzlauer-berg",
    "berlin-friedrichshain",
    "berlin-kreuzberg",
    "berlin-gesundbrunnen",
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
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

def fetch(url, headers=BROWSER_HEADERS):
    try:
        r = requests.get(url, headers=headers, timeout=15)
        return r
    except Exception as e:
        print(f"  ERR {url}: {e}")
        return None

def validate_gym_id(token, gym_id):
    try:
        r = requests.get(f"{BASE}/gyms/{BRAND_ID}/gym/{gym_id}", headers=api_headers(token), timeout=8)
        if r.status_code == 200:
            return r.json().get("data", {}).get("name")
    except:
        pass
    return None

def walk_json(obj, path=""):
    """Recursively walk JSON, yield (path, value) for string leaves."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_json(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_json(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj

def looks_like_firebase_id(s):
    return (
        len(s) == 20
        and re.fullmatch(r'[A-Za-z0-9]{20}', s)
        and bool(re.search(r'\d', s))
        and not s.islower()
        and not s.isupper()
        and not s[0].isupper() or bool(re.search(r'\d', s[:4]))  # avoid pure camelCase
    )

def find_ids_in_json(obj, context_filter=None):
    """Walk JSON tree, return (path, value) where value looks like a Firebase ID."""
    results = []
    for path, value in walk_json(obj):
        if looks_like_firebase_id(value):
            if context_filter is None or any(k in path.lower() for k in context_filter):
                results.append((path, value))
    return results

def main():
    print("=== Firebase Token ===")
    token = get_id_token()
    print("OK\n")

    found_ids = {}  # id → name
    build_id = None

    # ── 1. __NEXT_DATA__ vollständig parsen ──────────────────────────────────
    print("=== __NEXT_DATA__ vollständig parsen ===")
    for slug in CONFIRMED_SLUGS:
        url = f"https://johnreed.fitness/clubs/{slug}"
        r = fetch(url)
        if not r or r.status_code != 200:
            print(f"  SKIP {slug}")
            continue

        # Build ID extrahieren (für static routes)
        if not build_id:
            m = re.search(r'"buildId"\s*:\s*"([^"]+)"', r.text)
            if m:
                build_id = m.group(1)
                print(f"  Next.js buildId: {build_id}")

        # __NEXT_DATA__ extrahieren
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.DOTALL)
        if not m:
            print(f"  {slug}: kein __NEXT_DATA__")
            continue

        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            print(f"  {slug}: JSON-Parse-Fehler: {e}")
            continue

        # Alle String-Felder durchsuchen, die Firebase-ID-ähnlich sind
        all_ids = find_ids_in_json(data)
        gym_ids = [(p, v) for p, v in all_ids
                   if any(k in p.lower() for k in ['id', 'gym', 'studio', 'club', 'key', 'ref'])]

        # Auch alle übrigen ausgeben
        other_ids = [(p, v) for p, v in all_ids if (p, v) not in gym_ids]

        print(f"\n  [{slug}]")
        if gym_ids:
            print(f"    ID-relevante Felder: {gym_ids}")
        if other_ids:
            print(f"    Andere ID-Kandidaten (erste 5): {other_ids[:5]}")
        if not all_ids:
            print(f"    Keine Firebase-ID-Kandidaten in __NEXT_DATA__")

        # Auch nach mamba-app-Referenzen suchen
        mamba_refs = re.findall(r'mamba-app[^\s"\'<>]{5,100}', r.text)
        if mamba_refs:
            print(f"    mamba-app Referenzen: {mamba_refs}")

        # Alle alphanumerischen Strings aus dem RAW HTML (nicht nur quoted)
        raw_candidates = re.findall(r'[^A-Za-z0-9]([A-Za-z0-9]{20})[^A-Za-z0-9]', r.text)
        firebase_like = [c for c in set(raw_candidates)
                         if re.search(r'\d', c) and not c.startswith('R0lG')]
        if firebase_like:
            print(f"    Raw ID-Kandidaten (erste 10): {firebase_like[:10]}")

    print()

    # ── 2. Next.js Static Data Routes ───────────────────────────────────────
    print("=== Next.js Static Routes (/_next/data/{buildId}/clubs/{slug}.json) ===")
    if build_id:
        print(f"  Verwende buildId: {build_id}")
        for slug in CONFIRMED_SLUGS:
            url = f"https://johnreed.fitness/_next/data/{build_id}/clubs/{slug}.json"
            r = fetch(url)
            status = r.status_code if r else "ERR"
            print(f"  {status}  {url}")
            if r and r.status_code == 200:
                try:
                    data = r.json()
                    all_ids = find_ids_in_json(data)
                    if all_ids:
                        print(f"    Firebase-ID-Kandidaten: {all_ids}")
                    print(f"    Vollständiger Inhalt (erste 1000 Zeichen):")
                    print(f"    {json.dumps(data)[:1000]}")
                except:
                    print(f"    Raw: {r.text[:500]}")
    else:
        print("  Kein buildId gefunden.")
    print()

    # ── 3. Alternativer URL-Pfad /studio/ ────────────────────────────────────
    print("=== Alternativpfad /studio/ testen ===")
    studio_slugs_extra = [
        "berlin-mitte", "berlin-neukoelln", "berlin-tempelhof",
        "berlin-spandau", "berlin-steglitz", "berlin-schoeneberg",
    ]
    for slug in studio_slugs_extra:
        for path_prefix in ["/studio/", "/clubs/"]:
            r = fetch(f"https://johnreed.fitness{path_prefix}{slug}")
            if r and r.status_code == 200:
                print(f"  200  https://johnreed.fitness{path_prefix}{slug}  ← NEU!")
    print()

    # ── 4. API-Validierung aller bisher gefundenen Kandidaten ────────────────
    to_validate = set(found_ids.keys())
    if to_validate:
        print(f"=== API-Validierung von {len(to_validate)} Kandidaten ===")
        for cid in to_validate:
            name = validate_gym_id(token, cid)
            if name:
                print(f"  ✓ {cid} → {name}")
            else:
                print(f"  ✗ {cid}")

    # ── 5. Zusammenfassung ───────────────────────────────────────────────────
    print("\n=== ZUSAMMENFASSUNG ===")
    print("Bestätigte Berliner Studios (Website):")
    for s in CONFIRMED_SLUGS:
        print(f"  https://johnreed.fitness/clubs/{s}")
    print(f"\nBestätigte Firebase-IDs:")
    print(f"  mL6O8ISwlk5tQt7mnwjo → JOHN REED Berlin Charlottenburg")
    for gym_id, name in found_ids.items():
        print(f"  {gym_id} → {name}")

if __name__ == "__main__":
    main()
