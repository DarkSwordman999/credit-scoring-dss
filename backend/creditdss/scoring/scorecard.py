"""Скоринговая карта: баллы по характеристикам заёмщика, перевод балла в вероятность дефолта (PD), вклад факторов.

Балл = базовые баллы + сумма баллов по характеристикам. Чем больше балл, тем ниже риск.
PD получается из балла по стандартной для скоринговых карт калибровке: каждые PDO баллов удваивают
отношение «хороших» заёмщиков к «плохим», а базовому баллу соответствует базовое отношение:
    шансы = base_odds · 2^((балл − base_score) / pdo),   PD = 1 / (1 + шансы).

Вклад характеристики (С-9) — отклонение её баллов от нейтрального значения (середины диапазона баллов
этой характеристики): положительный вклад снижает оценку риска, отрицательный — повышает.
"""
import copy
import math

from .features import LABELS, display

INF = None   # открытая граница интервала


def _num(feature, label, bins):
    return {"feature": feature, "label": label, "type": "numeric",
            "bins": [{"min": a, "max": b, "points": p, "text": t} for a, b, p, t in bins]}


def _cat(feature, label, bins, default_points=0, default_text="прочее"):
    return {"feature": feature, "label": label, "type": "category", "default_points": default_points,
            "default_text": default_text,
            "bins": [{"values": v, "points": p, "text": t} for v, p, t in bins]}


# Экспертная скоринговая карта — базовая (резервная) методика оценки. Её версия 1 публикуется при создании БД;
# риск-аналитик меняет баллы в новых версиях и проверяет их на истории выданных кредитов (С-13, С-14).
DEFAULT_SCORECARD: dict = {
    "base_points": 300,
    "base_score": 600,
    "base_odds": 50,
    "pdo": 20,
    "characteristics": [
        _num("age", "Возраст", [
            (INF, 23, 5, "моложе 23 лет"), (23, 30, 20, "23–29 лет"), (30, 45, 35, "30–44 года"),
            (45, 60, 40, "45–59 лет"), (60, INF, 25, "60 лет и старше")]),
        _num("experience_months", "Стаж на текущем месте", [
            (INF, 6, 0, "менее 6 месяцев"), (6, 12, 12, "от 6 до 12 месяцев"), (12, 36, 25, "от 1 до 3 лет"),
            (36, INF, 38, "более 3 лет")]),
        _num("income", "Доход", [
            (INF, 25000, 0, "менее 25 тыс. руб. в месяц"), (25000, 50000, 15, "25–50 тыс. руб. в месяц"),
            (50000, 100000, 28, "50–100 тыс. руб. в месяц"), (100000, INF, 38, "более 100 тыс. руб. в месяц")]),
        _num("pdn", "Долговая нагрузка (ПДН)", [
            (INF, 0.3, 45, "низкая: менее 30 % дохода"), (0.3, 0.5, 30, "умеренная: 30–50 % дохода"),
            (0.5, 0.7, 12, "высокая: 50–70 % дохода"), (0.7, INF, 0, "очень высокая: более 70 % дохода")]),
        _num("history_months", "Кредитная история", [
            (INF, 1, 10, "кредитной истории нет"), (1, 12, 5, "короткая: менее года"),
            (12, 36, 20, "от 1 до 3 лет"), (36, INF, 32, "длинная: более 3 лет")]),
        _num("max_dpd", "Просрочки в прошлом", [
            (INF, 1, 40, "просрочек не было"), (1, 30, 25, "были короткие просрочки до 30 дней"),
            (30, 90, 5, "была просрочка 30–89 дней"), (90, INF, -10, "была просрочка 90 дней и более")]),
        _num("dpd30_12m", "Просрочки 30+ дней за последний год", [
            (INF, 1, 30, "не было"), (1, 2, 10, "одна"), (2, INF, -5, "две и более")]),
        _num("inquiries_6m", "Запросы кредитной истории за 6 месяцев", [
            (INF, 3, 25, "мало: до 2"), (3, 6, 12, "3–5 запросов"), (6, INF, 0, "много: 6 и более")]),
        _num("active_loans", "Действующие кредиты", [
            (INF, 1, 18, "нет"), (1, 3, 25, "1–2 кредита"), (3, 5, 10, "3–4 кредита"), (5, INF, 0, "5 и более")]),
        _cat("salary_project", "Зарплатный проект Банка", [
            ([True], 25, "получает зарплату на карту Банка")], default_points=0, default_text="зарплата в другом банке"),
        _cat("housing", "Жильё", [
            (["own"], 20, "собственное жильё"), (["mortgage"], 15, "жильё в ипотеке"),
            (["parents"], 8, "живёт с родителями"), (["rent"], 0, "арендует жильё")]),
        _cat("education", "Образование", [
            (["higher"], 18, "высшее"), (["secondary_special"], 8, "среднее специальное"),
            (["secondary"], 0, "среднее")]),
        _num("amount_to_income", "Сумма кредита к годовому доходу", [
            (INF, 0.5, 25, "менее половины годового дохода"), (0.5, 1, 15, "от половины до годового дохода"),
            (1, 2, 5, "1–2 годовых дохода"), (2, INF, 0, "более двух годовых доходов")]),
        _num("client_since_months", "Отношения с Банком", [
            (INF, 1, 0, "новый клиент"), (1, 24, 8, "клиент менее 2 лет"), (24, INF, 18, "клиент 2 года и более")]),
    ],
}


