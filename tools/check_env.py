#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка окружения: что подключено, чего не хватает.

Запускается до первой тетради — и на своей машине, и в JupyterHub:

    python3 tools/check_env.py

Печатает состояние по четырём направлениям: библиотеки, переменные окружения,
база данных, ассистент и система дашбордов. Значения ключей и паролей
не печатаются никогда — только факт «задана» и длина строки: этого достаточно,
чтобы понять, подставилась переменная или нет, и безопасно показать вывод коллеге.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ОК, НЕТ, ВНИМ = "  ✓", "  ✗", "  •"

# Переменные, по которым тетради находят ключ, базу и дашборды. Второй элемент —
# обязательна ли переменная: без ключа ассистента работают только SQL-тетради.
ПЕРЕМЕННЫЕ = [
    ("GIGACHAT_AUTH_KEY", False, "ключ ассистента (Base64 из личного кабинета)"),
    ("GIGACHAT_SCOPE", False, "область ключа: PERS — личный, CORP — корпоративный"),
    ("GIGACHAT_MODEL", False, "модель ассистента"),
    ("AI_PROVIDER_URL", False, "запасной ассистент с OpenAI-совместимым интерфейсом"),
    ("AI_PROVIDER_TOKEN", False, "токен запасного ассистента"),
    ("PGHOST", True, "адрес базы"),
    ("PGPORT", True, "порт базы"),
    ("PGDATABASE", True, "имя базы"),
    ("PGUSER", True, "пользователь базы"),
    ("PGPASSWORD", True, "пароль базы"),
    ("MB_URL", False, "адрес системы дашбордов"),
]

СЕКРЕТНЫЕ = {"GIGACHAT_AUTH_KEY", "AI_PROVIDER_TOKEN", "PGPASSWORD", "MB_PASS"}

ЗНАЧЕНИЯ_ПО_УМОЛЧАНИЮ = {
    "PGHOST": "localhost", "PGPORT": "5433", "PGDATABASE": "bank_training",
    "PGUSER": "bank_user", "PGPASSWORD": "bank_pass",
    "MB_URL": "http://localhost:3000",
}


def _загрузить_env() -> str:
    """Читаем .env рядом с проектом — тем же способом, что и тетради."""
    env = ROOT / ".env"
    if not env.exists():
        return "файла .env нет — значения берутся из переменных окружения"
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    return f"прочитан {env}"


def библиотеки() -> bool:
    print("\nБиблиотеки")
    print(f"{ОК} Python {sys.version.split()[0]}")
    всё_на_месте = True
    for имя, зачем in [("psycopg2", "подключение к базе"),
                       ("pandas", "памятка SQL ↔ pandas"),
                       ("matplotlib", "графики"),
                       ("requests", "обращение к ассистенту"),
                       ("IPython", "тетради")]:
        try:
            модуль = __import__(имя)
            версия = getattr(модуль, "__version__", "")
            print(f"{ОК} {имя} {версия} — {зачем}")
        except ImportError:
            всё_на_месте = False
            print(f"{НЕТ} {имя} не установлен — {зачем}. "
                  f"Поставьте: pip install -r requirements.txt")
    return всё_на_месте


def переменные() -> None:
    print("\nПеременные окружения")
    for имя, обязательна, зачем in ПЕРЕМЕННЫЕ:
        значение = os.environ.get(имя, "").strip()
        if значение:
            # Значение не печатаем никогда: секретное — прячем целиком,
            # остальное показываем, потому что по нему и ищут ошибку.
            видимо = (f"задана, длина {len(значение)}" if имя in СЕКРЕТНЫЕ
                      else значение)
            print(f"{ОК} {имя} = {видимо}")
        elif имя in ЗНАЧЕНИЯ_ПО_УМОЛЧАНИЮ:
            print(f"{ВНИМ} {имя} не задана — будет "
                  f"{ЗНАЧЕНИЯ_ПО_УМОЛЧАНИЮ[имя]} ({зачем})")
        elif обязательна:
            print(f"{НЕТ} {имя} не задана — {зачем}")
        else:
            print(f"{ВНИМ} {имя} не задана — {зачем}")


