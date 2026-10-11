# Мониторинг складов и пожарных датчиков

Простой backend на **FastAPI + SQLite + JWT**.  
Администратор заводит склады и датчики, дежурный смотрит карту и уведомления.

## Как запустить

```bash
cd /Users/roman/surkova
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Открыть:

- UI (кнопки): http://127.0.0.1:8000/ui/  ← открывайте именно этот адрес, не файл index.html
- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

Проверка сценария одной командой:

```bash
./test_api.sh
```

## Учётные записи (создаются при первом запуске)

| Логин   | Пароль | Роль        | Что может |
|---------|--------|-------------|-----------|
| `admin` | `admin`| администратор | добавлять склады, зоны, датчики |
| `duty`  | `duty` | дежурный (role 1) | карта, уведомления, подтверждение пожара/ложного |

Пароли хранятся в SQLite как есть (демо). В проде нужно хешировать.

## JWT — как логиниться

1. Получить токен:

```bash
curl -s -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"duty","password":"duty"}'
```

Ответ:

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "user": {"id": 2, "username": "duty", "role": "duty"}
}
```

2. Во все защищённые запросы передавать заголовок:

```text
Authorization: Bearer eyJhbGciOi...
```

Пример:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s http://127.0.0.1:8000/api/map \
  -H "Authorization: Bearer $TOKEN"
```

Токен живёт **12 часов**. Эндпоинты приёма показаний датчиков (`/api/ingest/...`, `/api/sensors/{id}/reading`) **без JWT** — датчик шлёт данные напрямую.

## Роли и карта

- Карта 500×400, координаты складов и датчиков приходят с бэка (`map_x`, `map_y`).
- При старте: **Склад А** и **Склад Б**, у каждого по 3 датчика в разных точках.
- При добавлении склада/датчика бэкенд сам ищет свободное место (датчики не ближе ~55 px).
- На карте датчик:
  - **green** — работает (`ok`)
  - **gray** — не работает (`offline`)
  - **red** — тревога / пожар (`alarm`)
- Зона контроля = **3 датчика**: температура, кислород, задымление.
- Сработали **2 или 3** → сигнал **пожар** (звук `sharp`) + уведомление в пожарную.
- Сработал **1** → **ложное** (звук `soft`).
- Из 3 работает только 2 → уведомление «проверьте датчик».

Дежурный после выезда закрывает событие:

- `confirmed_fire` — пожар был
- `confirmed_false` — ложное

Так считаются ложные срабатывания в `/api/stats`.

## Протокол датчика

Датчик — устройство в сети склада со своим **IP**. Периодически (или по событию) шлёт HTTP POST на сервер.

### Пример данных

```json
{
  "value": 72.5,
  "online": true
}
```

| Поле     | Тип     | Смысл |
|----------|---------|--------|
| `value`  | number  | температура °C / O₂ % / уровень дыма |
| `online` | boolean | `false` → датчик offline (серый на карте) |

### Пороги по умолчанию (зона 1.1)

| Тип           | IP            | Порог | Тревога если |
|---------------|---------------|-------|--------------|
| temperature   | 192.168.1.11  | 60    | value > 60   |
| oxygen        | 192.168.1.12  | 18    | value < 18   |
| smoke         | 192.168.1.13  | 50    | value > 50   |

### Как датчик шлёт данные

По IP:

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/192.168.1.11 \
  -H "Content-Type: application/json" \
  -d '{"value": 90, "online": true}'
```

Или по id датчика:

```bash
curl -X POST http://127.0.0.1:8000/api/sensors/1/reading \
  -H "Content-Type: application/json" \
  -d '{"value": 24, "online": true}'
```

### Процесс взаимодействия

1. Дежурный логинится → получает JWT → открывает `/api/map`.
2. Датчики шлют показания на `/api/ingest/{ip}`.
3. Сервер обновляет статус и цвет, при необходимости создаёт событие и уведомление.
4. Дежурный видит `/api/notifications` (звук `soft` / `sharp`).
5. При пожаре уведомление дублируется target=`fire_dept`.
6. Дежурный ведёт пожарных на точку и закрывает событие через `/api/events/{id}/resolve`.

## Основные API

| Метод | Путь | Кто | Описание |
|-------|------|-----|----------|
| POST | `/api/login` | все | логин → JWT |
| GET | `/api/me` | JWT | текущий пользователь |
| POST | `/api/warehouses` | admin | добавить склад |
| POST | `/api/zones` | admin | добавить зону на карте |
| POST | `/api/sensors` | admin | добавить датчик |
| GET | `/api/map` | JWT | схема складов + датчики |
| POST | `/api/ingest/{ip}` | датчик | показание по IP |
| GET | `/api/notifications` | JWT | уведомления |
| GET | `/api/events` | JWT | события |
| POST | `/api/events/{id}/resolve` | duty/admin | подтвердить пожар/ложное |
| GET | `/api/stats` | JWT | статистика ложных |

## Структура проекта

```text
app/
  main.py      — API
  auth.py      — JWT
  models.py    — таблицы SQLite
  schemas.py   — тела запросов/ответов
  logic.py     — правила пожар / ложное / offline
  db.py        — подключение к БД
test_api.sh    — проверка сценария curl
README.md      — эта документация
```

БД создаётся файл `fire_monitor.db` в корне при первом запуске.
