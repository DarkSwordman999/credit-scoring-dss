"""Кредитный портфель: выданные кредиты, их обслуживание и качество по классам риска на момент выдачи."""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..db import get_db
from ..models import Application, Client, Loan, Product, ScoringResult, User
from ..security import require
from .applications import STAFF, _client_name, _mask

router = APIRouter(prefix="/api/loans", tags=["Кредитный портфель"])
VIEW = require(*STAFF)

LOAN_STATUSES = {"active": "Действующий", "closed": "Погашен", "default": "Дефолт (просрочка 90+)"}


def _filtered(db: Session, status: list[str] | None, q: str, date_from: date | None, date_to: date | None,
              product_id: int | None, risk_class: list[str] | None, overdue: bool):
    # последняя оценка заявки — коррелированным подзапросом по индексу scoring_results.application_id
    # (через производную таблицу SQLite перебирал все оценки для каждого кредита: 30+ с на демо-данных)
    sr = aliased(ScoringResult)
    latest = (select(func.max(ScoringResult.id)).where(ScoringResult.application_id == Application.id)
              .correlate(Application).scalar_subquery())
    query = (db.query(Loan, Application, Client, Product, sr.risk_class, sr.pd)
             .join(Application, Application.id == Loan.application_id)
             .join(Client, Client.id == Application.client_id)
             .join(Product, Product.id == Application.product_id)
             .outerjoin(sr, sr.id == latest))
    if status:
        query = query.filter(Loan.status.in_(status))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Loan.contract_number.ilike(like), Application.number.ilike(like),
                                 Client.last_name.ilike(like)))
    if date_from:
        query = query.filter(Loan.issued_at >= date_from)
    if date_to:
        query = query.filter(Loan.issued_at <= date_to)
    if product_id:
        query = query.filter(Application.product_id == product_id)
    if risk_class:
        query = query.filter(sr.risk_class.in_(risk_class))
    if overdue:
        query = query.filter(Loan.max_dpd_12m > 0)
    return query, sr


@router.get("", summary="Выданные кредиты с отбором и итогами портфеля")
def list_loans(status: list[str] | None = Query(default=None), q: str = "", date_from: date | None = None,
               date_to: date | None = None, product_id: int | None = None,
               risk_class: list[str] | None = Query(default=None), overdue: bool = False, page: int = 1,
               size: int = 50, user: User = Depends(VIEW), db: Session = Depends(get_db)):
    query, sr = _filtered(db, status, q, date_from, date_to, product_id, risk_class, overdue)
    total = query.count()
    size = max(1, min(size, 200))
    rows = (query.order_by(Loan.issued_at.desc(), Loan.id.desc())
            .offset((max(page, 1) - 1) * size).limit(size).all())
    masked = _mask(user)
    items = [{"id": ln.id, "contract_number": ln.contract_number, "application_id": a.id,
              "application_number": a.number, "client_id": c.id, "client": _client_name(c, masked),
              "product": p.name, "issued_at": ln.issued_at, "amount": float(ln.amount),
              "term_months": ln.term_months, "rate": ln.rate, "status": ln.status,
              "status_name": LOAN_STATUSES.get(ln.status, ln.status), "max_dpd_12m": ln.max_dpd_12m,
              "risk_class": rc, "pd": pd}
             for ln, a, c, p, rc, pd in rows]

    # итоги по всей выборке, а не по странице
    sub = query.with_entities(Loan.id.label("id"), Loan.amount.label("amount"), Loan.rate.label("rate"),
                              Loan.status.label("status"), Loan.max_dpd_12m.label("dpd"),
                              sr.risk_class.label("rc"), sr.pd.label("pd")).subquery()
    by_status = {s: {"count": n, "amount": float(v or 0)} for s, n, v in
                 db.query(sub.c.status, func.count(), func.sum(sub.c.amount)).group_by(sub.c.status).all()}
    agg = db.query(func.sum(sub.c.amount), func.sum(sub.c.amount * sub.c.rate),
                   func.sum(func.coalesce(sub.c.pd, 0)), func.count(sub.c.pd),
                   func.sum(case((sub.c.dpd > 0, 1), else_=0))).one()
    amount_sum, rate_x_amount, pd_sum, pd_count, with_dpd = agg
    classes = []
    for rc, n, v, defaults, pd_avg in (db.query(sub.c.rc, func.count(), func.sum(sub.c.amount),
                                                func.sum(case((sub.c.status == "default", 1), else_=0)),
                                                func.avg(sub.c.pd))
                                       .group_by(sub.c.rc).order_by(sub.c.rc).all()):
        classes.append({"risk_class": rc or "—", "count": n, "amount": float(v or 0), "defaults": int(defaults or 0),
                        "default_rate": (defaults or 0) / n if n else None, "pd_avg": pd_avg})
    finished = sum(by_status.get(s, {}).get("count", 0) for s in ("closed", "default"))
    summary = {"count": total, "amount": float(amount_sum or 0),
               "rate_avg": float(rate_x_amount) / float(amount_sum) if amount_sum else None,
               "pd_avg": pd_sum / pd_count if pd_count else None, "with_dpd": int(with_dpd or 0),
               "by_status": by_status, "statuses": LOAN_STATUSES,
               "default_rate": by_status.get("default", {}).get("count", 0) / total if total else None,
               "finished": finished, "by_class": classes}
    return {"total": total, "items": items, "summary": summary}
