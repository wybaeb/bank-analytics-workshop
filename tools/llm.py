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


def _tls():
    """Что передать в `verify` при обращении к GigaChat.

    Сертификат GigaChat подписан НУЦ Минцифры, а на учебной машине этой цепочки
    обычно нет — поэтому по умолчанию проверка выключена, иначе первое же
    обращение падает и практика останавливается на установке сертификатов.

    В корпоративном контуре так оставлять нельзя: поставьте сертификаты и
    укажите `GIGACHAT_CA_BUNDLE` (путь к файлу с цепочкой) либо
    `GIGACHAT_VERIFY=1`, если цепочка уже в системном хранилище.
    """
    bundle = os.environ.get("GIGACHAT_CA_BUNDLE", "").strip()
    if bundle:
        return bundle
    return os.environ.get("GIGACHAT_VERIFY", "").strip().lower() in ("1", "true", "yes")


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
            verify=_tls(), timeout=60,
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
                        json=body, verify=_tls(), timeout=300,
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
            log: Callable[[str], None] = print,
            force_first: str | None = None) -> tuple[str, list[dict]]:
        """Диалог с инструментами.

        `functions` — описания в формате JSON Schema (name, description, parameters).
        `call_tool(name, arguments)` — выполняет инструмент и возвращает результат.
        `force_first` — имя инструмента, который ассистент обязан вызвать первым
        шагом. Без этого модель иногда «пересказывает» вызов текстом вместо того,
        чтобы действительно сходить в данные.

        Возвращает финальный текст ответа и полную ленту сообщений.
        """
        # GigaChat всё ещё принимает legacy functions/function_call.
        # OpenAI-совместимые роутеры (agentplatform.ru, OpenRouter, свежий OpenAI)
        # legacy формат игнорируют — модель отвечает текстом «не могу вызвать».
        # Поэтому для openai-пути отправляем новый tools/tool_choice.
        messages = list(messages)
        for step in range(max_steps):
            body = {"model": self.model, "messages": messages,
                    "temperature": self.temperature}
            if self.backend == "gigachat":
                body["functions"] = functions
                body["function_call"] = (
                    {"name": force_first} if (step == 0 and force_first) else "auto"
                )
            else:
                body["tools"] = [{"type": "function", "function": f} for f in functions]
                body["tool_choice"] = (
                    {"type": "function", "function": {"name": force_first}}
                    if (step == 0 and force_first) else "auto"
                )

            message = self._post(body)["choices"][0]["message"]
            calls = self._extract_calls(message)

            if not calls:
                messages.append({"role": "assistant",
                                 "content": message.get("content", "") or ""})
                return message.get("content", "") or "", messages

            # Собираем ответ ассистента в формате того же протокола, в котором получили.
            if self.backend == "gigachat":
                one = calls[0]
                messages.append({"role": "assistant", "content": message.get("content", ""),
                                 "function_call": {"name": one["name"],
                                                   "arguments": one["arguments_obj"]}})
            else:
                messages.append({"role": "assistant",
                                 "content": message.get("content"),
                                 "tool_calls": [{"id": c["id"], "type": "function",
                                                 "function": {"name": c["name"],
                                                              "arguments": c["arguments_str"]}}
                                                for c in calls]})

            for c in calls:
                log(f"  шаг {step + 1}: {c['name']}("
                    f"{', '.join(f'{k}=…' for k in c['arguments_obj'])})")
                try:
                    result = call_tool(c["name"], c["arguments_obj"])
                except Exception as exc:
                    result = {"error": str(exc)}
                payload = json.dumps(result, ensure_ascii=False, default=str)[:12000]
                if self.backend == "gigachat":
                    messages.append({"role": "function", "name": c["name"], "content": payload})
                else:
                    messages.append({"role": "tool", "tool_call_id": c["id"],
                                     "name": c["name"], "content": payload})

        return "Ассистент не уложился в отведённое число шагов.", messages

    @staticmethod
    def _extract_calls(message: dict) -> list[dict]:
        """Единый вид вызовов инструмента для обоих протоколов."""
        calls: list[dict] = []
        for tc in message.get("tool_calls") or []:                # OpenAI новый
            fn = tc.get("function", {})
            raw = fn.get("arguments", "{}")
            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
            calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""),
                          "arguments_obj": args,
                          "arguments_str": raw if isinstance(raw, str)
                          else json.dumps(args, ensure_ascii=False)})
        if calls:
            return calls
        fc = message.get("function_call")                          # OpenAI/GigaChat legacy
        if fc:
            raw = fc.get("arguments", {})
            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
            calls.append({"id": "", "name": fc.get("name", ""),
                          "arguments_obj": args,
                          "arguments_str": raw if isinstance(raw, str)
                          else json.dumps(args, ensure_ascii=False)})
        return calls
