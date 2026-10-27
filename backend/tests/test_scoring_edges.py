"""Границы и крайние случаи расчётов: пороги классов риска (С-7), матрица условий (С-10), аннуитет и ПДН (С-8),
калибровка балла (С-9), проверка версии методики, метрики качества (С-13, С-15)."""
import math
import random

import pytest

from creditdss.scoring import engine, features, metrics, scorecard, stopfactors
from creditdss.scoring.engine import DEFAULT_CLASSES, DEFAULT_MATRIX

MATRIX = [dict(zip(("risk_class", "pdn_from", "pdn_to", "decision", "amount_factor", "rate_add"), r))
          for r in DEFAULT_MATRIX]
PROD = {"base_rate": 20.0, "min_amount": 30000, "max_amount": 3000000}


# ---------------------------------------------------------------- классы риска
@pytest.mark.parametrize("pd, cls", [
    (0.0, "A"), (0.019999, "A"), (0.02, "B"), (0.049999, "B"), (0.05, "C"),
    (0.0999, "C"), (0.10, "D"), (0.1999, "D"), (0.20, "E"), (0.99, "E"),
])
def test_risk_class_upper_bound_is_exclusive(pd, cls):
    assert engine.risk_class(pd, DEFAULT_CLASSES) == cls


def test_risk_class_without_open_last_class_falls_to_last():
    assert engine.risk_class(0.5, [["A", 0.1], ["B", 0.3]]) == "B"


def test_score_thresholds_match_pd_thresholds():
    """PD < p ⇔ балл > 600 + 20·log2((1/p − 1)/50): граница класса A — 599,42 балла."""
    p = scorecard.default_params()
    for upper in (0.02, 0.05, 0.10, 0.20):
        s = 600 + 20 * math.log2((1 / upper - 1) / 50)
        assert scorecard.pd_from_score(p, s + 0.01) < upper <= scorecard.pd_from_score(p, s - 0.01)
    assert engine.risk_class(scorecard.pd_from_score(p, 600), DEFAULT_CLASSES) == "A"
    assert engine.risk_class(scorecard.pd_from_score(p, 599), DEFAULT_CLASSES) == "B"


def test_pd_decreases_with_score_and_stays_in_0_1():
    p = scorecard.default_params()
    pds = [scorecard.pd_from_score(p, s) for s in range(250, 800, 5)]
    assert all(0 < x < 1 for x in pds)
    assert all(a > b for a, b in zip(pds, pds[1:]))


def test_default_scorecard_score_range():
    """Балл карты по умолчанию — от 295 до 719 (диапазон, указанный в описании методики)."""
    p = scorecard.default_params()
    lo = p["base_points"] + sum(min(b["points"] for b in ch["bins"] + (
        [{"points": ch.get("default_points", 0)}] if ch["type"] == "category" else [])) for ch in p["characteristics"])
    hi = p["base_points"] + sum(max(b["points"] for b in ch["bins"] + (
        [{"points": ch.get("default_points", 0)}] if ch["type"] == "category" else [])) for ch in p["characteristics"])
    assert (lo, hi) == (295, 719)


# ---------------------------------------------------------------- матрица условий
def rec(cls, pdn, amount=300000):
    return engine.recommend(cls, pdn, amount, 36, PROD, MATRIX)


def test_matrix_pdn_bounds_lower_inclusive_upper_exclusive():
    assert rec("A", 0.4999)["rec_rate"] == 20.0              # [0; 0,5): без надбавки
    assert rec("A", 0.5)["rec_rate"] == 21.0                 # [0,5; 0,8): +1 п. п.
    r = rec("A", 0.8)                                        # [0,8; ∞): сумма ×0,7, +2 п. п.
    assert r["recommendation"] == "approve_changed" and r["rec_amount"] == 210000 and r["rec_rate"] == 22.0
    assert rec("C", 0.7999)["recommendation"] == "approve_changed"
    assert rec("C", 0.8)["recommendation"] == "reject"
    assert rec("D", 0.5)["recommendation"] == "reject"


def test_reject_has_no_terms():
    assert rec("E", 0.1) == {"recommendation": "reject", "rec_amount": None, "rec_term": None, "rec_rate": None}


def test_amount_rounded_down_to_thousand():
    assert rec("C", 0.6, amount=123456)["rec_amount"] == 86000    # 123 456 × 0,7 = 86 419,2


