#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"

echo "=== 1. API info ==="
curl -s "$BASE/api" | python3 -m json.tool

echo "=== 2. Логин дежурного (JWT) ==="
DUTY_JSON=$(curl -s -X POST "$BASE/api/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"duty","password":"duty"}')
echo "$DUTY_JSON" | python3 -m json.tool
DUTY_TOKEN=$(echo "$DUTY_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH_DUTY="Authorization: Bearer $DUTY_TOKEN"

echo "=== 3. Логин админа (JWT) ==="
ADMIN_JSON=$(curl -s -X POST "$BASE/api/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}')
echo "$ADMIN_JSON" | python3 -m json.tool
ADMIN_TOKEN=$(echo "$ADMIN_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH_ADMIN="Authorization: Bearer $ADMIN_TOKEN"

echo "=== 4. /api/me дежурный ==="
curl -s "$BASE/api/me" -H "$AUTH_DUTY" | python3 -m json.tool

echo "=== 5. Карта (до тревоги) ==="
curl -s "$BASE/api/map" -H "$AUTH_DUTY" | python3 -m json.tool

echo "=== 6. Нормальные показания всех 3 датчиков ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.11" \
  -H "Content-Type: application/json" \
  -d '{"value": 24, "online": true}' | python3 -m json.tool
curl -s -X POST "$BASE/api/ingest/192.168.1.12" \
  -H "Content-Type: application/json" \
  -d '{"value": 20.9, "online": true}' | python3 -m json.tool
curl -s -X POST "$BASE/api/ingest/192.168.1.13" \
  -H "Content-Type: application/json" \
  -d '{"value": 5, "online": true}' | python3 -m json.tool

echo "=== 7. Один датчик в тревоге → ложное ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.11" \
  -H "Content-Type: application/json" \
  -d '{"value": 90, "online": true}' | python3 -m json.tool
curl -s "$BASE/api/notifications" -H "$AUTH_DUTY" | python3 -m json.tool

echo "=== 8. Второй датчик в тревоге → ПОЖАР ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.13" \
  -H "Content-Type: application/json" \
  -d '{"value": 80, "online": true}' | python3 -m json.tool
echo "--- уведомления дежурному ---"
curl -s "$BASE/api/notifications?target=duty" -H "$AUTH_DUTY" | python3 -m json.tool
echo "--- уведомления пожарной ---"
curl -s "$BASE/api/notifications?target=fire_dept" -H "$AUTH_DUTY" | python3 -m json.tool

echo "=== 9. Карта после пожара ==="
curl -s "$BASE/api/map" -H "$AUTH_DUTY" | python3 -m json.tool

echo "=== 10. Дежурный подтверждает пожар ==="
EVENT_ID=$(curl -s "$BASE/api/events" -H "$AUTH_DUTY" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
curl -s -X POST "$BASE/api/events/$EVENT_ID/resolve" \
  -H "Content-Type: application/json" \
  -H "$AUTH_DUTY" \
  -d '{"resolution":"confirmed_fire"}' | python3 -m json.tool

echo "=== 11. Offline датчик ==="
curl -s -X POST "$BASE/api/ingest/192.168.1.12" \
  -H "Content-Type: application/json" \
  -d '{"value": 0, "online": false}' | python3 -m json.tool
curl -s "$BASE/api/notifications" -H "$AUTH_DUTY" | python3 -m json.tool | head -n 40

echo "=== 12. Статистика ==="
curl -s "$BASE/api/stats" -H "$AUTH_DUTY" | python3 -m json.tool

echo "=== 13. Админ добавляет склад ==="
curl -s -X POST "$BASE/api/warehouses" \
  -H "Content-Type: application/json" \
  -H "$AUTH_ADMIN" \
  -d '{"name":"Склад Б","description":"Новый","map_x":300,"map_y":100}' | python3 -m json.tool

echo "=== 14. Без токена → 401 ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/map")
echo "HTTP $CODE (ожидаем 401)"
test "$CODE" = "401"

echo "OK"
