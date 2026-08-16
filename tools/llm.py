#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тонкий клиент ассистента для тетрадей практики.

Основной путь — GigaChat. Запасной — любой ассистент с OpenAI-совместимым
интерфейсом (заполните AI_PROVIDER_URL и AI_PROVIDER_TOKEN).

Ключи берутся только из окружения или из файла `.env` рядом с этим репозиторием
и нигде не печатаются.

Интерфейс один на оба пути:

    from tools.llm import Assistant
    a = Assistant()
    a.ask("Привет")                       # один вопрос — один ответ
    a.run(messages, functions, call_tool)  # диалог с вызовом инструментов
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parent.parent
GIGA_OAUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGA_BASE = "https://gigachat.devices.sberbank.ru/api/v1"


def load_env(path: Path | None = None) -> None:
    """Простое чтение .env — чтобы тетрадь работала без внешних библиотек."""
    env = path or ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_env()


class Assistant:
    """Ассистент с поддержкой вызова инструментов."""

    def __init__(self, model: str | None = None, temperature: float = 0.1):
        self.temperature = temperature
        self.gigachat_key = os.environ.get("GIGACHAT_AUTH_KEY", "").strip()
        self.provider_url = os.environ.get("AI_PROVIDER_URL", "").strip()
        self.provider_token = os.environ.get("AI_PROVIDER_TOKEN", "").strip()

        forced = os.environ.get("ASSISTANT_BACKEND", "").strip().lower()
        use_giga = bool(self.gigachat_key) if forced != "openai" else False
        if use_giga:
            self.backend = "gigachat"
            self.model = model or os.environ.get("GIGACHAT_MODEL", "GigaChat-2-Max")
        elif self.provider_url and self.provider_token:
            self.backend = "openai"
            self.model = model or os.environ.get("AI_PROVIDER_MODEL", "gpt-4o-mini")
        else:
            raise SystemExit(
                "Не задан ключ ассистента. Скопируйте .env.example в .env и заполните "
                "GIGACHAT_AUTH_KEY (или AI_PROVIDER_URL + AI_PROVIDER_TOKEN)."
            )
        self._token = {"value": None, "exp": 0.0}

    # ------------------------------------------------------------ транспорт

    def _giga_token(self) -> str:
        if self._token["value"] and time.time() < self._token["exp"] - 60:
            return str(self._token["value"])
        r = requests.post(
            GIGA_OAUTH,
            headers={"Authorization": "Basic " + self.gigachat_key,
                     "RqUID": str(uuid.uuid4()),
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"scope": os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")},
            verify=False, timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        self._token["value"] = data["access_token"]
        self._token["exp"] = data.get("expires_at", 0) / 1000 or time.time() + 1500
        return str(self._token["value"])

    def _post(self, body: dict, retries: int = 4) -> dict:
        last = None
        for attempt in range(retries):
            try:
                if self.backend == "gigachat":
                    r = requests.post(
                        f"{GIGA_BASE}/chat/completions",
                        headers={"Authorization": "Bearer " + self._giga_token(),
                                 "Content-Type": "application/json"},
                        json=body, verify=False, timeout=300,
                    )
                else:
                    r = requests.post(
                        f"{self.provider_url.rstrip('/')}/chat/completions",
                        headers={"Authorization": "Bearer " + self.provider_token,
                                 "Content-Type": "application/json"},
                        json=body, timeout=300,
                    )
                if r.status_code == 200:
                    return r.json()
                last = f"{r.status_code}: {r.text[:300]}"
            except Exception as exc:                       # сеть моргнула — повторим
                last = str(exc)
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"Ассистент не ответил: {last}")

    # -------------------------------------------------------------- запросы

    def ask(self, prompt: str, system: str | None = None) -> str:
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        body = {"model": self.model, "messages": messages, "temperature": self.temperature}
        return self._post(body)["choices"][0]["message"]["content"]

    def run(self, messages: list[dict], functions: list[dict],
            call_tool: Callable[[str, dict], object], max_steps: int = 12,
            log: Callable[[str], None] = print) -> tuple[str, list[dict]]:
        """Диалог с инструментами.

        `functions` — описания в формате JSON Schema (name, description, parameters).
        `call_tool(name, arguments)` — выполняет инструмент и возвращает результат.
        Возвращает финальный текст ответа и полную ленту сообщений.
        """
        messages = list(messages)
        for step in range(max_steps):
            body = {"model": self.model, "messages": messages,
                    "temperature": self.temperature, "functions": functions,
                    "function_call": "auto"}
            message = self._post(body)["choices"][0]["message"]
            call = message.get("function_call")

            if not call:
                messages.append({"role": "assistant", "content": message.get("content", "")})
                return message.get("content", ""), messages

            name = call["name"]
            raw_args = call.get("arguments", {})
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            log(f"  шаг {step + 1}: {name}({', '.join(f'{k}=…' for k in args)})")

            # GigaChat ждёт аргументы объектом, OpenAI-совместимый путь — строкой.
            echo_args = args if self.backend == "gigachat" else json.dumps(args, ensure_ascii=False)
            messages.append({"role": "assistant", "content": message.get("content", ""),
                             "function_call": {"name": name, "arguments": echo_args}})
            try:
                result = call_tool(name, args)
            except Exception as exc:
                result = {"error": str(exc)}
            messages.append({"role": "function", "name": name,
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:12000]})

        return "Ассистент не уложился в отведённое число шагов.", messages