def test_amount_clipped_to_product_limits():
    r = rec("A", 0.2, amount=4_000_000)
    assert r["rec_amount"] == 3_000_000 and r["recommendation"] == "approve_changed"   # меньше запрошенного
    assert rec("D", 0.2, amount=40000)["rec_amount"] == 30000                          # 24 000 → минимум продукта


def test_no_matching_rule_is_reject():
    assert rec("A", -0.1)["recommendation"] == "reject"
    assert engine.recommend("Z", 0.1, 300000, 36, PROD, MATRIX)["recommendation"] == "reject"


def test_matrix_covers_every_class_and_any_pdn():
    for cls, _ in DEFAULT_CLASSES:
        rows = sorted((r for r in MATRIX if r["risk_class"] == cls), key=lambda r: r["pdn_from"])
        assert rows[0]["pdn_from"] == 0 and rows[-1]["pdn_to"] >= 99
        assert all(a["pdn_to"] == b["pdn_from"] for a, b in zip(rows, rows[1:]))


# ---------------------------------------------------------------- аннуитет и признаки
def test_annuity_known_values():
    assert features.annuity(100000, 12, 12) == pytest.approx(8884.88, abs=0.01)
    assert features.annuity(120000, 0, 12) == 10000
    assert features.annuity(100000, 12, 0) == 0.0


def test_annuity_total_covers_principal_and_interest():
    pay = features.annuity(500000, 19.9, 60)
    assert 500000 < pay * 60 < 500000 * (1 + 0.199 * 5)


# ---------------------------------------------------------------- вклад факторов и объяснение
def test_neutral_includes_default_points_for_category():
    ch = {"type": "category", "bins": [{"values": [True], "points": 25}], "default_points": 0}
    assert scorecard.neutral(ch) == 12.5


def test_explain_limits_and_order():
    parts = [{"label": f"f{i}", "bin": "x", "contribution": c} for i, c in enumerate([-9, -1, -5, 3, 7, 0, -2, -3, -4, -6, 8])]
    out = scorecard.explain(parts)
    ups = [p["contribution"] for p in out if p["effect"] == "risk_up"]
    downs = [p["contribution"] for p in out if p["effect"] == "risk_down"]
    assert ups == [-9, -6, -5, -4, -3] and downs == [8, 7, 3]
    assert all(p["contribution"] != 0 for p in out)


def test_value_out_of_bins_scores_zero():
    ch = {"type": "numeric", "bins": [{"min": 0, "max": 10, "points": 5, "text": "0–10"}]}
    assert scorecard._match(ch, 50) == (0, "вне диапазона")
    cat = {"type": "category", "bins": [{"values": ["own"], "points": 20, "text": "своё"}], "default_points": 3,
           "default_text": "прочее"}
    assert scorecard._match(cat, "rent") == (3, "прочее")


# ---------------------------------------------------------------- проверка версии методики
@pytest.mark.parametrize("change, message", [
    (lambda p: p.pop("base_score"), "base_score"),
    (lambda p: p.update(base_odds=0), "шансы"),
    (lambda p: p.update(characteristics=[]), "нет характеристик"),
    (lambda p: p["characteristics"].append({"feature": "zodiac", "bins": []}), "неизвестный признак"),
    (lambda p: p["characteristics"][0].update(bins=[]), "нет интервалов"),
    (lambda p: p["characteristics"][0]["bins"][0].update(points=float("nan")), "не заданы баллы"),
    (lambda p: p["characteristics"][0]["bins"][0].update(min=0), "крайние интервалы"),
])
def test_validate_reports_each_problem(change, message):
    p = scorecard.default_params()
    change(p)
    assert any(message in e for e in scorecard.validate(p)), scorecard.validate(p)


# ---------------------------------------------------------------- стоп-факторы
def test_stop_factor_unknown_rule_or_missing_threshold_is_ignored():
    f = {"age": 18, "pdn": 2.0}
    assert stopfactors.check([{"code": "X", "description": "?", "rule": "no_such_rule", "threshold": 1}], f) == []
    assert stopfactors.check([{"code": "X", "description": "?", "rule": "age_min", "threshold": None}], f) == []
    hit = stopfactors.check([{"code": "SF01", "description": "молод", "rule": "age_min", "threshold": 21}], f)
    assert hit == [{"code": "SF01", "description": "молод"}]


