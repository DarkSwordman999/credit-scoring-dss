"""Стоп-факторы кредитной политики (С-5): типы условий и их проверка по признакам заявки."""

# тип условия: (описание условия для справочника, нужен ли порог, функция срабатывания)
RULES: dict[str, tuple[str, bool, callable]] = {
    "age_min": ("Возраст меньше порога, лет", True, lambda f, t: f["age"] < t),
    "age_max_maturity": ("Возраст на дату погашения больше порога, лет", True, lambda f, t: f["age_at_maturity"] > t),
    "citizenship": ("Нет гражданства РФ", False, lambda f, t: not f["citizenship_rf"]),
    "current_dpd": ("Текущая просрочка больше порога, дн.", True, lambda f, t: f["current_dpd"] > t),
    "max_dpd": ("Просрочка в истории не меньше порога, дн.", True, lambda f, t: f["max_dpd"] >= t),
    "bankruptcy": ("Есть сведения о банкротстве", False, lambda f, t: f["bankruptcy"]),
    "passport_invalid": ("Паспорт недействителен", False, lambda f, t: not f["passport_valid"]),
    "stoplist": ("Клиент во внутреннем стоп-листе Банка", False, lambda f, t: f["in_stoplist"]),
    "rosfin": ("Клиент в перечне Росфинмониторинга", False, lambda f, t: f["in_rosfin"]),
    "pdn_max": ("ПДН больше порога, доля", True, lambda f, t: f["pdn"] > t),
    "inquiries_max": ("Запросов в БКИ за 6 мес. больше порога", True, lambda f, t: f["inquiries_6m"] > t),
    "income_min": ("Доход меньше порога, руб./мес.", True, lambda f, t: f["income"] < t),
    "unemployed": ("Нет постоянного источника дохода", False, lambda f, t: f["employment_type"] == "unemployed"),
}

# стоп-факторы по умолчанию: код, описание, тип, порог, активен
DEFAULTS = [
    ("SF01", "Возраст заёмщика менее 21 года", "age_min", 21, True),
    ("SF02", "Возраст на дату погашения более 70 лет", "age_max_maturity", 70, True),
    ("SF03", "Нет гражданства Российской Федерации", "citizenship", None, True),
    ("SF04", "Текущая просрочка по кредитам", "current_dpd", 0, True),
    ("SF05", "Сведения о банкротстве", "bankruptcy", None, True),
    ("SF06", "Паспорт недействителен", "passport_invalid", None, True),
    ("SF07", "Клиент во внутреннем стоп-листе Банка", "stoplist", None, True),
    ("SF08", "Клиент в перечне Росфинмониторинга", "rosfin", None, True),
    ("SF09", "ПДН превышает 80 %", "pdn_max", 0.8, True),
    ("SF10", "Более 10 запросов кредитной истории за 6 месяцев", "inquiries_max", 10, True),
    ("SF11", "Доход ниже 15 000 руб. в месяц", "income_min", 15000, True),
    ("SF12", "Нет постоянного источника дохода", "unemployed", None, True),
    ("SF13", "Просрочка 90 дней и более в кредитной истории", "max_dpd", 90, False),
]


def check(stop_factors: list[dict], features: dict) -> list[dict]:
    """Сработавшие активные стоп-факторы: [{code, description}]."""
    hit = []
    for sf in stop_factors:
        if not sf.get("active", True):
            continue
        rule = RULES.get(sf["rule"])
        if rule is None:
            continue
        _, needs_threshold, fn = rule
        t = sf.get("threshold")
        if needs_threshold and t is None:
            continue
        if fn(features, t):
            hit.append({"code": sf["code"], "description": sf["description"]})
    return hit
