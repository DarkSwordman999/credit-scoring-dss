"""Кредитное досье заявки (ПР 5-6, работа 2.5) и справочники кредитной политики для расчёта оценки."""
from sqlalchemy.orm import Session

from .. import appsettings
from ..errors import DomainError, NotFound
from ..models import (AbsData, Application, ConditionRule, CreditReport, ScoringModel, StopFactor,
                      Verification)


def build(db: Session, app_id: int) -> dict:
    app = db.get(Application, app_id)
    if app is None:
        raise NotFound("Заявка не найдена")
    rep = db.query(CreditReport).filter_by(application_id=app.id).first()
    abs_ = db.query(AbsData).filter_by(application_id=app.id).first()
    checks = {v.check: v.passed for v in db.query(Verification).filter_by(application_id=app.id).all()}
    cl, emp, prod = app.client, app.employment, app.product
    return {
        "as_of": (app.registered_at or app.created_at).date().isoformat(),
        "application": {"id": app.id, "number": app.number, "amount": float(app.amount),
                        "term_months": app.term_months, "channel": app.channel, "dependents": app.dependents,
                        "marital_status": app.marital_status, "education": app.education, "housing": app.housing},
        "client": {"birth_date": cl.birth_date.isoformat(), "citizenship": cl.citizenship},
        "employment": {"employment_type": emp.employment_type, "experience_months": emp.experience_months,
                       "income_confirmed": float(emp.income_confirmed)},
        "product": {"id": prod.id, "base_rate": prod.base_rate, "min_amount": float(prod.min_amount),
                    "max_amount": float(prod.max_amount)},
        "report": None if rep is None else {
            "found": rep.found, "loans_count": rep.loans_count, "active_loans": rep.active_loans,
            "total_debt": float(rep.total_debt), "monthly_payments": float(rep.monthly_payments),
            "max_dpd": rep.max_dpd, "current_dpd": rep.current_dpd, "dpd30_12m": rep.dpd30_12m,
            "inquiries_6m": rep.inquiries_6m, "history_months": rep.history_months, "bankruptcy": rep.bankruptcy},
        "abs": None if abs_ is None else {
            "is_client": abs_.is_client, "client_since_months": abs_.client_since_months,
            "salary_project": abs_.salary_project, "salary_avg": float(abs_.salary_avg),
            "accounts_count": abs_.accounts_count, "deposits_balance": float(abs_.deposits_balance),
            "bank_loans_count": abs_.bank_loans_count},
        "checks": checks,
    }


def policy(db: Session) -> dict:
    """Действующие справочники кредитной политики: стоп-факторы, классы риска, матрица условий."""
    return {
        "stop_factors": [{"code": s.code, "description": s.description, "rule": s.rule, "threshold": s.threshold,
                          "active": s.active} for s in db.query(StopFactor).order_by(StopFactor.code).all()],
        "classes": appsettings.get(db, "risk_classes"),
        "matrix": [{"risk_class": r.risk_class, "pdn_from": r.pdn_from, "pdn_to": r.pdn_to, "decision": r.decision,
                    "amount_factor": r.amount_factor, "rate_add": r.rate_add}
                   for r in db.query(ConditionRule).order_by(ConditionRule.risk_class, ConditionRule.pdn_from).all()],
    }


def published_model(db: Session) -> ScoringModel:
    m = db.query(ScoringModel).filter_by(status="published").order_by(ScoringModel.version.desc()).first()
    if m is None:
        raise DomainError("Нет опубликованной версии методики оценки", status=409)
    return m
