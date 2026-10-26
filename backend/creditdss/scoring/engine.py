"""Расчёт оценки заявки (ПР 5-6, блок A3; ПР 7-8, диаграмма последовательности «Выполнить скоринг заявки»).

1. Проверить стоп-факторы; сработал хотя бы один — рекомендация «Отказ» с кодом (С-5).
2. Сформировать признаки (С-6), рассчитать PD и вклад факторов (С-9), ПДН (С-8).
3. Присвоить класс риска по порогам PD (С-7), сформировать рекомендацию и условия по матрице (С-10).
"""
import time

from . import features as feat
from . import scorecard, stopfactors

# С-7: пороги PD для классов риска (верхняя граница, не включительно)
DEFAULT_CLASSES = [["A", 0.02], ["B", 0.05], ["C", 0.10], ["D", 0.20], ["E", None]]

# С-10: матрица «класс риска × ПДН»: класс, ПДН от, ПДН до, рекомендация, множитель суммы, надбавка к ставке
DEFAULT_MATRIX = [
    ("A", 0.0, 0.5, "approve", 1.0, 0.0), ("A", 0.5, 0.8, "approve", 1.0, 1.0),
    ("A", 0.8, 99, "approve_changed", 0.7, 2.0),
    ("B", 0.0, 0.5, "approve", 1.0, 1.0), ("B", 0.5, 0.8, "approve_changed", 0.85, 2.0),
    ("B", 0.8, 99, "approve_changed", 0.6, 3.0),
    ("C", 0.0, 0.5, "approve_changed", 0.85, 3.0), ("C", 0.5, 0.8, "approve_changed", 0.7, 4.0),
    ("C", 0.8, 99, "reject", 0.0, 0.0),
    ("D", 0.0, 0.5, "approve_changed", 0.6, 6.0), ("D", 0.5, 99, "reject", 0.0, 0.0),
    ("E", 0.0, 99, "reject", 0.0, 0.0),
]


def risk_class(pd: float, classes: list) -> str:
    for name, upper in classes:
        if upper is None or pd < upper:
            return name
    return classes[-1][0]


def recommend(cls: str, pdn: float, amount: float, term: int, product: dict, matrix: list[dict]) -> dict:
    rule = next((r for r in matrix if r["risk_class"] == cls and r["pdn_from"] <= pdn < r["pdn_to"]), None)
    if rule is None or rule["decision"] == "reject":
        return {"recommendation": "reject", "rec_amount": None, "rec_term": None, "rec_rate": None}
    rec_amount = amount * rule["amount_factor"]
    rec_amount = max(float(product["min_amount"]), min(float(product["max_amount"]), rec_amount))
    rec_amount = float(int(rec_amount // 1000) * 1000)
    decision = rule["decision"]
    if decision == "approve" and rec_amount < amount:
        decision = "approve_changed"
    return {"recommendation": decision, "rec_amount": rec_amount, "rec_term": term,
            "rec_rate": round(float(product["base_rate"]) + rule["rate_add"], 2)}


def evaluate(dossier: dict, params: dict, stop_factor_list: list[dict], classes: list, matrix: list[dict]) -> dict:
    """Результат оценки: PD, балл, класс, ПДН, стоп-факторы, факторы, признаки, рекомендация и условия."""
    t0 = time.perf_counter()
    f = feat.build(dossier)
    hits = stopfactors.check(stop_factor_list, f)
    res = {"features": f, "pdn": f["pdn"], "stop_factors": hits, "pd": None, "score": None,
           "risk_class": None, "factors": []}
    app, product = dossier["application"], dossier["product"]
    if hits:
        # ПР 5-6, A3: при срабатывании стоп-фактора сразу формируется отказ, переход к сохранению результата
        res.update({"recommendation": "reject", "rec_amount": None, "rec_term": None, "rec_rate": None})
    else:
        s, parts = scorecard.score(params, f)
        pd = scorecard.pd_from_score(params, s)
        cls = risk_class(pd, classes)
        res.update({"pd": round(pd, 5), "score": round(s, 1), "risk_class": cls,
                    "factors": scorecard.explain(parts)})
        res.update(recommend(cls, f["pdn"], float(app["amount"]), int(app["term_months"]), product, matrix))
    res["duration_ms"] = int((time.perf_counter() - t0) * 1000)
    return res
