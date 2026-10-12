from datetime import datetime

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class WarehouseOut(BaseModel):
    id: int
    name: str
    description: str = ""
    map_x: float = 0.0
    map_y: float = 0.0

    model_config = {"from_attributes": True}


class SensorOut(BaseModel):
    id: int
    zone_id: int
    sensor_type: str
    name: str
    ip: str
    status: str
    last_value: float | None
    last_seen: datetime | None
    threshold: float
    map_x: float
    map_y: float
    # цвет на карте: green | gray | red
    map_color: str = "green"

    model_config = {"from_attributes": True}


class SensorReadingIn(BaseModel):
    """Данные, которые датчик шлёт по HTTP со своего IP."""

    value: float
    # ok | offline — датчик сам может сообщить о проблеме
    online: bool = True


class EventOut(BaseModel):
    id: int
    zone_id: int
    event_type: str
    message: str
    sound: str
    sent_to_fire_dept: bool
    resolution: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ResolveEventIn(BaseModel):
    # confirmed_fire | confirmed_false
    resolution: str


class NotificationOut(BaseModel):
    id: int
    event_id: int
    target: str
    title: str
    body: str
    sound: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MapSensorPoint(BaseModel):
    sensor_id: int
    zone_id: int
    zone_name: str
    warehouse_id: int
    warehouse_name: str
    name: str
    sensor_type: str
    status: str
    map_color: str
    map_x: float
    map_y: float
    last_value: float | None
    description: str


class MapZone(BaseModel):
    id: int
    warehouse_id: int
    name: str
    alarmed_count: int
    state: str
    watch_remaining_sec: int | None = None


class MapOut(BaseModel):
    map_width: float
    map_height: float
    confirm_seconds: int
    warehouses: list[WarehouseOut]
    zones: list[MapZone]
    sensors: list[MapSensorPoint]


class StatsOut(BaseModel):
    total_fire_signals: int
    confirmed_fires: int
    false_alarms: int
    false_alarm_rate: float
