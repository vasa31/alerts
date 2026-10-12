from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # admin | duty (role 1 = дежурный)
    role: Mapped[str] = mapped_column(String(32), default="duty")
    password: Mapped[str] = mapped_column(String(128), default="1234")


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    # схема карты: координаты склада на общей карте
    map_x: Mapped[float] = mapped_column(Float, default=0.0)
    map_y: Mapped[float] = mapped_column(Float, default=0.0)

    zones: Mapped[list["Zone"]] = relationship(back_populates="warehouse")


class Zone(Base):
    """Точка контроля на складе. На точке стоят 3 датчика."""

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    map_x: Mapped[float] = mapped_column(Float, default=0.0)
    map_y: Mapped[float] = mapped_column(Float, default=0.0)
    watch_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    warehouse: Mapped["Warehouse"] = relationship(back_populates="zones")
    sensors: Mapped[list["Sensor"]] = relationship(back_populates="zone")
    events: Mapped[list["Event"]] = relationship(back_populates="zone")


class Sensor(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    # temperature | oxygen | smoke
    sensor_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    ip: Mapped[str] = mapped_column(String(64))
    # ok | offline | alarm
    status: Mapped[str] = mapped_column(String(32), default="ok")
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # порог срабатывания
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    # координаты на карте (свои, не зоны)
    map_x: Mapped[float] = mapped_column(Float, default=0.0)
    map_y: Mapped[float] = mapped_column(Float, default=0.0)

    zone: Mapped["Zone"] = relationship(back_populates="sensors")


class Event(Base):
    """Событие: пожар / ложное / датчик offline."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    # sensor_offline | false_alarm | fire_signal | fire_confirmed | false_confirmed
    event_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, default="")
    # soft | sharp — тип звука уведомления
    sound: Mapped[str] = mapped_column(String(32), default="soft")
    sent_to_fire_dept: Mapped[bool] = mapped_column(Boolean, default=False)
    # бот помечает пожар, когда сообщение ушло в Telegram
    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    # open | confirmed_fire | confirmed_false | closed
    resolution: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    zone: Mapped["Zone"] = relationship(back_populates="events")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    # duty | fire_dept
    target: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text, default="")
    sound: Mapped[str] = mapped_column(String(32), default="soft")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TelegramChat(Base):
    """Чат, который написал боту /start и получает пожары."""

    __tablename__ = "telegram_chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
