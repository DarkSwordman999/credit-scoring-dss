"""Реестр заёмщиков: клиенты, их заявки, решения и кредиты (досье клиента, ПР 3 — «Сформировать досье заёмщика»)."""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..errors import NotFound
from ..models import Application, Client, CreditReport, Employment, Loan, User
from ..scoring.features import CHOICES
from ..security import require
from .applications import STAFF, _client_name, _client_out, _list_item, _mask, latest_by_app

router = APIRouter(prefix="/api/clients", tags=["Заёмщики"])
VIEW = require(*STAFF)


def _age(born: date, on: date | None = None) -> int:
    on = on or date.today()
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def _passport(c: Client, masked: bool) -> str:
    return f"{c.passport_series} ******" if masked else f"{c.passport_series} {c.passport_number}"


@router.get("", summary="Список заёмщиков с числом заявок и кредитов")
def list_clients(q: str = "", with_loans: bool = False, overdue: bool = False, page: int = 1, size: int = 50,
                 user: User = Depends(VIEW), db: Session = Depends(get_db)):
    apps = (db.query(Application.client_id.label("cid"), func.count(Application.id).label("apps"),
                     func.sum(case((Application.status == "rejected", 1), else_=0)).label("rejected"),
                     func.sum(case((Application.status.in_(("approved", "issued")), 1), else_=0)).label("approved"),
                     func.max(Application.created_at).label("last_at"))
            .group_by(Application.client_id).subquery())
    loans = (db.query(Application.client_id.label("cid"), func.count(Loan.id).label("loans"),
                      func.sum(case((Loan.status == "active", Loan.amount), else_=0)).label("active_amount"),
                      func.sum(case((Loan.status == "active", 1), else_=0)).label("active"),
                      func.sum(case((Loan.status == "default", 1), else_=0)).label("defaults"),
                      func.max(Loan.max_dpd_12m).label("max_dpd"))
             .join(Loan, Loan.application_id == Application.id).group_by(Application.client_id).subquery())
    query = (db.query(Client, apps.c.apps, apps.c.rejected, apps.c.approved, apps.c.last_at, loans.c.loans,
                      loans.c.active, loans.c.active_amount, loans.c.defaults, loans.c.max_dpd)
             .outerjoin(apps, apps.c.cid == Client.id).outerjoin(loans, loans.c.cid == Client.id))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Client.last_name.ilike(like), Client.first_name.ilike(like),
                                 Client.passport_number == q.strip(), Client.phone.ilike(like)))
    if with_loans:
        query = query.filter(loans.c.loans > 0)
    if overdue:
        query = query.filter(or_(loans.c.max_dpd > 0, loans.c.defaults > 0))
    total = query.count()
    size = max(1, min(size, 200))
    rows = (query.order_by(apps.c.last_at.desc().nullslast(), Client.id.desc())
            .offset((max(page, 1) - 1) * size).limit(size).all())
    masked = _mask(user)
    items = []
    for c, n_apps, rej, appr, last_at, n_loans, active, active_amount, defaults, max_dpd in rows:
        items.append({"id": c.id, "full_name": _client_name(c, masked), "birth_date": c.birth_date,
                      "age": _age(c.birth_date), "passport": _passport(c, masked),
                      "phone": "***" if masked else c.phone, "applications": n_apps or 0,
                      "approved": appr or 0, "rejected": rej or 0, "last_application_at": last_at,
                      "loans": n_loans or 0, "active_loans": active or 0,
                      "active_amount": float(active_amount or 0), "defaults": defaults or 0,
                      "max_dpd": max_dpd or 0})
    return {"total": total, "items": items}


@router.get("/{client_id}", summary="Карточка заёмщика: данные, доход, кредитная история, заявки, кредиты")
def client_card(client_id: int, user: User = Depends(VIEW), db: Session = Depends(get_db)):
    c = db.get(Client, client_id)
    if c is None:
        raise NotFound("Клиент не найден")
    masked = _mask(user)
    apps = db.query(Application).filter_by(client_id=c.id).order_by(Application.created_at.desc()).all()
    scor, decs, loans = latest_by_app(db, apps)
    emp = db.query(Employment).filter_by(client_id=c.id).order_by(Employment.id.desc()).first()
    rep = (db.query(CreditReport).join(Application, Application.id == CreditReport.application_id)
           .filter(Application.client_id == c.id).order_by(CreditReport.received_at.desc()).first())
    loan_rows = []
    for a in apps:
        ln = loans.get(a.id)
        if ln:
            loan_rows.append({"id": ln.id, "application_id": a.id, "application_number": a.number,
                              "contract_number": ln.contract_number, "product": a.product.name,
                              "issued_at": ln.issued_at, "amount": float(ln.amount), "term_months": ln.term_months,
                              "rate": ln.rate, "status": ln.status, "max_dpd_12m": ln.max_dpd_12m})
    items = [_list_item(a, scor.get(a.id), masked, decs.get(a.id), loans.get(a.id)) for a in apps]
    audit.log(db, user, "Просмотр карточки клиента", "client", c.id)
    db.commit()
    emp_types = CHOICES["employment_type"]
    return {
        "client": {**_client_out(c, masked), "age": _age(c.birth_date), "created_at": c.created_at},
        "employment": None if emp is None else {
            "employment_type": emp.employment_type, "employment_name": emp_types.get(emp.employment_type,
                                                                                   emp.employment_type),
            "employer": emp.employer, "position": emp.position, "experience_months": emp.experience_months,
            "income_confirmed": float(emp.income_confirmed)},
        "credit_report": None if rep is None else {
            "received_at": rep.received_at, "found": rep.found, "loans_count": rep.loans_count,
            "active_loans": rep.active_loans, "total_debt": float(rep.total_debt),
            "monthly_payments": float(rep.monthly_payments), "max_dpd": rep.max_dpd,
            "current_dpd": rep.current_dpd, "inquiries_6m": rep.inquiries_6m, "history_months": rep.history_months,
            "bankruptcy": rep.bankruptcy},
        "stats": {"applications": len(apps),
                  "approved": sum(1 for a in apps if a.status in ("approved", "issued")),
                  "rejected": sum(1 for a in apps if a.status == "rejected"),
                  "loans": len(loan_rows),
                  "active_amount": sum(x["amount"] for x in loan_rows if x["status"] == "active"),
                  "defaults": sum(1 for x in loan_rows if x["status"] == "default")},
        "applications": items,
        "loans": loan_rows,
    }
