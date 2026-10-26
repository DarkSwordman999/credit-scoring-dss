"""Оценка заявки: стоп-факторы, ПДН, скоринговая карта, вероятность дефолта, класс риска, рекомендация."""
import math
from datetime import date

# Скоринговая карта: для каждой характеристики — интервалы (от, до) и баллы. Больше баллов — ниже риск.
SCORECARD = {
    "age": ("Возраст", [(0, 23, 5, "моложе 23 лет"), (23, 30, 20, "23–29 лет"), (30, 45, 35, "30–44 года"),
                        (45, 60, 40, "45–59 лет"), (60, 200, 25, "60 лет и старше")]),
    "experience": ("Стаж", [(0, 6, 0, "менее 6 месяцев"), (6, 12, 12, "от 6 до 12 месяцев"),
                            (12, 36, 25, "от 1 до 3 лет"), (36, 10000, 38, "более 3 лет")]),
    "income": ("Доход", [(0, 25000, 0, "менее 25 тыс. руб."), (25000, 50000, 15, "25–50 тыс. руб."),
                         (50000, 100000, 28, "50–100 тыс. руб."), (100000, 1e12, 38, "более 100 тыс. руб.")]),
    "pdn": ("Долговая нагрузка", [(0, 0.3, 45, "низкая: до 30 % дохода"), (0.3, 0.5, 30, "умеренная: 30–50 %"),
                                  (0.5, 0.7, 12, "высокая: 50–70 %"), (0.7, 100, 0, "очень высокая: более 70 %")]),
    "history_months": ("Кредитная история", [(0, 1, 10, "нет"), (1, 12, 5, "менее года"),
                                             (12, 36, 20, "от 1 до 3 лет"), (36, 10000, 32, "более 3 лет")]),
    "max_dpd": ("Просрочки в прошлом", [(0, 1, 40, "не было"), (1, 30, 25, "до 30 дней"),
                                        (30, 90, 5, "30–89 дней"), (90, 100000, -10, "90 дней и более")]),
    "inquiries": ("Запросы в БКИ за 6 мес.", [(0, 3, 25, "до 2"), (3, 6, 12, "3–5"), (6, 1000, 0, "6 и более")]),
}
BASE_POINTS = 400      # базовые баллы
BASE_SCORE = 600       # балл, которому соответствуют шансы 50:1 (50 «хороших» на одного «плохого»)
BASE_ODDS = 50
PDO = 20               # каждые 20 баллов удваивают шансы

# классы риска по вероятности дефолта: (класс, верхняя граница PD)
CLASSES = [("A", 0.02), ("B", 0.05), ("C", 0.10), ("D", 0.20), ("E", 1.01)]

# условия по классу риска: (множитель суммы, надбавка к ставке, предельный ПДН); None — отказ
CONDITIONS = {"A": (1.0, 0.0, 0.8), "B": (1.0, 1.0, 0.8), "C": (0.8, 3.0, 0.5), "D": (0.6, 6.0, 0.5), "E": None}


def age(birth_date: str, on: date) -> int:
    b = date.fromisoformat(birth_date)
    return on.year - b.year - ((on.month, on.day) < (b.month, b.day))


def annuity(amount: float, rate: float, months: int) -> float:
    """Ежемесячный аннуитетный платёж."""
    r = rate / 100 / 12
    return amount * r / (1 - (1 + r) ** -months)


def pdn(payments: float, amount: float, rate: float, term: int, income: float) -> float:
    """ПДН = (платежи по действующим кредитам + платёж по новому) / доход."""
    if income <= 0:
        return 9.99
    return (payments + annuity(amount, rate, term)) / income


def stop_factor(a: dict) -> str | None:
    """Формальные правила кредитной политики: сработало — сразу отказ."""
    if a["age"] < 21:
        return "Возраст заёмщика менее 21 года"
    if a["age"] + a["term"] / 12 > 70:
        return "Возраст на дату погашения более 70 лет"
    if a["current_dpd"] > 0:
        return "Текущая просрочка по кредитам"
    if a["pdn"] > 0.8:
        return "Долговая нагрузка (ПДН) больше 80 %"
    if a["income"] < 15000:
        return "Доход ниже 15 000 руб. в месяц"
    return None


def score(a: dict) -> tuple[float, list[dict]]:
    """Балл и вклад каждой характеристики (отклонение от середины её диапазона баллов)."""
    total = BASE_POINTS
    factors = []
    for key, (label, bins) in SCORECARD.items():
        value = a[key]
        points, text = next((p, t) for lo, hi, p, t in bins if lo <= value < hi)
        all_points = [p for _, _, p, _ in bins]
        middle = (min(all_points) + max(all_points)) / 2
        total += points
        factors.append({"label": label, "text": text, "points": points, "effect": points - middle})
    return total, factors


def pd_from_score(s: float) -> float:
    odds = BASE_ODDS * 2 ** ((s - BASE_SCORE) / PDO)
    return 1 / (1 + odds)


def risk_class(pd: float) -> str:
    return next(c for c, upper in CLASSES if pd < upper)


def evaluate(a: dict, product: dict) -> dict:
    """a — анкета: age, term, amount, income, experience, payments, max_dpd, current_dpd, inquiries, history_months.
    Возвращает оценку и рекомендацию."""
    a = dict(a, pdn=pdn(a["payments"], a["amount"], product["rate"], a["term"], a["income"]))
    result = {"pdn": round(a["pdn"], 4), "score": None, "pd": None, "risk_class": None, "factors": [],
              "stop_factor": stop_factor(a), "recommendation": "reject", "rec_amount": None, "rec_rate": None}
    if result["stop_factor"]:
        return result
    s, factors = score(a)
    pd = pd_from_score(s)
    cls = risk_class(pd)
    # три фактора, сильнее всего повысивших риск, и три — сильнее всего снизивших
    up = sorted((f for f in factors if f["effect"] < 0), key=lambda f: f["effect"])[:3]
    down = sorted((f for f in factors if f["effect"] > 0), key=lambda f: -f["effect"])[:3]
    result.update(score=s, pd=round(pd, 5), risk_class=cls, factors=up + down)
    cond = CONDITIONS[cls]
    if cond and a["pdn"] <= cond[2]:
        amount = max(product["min_amount"], math.floor(a["amount"] * cond[0] / 1000) * 1000)
        result.update(recommendation="approve", rec_amount=amount, rec_rate=round(product["rate"] + cond[1], 2))
    return result
