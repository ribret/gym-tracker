#!/usr/bin/env python3
"""
Discover John Reed Berlin gym IDs — v6.
Strategy: Query WPGraphQL API (johnreed.fitness/graphql) for all studio custom fields.
The Firebase ID must be stored as a WP custom field (server-side mapping: mlStudioID → Firebase ID).
Also: Women's Club slug discovery via GraphQL studio list.
"""

import os, json, re, requests

FIREBASE_API_KEY       = os.environ["FIREBASE_API_KEY"]
FIREBASE_REFRESH_TOKEN = os.environ["FIREBASE_REFRESH_TOKEN"]

BRAND_ID  = "johnreed"
BASE      = "https://app-api.rsg.mamba-app.one-member.com"
GQL_URL   = "https://johnreed.fitness/graphql"
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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

def get_id_token():
    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        json={"grantType": "refresh_token", "refreshToken": FIREBASE_REFRESH_TOKEN},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id_token"]

def gql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    try:
        r = requests.post(GQL_URL, json=payload, headers=BROWSER_HEADERS, timeout=15)
        print(f"  GQL {r.status_code}")
        return r
    except Exception as e:
        print(f"  GQL ERR: {e}")
        return None

def try_api(token, path):
    url = BASE + path
    try:
        r = requests.get(url, headers={
            "Authorization": f"Bearer {token}",
            "X-HERO-APP-PLATFORM": "iPhone",
            "X-HERO-BRAND-ID": BRAND_ID,
            "X-HERO-APP-IDENTIFIER": "com.heroworkout.mamba.johnreed",
            "X-HERO-APP-VERSION": "1.20.0",
            "X-HERO-API-VERSION": "v1",
            "Accept": "application/json",
            "User-Agent": "ktor-client",
        }, timeout=8)
        if r.status_code == 200:
            data = r.json().get("data", {})
            name = data.get("name", data.get("id", "?"))
            print(f"  ✓ 200  {url}  → {name}")
        else:
            print(f"  {r.status_code}  {url}")
        return r
    except Exception as e:
        print(f"  ERR  {url}: {e}")
        return None

def main():
    print("=== Firebase Token ===")
    token = get_id_token()
    print("OK\n")

    # ── 1. GraphQL Schema-Introspection: was gibt es für Studio-Typen? ──────
    print("=== GQL: Schema-Introspection (Studio-Typ) ===")
    r = gql("""
    {
      __schema {
        types {
          name
          kind
          fields {
            name
          }
        }
      }
    }
    """)
    if r and r.status_code == 200:
        try:
            types = r.json()["data"]["__schema"]["types"]
            # Suche nach Studio-relevanten Typen
            for t in types:
                name = t.get("name", "")
                if any(kw in name.lower() for kw in ["studio", "gym", "club", "rsg", "magicline", "capacity", "utiliz"]):
                    fields = [f["name"] for f in (t.get("fields") or [])]
                    print(f"  Typ: {name} → Felder: {fields[:15]}")
        except Exception as e:
            print(f"  Parse-Fehler: {e}")
            print(r.text[:500])
    print()

    # ── 2. GraphQL: Alle Studios mit Custom-Fields abrufen ──────────────────
    print("=== GQL: Studios mit allen Custom-Fields ===")
    studio_queries = [
        # Variante 1: "studios" collection
        """{ studios(first: 50) { nodes { id slug title
          customStudioSettings { mlStudioID rsgGymId firebaseGymId gymId studioId externalId }
        } } }""",
        # Variante 2: "studio" singular with allStudios
        """{ allStudios: studios(first: 50) { nodes { id slug
          studioFields { mlStudioID rsgId firebaseId gymId }
        } } }""",
        # Variante 3: Nur slug + studioId
        """{ studios(first: 50) { nodes { slug studioId mlStudioID } } }""",
        # Variante 4: pageProps-Style
        """{ studios(first: 50, where: {language: DE}) { nodes {
          id slug title
          translation(language: DE) {
            customStudioSettings { mlStudioID }
          }
        } } }""",
    ]
    for i, q in enumerate(studio_queries, 1):
        print(f"\n  Variante {i}:")
        r = gql(q)
        if r and r.status_code == 200:
            data = r.json()
            if "errors" not in data or not data.get("errors"):
                print(f"  Erfolg! Antwort: {json.dumps(data)[:2000]}")
                break
            else:
                err = data["errors"][0].get("message", "?")
                print(f"  GraphQL-Fehler: {err}")
        print()

    # ── 3. GraphQL: Studio by slug, alle Felder ─────────────────────────────
    print("\n=== GQL: Studio by Slug (Charlottenburg als Kontrolle) ===")
    for slug_field in ["uri", "slug", "id"]:
        r = gql(f"""
        {{
          studio({slug_field}: "berlin-charlottenburg") {{
            id slug title
            customStudioSettings {{
              mlStudioID
            }}
          }}
        }}
        """)
        if r and r.status_code == 200:
            data = r.json()
            if "errors" not in data:
                print(f"  {slug_field}: {json.dumps(data)[:500]}")
                break
            else:
                print(f"  {slug_field}: {data['errors'][0].get('message', '?')}")
    print()

    # ── 4. Magicline API direkt ──────────────────────────────────────────────
    print("=== Magicline API: mlStudioID → Daten ===")
    ml_endpoints = [
        "https://app.magicline.com/api/v1/studio/3818598990",
        "https://api.magicline.com/v1/studios/3818598990",
        "https://rsg.magicline.com/api/studio/3818598990",
    ]
    for url in ml_endpoints:
        try:
            r = requests.get(url, timeout=8,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            print(f"  {r.status_code}  {url}")
            if r.status_code == 200:
                print(f"  → {r.text[:300]}")
        except Exception as e:
            print(f"  ERR  {url}: {e}")
    print()

    # ── 5. Women's Club: GraphQL Studio-Liste nach Women-Studios ─────────────
    print("=== GQL: Alle Studios inkl. Women's Club ===")
    r = gql("""
    { studios(first: 100) { nodes { id slug title } } }
    """)
    if r and r.status_code == 200:
        data = r.json()
        if "data" in data and data["data"].get("studios"):
            nodes = data["data"]["studios"]["nodes"]
            berlin = [n for n in nodes if "berlin" in n.get("slug", "").lower()
                      or "berlin" in n.get("title", "").lower()]
            print(f"  Berliner Studios ({len(berlin)}):")
            for n in berlin:
                print(f"    {n.get('slug', '?')}  →  {n.get('title', '?')}")
        else:
            print(f"  {json.dumps(data)[:300]}")
    print()

    # ── 6. Zusammenfassung ───────────────────────────────────────────────────
    print("=== STAND ===")
    print(f"{'Studio':<35} {'mlStudioID':<15} {'Firebase-ID'}")
    print("-" * 75)
    for slug, ml_id in KNOWN_ML_IDS.items():
        fb = KNOWN_FIREBASE_ID if slug == "berlin-charlottenburg" else "❓"
        print(f"  {slug:<35} {ml_id:<15} {fb}")
    print(f"  {'berlin-womens-prenzlauer-berg':<35} {'❓':<15} ❓")

if __name__ == "__main__":
    main()
