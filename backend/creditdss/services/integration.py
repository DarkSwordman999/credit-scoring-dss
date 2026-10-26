"""Адаптеры внешних систем (ПР 7-8: АдаптерБКИ, АдаптерАБС; Р-4 — подключение источников через адаптеры).

Режим demo — встроенные имитаторы бюро кредитных историй и АБС: ответ строится детерминированно по паспорту,
поэтому для одного клиента он всегда одинаков. Режим http — запрос к API по адресу из параметров системы
в формате JSON (docs/INTEGRATION.md). Функции этого модуля не обращаются к БД: их можно вызывать параллельно.
"""
import hashlib
import random
from dataclasses import dataclass

import httpx


class Unavailable(Exception):
    """Внешний сервис недоступен — запрос нужно повторить позже."""


@dataclass
class Subject:
    last_name: str
    first_name: str
    middle_name: str
    birth_date: str
    passport_series: str
    passport_number: str

    def seed(self, salt: str) -> int:
        key = f"{salt}:{self.passport_series}{self.passport_number}:{self.birth_date}"
        return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)


# ---------------------------------------------------------------- БКИ

def bki_report(subject: Subject, consent: dict, mode: str = "demo", url: str = "", failure_rate: float = 0.0,
               timeout: float = 20.0) -> dict | None:
    """Кредитный отчёт или None, если субъект в бюро не найден. Unavailable — сервис недоступен (С-3)."""
    if mode == "http":
        try:
            r = httpx.post(url, json={"subject": subject.__dict__, "consent": consent}, timeout=timeout)
        except httpx.HTTPError as e:
            raise Unavailable(f"БКИ недоступно: {e}") from e
        if r.status_code == 404:
            return None
        if r.status_code >= 500:
            raise Unavailable(f"БКИ: ошибка {r.status_code}")
        r.raise_for_status()
        return _normalize_report(r.json())
    if failure_rate and random.random() < failure_rate:
        raise Unavailable("БКИ: сервис временно недоступен (имитация)")
    return demo_bki(subject)


def _normalize_report(d: dict) -> dict:
    keys = ("loans_count", "active_loans", "total_debt", "monthly_payments", "max_dpd", "current_dpd",
            "dpd30_12m", "inquiries_6m", "history_months", "bankruptcy")
    out = {k: d.get(k, 0) for k in keys}
    out["bankruptcy"] = bool(d.get("bankruptcy", False))
    out["raw"] = d
    return out


def demo_bki(subject: Subject) -> dict | None:
    rnd = random.Random(subject.seed("bki"))
    if rnd.random() < 0.08:          # у части клиентов кредитной истории нет
        return None
    risky = rnd.random() < 0.18
    history = rnd.randint(6, 180)
    loans = rnd.randint(1, 8)
    active = min(loans, rnd.choice([0, 1, 1, 2, 2, 3, 4]) + (1 if risky and rnd.random() < 0.5 else 0))
    payments = sum(rnd.choice([3000, 5000, 8000, 12000, 18000, 25000]) for _ in range(active))
    debt = payments * rnd.randint(8, 30)
    max_dpd = rnd.choice([0, 0, 0, 0, 5, 15, 35, 95]) if not risky else rnd.choice([0, 15, 35, 65, 95, 120])
    current = rnd.choice([0] * 12 + [10, 35]) if risky else 0
    dpd30 = 0 if max_dpd < 30 else rnd.choice([0, 1, 1, 2, 3]) if risky else rnd.choice([0, 0, 1])
    inquiries = rnd.choice([0, 1, 1, 2, 2, 3, 4, 6]) + (rnd.randint(2, 6) if risky else 0)
    report = {"loans_count": loans, "active_loans": active, "total_debt": debt, "monthly_payments": payments,
              "max_dpd": max_dpd, "current_dpd": current, "dpd30_12m": dpd30, "inquiries_6m": inquiries,
              "history_months": history, "bankruptcy": risky and rnd.random() < 0.05,
              "bureau": "Имитатор БКИ"}
    return _normalize_report(report)