def база() -> bool:
    print("\nБаза данных")
    try:
        import psycopg2
    except ImportError:
        print(f"{НЕТ} psycopg2 не установлен, проверить подключение нечем")
        return False

    хост = os.environ.get("PGHOST", "localhost")
    порт = int(os.environ.get("PGPORT", "5433"))
    имя = os.environ.get("PGDATABASE", "bank_training")
    try:
        conn = psycopg2.connect(
            host=хост, port=порт, dbname=имя,
            user=os.environ.get("PGUSER", "bank_user"),
            password=os.environ.get("PGPASSWORD", "bank_pass"),
            connect_timeout=5)
    except Exception as e:                                   # noqa: BLE001
        # Текст исключения psycopg2 не содержит пароля, но может содержать
        # строку подключения — печатаем только первую строку без параметров.
        причина = str(e).strip().splitlines()[0].split("password")[0]
        print(f"{НЕТ} {хост}:{порт}/{имя} — не подключиться: {причина}")
        print(f"{ВНИМ} стенд поднят? ./run.sh up · порт занят? ./run.sh status")
        return False

    with conn, conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(f"{ОК} {хост}:{порт}/{имя} — {cur.fetchone()[0].split(' on ')[0]}")
        cur.execute("""SELECT table_name FROM information_schema.tables
                       WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                       ORDER BY table_name""")
        таблицы = [r[0] for r in cur.fetchall()]
        if not таблицы:
            print(f"{НЕТ} в базе нет таблиц — данные не загрузились, "
                  f"пересоберите стенд: ./run.sh reset")
            conn.close()
            return False
        for t in таблицы:
            cur.execute(f'SELECT count(*) FROM "{t}"')
            print(f"{ОК} {t}: {cur.fetchone()[0]} строк")
    conn.close()
    return True


def ассистент() -> bool:
    print("\nАссистент")
    if not (os.environ.get("GIGACHAT_AUTH_KEY", "").strip()
            or os.environ.get("AI_PROVIDER_TOKEN", "").strip()):
        print(f"{ВНИМ} ключ не задан — SQL-тетради работают, "
              f"тетради с ассистентом нет")
        return False
    try:
        from tools.llm import Assistant
        клиент = Assistant()
        if клиент.backend == "gigachat":
            клиент._giga_token()                             # noqa: SLF001
            print(f"{ОК} GigaChat: токен получен, модель {клиент.model}")
        else:
            print(f"{ОК} OpenAI-совместимый шлюз, модель {клиент.model}")
        return True
    except Exception as e:                                   # noqa: BLE001
        причина = str(e).strip().splitlines()[0][:160]
        print(f"{НЕТ} ключ задан, но токен не получен: {причина}")
        print(f"{ВНИМ} частые причины: закрыт выход в интернет из контейнера; "
              f"не установлены сертификаты НУЦ Минцифры; ключ выдан "
              f"на другую область (GIGACHAT_SCOPE)")
        return False


def дашборды() -> bool:
    адрес = os.environ.get("MB_URL", "http://localhost:3000")
    print("\nСистема дашбордов")
    try:
        import requests
        r = requests.get(f"{адрес}/api/health", timeout=5)
        if r.status_code == 200:
            print(f"{ОК} {адрес} отвечает")
            return True
        print(f"{ВНИМ} {адрес} отвечает кодом {r.status_code} — "
              f"возможно, ещё запускается")
    except Exception:                                        # noqa: BLE001
        print(f"{ВНИМ} {адрес} недоступен — нужен только для кейсов с панелями")
    return False


def main() -> int:
    print("Проверка окружения практики")
    print(f"{ВНИМ} {_загрузить_env()}")
    print(f"{ВНИМ} рабочая папка: {ROOT}")
    print(f"{ВНИМ} имя машины: {socket.gethostname()}")

    есть_библиотеки = библиотеки()
    переменные()
    есть_база = база()
    есть_ассистент = ассистент()
    дашборды()

    print("\nИтог")
    if есть_библиотеки and есть_база and есть_ассистент:
        print(f"{ОК} всё на месте: можно открывать любую тетрадь практики")
        return 0
    if есть_библиотеки and есть_база:
        print(f"{ВНИМ} тетради с SQL работают; для тетрадей с ассистентом "
              f"нужен ключ")
        return 0
    print(f"{НЕТ} до запуска тетрадей нужно закрыть отмеченные пункты выше")
    return 1


if __name__ == "__main__":
    sys.exit(main())
