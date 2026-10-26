"""Параметры системы, которые меняют в интерфейсе (хранятся в таблице app_settings)."""
from sqlalchemy.orm import Session

from .errors import DomainError
from .models import AppSetting
from .scoring.engine import DEFAULT_CLASSES

DEFAULTS: dict = {
    # С-7: пороги PD для классов риска
    "risk_classes": DEFAULT_CLASSES,
    # С-3: режим интеграции с БКИ: demo — встроенный имитатор бюро, http — API бюро по адресу bki_url
    "bki_mode": "demo",
    "bki_url": "",
    "bki_retries": 3,
    "bki_retry_minutes": 5,
    # доля отказов имитатора БКИ (для проверки повторных запросов), 0–1
    "bki_demo_failure_rate": 0.0,
    # С-4: режим интеграции с АБС
    "abs_mode": "demo",
    "abs_url": "",
    # С-15: пороги мониторинга модели
    "psi_alert": 0.25,
    "gini_drop_alert": 0.10,
    # срок действия согласий по умолчанию, дней
    "consent_days": 90,
    # минимальная длина комментария, если решение отличается от рекомендации (С-11)
    "comment_min": 20,
}

LABELS = {
    "risk_classes": "Пороги PD классов риска",
    "bki_mode": "Режим интеграции с БКИ",
    "bki_url": "Адрес API бюро кредитных историй",
    "bki_retries": "Число попыток запроса в БКИ",
    "bki_retry_minutes": "Интервал повтора запроса в БКИ, мин.",
    "bki_demo_failure_rate": "Доля отказов имитатора БКИ",
    "abs_mode": "Режим интеграции с АБС",
    "abs_url": "Адрес API АБС",
    "psi_alert": "Порог оповещения по PSI",
    "gini_drop_alert": "Порог снижения Gini (доля)",
    "consent_days": "Срок действия согласий, дней",
    "comment_min": "Минимальная длина комментария к решению",
}


def get(db: Session, key: str):
    row = db.get(AppSetting, key)
    return DEFAULTS[key] if row is None else row.value


def all_(db: Session) -> dict:
    out = dict(DEFAULTS)
    for row in db.query(AppSetting).all():
        if row.key in DEFAULTS:
            out[row.key] = row.value
    return out


def _check(key: str, value):
    if key not in DEFAULTS:
        raise DomainError(f"Неизвестный параметр {key}")
    if key == "risk_classes":
        if not isinstance(value, list) or len(value) < 2:
            raise DomainError("Нужно не меньше двух классов риска")
        prev = 0.0
        for i, item in enumerate(value):
            if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str):
                raise DomainError("Класс риска задаётся парой [название, верхняя граница PD]")
            upper = item[1]
            last = i == len(value) - 1
            if last and upper is not None:
                raise DomainError("У последнего класса верхней границы нет")
            if not last and (not isinstance(upper, (int, float)) or not prev < upper <= 1):
                raise DomainError("Границы PD должны возрастать в пределах от 0 до 1")
            if not last:
                prev = upper
        return value
    if key in ("bki_mode", "abs_mode"):
        if value not in ("demo", "http"):
            raise DomainError("Режим: demo или http")
        return value
    if key in ("bki_url", "abs_url"):
        return str(value or "").strip()
    if key in ("bki_retries", "bki_retry_minutes", "consent_days", "comment_min"):
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise DomainError(f"{LABELS[key]}: нужно целое число")
        if v < 1 or v > 10000:
            raise DomainError(f"{LABELS[key]}: недопустимое значение")
        return v
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise DomainError(f"{LABELS[key]}: нужно число")
    if not 0 <= v <= 1:
        raise DomainError(f"{LABELS[key]}: от 0 до 1")
    return v


def set_(db: Session, key: str, value) -> object:
    value = _check(key, value)
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    return value