# ---------------------------------------------------------------- АБС

def abs_client(subject: Subject, mode: str = "demo", url: str = "", timeout: float = 20.0) -> dict:
    """Данные о клиенте в Банке: счета, зарплатные поступления, действующие кредиты (С-4)."""
    if mode == "http":
        try:
            r = httpx.post(url, json={"subject": subject.__dict__}, timeout=timeout)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise Unavailable(f"АБС недоступна: {e}") from e
        return _normalize_abs(r.json())
    return demo_abs(subject)


def _normalize_abs(d: dict) -> dict:
    out = {"is_client": bool(d.get("is_client", False)), "salary_project": bool(d.get("salary_project", False))}
    for k in ("client_since_months", "accounts_count", "bank_loans_count"):
        out[k] = int(d.get(k) or 0)
    for k in ("salary_avg", "deposits_balance", "bank_monthly_payments"):
        out[k] = float(d.get(k) or 0)
    out["raw"] = d
    return out


def demo_abs(subject: Subject) -> dict:
    rnd = random.Random(subject.seed("abs"))
    if rnd.random() < 0.55:
        return _normalize_abs({"is_client": False, "system": "Имитатор АБС"})
    salary = rnd.random() < 0.5
    return _normalize_abs({
        "is_client": True, "client_since_months": rnd.randint(1, 120), "salary_project": salary,
        "salary_avg": rnd.choice([35000, 45000, 60000, 80000, 110000, 150000]) if salary else 0,
        "accounts_count": rnd.randint(1, 4), "deposits_balance": rnd.choice([0, 0, 15000, 50000, 200000, 600000]),
        "bank_loans_count": rnd.choice([0, 0, 1, 2]), "bank_monthly_payments": rnd.choice([0, 0, 6000, 12000]),
        "system": "Имитатор АБС",
    })


def abs_send_approved(payload: dict, mode: str = "demo", url: str = "", timeout: float = 20.0) -> str:
    """Передача одобренной заявки в АБС для оформления договора. Возвращает номер договора."""
    if mode == "http":
        try:
            r = httpx.post(url.rstrip("/") + "/contracts", json=payload, timeout=timeout)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise Unavailable(f"АБС недоступна: {e}") from e
        return str(r.json().get("contract_number", ""))
    return "КД-" + payload["number"].removeprefix("КЗ-")


# ---------------------------------------------------------------- проверки

def verify(subject: Subject, stoplist: list[dict]) -> dict[str, tuple[bool, str]]:
    """Проверка паспорта по базе недействительных паспортов, перечня Росфинмониторинга и внутреннего
    стоп-листа (ПР 5-6, работа 2.3). stoplist — записи таблицы stoplist."""
    full = f"{subject.last_name} {subject.first_name} {subject.middle_name}".strip().lower()
    result = {"passport": (True, "паспорт действителен"), "rosfin": (True, "в перечне не найден"),
              "stoplist": (True, "в стоп-листе не найден")}
    keys = {"invalid_passport": "passport", "rosfin": "rosfin", "internal": "stoplist"}
    for e in stoplist:
        key = keys.get(e["source"])
        if key is None:
            continue
        by_passport = e["passport_series"] and e["passport_series"] == subject.passport_series \
            and e["passport_number"] == subject.passport_number
        by_name = e["source"] != "invalid_passport" and e["full_name"] and e["full_name"].strip().lower() == full \
            and (not e.get("birth_date") or e["birth_date"] == subject.birth_date)
        if by_passport or by_name:
            text = {"passport": "паспорт в базе недействительных паспортов", "rosfin": "найден в перечне Росфинмониторинга",
                    "stoplist": "найден во внутреннем стоп-листе Банка"}[key]
            result[key] = (False, f"{text}: {e['reason']}" if e.get("reason") else text)
    return result
