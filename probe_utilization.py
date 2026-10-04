"""Einmaliger API-Test (04.10.2026): enthaelt die Stundentabelle Ist-Werte vergangener
Stunden? Gibt die volle Antwort fuer 3 Studios aus, speichert nichts. Wird nach dem
Test wieder entfernt."""
import json, requests
from datetime import datetime
from gym_tracker import GYMS, BASE_URL, BRAND_ID, BERLIN, get_id_token, _api_headers

tok = get_id_token()
print("Abruf:", datetime.now(BERLIN).strftime("%Y-%m-%d %H:%M:%S"), "Berlin")
for key in GYMS:
    r = requests.get(f"{BASE_URL}/gyms/{BRAND_ID}/gym/{GYMS[key]['id']}/utilization",
                     headers=_api_headers(tok), timeout=10)
    print(f"\n=== {key} HTTP {r.status_code}")
    print(json.dumps(r.json(), indent=1, ensure_ascii=False)[:4000])
