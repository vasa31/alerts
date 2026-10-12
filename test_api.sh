#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"

echo "=== 1. API info ==="
curl -s "$BASE/api" | python3 -m json.tool

echo "=== 2. Логин duty ==="
DUTY_JSON=$(curl -s -X POST "$BASE/api/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"duty","password":"duty"}')
echo "$DUTY_JSON" | python3 -m json.tool
DUTY_TOKEN=$(echo "$DUTY_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH_DUTY="Authorization: Bearer $DUTY_TOKEN"

echo "=== 3. Карта ==="
curl -s "$BASE/api/map" -H "$AUTH_DUTY" | python3 -c "import sys,json; d=json.load(sys.stdin); print('warehouses',len(d['warehouses']),'sensors',len(d['sensors']),'confirm',d['confirm_seconds'])"

echo "=== 4. Норма ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.11" -H "Content-Type: application/json" -d '{"value":24,"online":true}' >/dev/null
curl -s -X POST "$BASE/api/ingest/192.168.1.12" -H "Content-Type: application/json" -d '{"value":20.9,"online":true}' >/dev/null
curl -s -X POST "$BASE/api/ingest/192.168.1.13" -H "Content-Type: application/json" -d '{"value":5,"online":true}' >/dev/null

echo "=== 5. 1 тревога → ложное ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.11" -H "Content-Type: application/json" -d '{"value":90,"online":true}' | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
curl -s "$BASE/api/events" -H "$AUTH_DUTY" | python3 -c "import sys,json; print([e['event_type'] for e in json.load(sys.stdin)[:3]])"

echo "=== 6. 2 тревоги → наблюдение (не пожар) ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.13" -H "Content-Type: application/json" -d '{"value":80,"online":true}' >/dev/null
curl -s "$BASE/api/events" -H "$AUTH_DUTY" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['event_type'])"
FIRE_DEPT=$(curl -s "$BASE/api/notifications?target=fire_dept" -H "$AUTH_DUTY")
echo "пожарной после 2 датчиков: $FIRE_DEPT"

echo "=== 7. Затихли → пожара нет ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.11" -H "Content-Type: application/json" -d '{"value":24,"online":true}' >/dev/null
curl -s -X POST "$BASE/api/ingest/192.168.1.13" -H "Content-Type: application/json" -d '{"value":5,"online":true}' >/dev/null
curl -s "$BASE/api/events" -H "$AUTH_DUTY" | python3 -c "import sys,json; e=json.load(sys.stdin)[0]; print(e['event_type'], e['resolution'])"

echo "=== 8. 2 тревоги + force окно → пожар ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.11" -H "Content-Type: application/json" -d '{"value":90,"online":true}' >/dev/null
curl -s -X POST "$BASE/api/ingest/192.168.1.13" -H "Content-Type: application/json" -d '{"value":80,"online":true}' >/dev/null
curl -s -X POST "$BASE/api/watch/check?force=true" -H "$AUTH_DUTY" | python3 -m json.tool
curl -s "$BASE/api/notifications?target=fire_dept" -H "$AUTH_DUTY" | python3 -c "import sys,json; n=json.load(sys.stdin); print('fire_dept', n[0]['title'] if n else 'empty')"

echo "=== 9. Подтвердить пожар ==="
EVENT_ID=$(curl -s "$BASE/api/events" -H "$AUTH_DUTY" | python3 -c "import sys,json; evs=json.load(sys.stdin); print(next(e['id'] for e in evs if e['event_type']=='fire_signal' and e['resolution']=='open'))")
curl -s -X POST "$BASE/api/events/$EVENT_ID/resolve" \
  -H "Content-Type: application/json" -H "$AUTH_DUTY" \
  -d '{"resolution":"confirmed_fire"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['resolution'])"

echo "=== 10. POST /api/warehouses должен быть 405/404 ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/warehouses" \
  -H "Content-Type: application/json" -H "$AUTH_DUTY" \
  -d '{"name":"X"}')
echo "HTTP $CODE"
test "$CODE" != "200"

echo "=== 11. Без токена → 401 ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/map")
echo "HTTP $CODE"
test "$CODE" = "401"

echo "OK"
