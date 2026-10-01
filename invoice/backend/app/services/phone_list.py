
from __future__ import annotations

import re
from typing import List


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    # "8707..." (обычная бытовая запись KZ/RU-номера с внутренним префиксом 8)
    # и "+7707..."/"7707..." — один и тот же номер. Без этой замены они
    # нормализовались в разные строки, и, например, assert_phone_allowed_for_counterparty
    # мог отклонить настоящий номер получателя как "чужой" (см. аудит от 2026-08-25).
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return digits
    if len(digits) == 10:
        return "7" + digits
    return digits


def split_phone_values(raw: str | None) -> List[str]:
    if not raw:
        return []
    parts = re.split(r"[;,/\n]+", raw)
    unique: List[str] = []
    for part in parts:
        value = (part or "").strip()
        if not value:
            continue
        if value not in unique:
            unique.append(value)
    return unique


def join_phone_values(phones: List[str]) -> str:
    unique: List[str] = []
    for phone in phones:
        value = (phone or "").strip()
        if not value:
            continue
        if value not in unique:
            unique.append(value)
    return ";".join(unique)


def normalized_phone_set(raw: str | None) -> set[str]:
    result: set[str] = set()
    for value in split_phone_values(raw):
        normalized = normalize_phone(value)
        if normalized:
            result.add(normalized)
    return result
