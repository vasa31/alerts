"""Логика оценки зоны: 3 датчика на точке контроля."""

from datetime import datetime

from sqlalchemy.orm import Session

from .models import Event, Notification, Sensor, Zone

# Пороги по умолчанию (если не заданы при создании):
# temperature > threshold °C
# oxygen < threshold % (мало кислорода — горение)
# smoke > threshold (задымление)


def map_color(status: str) -> str:
    if status == "alarm":
        return "red"
    if status == "offline":
        return "gray"
    return "green"


def is_alarm_value(sensor: Sensor, value: float) -> bool:
    if sensor.sensor_type == "oxygen":
        return value < sensor.threshold
    # temperature, smoke — превышение порога
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


def evaluate_zone(db: Session, zone: Zone) -> Event | None:
    """
    После каждого показания пересчитываем зону.

    - 2 или 3 датчика в alarm → fire_signal (+ в пожарную)
    - ровно 1 в alarm → false_alarm
    - есть offline при рабочих 2 → уведомление проверить датчик
    """
    sensors = list(zone.sensors)
    if not sensors:
        return None

    working = [s for s in sensors if s.status != "offline"]
    offline = [s for s in sensors if s.status == "offline"]
    alarmed = [s for s in sensors if s.status == "alarm"]

    # Если часть датчиков offline — мягкое уведомление
    if offline and len(working) >= 2:
        msg = (
            f"Зона «{zone.name}»: работает {len(working)} из {len(sensors)}. "
            f"Проверьте датчик(и): "
            + ", ".join(f"{s.name} ({s.sensor_type}, {s.ip})" for s in offline)
        )
        exists = (
            db.query(Event)
            .filter(
                Event.zone_id == zone.id,
                Event.event_type == "sensor_offline",
                Event.resolution == "open",
            )
            .first()
        )
        if not exists:
            ev = Event(
                zone_id=zone.id,
                event_type="sensor_offline",
                message=msg,
                sound="soft",
                sent_to_fire_dept=False,
            )
            db.add(ev)
            db.flush()
            create_notification(
                db,
                ev,
                "duty",
                "Датчик не работает",
                msg,
            )
            db.commit()
            db.refresh(ev)
            return ev

    if len(alarmed) >= 2:
        names = ", ".join(
            f"{s.name}={s.last_value} ({s.sensor_type})" for s in alarmed
        )
        msg = (
            f"ПОЖАР: зона «{zone.name}» — сработали {len(alarmed)} датчика: {names}. "
            f"Координаты: x={zone.map_x}, y={zone.map_y}"
        )
        open_fire = (
            db.query(Event)
            .filter(
                Event.zone_id == zone.id,
                Event.event_type == "fire_signal",
                Event.resolution == "open",
            )
            .first()
        )
        if open_fire:
            return open_fire

        ev = Event(
            zone_id=zone.id,
            event_type="fire_signal",
            message=msg,
            sound="sharp",
            sent_to_fire_dept=True,
        )
        db.add(ev)
        db.flush()
        create_notification(db, ev, "duty", "ПОЖАР!", msg)
        create_notification(
            db,
            ev,
            "fire_dept",
            "Вызов: пожар на складе",
            msg,
        )
        db.commit()
        db.refresh(ev)
        return ev

    if len(alarmed) == 1:
        s = alarmed[0]
        msg = (
            f"Ложное срабатывание (1 из 3): зона «{zone.name}», "
            f"датчик {s.name} ({s.sensor_type}) значение={s.last_value}"
        )
        exists = (
            db.query(Event)
            .filter(
                Event.zone_id == zone.id,
                Event.event_type == "false_alarm",
                Event.resolution == "open",
            )
            .first()
        )
        if exists:
            return exists

        ev = Event(
            zone_id=zone.id,
            event_type="false_alarm",
            message=msg,
            sound="soft",
            sent_to_fire_dept=False,
        )
        db.add(ev)
        db.flush()
        create_notification(db, ev, "duty", "Ложное срабатывание", msg)
        db.commit()
        db.refresh(ev)
        return ev

    return None


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
