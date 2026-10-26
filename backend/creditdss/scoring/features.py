"""Формирование признаков (ПР 5-6, работа 3.3; С-6): не менее 30 признаков анкеты, кредитной истории и данных АБС.

Досье — словарь с разделами application, client, employment, product, report, abs, checks (см. services/dossier.py).
"""
from datetime import date

# подписи признаков для карточки заявки и отчётов
LABELS: dict[str, str] = {
    "age": "Возраст, лет",
    "age_at_maturity": "Возраст на дату погашения, лет",
    "citizenship_rf": "Гражданство РФ",
    "employment_type": "Тип занятости",
    "experience_months": "Стаж на текущем месте, мес.",
    "income_confirmed": "Подтверждённый доход, руб./мес.",
    "income": "Доход для расчёта ПДН, руб./мес.",
    "dependents": "Иждивенцы",
    "marital_status": "Семейное положение",
    "education": "Образование",
    "housing": "Жильё",
    "channel": "Канал поступления",
    "amount": "Запрошенная сумма, руб.",
    "term_months": "Срок, мес.",
    "rate": "Ставка, % годовых",
    "new_payment": "Платёж по запрашиваемому кредиту, руб./мес.",
    "amount_to_income": "Сумма к годовому доходу",
    "bki_found": "Кредитная история найдена",
    "loans_count": "Кредитов в истории",
    "active_loans": "Действующих кредитов",
    "total_debt": "Текущая задолженность, руб.",
    "monthly_payments": "Платежи по действующим кредитам, руб./мес.",
    "max_dpd": "Максимальная просрочка в истории, дн.",
    "current_dpd": "Текущая просрочка, дн.",
    "dpd30_12m": "Просрочек 30+ дней за 12 мес.",
    "inquiries_6m": "Запросов в БКИ за 6 мес.",
    "history_months": "Длина кредитной истории, мес.",
    "bankruptcy": "Сведения о банкротстве",
    "debt_to_income": "Задолженность к годовому доходу",
    "abs_client": "Клиент Банка",
    "client_since_months": "Клиент Банка, мес.",
    "salary_project": "Зарплатный проект Банка",
    "salary_avg": "Зарплатные поступления, руб./мес.",
    "accounts_count": "Счетов в Банке",
    "deposits_balance": "Остаток на вкладах, руб.",
    "bank_loans_count": "Кредитов в Банке",
    "pdn": "ПДН",
    "passport_valid": "Паспорт действителен",
    "in_stoplist": "Во внутреннем стоп-листе",
    "in_rosfin": "В перечне Росфинмониторинга",
}

CHOICES: dict[str, dict[str, str]] = {
    "employment_type": {"employee": "Работа по найму", "self_employed": "Самозанятый / ИП",
                        "pensioner": "Пенсионер", "unemployed": "Не работает"},
    "marital_status": {"single": "Холост / не замужем", "married": "В браке", "divorced": "В разводе",
                       "widowed": "Вдовец / вдова"},
    "education": {"higher": "Высшее", "secondary_special": "Среднее специальное", "secondary": "Среднее"},
    "housing": {"own": "Собственное", "mortgage": "Ипотека", "rent": "Аренда", "parents": "С родителями"},
    "channel": {"office": "Офис", "online": "Онлайн"},
}


def years_between(born: date, on: date) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def annuity(amount: float, rate_pct: float, months: int) -> float:
    """Ежемесячный аннуитетный платёж."""
    if months <= 0:
        return 0.0
    r = rate_pct / 100 / 12
    if r == 0:
        return amount / months
    return amount * r / (1 - (1 + r) ** -months)


def build(d: dict) -> dict:
    """Вектор признаков по досье заявки."""
    app, cl, emp, prod = d["application"], d["client"], d["employment"], d["product"]
    rep = d.get("report") or {}
    abs_ = d.get("abs") or {}
    checks = d.get("checks") or {}
    on = d.get("as_of") or date.today()
    if isinstance(on, str):
        on = date.fromisoformat(on)
    born = cl["birth_date"]
    if isinstance(born, str):
        born = date.fromisoformat(born)

    amount, term = float(app["amount"]), int(app["term_months"])
    rate = float(prod["base_rate"])
    income_confirmed = float(emp.get("income_confirmed") or 0)
    salary_avg = float(abs_.get("salary_avg") or 0)
    # доход для ПДН: по зарплатному проекту — поступления по данным АБС, иначе подтверждённый доход анкеты
    income = salary_avg if abs_.get("salary_project") and salary_avg > 0 else income_confirmed
    new_payment = annuity(amount, rate, term)
    monthly_payments = float(rep.get("monthly_payments") or 0)
    total_debt = float(rep.get("total_debt") or 0)
    age = years_between(born, on)

    f = {
        "age": age,
        "age_at_maturity": age + term / 12,
        "citizenship_rf": (cl.get("citizenship") or "РФ") in ("РФ", "Россия", "Российская Федерация"),
        "employment_type": emp.get("employment_type") or "employee",
        "experience_months": int(emp.get("experience_months") or 0),
        "income_confirmed": income_confirmed,
        "income": income,
        "dependents": int(app.get("dependents") or 0),
        "marital_status": app.get("marital_status") or "single",
        "education": app.get("education") or "secondary",
        "housing": app.get("housing") or "own",
        "channel": app.get("channel") or "office",
        "amount": amount,
        "term_months": term,
        "rate": rate,
        "new_payment": round(new_payment, 2),
        "amount_to_income": amount / (income * 12) if income > 0 else 99.0,
        "bki_found": bool(rep.get("found", False)),
        "loans_count": int(rep.get("loans_count") or 0),
        "active_loans": int(rep.get("active_loans") or 0),
        "total_debt": total_debt,
        "monthly_payments": monthly_payments,
        "max_dpd": int(rep.get("max_dpd") or 0),
        "current_dpd": int(rep.get("current_dpd") or 0),
        "dpd30_12m": int(rep.get("dpd30_12m") or 0),
        "inquiries_6m": int(rep.get("inquiries_6m") or 0),
        "history_months": int(rep.get("history_months") or 0),
        "bankruptcy": bool(rep.get("bankruptcy", False)),
        "debt_to_income": total_debt / (income * 12) if income > 0 else 99.0,
        "abs_client": bool(abs_.get("is_client", False)),
        "client_since_months": int(abs_.get("client_since_months") or 0),
        "salary_project": bool(abs_.get("salary_project", False)),
        "salary_avg": salary_avg,
        "accounts_count": int(abs_.get("accounts_count") or 0),
        "deposits_balance": float(abs_.get("deposits_balance") or 0),
        "bank_loans_count": int(abs_.get("bank_loans_count") or 0),
        # С-8: ПДН = (платежи по всем кредитам, включая запрашиваемый) / среднемесячный доход
        "pdn": (monthly_payments + new_payment) / income if income > 0 else 9.99,
        "passport_valid": bool(checks.get("passport", True)),
        "in_stoplist": not checks.get("stoplist", True),
        "in_rosfin": not checks.get("rosfin", True),
    }
    for k in ("pdn", "amount_to_income", "debt_to_income", "age_at_maturity"):
        f[k] = round(f[k], 4)
    return f


def display(name: str, value) -> str:
    """Значение признака для человека."""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if name in CHOICES:
        return CHOICES[name].get(str(value), str(value))
    if name == "pdn":
        return f"{value * 100:.1f} %"
    if name in ("amount_to_income", "debt_to_income"):
        return f"{value:.2f}"
    if isinstance(value, float):
        return f"{value:,.0f}".replace(",", " ")
    return str(value)
