# -*- coding: utf-8 -*-
"""Сборка тетрадей из текста. Тетрадь — обычный JSON, собирать её скриптом
надёжнее, чем править руками: не съезжают номера ячеек и метаданные."""
from __future__ import annotations

import json
from pathlib import Path

_counter = {"n": 0}


def _cell_id() -> str:
    _counter["n"] += 1
    return f"c{_counter['n']:03d}"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "id": _cell_id(), "metadata": {}, "source": _lines(text)}


def code(src: str) -> dict:
    return {"cell_type": "code", "id": _cell_id(), "execution_count": None,
            "metadata": {}, "outputs": [], "source": _lines(src)}


def sql(query: str, magic: str = "%%sql") -> dict:
    return code(f"{magic}\n{query.strip()}")


def _lines(text: str) -> list[str]:
    text = text.strip("\n")
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


def write(path: str | Path, cells: list[dict]) -> None:
    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{p}: {len(cells)} ячеек")
