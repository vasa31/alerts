from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .auth import create_access_token, get_current_user, require_admin
from .db import Base, engine, get_db
from .logic import apply_reading, map_color
from .models import Event, Notification, Sensor, User, Warehouse, Zone
from .placement import MAP_HEIGHT, MAP_WIDTH, place_sensor, place_warehouse
from .schemas import (
    EventOut,
    LoginIn,
    MapOut,
    MapSensorPoint,
    NotificationOut,
    ResolveEventIn,
    SensorIn,
    SensorOut,
    SensorReadingIn,
    StatsOut,
    TokenOut,
    UserOut,
    WarehouseIn,
    WarehouseOut,
    ZoneIn,
    ZoneOut,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Мониторинг складов / пожарные датчики",
    description=(
        "Личный кабинет: админ добавляет склады и датчики, "
        "дежурный (role=duty) смотрит карту и уведомления. "
        "Авторизация: JWT Bearer token."
    ),
    version="1.0.0",
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


# ---------- auth ----------


@app.post("/api/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    """Логин → JWT. Дальше: Authorization: Bearer <access_token>"""
    user = (
        db.query(User)
        .filter(User.username == data.username, User.password == data.password)
        .first()
    )
    if not user:
        raise HTTPException(401, "Неверный логин или пароль")
    token = create_access_token(user)
    return TokenOut(access_token=token, user=user)


@app.get("/api/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# ---------- admin: склады / зоны / датчики ----------


@app.post("/api/warehouses", response_model=WarehouseOut)
def create_warehouse(
    data: WarehouseIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    prefer = (data.map_x, data.map_y) if data.map_x or data.map_y else None
    x, y = place_warehouse(db, prefer)
    wh = Warehouse(
        name=data.name,
        description=data.description,
        map_x=x,
        map_y=y,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@app.get("/api/warehouses", response_model=list[WarehouseOut])
def list_warehouses(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Warehouse).all()


@app.post("/api/zones", response_model=ZoneOut)
def create_zone(
    data: ZoneIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    wh = db.get(Warehouse, data.warehouse_id)
    if not wh:
        raise HTTPException(404, "Склад не найден")
    prefer = (data.map_x, data.map_y) if data.map_x or data.map_y else (wh.map_x + 40, wh.map_y + 40)
    x, y = place_sensor(db, near=(wh.map_x, wh.map_y), prefer=prefer)
    zone = Zone(
        warehouse_id=data.warehouse_id,
        name=data.name,
        description=data.description,
        map_x=x,
        map_y=y,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@app.get("/api/zones", response_model=list[ZoneOut])
def list_zones(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Zone).all()


@app.post("/api/sensors", response_model=SensorOut)
def create_sensor(
    data: SensorIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if data.sensor_type not in ("temperature", "oxygen", "smoke"):
        raise HTTPException(400, "sensor_type: temperature | oxygen | smoke")
    zone = db.get(Zone, data.zone_id)
    if not zone:
        raise HTTPException(404, "Зона не найдена")
    prefer = (data.map_x, data.map_y) if data.map_x or data.map_y else None
    x, y = place_sensor(db, near=(zone.map_x, zone.map_y), prefer=prefer)
    payload = data.model_dump()
    payload["map_x"] = x
    payload["map_y"] = y
    s = Sensor(**payload)
    db.add(s)
    db.commit()
    db.refresh(s)
    return sensor_out(s)


@app.get("/api/sensors", response_model=list[SensorOut])
def list_sensors(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return [sensor_out(s) for s in db.query(Sensor).all()]


# ---------- протокол датчика: приём данных по HTTP (без JWT) ----------


@app.post("/api/sensors/{sensor_id}/reading", response_model=SensorOut)
def sensor_reading(
    sensor_id: int,
    data: SensorReadingIn,
    db: Session = Depends(get_db),
):
    """
    Эндпоинт, на который датчик шлёт показания со своего IP.
    JWT не нужен — датчик пишет напрямую.

    Пример тела:
    {"value": 72.5, "online": true}
    """
    sensor = db.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Датчик не найден")
    sensor = apply_reading(db, sensor, data.value, data.online)
    return sensor_out(sensor)


@app.post("/api/ingest/{ip}", response_model=SensorOut)
def ingest_by_ip(
    ip: str,
    data: SensorReadingIn,
    db: Session = Depends(get_db),
):
    """Альтернатива: приём по IP датчика (как в реальном протоколе)."""
    sensor = db.query(Sensor).filter(Sensor.ip == ip).first()
    if not sensor:
        raise HTTPException(404, f"Датчик с IP {ip} не найден")
    sensor = apply_reading(db, sensor, data.value, data.online)
    return sensor_out(sensor)


# ---------- карта для дежурного ----------


@app.get("/api/map", response_model=MapOut)
def get_map(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
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
    return MapOut(
        map_width=MAP_WIDTH,
        map_height=MAP_HEIGHT,
        warehouses=warehouses,
        sensors=points,
    )


# ---------- уведомления и события ----------


@app.get("/api/notifications", response_model=list[NotificationOut])
def list_notifications(
    target: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Notification).order_by(Notification.id.desc())
    if target:
        q = q.filter(Notification.target == target)
    elif user.role == "duty":
        q = q.filter(Notification.target == "duty")
    return q.limit(50).all()


@app.post("/api/notifications/{notification_id}/read", response_model=NotificationOut)
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


@app.get("/api/events", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Event).order_by(Event.id.desc()).all()


@app.post("/api/events/{event_id}/resolve", response_model=EventOut)
def resolve_event(
    event_id: int,
    data: ResolveEventIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Дежурный подтверждает: реальный пожар или ложное срабатывание."""
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


@app.get("/api/stats", response_model=StatsOut)
def stats(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Сравнение с старым протоколом: ложные vs подтверждённые пожары."""
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


@app.get("/")
def root():
    return RedirectResponse(url="/ui/")


@app.get("/ui")
@app.get("/ui/")
def ui_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api")
def api_info():
    return {
        "ok": True,
        "ui": "/ui/",
        "docs": "/docs",
        "users": {
            "admin / admin": "администратор — склады, зоны, датчики",
            "duty / duty": "дежурный — карта, уведомления, подтверждение пожара",
        },
        "auth": "POST /api/login → access_token → Authorization: Bearer <token>",
    }


app.mount("/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui-static")
