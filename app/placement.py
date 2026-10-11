"""Расстановка складов и датчиков на карте без близкого наложения."""

from math import hypot

from sqlalchemy.orm import Session

from .models import Sensor, Warehouse, Zone

MAP_WIDTH = 500.0
MAP_HEIGHT = 400.0
MIN_DIST_SENSOR = 55.0
MIN_DIST_WAREHOUSE = 90.0
MARGIN = 40.0


def _occupied(db: Session) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for w in db.query(Warehouse).all():
        points.append((w.map_x, w.map_y))
    for z in db.query(Zone).all():
        points.append((z.map_x, z.map_y))
    for s in db.query(Sensor).all():
        points.append((s.map_x, s.map_y))
    return points


def _far_enough(
    x: float,
    y: float,
    occupied: list[tuple[float, float]],
    min_dist: float,
) -> bool:
    return all(hypot(x - ox, y - oy) >= min_dist for ox, oy in occupied)


def find_free_point(
    db: Session,
    min_dist: float = MIN_DIST_SENSOR,
    prefer: tuple[float, float] | None = None,
) -> tuple[float, float]:
    """Ищет свободную точку на карте. Если prefer задан и свободен — берём его."""
    occupied = _occupied(db)

    if prefer is not None:
        px, py = prefer
        if (
            MARGIN <= px <= MAP_WIDTH - MARGIN
            and MARGIN <= py <= MAP_HEIGHT - MARGIN
            and _far_enough(px, py, occupied, min_dist)
        ):
            return px, py

    # сетка по карте
    step = max(20.0, min_dist * 0.6)
    candidates: list[tuple[float, float]] = []
    y = MARGIN
    while y <= MAP_HEIGHT - MARGIN:
        x = MARGIN
        while x <= MAP_WIDTH - MARGIN:
            candidates.append((x, y))
            x += step
        y += step

    # чуть смещаем ряды, чтобы плотнее заполнять
    y = MARGIN + step / 2
    while y <= MAP_HEIGHT - MARGIN:
        x = MARGIN + step / 2
        while x <= MAP_WIDTH - MARGIN:
            candidates.append((x, y))
            x += step
        y += step

    if prefer is not None:
        px, py = prefer
        candidates.sort(key=lambda p: hypot(p[0] - px, p[1] - py))

    for x, y in candidates:
        if _far_enough(x, y, occupied, min_dist):
            return round(x, 1), round(y, 1)

    # запасной вариант — в конец списка с увеличенным сдвигом
    n = len(occupied) + 1
    return (
        round(MARGIN + (n * 37) % (MAP_WIDTH - 2 * MARGIN), 1),
        round(MARGIN + (n * 53) % (MAP_HEIGHT - 2 * MARGIN), 1),
    )


def place_warehouse(db: Session, prefer: tuple[float, float] | None = None) -> tuple[float, float]:
    return find_free_point(db, MIN_DIST_WAREHOUSE, prefer)


def place_sensor(
    db: Session,
    near: tuple[float, float] | None = None,
    prefer: tuple[float, float] | None = None,
) -> tuple[float, float]:
    return find_free_point(db, MIN_DIST_SENSOR, prefer or near)