def default_params() -> dict:
    return copy.deepcopy(DEFAULT_SCORECARD)


def _match(ch: dict, value) -> tuple[float, str]:
    if ch["type"] == "numeric":
        v = float(value)
        for b in ch["bins"]:
            lo, hi = b.get("min"), b.get("max")
            if (lo is None or v >= lo) and (hi is None or v < hi):
                return b["points"], b["text"]
        return 0, "вне диапазона"
    for b in ch["bins"]:
        if value in b["values"]:
            return b["points"], b["text"]
    return ch.get("default_points", 0), ch.get("default_text", "прочее")


def neutral(ch: dict) -> float:
    pts = [b["points"] for b in ch["bins"]]
    if ch["type"] == "category":
        pts.append(ch.get("default_points", 0))
    return (min(pts) + max(pts)) / 2


def score(params: dict, features: dict) -> tuple[float, list[dict]]:
    """Балл и разбивка по характеристикам."""
    total = float(params["base_points"])
    parts = []
    for ch in params["characteristics"]:
        name = ch["feature"]
        value = features.get(name)
        pts, text = _match(ch, value)
        total += pts
        parts.append({"feature": name, "label": ch["label"], "value": display(name, value), "bin": text,
                      "points": pts, "contribution": round(pts - neutral(ch), 2)})
    return total, parts


def pd_from_score(params: dict, s: float) -> float:
    odds = params["base_odds"] * 2 ** ((s - params["base_score"]) / params["pdo"])
    return 1 / (1 + odds)


def explain(parts: list[dict], n: int = 5) -> list[dict]:
    """Пять факторов, сильнее всего повысивших оценку риска, и пять — сильнее всего понизивших (С-9)."""
    neg = sorted((p for p in parts if p["contribution"] < 0), key=lambda p: p["contribution"])[:n]
    pos = sorted((p for p in parts if p["contribution"] > 0), key=lambda p: -p["contribution"])[:n]
    out = []
    for p in neg:
        out.append({**p, "effect": "risk_up", "text": f"{p['label']}: {p['bin']} — повышает риск"})
    for p in pos:
        out.append({**p, "effect": "risk_down", "text": f"{p['label']}: {p['bin']} — снижает риск"})
    return out


def validate(params: dict) -> list[str]:
    """Проверка структуры версии методики перед сохранением."""
    errors = []
    for k in ("base_points", "base_score", "base_odds", "pdo"):
        if not isinstance(params.get(k), (int, float)):
            errors.append(f"не задан параметр {k}")
    if isinstance(params.get("pdo"), (int, float)) and params["pdo"] <= 0:
        errors.append("PDO должен быть больше нуля")
    if isinstance(params.get("base_odds"), (int, float)) and params["base_odds"] <= 0:
        errors.append("базовые шансы должны быть больше нуля")
    chars = params.get("characteristics")
    if not isinstance(chars, list) or not chars:
        return errors + ["нет характеристик"]
    for ch in chars:
        name = ch.get("feature")
        if name not in LABELS:
            errors.append(f"неизвестный признак {name}")
            continue
        bins = ch.get("bins") or []
        if not bins:
            errors.append(f"{ch.get('label', name)}: нет интервалов")
        for b in bins:
            if not isinstance(b.get("points"), (int, float)) or math.isnan(b["points"]):
                errors.append(f"{ch.get('label', name)}: у интервала «{b.get('text', '')}» не заданы баллы")
        if ch.get("type") == "numeric":
            for a, b in zip(bins, bins[1:]):
                if a.get("max") != b.get("min"):
                    errors.append(f"{ch.get('label', name)}: интервалы должны идти подряд без пропусков")
                    break
            if bins and (bins[0].get("min") is not None or bins[-1].get("max") is not None):
                errors.append(f"{ch.get('label', name)}: крайние интервалы должны быть открытыми")
    return errors
