"""Модуль скоринга: признаки (С-6), стоп-факторы (С-5), класс риска (С-7), ПДН (С-8), факторы (С-9),
матрица условий (С-10), метрики (С-13, С-15)."""
from datetime import date, timedelta

import pytest

from creditdss.scoring import engine, features, metrics, scorecard, stopfactors
from creditdss.scoring.engine import DEFAULT_CLASSES, DEFAULT_MATRIX

MATRIX = [dict(zip(("risk_class", "pdn_from", "pdn_to", "decision", "amount_factor", "rate_add"), r))
          for r in DEFAULT_MATRIX]
SF = [{"code": c, "description": d, "rule": r, "threshold": t, "active": a} for c, d, r, t, a in stopfactors.DEFAULTS]


def dossier(**over):
    d = {
        "as_of": date.today().isoformat(),
        "application": {"amount": 300000, "term_months": 36, "channel": "office", "dependents": 0,
                        "marital_status": "married", "education": "higher", "housing": "own"},
        "client": {"birth_date": (date.today() - timedelta(days=40 * 366)).isoformat(), "citizenship": "РФ"},
        "employment": {"employment_type": "employee", "experience_months": 60, "income_confirmed": 100000},
        "product": {"base_rate": 19.9, "min_amount": 30000, "max_amount": 3000000},
        "report": {"found": True, "loans_count": 3, "active_loans": 1, "total_debt": 100000,
                   "monthly_payments": 10000, "max_dpd": 0, "current_dpd": 0, "dpd30_12m": 0, "inquiries_6m": 1,
                   "history_months": 60, "bankruptcy": False},
        "abs": {"is_client": True, "client_since_months": 30, "salary_project": False, "salary_avg": 0,
                "accounts_count": 1, "deposits_balance": 0, "bank_loans_count": 0},
        "checks": {"passport": True, "stoplist": True, "rosfin": True},
    }
    for k, v in over.items():
        d[k].update(v)
    return d


def test_feature_vector_has_at_least_30_features():
    f = features.build(dossier())
    assert len(f) >= 30
    assert set(f) <= set(features.LABELS)


def test_pdn_is_payments_including_new_loan_to_income():
    f = features.build(dossier())
    new = features.annuity(300000, 19.9, 36)
    assert f["new_payment"] == pytest.approx(new, abs=0.01)
    assert f["pdn"] == pytest.approx((10000 + new) / 100000, abs=1e-4)


def test_salary_project_income_from_abs():
    f = features.build(dossier(abs={"salary_project": True, "salary_avg": 150000}))
    assert f["income"] == 150000


def test_good_borrower_is_approved_with_explanation():
    r = engine.evaluate(dossier(), scorecard.default_params(), SF, DEFAULT_CLASSES, MATRIX)
    assert r["stop_factors"] == []
    assert r["risk_class"] in ("A", "B")
    assert r["recommendation"] in ("approve", "approve_changed")
    assert 0 < r["pd"] < 0.05
    up = [x for x in r["factors"] if x["effect"] == "risk_up"]
    down = [x for x in r["factors"] if x["effect"] == "risk_down"]
    assert len(up) <= 5 and len(down) == 5
    assert all(x["text"] for x in r["factors"])


def test_risky_borrower_gets_higher_pd():
    good = engine.evaluate(dossier(), scorecard.default_params(), SF, DEFAULT_CLASSES, MATRIX)
    bad = engine.evaluate(dossier(report={"max_dpd": 60, "dpd30_12m": 2, "inquiries_6m": 7},
                                  employment={"experience_months": 3, "income_confirmed": 40000}),
                          scorecard.default_params(), SF, DEFAULT_CLASSES, MATRIX)
    assert bad["pd"] > good["pd"]
    assert any(x["effect"] == "risk_up" for x in bad["factors"])


@pytest.mark.parametrize("over,code", [
    ({"client": {"birth_date": (date.today() - timedelta(days=19 * 366)).isoformat()}}, "SF01"),
    ({"report": {"current_dpd": 15}}, "SF04"),
    ({"report": {"bankruptcy": True}}, "SF05"),
    ({"checks": {"passport": False}}, "SF06"),
    ({"checks": {"stoplist": False}}, "SF07"),
    ({"application": {"amount": 3000000, "term_months": 12}}, "SF09"),
    ({"employment": {"income_confirmed": 10000}}, "SF11"),
])
def test_stop_factor_gives_reject_without_pd(over, code):
    r = engine.evaluate(dossier(**over), scorecard.default_params(), SF, DEFAULT_CLASSES, MATRIX)
    assert code in [s["code"] for s in r["stop_factors"]]
    assert r["recommendation"] == "reject"
    assert r["pd"] is None


def test_inactive_stop_factor_ignored():
    sf = [dict(s, active=False) if s["code"] == "SF04" else s for s in SF]
    r = engine.evaluate(dossier(report={"current_dpd": 15}), scorecard.default_params(), sf, DEFAULT_CLASSES, MATRIX)
    assert "SF04" not in [s["code"] for s in r["stop_factors"]]


def test_risk_class_thresholds():
    assert engine.risk_class(0.01, DEFAULT_CLASSES) == "A"
    assert engine.risk_class(0.02, DEFAULT_CLASSES) == "B"
    assert engine.risk_class(0.07, DEFAULT_CLASSES) == "C"
    assert engine.risk_class(0.15, DEFAULT_CLASSES) == "D"
    assert engine.risk_class(0.5, DEFAULT_CLASSES) == "E"


def test_matrix_recommendation():
    prod = {"base_rate": 19.9, "min_amount": 30000, "max_amount": 3000000}
    assert engine.recommend("A", 0.2, 300000, 36, prod, MATRIX) == {
        "recommendation": "approve", "rec_amount": 300000, "rec_term": 36, "rec_rate": 19.9}
    r = engine.recommend("C", 0.6, 300000, 36, prod, MATRIX)
    assert r["recommendation"] == "approve_changed" and r["rec_amount"] == 210000 and r["rec_rate"] == 23.9
    assert engine.recommend("E", 0.1, 300000, 36, prod, MATRIX)["recommendation"] == "reject"


def test_pd_calibration():
    p = scorecard.default_params()
    assert scorecard.pd_from_score(p, 600) == pytest.approx(1 / 51)
    assert scorecard.pd_from_score(p, 620) == pytest.approx(1 / 101)


def test_validate_params():
    p = scorecard.default_params()
    assert scorecard.validate(p) == []
    p["characteristics"][0]["bins"][1]["min"] = 24
    p["pdo"] = 0
    errors = scorecard.validate(p)
    assert any("подряд" in e for e in errors) and any("PDO" in e for e in errors)


def test_metrics():
    assert metrics.auc([0.1, 0.2, 0.8, 0.9], [False, False, True, True]) == 1.0
    assert metrics.auc([0.9, 0.8, 0.2, 0.1], [False, False, True, True]) == 0.0
    assert metrics.auc([0.5, 0.5], [False, True]) == 0.5
    assert metrics.ks([0.1, 0.2, 0.8, 0.9], [False, False, True, True]) == 1.0
    assert metrics.auc([0.1, 0.2], [False, False]) is None
    ref = [i / 100 for i in range(100)]
    assert metrics.psi(ref, ref) == pytest.approx(0, abs=1e-6)
    assert metrics.psi(ref, [0.95] * 50) > 0.25
