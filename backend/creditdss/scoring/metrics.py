"""Метрики качества и стабильности (С-13, С-15): ROC AUC, Gini, KS, PSI."""
import math


def auc(scores: list[float], bad: list[bool]) -> float | None:
    """ROC AUC для оценки риска: score — чем больше, тем выше риск (например, PD).
    Считается через ранги (статистика Манна — Уитни) с учётом равных значений."""
    n_bad = sum(1 for b in bad if b)
    n_good = len(bad) - n_bad
    if n_bad == 0 or n_good == 0:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    rank_sum_bad = sum(r for r, b in zip(ranks, bad) if b)
    return (rank_sum_bad - n_bad * (n_bad + 1) / 2) / (n_bad * n_good)


def gini(a: float | None) -> float | None:
    return None if a is None else 2 * a - 1


def ks(scores: list[float], bad: list[bool]) -> float | None:
    """Статистика Колмогорова — Смирнова: максимальное расхождение распределений «плохих» и «хороших»."""
    n_bad = sum(1 for b in bad if b)
    n_good = len(bad) - n_bad
    if n_bad == 0 or n_good == 0:
        return None
    pairs = sorted(zip(scores, bad), key=lambda p: -p[0])
    cb = cg = 0
    best = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            if pairs[j][1]:
                cb += 1
            else:
                cg += 1
            j += 1
        best = max(best, abs(cb / n_bad - cg / n_good))
        i = j
    return best


def evaluate(pds: list[float], bad: list[bool]) -> dict:
    a = auc(pds, bad)
    return {"n": len(bad), "bad": sum(1 for b in bad if b),
            "default_rate": round(sum(1 for b in bad if b) / len(bad), 4) if bad else None,
            "auc": None if a is None else round(a, 4), "gini": None if a is None else round(gini(a), 4),
            "ks": None if (k := ks(pds, bad)) is None else round(k, 4)}


def psi(reference: list[float], current: list[float], bins: int = 10) -> float | None:
    """Индекс стабильности популяции по децилям эталонного распределения. PSI > 0,25 — существенный сдвиг."""
    if len(reference) < bins or not current:
        return None
    ref = sorted(reference)
    edges = [ref[int(len(ref) * k / bins)] for k in range(1, bins)]

    def shares(values):
        counts = [0] * bins
        for v in values:
            k = 0
            while k < len(edges) and v >= edges[k]:
                k += 1
            counts[k] += 1
        return [max(c / len(values), 1e-4) for c in counts]

    e, a = shares(reference), shares(current)
    return round(sum((ai - ei) * math.log(ai / ei) for ai, ei in zip(a, e)), 4)


def brier(pds: list[float], bad: list[bool]) -> float | None:
    """Показатель Брайера: средний квадрат разности прогнозной PD и факта дефолта (0 — идеально)."""
    if not pds:
        return None
    return sum((p - (1.0 if b else 0.0)) ** 2 for p, b in zip(pds, bad)) / len(pds)


def calibration(pds: list[float], bad: list[bool], classes: list) -> list[dict]:
    """Прогнозная PD против фактической доли дефолтов по классам риска. Расхождение отмечается, если факт
    отличается от прогноза больше чем на две стандартные ошибки доли (и в классе не меньше 30 кредитов)."""
    groups: dict[str, list] = {name: [0, 0.0, 0] for name, _ in classes}
    for p, b in zip(pds, bad):
        name = next((n for n, upper in classes if upper is None or p < upper), classes[-1][0])
        g = groups[name]
        g[0] += 1
        g[1] += p
        g[2] += 1 if b else 0
    out = []
    for name, (n, sum_pd, n_bad) in groups.items():
        if not n:
            out.append({"risk_class": name, "n": 0, "pd_mean": None, "default_rate": None, "deviates": False})
            continue
        pd_mean, rate = sum_pd / n, n_bad / n
        se = math.sqrt(max(pd_mean * (1 - pd_mean), 1e-12) / n)
        out.append({"risk_class": name, "n": n, "bad": n_bad, "pd_mean": round(pd_mean, 4),
                    "default_rate": round(rate, 4), "deviates": n >= 30 and abs(rate - pd_mean) > 2 * se})
    return out
