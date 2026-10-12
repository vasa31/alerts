"""Telegram-бот: /start подписывает чат, при пожаре шлёт сообщение."""

import logging
import os
import sys
import threading
import time

import httpx

from .db import SessionLocal, prepare_db
from .models import Event, TelegramChat

log = logging.getLogger("telegram")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"

_stop = threading.Event()
_drain_lock = threading.Lock()
_last_nosub_warn = 0.0


def _chat_title(chat: dict) -> str:
    name = " ".join(
        part for part in (chat.get("first_name"), chat.get("last_name")) if part
    ).strip()
    username = chat.get("username")
    if username and name:
        return f"{name} (@{username})"
    if username:
        return f"@{username}"
    return name or chat.get("title") or str(chat.get("id"))


def _active_chat_ids() -> list[int]:
    db = SessionLocal()
    try:
        rows = db.query(TelegramChat).filter(TelegramChat.active.is_(True)).all()
        return [row.chat_id for row in rows]
    finally:
        db.close()


def _save_chat(chat: dict, active: bool) -> None:
    chat_id = int(chat["id"])
    db = SessionLocal()
    try:
        row = db.query(TelegramChat).filter(TelegramChat.chat_id == chat_id).first()
        if row:
            row.active = active
            row.title = _chat_title(chat)
        else:
            db.add(
                TelegramChat(
                    chat_id=chat_id,
                    title=_chat_title(chat),
                    active=active,
                )
            )
        db.commit()
    finally:
        db.close()


def _deactivate(chat_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.query(TelegramChat).filter(TelegramChat.chat_id == chat_id).first()
        if row:
            row.active = False
            db.commit()
    finally:
        db.close()


def _send(client: httpx.Client, chat_id: int, text: str) -> bool:
    try:
        response = client.post(
            f"{API}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    except httpx.HTTPError:
        log.exception("Не удалось отправить сообщение в чат %s", chat_id)
        return False
    if response.status_code == 200:
        return True
    if response.status_code in (400, 403):
        log.warning("Чат %s недоступен: %s", chat_id, response.text)
        _deactivate(chat_id)
        return False
    log.error("Telegram %s: %s", response.status_code, response.text)
    return False


def deliver(text: str) -> bool:
    chat_ids = _active_chat_ids()
    if not chat_ids:
        return False
    delivered = False
    with httpx.Client(timeout=20.0) as client:
        for chat_id in chat_ids:
            if _send(client, chat_id, text):
                delivered = True
    return delivered


def _drain_fires() -> None:
    if not _drain_lock.acquire(blocking=False):
        return
    try:
        _drain_fires_locked()
    finally:
        _drain_lock.release()


def _drain_fires_locked() -> None:
    global _last_nosub_warn
    db = SessionLocal()
    try:
        pending = (
            db.query(Event)
            .filter(
                Event.event_type == "fire_signal",
                Event.telegram_sent.is_(False),
            )
            .order_by(Event.id)
            .all()
        )
        if not pending:
            return
        if not _active_chat_ids():
            now = time.monotonic()
            if now - _last_nosub_warn > 60:
                log.warning(
                    "Есть пожар, но нет подписчиков. Напишите боту /start"
                )
                _last_nosub_warn = now
            return
        for event in pending:
            if not deliver(event.message):
                return
            event.telegram_sent = True
            db.commit()
            log.info("Пожар #%s отправлен в Telegram", event.id)
    finally:
        db.close()


def _fire_loop() -> None:
    while not _stop.is_set():
        try:
            _drain_fires()
        except Exception:
            log.exception("Ошибка рассылки пожаров")
        _stop.wait(2)


def _command(text: str) -> str:
    if not text:
        return ""
    return text.split()[0].split("@")[0].lower()


def _handle(client: httpx.Client, update: dict) -> None:
    message = update.get("message") or {}
    chat = message.get("chat")
    if not chat:
        return
    command = _command((message.get("text") or "").strip())
    if command == "/start":
        _save_chat(chat, True)
        _send(
            client,
            chat["id"],
            "Подписка включена. Когда система зафиксирует пожар, сообщение придёт сюда.\n"
            "/stop — отписаться",
        )
        _drain_fires()
        return
    if command == "/stop":
        _save_chat(chat, False)
        _send(client, chat["id"], "Подписка выключена. Пожары больше не присылаю.")
        return
    _send(
        client,
        chat["id"],
        "Я присылаю уведомления о пожаре на складе.\n"
        "/start — подписаться\n"
        "/stop — отписаться",
    )


def _import_env_chats() -> None:
    raw = os.getenv("TELEGRAM_CHAT_IDS", "")
    for part in raw.split(","):
        part = part.strip()
        if not part or not part.lstrip("-").isdigit():
            continue
        _save_chat({"id": int(part), "title": part}, True)


def _poll() -> None:
    offset = None
    with httpx.Client(timeout=httpx.Timeout(40.0, connect=10.0)) as client:
        client.post(f"{API}/deleteWebhook", json={"drop_pending_updates": False})
        while not _stop.is_set():
            params: dict = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            try:
                response = client.get(f"{API}/getUpdates", params=params)
                response.raise_for_status()
                payload = response.json()
            except Exception:
                log.exception("Ошибка getUpdates, повтор через 5 с")
                _stop.wait(5)
                continue
            for update in payload.get("result") or []:
                offset = update["update_id"] + 1
                try:
                    _handle(client, update)
                except Exception:
                    log.exception("Не разобрал update %s", update.get("update_id"))


def _bot_username() -> str:
    with httpx.Client(timeout=20.0) as client:
        response = client.get(f"{API}/getMe")
        response.raise_for_status()
        return response.json()["result"].get("username") or ""


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not TOKEN:
        log.error("Задайте TELEGRAM_BOT_TOKEN")
        sys.exit(1)
    prepare_db()
    _import_env_chats()
    try:
        username = _bot_username()
    except Exception:
        log.exception("Telegram не принял токен")
        sys.exit(1)
    log.info("Бот @%s запущен. Подписка: /start", username)
    threading.Thread(target=_fire_loop, name="fire-watch", daemon=True).start()
    _poll()


if __name__ == "__main__":
    main()
