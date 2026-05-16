#!/usr/bin/env python3
"""
Discover John Reed Berlin gym IDs — v7.
GraphQL via GET (POST war geblockt), WordPress REST API, wp-json ACF-Felder.
"""

import os, json, re, requests
from urllib.parse import urlencode, quote

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID  = "johnreed"
BASE      = "https://app-api.rsg.mamba-app.one-member.com"
KNOWN_FIREBASE_ID = "mL6O8ISwlk5tQt7mnwjo"

KNOWN_ML_IDS = {
    "berlin-charlottenburg":  "3818598990",
    "berlin-prenzlauer-berg": "1404492860",
    "berlin-friedrichshain":  "3946841990",
    "berlin-kreuzberg":       "1414215390",
    "berlin-gesundbrunnen":   "1414770410",
    "berlin-boetzow":         "5854039410",
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

def get_id_token():
    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        json={"grantType": "refresh_token", "refreshToken": FIREBASE_REFRESH_TOKEN},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id_token"]

def get(url, **kwargs):
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=15, **kwargs)
        print(f"  {r.status_code}  {url[:100]}")
        return r
    except Exception as e:
        print(f"  ERR  {url[:80]}: {e}")
        return None

def gql_get(query):
    """GraphQL via GET request."""
    url = "https://johnreed.fitness/graphql?" + urlencode({"query": query})
    return get(url)

def main():
    print("=== Firebase Token ===")
    token = get_id_token()
    print("OK\n")

    # ── 1. GraphQL via GET ────────────────────────────────────────────────────
    print("=== WPGraphQL via GET ===")
    r = gql_get("{ __typename }")
    if r and r.status_code == 200:
        print(f"  GraphQL antwortet: {r.text[:200]}")

        # Alle Studio-Slugs + Custom Fields
        r2 = gql_get("""
        { studios(first:100) { nodes {
            slug title
            customStudioSettings { mlStudioID }
        } } }
        """)
        if r2 and r2.status_code == 200:
            data = r2.json()
            print(json.dumps(data)[:3000])

        # Introspection: Welche Felder hat customStudioSettings?
        r3 = gql_get("""
        { __type(name:"CustomStudioSettings") { fields { name type { name } } } }
        """)
        if r3 and r3.status_code == 200:
            print(f"  CustomStudioSettings-Felder: {r3.text[:1000]}")
    else:
        print("  GraphQL GET auch nicht verfügbar")
    print()

    # ── 2. WordPress REST API ─────────────────────────────────────────────────
    print("=== WordPress REST API ===")
    wp_base = "https://johnreed.fitness/wp-json"

    # Discovery: welche Post-Types gibt es?
    r = get(f"{wp_base}/wp/v2/")
    if r and r.status_code == 200:
        data = r.json()
        print(f"  WP REST API verfügbar: {list(data.keys())[:10]}")

    # Custom Post Types suchen
    r = get(f"{wp_base}/")
    if r and r.status_code == 200:
        data = r.json()
        namespaces = data.get("namespaces", [])
        routes = list(data.get("routes", {}).keys())
        studio_routes = [rt for rt in routes if "studio" in rt.lower() or "gym" in rt.lower()]
        print(f"  Namespaces: {namespaces}")
        print(f"  Studio-Routes: {studio_routes}")

    # Studios als Custom Post Type
    for cpt in ["studios", "studio", "gyms", "gym", "clubs", "club", "locations"]:
        r = get(f"{wp_base}/wp/v2/{cpt}?per_page=50")
        if r and r.status_code == 200:
            data = r.json()
            print(f"  ✓ {cpt}: {len(data)} Einträge")
            for item in data[:3]:
                print(f"    id={item.get('id')} slug={item.get('slug')} "
                      f"acf={item.get('acf', {})}")
            if len(data) > 3:
                print(f"    ... und {len(data)-3} weitere")
    print()

    # ── 3. ACF REST API ───────────────────────────────────────────────────────
    print("=== ACF REST Fields ===")
    # Hole bekannte wpPageIds aus __NEXT_DATA__ und schau ACF-Felder an
    known_page_ids = {
        "berlin-charlottenburg": 6209,
        "berlin-prenzlauer-berg": 5466,
        "berlin-friedrichshain": 12879,
        "berlin-kreuzberg": 6208,
        "berlin-gesundbrunnen": 6204,
    }
    for slug, page_id in known_page_ids.items():
        for ep in [f"wp/v2/studios/{page_id}", f"wp/v2/pages/{page_id}", f"acf/v3/studios/{page_id}"]:
            r = get(f"{wp_base}/{ep}")
            if r and r.status_code == 200:
                data = r.json()
                acf = data.get("acf", {})
                meta = data.get("meta", {})
                print(f"  [{slug}] via {ep}: acf={acf}, meta={list(meta.keys())[:5]}")
                if acf:
                    print(f"    ALLE ACF: {json.dumps(acf)[:500]}")
                break
    print()

    # ── 4. Suche nach Firebase-ID-Muster in WordPress REST Posts ─────────────
    print("=== WordPress Studio Posts: Firebase-ID in Meta suchen ===")
    r = get(f"{wp_base}/wp/v2/studios?per_page=100&_fields=id,slug,acf,meta,customStudioSettings")
    if r and r.status_code == 200:
        for item in r.json():
            text = json.dumps(item)
            firebase_ids = re.findall(r'[A-Za-z0-9]{20}', text)
            real_ids = [x for x in firebase_ids if re.search(r'\d', x) and not x.startswith('R0lG')]
            if real_ids:
                print(f"  {item.get('slug')}: mögliche IDs: {real_ids}")
    print()

    # ── 5. Zusammenfassung ────────────────────────────────────────────────────
    print("=== AKTUELLER STAND ===")
    for slug, ml_id in KNOWN_ML_IDS.items():
        fb = KNOWN_FIREBASE_ID if slug == "berlin-charlottenburg" else "❓"
        print(f"  {slug:<38} ml={ml_id}  firebase={fb}")
    print(f"  {'berlin-womens-prenzlauer-berg':<38} ml=❓        firebase=❓")
    print("\nFazit: Proxyman bleibt die einzige sichere Methode für Firebase-IDs.")

if __name__ == "__main__":
    main()
