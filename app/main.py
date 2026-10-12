from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .auth import create_access_token, get_current_user
from .db import Base, engine, get_db
from .logic import (
    CONFIRM_SECONDS,
    apply_reading,
    evaluate_all_zones,
    map_color,
    watch_remaining,
)
from .models import Event, Notification, Sensor, User, Warehouse, Zone
from .placement import MAP_HEIGHT, MAP_WIDTH
from .schemas import (
    EventOut,
    LoginIn,
    MapOut,
    MapSensorPoint,
    MapZone,
    NotificationOut,
    ResolveEventIn,
    SensorOut,
    SensorReadingIn,
    StatsOut,
    TokenOut,
    UserOut,
    WarehouseOut,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

TAGS_METADATA = [
    {
        "name": "1. Авторизация",
        "description": (
            "Логин и текущий пользователь. "
            "После `POST /api/login` нажмите **Authorize** и вставьте `access_token` "
            "(или `Bearer <token>`). Учётки: `duty`/`duty`, `admin`/`admin`."
        ),
    },
    {
        "name": "2. Карта и склады",
        "description": (
            "Схема складов А/Б и датчиков на карте. "
            "Цвета: green — ок, gray — offline, red — тревога."
        ),
    },
    {
        "name": "3. Протокол датчиков",
        "description": (
            "Приём показаний с датчиков по HTTP. **JWT не нужен**. "
            "Тело: `{\"value\": 72.5, \"online\": true}`."
        ),
    },
    {
        "name": "4. Наблюдение и пожар",
        "description": (
            "Логика 1/2/3 датчиков. "
            "1 → ложное; 2 → окно наблюдения; 3 → сразу пожар. "
            "`force=true` в check — как будто окно уже истекло."
        ),
    },
    {
        "name": "5. Уведомления",
        "description": "Уведомления дежурному (`duty`) и пожарной (`fire_dept`).",
    },
    {
        "name": "6. События",
        "description": (
            "Журнал событий и закрытие дежурным: "
            "`confirmed_fire` / `confirmed_false`."
        ),
    },
    {
        "name": "7. Статистика",
        "description": "Ложные vs подтверждённые пожары (сравнение со старым протоколом).",
    },
    {
        "name": "8. Служебное",
        "description": "Краткая справка по API.",
    },
]

app = FastAPI(
    title="Мониторинг складов / пожарные датчики",
    description="""
## Оглавление

1. **Авторизация** — логин JWT, текущий пользователь  
2. **Карта и склады** — карта, склады, список датчиков  
3. **Протокол датчиков** — приём показаний по IP (без JWT)  
4. **Наблюдение и пожар** — окно при 2 из 3, эскалация  
5. **Уведомления** — дежурный и пожарная  
6. **События** — журнал и подтверждение  
7. **Статистика** — ложные / подтверждённые  

**Как пользоваться Swagger:**  
`POST /api/login` → скопировать `access_token` → кнопка **Authorize** → вставить токен → вызывать защищённые методы.
""",
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def seed(db: Session) -> None:
    if db.query(User).first():
        return

    db.add_all(
        [
            User(username="admin", role="admin", password="admin"),
            User(username="duty", role="duty", password="duty"),
        ]
    )

    wh_a = Warehouse(
        name="Склад А",
        description="Левый склад",
        map_x=70,
        map_y=60,
    )
    wh_b = Warehouse(
        name="Склад Б",
        description="Правый склад",
        map_x=320,
        map_y=60,
    )
    db.add_all([wh_a, wh_b])
    db.flush()

    zone_a = Zone(
        warehouse_id=wh_a.id,
        name="Зона 1.1",
        description="Склад А — контроль",
        map_x=90,
        map_y=100,
    )
    zone_b = Zone(
        warehouse_id=wh_b.id,
        name="Зона 2.1",
        description="Склад Б — контроль",
        map_x=340,
        map_y=100,
    )
    db.add_all([zone_a, zone_b])
    db.flush()

    db.add_all(
        [
            Sensor(
                zone_id=zone_a.id,
                sensor_type="temperature",
                name="Датчик 1.1-T",
                ip="192.168.1.11",
                threshold=60.0,
                map_x=110,
                map_y=150,
            ),
            Sensor(
                zone_id=zone_a.id,
                sensor_type="oxygen",
                name="Датчик 1.1-O2",
                ip="192.168.1.12",
                threshold=18.0,
                map_x=180,
                map_y=220,
            ),
            Sensor(
                zone_id=zone_a.id,
                sensor_type="smoke",
                name="Датчик 1.1-S",
                ip="192.168.1.13",
                threshold=50.0,
                map_x=80,
                map_y=280,
            ),
            Sensor(
                zone_id=zone_b.id,
                sensor_type="temperature",
                name="Датчик 2.1-T",
                ip="192.168.1.21",
                threshold=60.0,
                map_x=360,
                map_y=160,
            ),
            Sensor(
                zone_id=zone_b.id,
                sensor_type="oxygen",
                name="Датчик 2.1-O2",
                ip="192.168.1.22",
                threshold=18.0,
                map_x=430,
                map_y=230,
            ),
            Sensor(
                zone_id=zone_b.id,
                sensor_type="smoke",
                name="Датчик 2.1-S",
                ip="192.168.1.23",
                threshold=50.0,
                map_x=300,
                map_y=300,
            ),
        ]
    )
    db.commit()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        seed(db)
    finally:
        db.close()


def sensor_out(s: Sensor) -> SensorOut:
    return SensorOut(
        id=s.id,
        zone_id=s.zone_id,
        sensor_type=s.sensor_type,
        name=s.name,
        ip=s.ip,
        status=s.status,
        last_value=s.last_value,
        last_seen=s.last_seen,
        threshold=s.threshold,
        map_x=s.map_x,
        map_y=s.map_y,
        map_color=map_color(s.status),
    )


# ---------- 1. Авторизация ----------


@app.post(
    "/api/login",
    response_model=TokenOut,
    tags=["1. Авторизация"],
    summary="Логин → JWT",
)
def login(data: LoginIn, db: Session = Depends(get_db)):
    """Логин → JWT. Дальше: **Authorize** в Swagger или заголовок `Authorization: Bearer <token>`."""
    user = (
        db.query(User)
        .filter(User.username == data.username, User.password == data.password)
        .first()
    )
    if not user:
        raise HTTPException(401, "Неверный логин или пароль")
    token = create_access_token(user)
    return TokenOut(access_token=token, user=user)


@app.get(
    "/api/me",
    response_model=UserOut,
    tags=["1. Авторизация"],
    summary="Текущий пользователь",
)
def me(user: User = Depends(get_current_user)):
    """Кто вошёл по токену."""
    return user


# ---------- 2. Карта и склады ----------


@app.get(
    "/api/map",
    response_model=MapOut,
    tags=["2. Карта и склады"],
    summary="Карта складов и датчиков",
)
def get_map(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Склады, зоны (таймер наблюдения), датчики с координатами и цветом."""
    evaluate_all_zones(db)
    warehouses = db.query(Warehouse).all()
    points: list[MapSensorPoint] = []
    for s in db.query(Sensor).all():
        zone = db.get(Zone, s.zone_id)
        wh = db.get(Warehouse, zone.warehouse_id) if zone else None
        points.append(
            MapSensorPoint(
                sensor_id=s.id,
                zone_id=s.zone_id,
                zone_name=zone.name if zone else "",
                warehouse_id=wh.id if wh else 0,
                warehouse_name=wh.name if wh else "",
                name=s.name,
                sensor_type=s.sensor_type,
                status=s.status,
                map_color=map_color(s.status),
                map_x=s.map_x,
                map_y=s.map_y,
                last_value=s.last_value,
                description=zone.description if zone else "",
            )
        )
    zones_out: list[MapZone] = []
    for zone in db.query(Zone).all():
        alarmed = sum(1 for s in zone.sensors if s.status == "alarm")
        zones_out.append(
            MapZone(
                id=zone.id,
                warehouse_id=zone.warehouse_id,
                name=zone.name,
                alarmed_count=alarmed,
                state=_zone_state(zone),
                watch_remaining_sec=watch_remaining(zone),
            )
        )
    return MapOut(
        map_width=MAP_WIDTH,
        map_height=MAP_HEIGHT,
        confirm_seconds=CONFIRM_SECONDS,
        warehouses=warehouses,
        zones=zones_out,
        sensors=points,
    )


@app.get(
    "/api/warehouses",
    response_model=list[WarehouseOut],
    tags=["2. Карта и склады"],
    summary="Список складов",
)
def list_warehouses(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Warehouse).all()


@app.get(
    "/api/sensors",
    response_model=list[SensorOut],
    tags=["2. Карта и склады"],
    summary="Список датчиков",
)
def list_sensors(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return [sensor_out(s) for s in db.query(Sensor).all()]


# ---------- 3. Протокол датчиков ----------


@app.post(
    "/api/ingest/{ip}",
    response_model=SensorOut,
    tags=["3. Протокол датчиков"],
    summary="Показание по IP датчика",
)
def ingest_by_ip(
    ip: str,
    data: SensorReadingIn,
    db: Session = Depends(get_db),
):
    """Приём по IP (как в реальном протоколе). JWT не нужен."""
    sensor = db.query(Sensor).filter(Sensor.ip == ip).first()
    if not sensor:
        raise HTTPException(404, f"Датчик с IP {ip} не найден")
    sensor = apply_reading(db, sensor, data.value, data.online)
    return sensor_out(sensor)


@app.post(
    "/api/sensors/{sensor_id}/reading",
    response_model=SensorOut,
    tags=["3. Протокол датчиков"],
    summary="Показание по id датчика",
)
def sensor_reading(
    sensor_id: int,
    data: SensorReadingIn,
    db: Session = Depends(get_db),
):
    """
    Датчик шлёт показания напрямую. JWT не нужен.

    Пример тела: `{"value": 72.5, "online": true}`
    """
    sensor = db.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Датчик не найден")
    sensor = apply_reading(db, sensor, data.value, data.online)
    return sensor_out(sensor)


# ---------- 4. Наблюдение и пожар ----------


def _zone_state(zone: Zone) -> str:
    alarmed = sum(1 for s in zone.sensors if s.status == "alarm")
    if alarmed >= 3:
        return "fire"
    if alarmed == 2:
        return "watch"
    if alarmed == 1:
        return "false"
    return "ok"


@app.post(
    "/api/watch/check",
    tags=["4. Наблюдение и пожар"],
    summary="Пересчитать окна наблюдения",
)
def watch_check(
    force: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """`force=true` — как будто время окна уже прошло (эскалация в пожар при 2 из 3)."""
    evaluate_all_zones(db, force_timeout=force)
    return {"ok": True, "force": force, "confirm_seconds": CONFIRM_SECONDS}


# ---------- 5. Уведомления ----------


@app.get(
    "/api/notifications",
    response_model=list[NotificationOut],
    tags=["5. Уведомления"],
    summary="Список уведомлений",
)
def list_notifications(
    target: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """`target=duty` или `target=fire_dept`. Без параметра дежурный видит только свои."""
    q = db.query(Notification).order_by(Notification.id.desc())
    if target:
        q = q.filter(Notification.target == target)
    elif user.role == "duty":
        q = q.filter(Notification.target == "duty")
    return q.limit(50).all()


@app.post(
    "/api/notifications/{notification_id}/read",
    response_model=NotificationOut,
    tags=["5. Уведомления"],
    summary="Отметить уведомление прочитанным",
)
def read_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    n = db.get(Notification, notification_id)
    if not n:
        raise HTTPException(404, "Уведомление не найдено")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n


# ---------- 6. События ----------


@app.get(
    "/api/events",
    response_model=list[EventOut],
    tags=["6. События"],
    summary="Журнал событий",
)
def list_events(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Типы: `false_alarm`, `watch`, `fire_signal`, `sensor_offline`."""
    return db.query(Event).order_by(Event.id.desc()).all()


@app.post(
    "/api/events/{event_id}/resolve",
    response_model=EventOut,
    tags=["6. События"],
    summary="Подтвердить пожар или ложное",
)
def resolve_event(
    event_id: int,
    data: ResolveEventIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Дежурный после выезда: `confirmed_fire` или `confirmed_false`."""
    if user.role not in ("duty", "admin"):
        raise HTTPException(403, "Только дежурный или админ")
    if data.resolution not in ("confirmed_fire", "confirmed_false"):
        raise HTTPException(400, "resolution: confirmed_fire | confirmed_false")

    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(404, "Событие не найдено")
    if ev.resolution != "open":
        raise HTTPException(400, "Событие уже закрыто")

    ev.resolution = data.resolution
    db.commit()
    db.refresh(ev)
    return ev


# ---------- 7. Статистика ----------


@app.get(
    "/api/stats",
    response_model=StatsOut,
    tags=["7. Статистика"],
    summary="Ложные vs подтверждённые",
)
def stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Сравнение с старым протоколом: доля ложных срабатываний."""
    fire_signals = (
        db.query(Event).filter(Event.event_type == "fire_signal").count()
    )
    confirmed = (
        db.query(Event).filter(Event.resolution == "confirmed_fire").count()
    )
    false_ones = (
        db.query(Event)
        .filter(
            (Event.event_type == "false_alarm")
            | (Event.resolution == "confirmed_false")
        )
        .count()
    )
    total = confirmed + false_ones
    rate = (false_ones / total * 100) if total else 0.0
    return StatsOut(
        total_fire_signals=fire_signals,
        confirmed_fires=confirmed,
        false_alarms=false_ones,
        false_alarm_rate=round(rate, 1),
    )


# ---------- UI / служебное ----------


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui/")


@app.get("/ui", include_in_schema=False)
@app.get("/ui/", include_in_schema=False)
def ui_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get(
    "/api",
    tags=["8. Служебное"],
    summary="Краткая справка",
)
def api_info():
    return {
        "ok": True,
        "ui": "/ui/",
        "docs": "/docs",
        "users": {
            "admin / admin": "просмотр карты и событий",
            "duty / duty": "дежурный — карта, уведомления, подтверждение пожара",
        },
        "auth": "POST /api/login → access_token → Authorization: Bearer <token>",
    }


app.mount("/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui-static")