@pytest.mark.parametrize("rule, threshold, value, fires", [
    ("age_min", 21, 20, True), ("age_min", 21, 21, False),
    ("max_dpd", 90, 90, True), ("max_dpd", 90, 89, False),
    ("pdn_max", 0.8, 0.8, False), ("pdn_max", 0.8, 0.8001, True),
    ("current_dpd", 0, 1, True), ("current_dpd", 0, 0, False),
])
def test_stop_factor_threshold_edges(rule, threshold, value, fires):
    key = {"age_min": "age", "max_dpd": "max_dpd", "pdn_max": "pdn", "current_dpd": "current_dpd"}[rule]
    hit = stopfactors.check([{"code": "T", "description": "t", "rule": rule, "threshold": threshold}], {key: value})
    assert bool(hit) is fires


# ---------------------------------------------------------------- метрики
def _auc_bruteforce(scores, bad):
    pairs = [(b, g) for b, yb in zip(scores, bad) if yb for g, yg in zip(scores, bad) if not yg]
    return sum(1.0 if b > g else 0.5 if b == g else 0.0 for b, g in pairs) / len(pairs)


def test_auc_matches_pairwise_definition_with_ties():
    rnd = random.Random(3)
    for _ in range(20):
        n = rnd.randint(5, 40)
        scores = [round(rnd.random(), 1) for _ in range(n)]      # много равных значений
        bad = [rnd.random() < 0.3 for _ in range(n)]
        if all(bad) or not any(bad):
            continue
        assert metrics.auc(scores, bad) == pytest.approx(_auc_bruteforce(scores, bad))


def test_gini_and_ks_edges():
    assert metrics.gini(None) is None and metrics.gini(0.75) == 0.5
    assert metrics.ks([0.1, 0.4, 0.35, 0.8], [False, False, True, True]) == pytest.approx(0.5)
    assert metrics.ks([0.5], [True]) is None


def test_psi_known_value_and_small_reference():
    assert metrics.psi([0.1] * 5, [0.2]) is None                  # эталон меньше числа корзин
    ref = [i / 100 for i in range(100)]
    cur = [i / 200 for i in range(100)]                          # всё сдвинулось в нижнюю половину
    e = 0.1
    expected = 5 * (0.2 - e) * math.log(0.2 / e) + 5 * (1e-4 - e) * math.log(1e-4 / e)
    assert metrics.psi(ref, cur) == pytest.approx(expected, abs=1e-3)


def test_evaluate_summary():
    r = metrics.evaluate([0.1, 0.2, 0.8, 0.9], [False, False, True, True])
    assert r == {"n": 4, "bad": 2, "default_rate": 0.5, "auc": 1.0, "gini": 1.0, "ks": 1.0}


# ---------------------------------------------------------------- калибровка
def test_brier_score():
    assert metrics.brier([], []) is None
    assert metrics.brier([0.0, 1.0], [False, True]) == 0
    assert metrics.brier([0.1, 0.9], [False, True]) == pytest.approx(0.01)
    assert metrics.brier([0.5] * 4, [True, False, True, False]) == pytest.approx(0.25)


def test_calibration_by_class():
    pds = [0.01] * 100 + [0.15] * 50
    bad = [False] * 99 + [True] + [True] * 20 + [False] * 30
    cal = {c["risk_class"]: c for c in metrics.calibration(pds, bad, DEFAULT_CLASSES)}
    assert cal["A"] == {"risk_class": "A", "n": 100, "bad": 1, "pd_mean": 0.01, "default_rate": 0.01, "deviates": False}
    assert cal["D"]["default_rate"] == 0.4 and cal["D"]["deviates"] is True     # 40 % против 15 % прогноза
    assert cal["B"]["n"] == 0 and cal["B"]["pd_mean"] is None


def test_calibration_small_class_is_not_flagged():
    cal = metrics.calibration([0.03] * 10, [True] * 5 + [False] * 5, DEFAULT_CLASSES)
    b = [c for c in cal if c["risk_class"] == "B"][0]
    assert b["default_rate"] == 0.5 and b["deviates"] is False                   # меньше 30 кредитов


def test_fit_base_odds_matches_observed_rate_and_keeps_order():
    p = scorecard.default_params()
    scores = [520 + 4 * i for i in range(50)]
    odds = scorecard.fit_base_odds(p, scores, 0.10)
    q = dict(p, base_odds=odds)
    pds = [scorecard.pd_from_score(q, s) for s in scores]
    assert sum(pds) / len(pds) == pytest.approx(0.10, abs=1e-3)
    assert all(a > b for a, b in zip(pds, pds[1:]))                 # порядок заёмщиков тот же
    assert scorecard.fit_base_odds(p, scores, 0) is None and scorecard.fit_base_odds(p, [], 0.1) is None
