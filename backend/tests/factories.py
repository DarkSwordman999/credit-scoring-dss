"""Тестовые данные заявок."""
from datetime import date, timedelta

_counter = [0]


def application_body(**over) -> dict:
    """Анкета благонадёжного заёмщика; over — замены по разделам: client={...}, employment={...}, application={...}."""
    _counter[0] += 1
    today = date.today()
    body = {
        "client": {"last_name": "Тестов", "first_name": "Пётр", "middle_name": "Иванович",
                   "birth_date": (today - timedelta(days=40 * 365)).isoformat(),
                   "passport_series": "7015", "passport_number": f"{500000 + _counter[0]:06d}",
                   "citizenship": "РФ", "reg_address": "г. Тула", "phone": "+7 900 000-00-00", "email": ""},
        "employment": {"employment_type": "employee", "employer": "ООО «Ромашка»", "position": "инженер",
                       "experience_months": 60, "income_confirmed": 120000},
        "application": {"product_id": 1, "amount": 300000, "term_months": 36, "purpose": "ремонт",
                        "channel": "office", "marital_status": "married", "dependents": 1,
                        "education": "higher", "housing": "own"},
        "consents": [{"kind": "pd", "signed_at": today.isoformat(), "valid_until": (today + timedelta(days=90)).isoformat()},
                     {"kind": "bki", "signed_at": today.isoformat(), "valid_until": (today + timedelta(days=90)).isoformat()}],
    }
    for section, values in over.items():
        if section == "consents":
            body["consents"] = values
        else:
            body[section].update(values)
    return body
