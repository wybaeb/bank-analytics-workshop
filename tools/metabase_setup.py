#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Первичная настройка системы дашбордов: администратор и подключение к базе.

Скрипт идемпотентный: повторный запуск ничего не ломает и не дублирует.
Карточки и дашборды не создаёт — их собирают руками на занятии и агентом
из тетради, это и есть содержание практики.

    python3 tools/metabase_setup.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MB_URL = os.getenv("MB_URL", "http://localhost:3000")
MB_USER = os.getenv("MB_USER", "workshop@example.local")
MB_PASS = os.getenv("MB_PASS", "WorkshopBI2026!")
DB_LABEL = os.getenv("MB_DB_NAME", "Учебная база банка")

# Адрес базы изнутри docker-сети, в которой живёт Metabase.
DB_DETAILS = {
    "host": os.getenv("MB_PG_HOST", "db"),
    "port": int(os.getenv("MB_PG_PORT", "5432")),
    "dbname": os.getenv("MB_PG_DB", "bank_training"),
    "user": os.getenv("MB_PG_USER", "bank_user"),
    "password": os.getenv("MB_PG_PASSWORD", "bank_pass"),
    "ssl": False,
    "tunnel-enabled": False,
}

RUNTIME_PATH = Path(__file__).resolve().parent.parent / "artifacts" / "stand.json"


def api(path: str, method: str = "GET", payload: dict | None = None,
        session: str | None = None, timeout: int = 60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{MB_URL}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("X-Metabase-Session", session)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    return json.loads(body) if body else {}


def wait_ready(minutes: int = 7) -> None:
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        try:
            api("/api/health", timeout=10)
            return
        except Exception:
            time.sleep(5)
    raise TimeoutError("Система дашбордов не поднялась. Проверьте `docker compose ps`.")


def first_run_setup() -> bool:
    props = api("/api/session/properties")
    token = props.get("setup-token")
    if props.get("has-user-setup") or not token:
        return False
    api("/api/setup", "POST", {
        "token": token,
        "prefs": {"allow_tracking": False, "site_name": "Учебный стенд"},
        "user": {"first_name": "Учебный", "last_name": "Стенд",
                 "email": MB_USER, "password": MB_PASS, "site_name": "Учебный стенд"},
        "database": {"engine": "postgres", "name": DB_LABEL, "is_full_sync": True,
                     "auto_run_queries": True, "details": DB_DETAILS},
    })
    time.sleep(5)
    return True


def login() -> str:
    return api("/api/session", "POST", {"username": MB_USER, "password": MB_PASS})["id"]


def ensure_database(session: str) -> int:
    payload = api("/api/database", session=session)
    items = payload if isinstance(payload, list) else payload.get("data", [])
    for db in items:
        if db.get("name") == DB_LABEL:
            return db["id"]
    created = api("/api/database", "POST", {
        "engine": "postgres", "name": DB_LABEL, "is_full_sync": True,
        "auto_run_queries": True, "details": DB_DETAILS,
    }, session=session)
    return created["id"]


def sync(session: str, db_id: int) -> None:
    for path in (f"/api/database/{db_id}/sync_schema", f"/api/database/{db_id}/rescan_values"):
        try:
            api(path, "POST", {}, session=session)
        except urllib.error.HTTPError:
            pass


def tables(session: str, db_id: int) -> list[str]:
    meta = api(f"/api/database/{db_id}/metadata", session=session)
    return sorted(t["name"] for t in meta.get("tables", []))


def main() -> None:
    wait_ready()
    fresh = first_run_setup()
    session = login()
    db_id = ensure_database(session)
    sync(session, db_id)

    names: list[str] = []
    for _ in range(20):          # синхронизация схемы идёт в фоне
        names = tables(session, db_id)
        if len(names) >= 6:
            break
        time.sleep(3)

    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(json.dumps({
        "url": MB_URL, "user": MB_USER, "database_id": db_id,
        "database_label": DB_LABEL, "tables": names,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(("Стенд настроен впервые." if fresh else "Стенд уже был настроен, проверка пройдена."))
    print(f"Адрес:  {MB_URL}")
    print(f"Логин:  {MB_USER}")
    print(f"Пароль: {MB_PASS}   (учебный пароль локального стенда, не секрет)")
    print(f"Источник «{DB_LABEL}» (id={db_id}), видно объектов: {len(names)}")
    for n in names:
        print(f"  · {n}")


if __name__ == "__main__":
    main()
