"""Отчёты по заявкам, решениям, качеству портфеля и методики (П-10, П-11, С-16; ПР 7-8, СервисОтчётов)."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..errors import DomainError
from ..models import (RECOMMENDATIONS, STATUSES, Application, Decision, Loan, MonitoringReport, ScoringModel,
                      ScoringResult, User)

KINDS = {
    "applications": "Отчёт по заявкам",
    "decisions": "Решения и уровень одобрения",
    "portfolio": "Качество кредитного портфеля",
    "model": "Качество и стабильность методики оценки",
}

CHANNELS = {"office": "Офис", "online": "Онлайн"}


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    if date_from > date_to:
        raise DomainError("Начало периода позже конца")
    return datetime.combine(date_from, datetime.min.time()), datetime.combine(date_to, datetime.max.time())


def _latest_scoring(db: Session, ids: list[int]) -> dict[int, ScoringResult]:
    out = {}
    for i in range(0, len(ids), 500):
        for sr in (db.query(ScoringResult).filter(ScoringResult.application_id.in_(ids[i:i + 500]))
                   .order_by(ScoringResult.id).all()):
            out[sr.application_id] = sr
    return out


def _pct(a: int, b: int) -> float | None:
    return round(a / b * 100, 1) if b else None


def build(db: Session, kind: str, date_from: date, date_to: date, masked: bool = False) -> dict:
    if kind not in KINDS:
        raise DomainError("Неизвестный вид отчёта")
    start, end = _bounds(date_from, date_to)
    rep = {"kind": kind, "title": KINDS[kind], "meta": [("Период", f"{date_from:%d.%m.%Y} — {date_to:%d.%m.%Y}")],
           "summary": [], "tables": []}
    return {"applications": _applications, "decisions": _decisions, "portfolio": _portfolio,
            "model": _model}[kind](db, start, end, rep, masked)


def _applications(db, start, end, rep, masked):
    apps = (db.query(Application).filter(Application.created_at >= start, Application.created_at <= end)
            .order_by(Application.created_at).all())
    srs = _latest_scoring(db, [a.id for a in apps])
    by_status = Counter(a.status for a in apps)
    by_channel = Counter(a.channel for a in apps)
    by_product = defaultdict(lambda: [0, 0.0])
    for a in apps:
        by_product[a.product.name][0] += 1
        by_product[a.product.name][1] += float(a.amount)
    rep["summary"] = [("Заявок", len(apps)), ("Запрошено, руб.", round(sum(float(a.amount) for a in apps), 2))]
    rep["tables"] = [
        {"title": "По состояниям", "headers": ["Состояние", "Заявок", "Доля, %"],
         "rows": [[STATUSES[s], n, _pct(n, len(apps))] for s, n in sorted(by_status.items(), key=lambda x: -x[1])]},
        {"title": "По каналам", "headers": ["Канал", "Заявок", "Доля, %"],
         "rows": [[CHANNELS.get(c, c), n, _pct(n, len(apps))] for c, n in by_channel.items()]},
        {"title": "По продуктам", "headers": ["Продукт", "Заявок", "Запрошено, руб."],
         "rows": [[p, v[0], round(v[1], 2)] for p, v in by_product.items()]},
        {"title": "Заявки", "headers": ["Номер", "Дата", "Клиент", "Продукт", "Сумма, руб.", "Срок, мес.", "Класс",
                                        "Рекомендация", "Состояние"],
         "rows": [[a.number, a.created_at, (a.client.last_name[:1] + "***") if masked else a.client.full_name,
                   a.product.name, float(a.amount), a.term_months,
                   srs[a.id].risk_class if a.id in srs else None,
                   RECOMMENDATIONS[srs[a.id].recommendation] if a.id in srs else None, STATUSES[a.status]]
                  for a in apps]},
    ]
    return rep


def _decisions(db, start, end, rep, masked):
    apps = (db.query(Application).filter(Application.decided_at >= start, Application.decided_at <= end).all())
    srs = _latest_scoring(db, [a.id for a in apps])
    final = [a for a in apps if a.status in ("approved", "rejected", "issued", "client_refused")]
    approved = [a for a in final if a.status != "rejected"]
    decisions = (db.query(Decision).filter(Decision.created_at >= start, Decision.created_at <= end,
                                           Decision.outcome.in_(("approve", "approve_changed", "reject", "committee")))
                 .all())
    users = {u.id: u.full_name for u in db.query(User).all()}
    rep["summary"] = [("Решений по заявкам", len(final)), ("Одобрено", len(approved)),
                      ("Уровень одобрения, %", _pct(len(approved), len(final))),
                      ("Передано на кредитный комитет", sum(1 for d in decisions if d.outcome == "committee"))]
    by_class = defaultdict(lambda: [0, 0])
    for a in final:
        cls = srs[a.id].risk_class if a.id in srs and srs[a.id].risk_class else "стоп-фактор"
        by_class[cls][0] += 1
        by_class[cls][1] += a.status != "rejected"
    by_user = defaultdict(lambda: [0, 0, 0])
    for d in decisions:
        u = by_user[users.get(d.user_id, "?")]
        u[0] += 1
        u[1] += d.outcome != "committee" and d.outcome != d.recommendation
        u[2] += d.outcome == "committee"
    lead = [(a.decided_at - (a.registered_at or a.created_at)).total_seconds() / 3600 for a in final
            if a.decided_at and (a.registered_at or a.created_at)]
    if lead:
        lead.sort()
        rep["summary"].append(("Медиана времени до решения, ч", round(lead[len(lead) // 2], 1)))
    rep["tables"] = [
        {"title": "Уровень одобрения по классам риска", "headers": ["Класс риска", "Решений", "Одобрено", "Доля, %"],
         "rows": [[c, v[0], v[1], _pct(v[1], v[0])] for c, v in sorted(by_class.items())]},
        {"title": "Решения сотрудников", "headers": ["Сотрудник", "Решений", "Отличаются от рекомендации",
                                                     "Доля отличий, %", "На комитет"],
         "rows": [[u, v[0], v[1], _pct(v[1], v[0] - v[2]), v[2]] for u, v in sorted(by_user.items())]},
    ]
    return rep


def _portfolio(db, start, end, rep, masked):
    loans = (db.query(Loan, Application).join(Application, Application.id == Loan.application_id)
             .filter(Loan.issued_at >= start.date(), Loan.issued_at <= end.date()).all())
    srs = _latest_scoring(db, [a.id for _, a in loans])
    cutoff = date.today() - timedelta(days=365)
    rows = defaultdict(lambda: [0, 0.0, 0, 0])
    for loan, a in loans:
        cls = srs[a.id].risk_class if a.id in srs and srs[a.id].risk_class else "—"
        r = rows[cls]
        r[0] += 1
        r[1] += float(loan.amount)
        if loan.issued_at <= cutoff:
            r[2] += 1
            r[3] += loan.max_dpd_12m >= 90
    matured = sum(r[2] for r in rows.values())
    bad = sum(r[3] for r in rows.values())
    rep["summary"] = [("Выдано кредитов", len(loans)),
                      ("Сумма выдач, руб.", round(sum(float(l.amount) for l, _ in loans), 2)),
                      ("Созревших (12+ мес.)", matured), ("Просрочка 90+ за 12 мес., %", _pct(bad, matured))]
    rep["tables"] = [{"title": "По классам риска", "headers": ["Класс риска", "Кредитов", "Сумма, руб.",
                                                               "Созревших", "С просрочкой 90+", "Доля 90+, %"],
                      "rows": [[c, v[0], round(v[1], 2), v[2], v[3], _pct(v[3], v[2])]
                               for c, v in sorted(rows.items())]}]
    return rep


def _model(db, start, end, rep, masked):
    p_from, p_to = f"{start:%Y-%m}", f"{end:%Y-%m}"
    versions = {m.id: m.version for m in db.query(ScoringModel).all()}
    reps = (db.query(MonitoringReport).filter(MonitoringReport.period >= p_from, MonitoringReport.period <= p_to)
            .order_by(MonitoringReport.period).all())
    pub = db.query(ScoringModel).filter_by(status="published").first()
    if pub:
        m = pub.metrics or {}
        rep["summary"] = [("Действующая версия", f"{pub.version} — {pub.name}"),
                          ("ROC AUC при проверке", m.get("auc")), ("Gini при проверке", m.get("gini")),
                          ("KS при проверке", m.get("ks"))]
    rep["tables"] = [{"title": "Мониторинг по месяцам", "headers": ["Месяц", "Версия", "Оценено заявок", "PSI",
                                                                    "Созревших кредитов", "Gini", "Gini при проверке",
                                                                    "Доля 90+", "Оповещения"],
                      "rows": [[r.period, versions.get(r.model_id), r.n_scored, r.psi, r.n_matured, r.gini, r.gini_ref,
                                r.default_rate, "; ".join(r.alerts) or "нет"] for r in reps]}]
    return rep
