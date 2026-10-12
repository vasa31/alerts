"""Логика зоны: 3 датчика (температура, кислород, дым)."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .models import Event, Notification, Sensor, Zone

# В демо короткое окно, чтобы проверить кнопками.
# На складе поставьте 300 (5 минут).
CONFIRM_SECONDS = 15


def map_color(status: str) -> str:
    if status == "alarm":
        return "red"
    if status == "offline":
        return "gray"
    return "green"


def is_alarm_value(sensor: Sensor, value: float) -> bool:
    if sensor.sensor_type == "oxygen":
        return value < sensor.threshold
    return value > sensor.threshold


def create_notification(
    db: Session,
    event: Event,
    target: str,
    title: str,
    body: str,
) -> Notification:
    n = Notification(
        event_id=event.id,
        target=target,
        title=title,
        body=body,
        sound=event.sound,
    )
    db.add(n)
    return n


def _open_event(db: Session, zone_id: int, event_type: str) -> Event | None:
    return (
        db.query(Event)
        .filter(
            Event.zone_id == zone_id,
            Event.event_type == event_type,
            Event.resolution == "open",
        )
        .first()
    )


def _sensor_names(sensors: list[Sensor]) -> str:
    return ", ".join(
        f"{s.name}={s.last_value} ({s.sensor_type})" for s in sensors
    )


def _emit(
    db: Session,
    zone: Zone,
    event_type: str,
    message: str,
    sound: str,
    sent_to_fire_dept: bool,
    duty_title: str,
    fire_title: str | None = None,
) -> Event:
    ev = Event(
        zone_id=zone.id,
        event_type=event_type,
        message=message,
        sound=sound,
        sent_to_fire_dept=sent_to_fire_dept,
    )
    db.add(ev)
    db.flush()
    create_notification(db, ev, "duty", duty_title, message)
    if sent_to_fire_dept and fire_title:
        create_notification(db, ev, "fire_dept", fire_title, message)
    return ev


def _close(ev: Event, resolution: str) -> None:
    ev.resolution = resolution


def _escalate_to_fire(db: Session, zone: Zone, alarmed: list[Sensor], why: str) -> Event:
    watch = _open_event(db, zone.id, "watch")
    if watch:
        _close(watch, "closed")

    existing = _open_event(db, zone.id, "fire_signal")
    if existing:
        zone.watch_started_at = None
        return existing

    names = _sensor_names(alarmed)
    msg = (
        f"ПОЖАР: зона «{zone.name}» — {why}. "
        f"Сработали {len(alarmed)} датчика: {names}. "
        f"Координаты зоны: x={zone.map_x}, y={zone.map_y}"
    )
    zone.watch_started_at = None
    return _emit(
        db,
        zone,
        "fire_signal",
        msg,
        "sharp",
        True,
        "ПОЖАР!",
        "Вызов: пожар на складе",
    )


def evaluate_zone(db: Session, zone: Zone, force_timeout: bool = False) -> Event | None:
    """
    1 датчик в alarm → ложное (звук soft), в пожарную не шлём.
    2 датчика → окно наблюдения CONFIRM_SECONDS.
      ещё мигают после окна → пожар.
      затихли раньше → пожара нет.
    3 датчика → сразу пожар (все типы согласны).
    """
    sensors = list(zone.sensors)
    if not sensors:
        return None

    working = [s for s in sensors if s.status != "offline"]
    offline = [s for s in sensors if s.status == "offline"]
    alarmed = [s for s in sensors if s.status == "alarm"]
    now = datetime.utcnow()

    if offline and len(working) >= 1:
        msg = (
            f"Зона «{zone.name}»: работает {len(working)} из {len(sensors)}. "
            "Проверьте датчик(и): "
            + ", ".join(f"{s.name} ({s.sensor_type}, {s.ip})" for s in offline)
        )
        if not _open_event(db, zone.id, "sensor_offline"):
            ev = _emit(db, zone, "sensor_offline", msg, "soft", False, "Датчик не работает")
            db.commit()
            db.refresh(ev)
            return ev

    if _open_event(db, zone.id, "fire_signal"):
        return _open_event(db, zone.id, "fire_signal")

    # 3 из 3 — сразу пожар
    if len(alarmed) >= 3:
        ev = _escalate_to_fire(db, zone, alarmed, "сработали все 3 датчика")
        db.commit()
        db.refresh(ev)
        return ev

    watch = _open_event(db, zone.id, "watch")

    # 2 из 3 — наблюдаем
    if len(alarmed) == 2:
        if not watch:
            fa = _open_event(db, zone.id, "false_alarm")
            if fa:
                _close(fa, "closed")
            zone.watch_started_at = now
            until = now + timedelta(seconds=CONFIRM_SECONDS)
            msg = (
                f"Наблюдение: зона «{zone.name}» — мигают 2 из 3: "
                f"{_sensor_names(alarmed)}. "
                f"Если через {CONFIRM_SECONDS} сек всё ещё тревога — это пожар. "
                f"Если затихнут — пожара нет. Окно до {until.isoformat()}Z"
            )
            ev = _emit(db, zone, "watch", msg, "soft", False, "Наблюдение (2 из 3)")
            db.commit()
            db.refresh(ev)
            return ev

        started = zone.watch_started_at or watch.created_at
        elapsed = (now - started).total_seconds()
        if force_timeout or elapsed >= CONFIRM_SECONDS:
            ev = _escalate_to_fire(
                db,
                zone,
                alarmed,
                f"2 датчика держат тревогу дольше {CONFIRM_SECONDS} сек",
            )
            db.commit()
            db.refresh(ev)
            return ev
        return watch

    # 0 или 1 — если шло наблюдение, тревога снялась
    if watch:
        zone.watch_started_at = None
        if len(alarmed) == 0:
            _close(watch, "confirmed_false")
            watch.message += " → затихли, пожара нет."
            create_notification(
                db,
                watch,
                "duty",
                "Пожара нет",
                f"Зона «{zone.name}»: 2 датчика затихли до конца окна.",
            )
        else:
            s = alarmed[0]
            _close(watch, "confirmed_false")
            watch.message += f" → остался 1 датчик ({s.name}), пожара нет."
            create_notification(
                db,
                watch,
                "duty",
                "Пожара нет (остался 1)",
                f"Зона «{zone.name}»: после наблюдения активен только {s.name}.",
            )
        db.commit()
        db.refresh(watch)
        return watch

    if len(alarmed) == 1:
        s = alarmed[0]
        msg = (
            f"Ложное (1 из 3): зона «{zone.name}», "
            f"датчик {s.name} ({s.sensor_type}) значение={s.last_value}"
        )
        exists = _open_event(db, zone.id, "false_alarm")
        if exists:
            return exists
        ev = _emit(db, zone, "false_alarm", msg, "soft", False, "Ложное срабатывание")
        db.commit()
        db.refresh(ev)
        return ev

    return None


def evaluate_all_zones(db: Session, force_timeout: bool = False) -> None:
    for zone in db.query(Zone).all():
        evaluate_zone(db, zone, force_timeout=force_timeout)


def apply_reading(
    db: Session,
    sensor: Sensor,
    value: float,
    online: bool,
) -> Sensor:
    sensor.last_seen = datetime.utcnow()
    if not online:
        sensor.status = "offline"
        sensor.last_value = value
    else:
        sensor.last_value = value
        sensor.status = "alarm" if is_alarm_value(sensor, value) else "ok"

    db.add(sensor)
    db.commit()
    db.refresh(sensor)

    zone = db.get(Zone, sensor.zone_id)
    if zone:
        evaluate_zone(db, zone)
        db.refresh(sensor)

    return sensor


def watch_remaining(zone: Zone) -> int | None:
    if not zone.watch_started_at:
        return None
    left = CONFIRM_SECONDS - (datetime.utcnow() - zone.watch_started_at).total_seconds()
    return max(0, int(left))
