"""Главная страница: очереди и показатели для роли пользователя."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (STATUSES, Application, BkiRequest, IntegrationLog, MonitoringReport, ScoringModel, User)
from ..security import current_user
from ..services import backup

router = APIRouter(prefix="/api/dashboard", tags=["Главная"])


def _queue(db: Session, statuses: tuple, officer_id: int | None = None, limit: int = 8) -> list[dict]:
    q = db.query(Application).filter(Application.status.in_(statuses))
    if officer_id:
        q = q.filter(Application.officer_id == officer_id)
    return [{"id": a.id, "number": a.number, "client": a.client.full_name, "amount": float(a.amount),
             "status": a.status, "status_name": STATUSES[a.status], "created_at": a.created_at}
            for a in q.order_by(Application.created_at).limit(limit).all()]


@router.get("")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    counts = {s: n for s, n in db.query(Application.status, func.count()).group_by(Application.status).all()}
    since = datetime.now() - timedelta(days=30)
    decided = (db.query(Application.status, func.count()).filter(Application.decided_at >= since)
               .group_by(Application.status).all())
    total = sum(n for _, n in decided)
    approved = sum(n for s, n in decided if s != "rejected")
    out = {"counts": counts, "statuses": STATUSES,
           "approval_rate_30d": round(approved / total * 100, 1) if total else None, "decided_30d": total,
           "today": db.query(Application).filter(Application.created_at >= datetime.now().replace(
               hour=0, minute=0, second=0, microsecond=0)).count()}
    r = user.role
    if r == "credit_officer":
        out["queues"] = [
            {"title": "Черновики", "items": _queue(db, ("draft",), user.id)},
            {"title": "Нужны документы", "items": _queue(db, ("docs_required",), user.id)},
            {"title": "Одобрены — ждут выдачи", "items": _queue(db, ("approved",), user.id)},
            {"title": "Сбор данных", "items": _queue(db, ("registered", "collecting"), user.id)},
        ]
        failed = (db.query(BkiRequest).join(Application, Application.id == BkiRequest.application_id)
                  .filter(BkiRequest.status == "failed", Application.status == "collecting").count())
        out["alerts"] = [f"Не получены данные БКИ или АБС по заявкам: {failed} — повторите запрос"] if failed else []
    elif r == "underwriter":
        out["queues"] = [{"title": "На рассмотрении", "items": _queue(db, ("review",), limit=12)}]
        out["alerts"] = []
    elif r == "head":
        out["queues"] = [{"title": "Кредитный комитет", "items": _queue(db, ("committee",))}]
        waiting = db.query(ScoringModel).filter_by(status="approval").all()
        out["alerts"] = [f"Версия методики {m.version} ждёт утверждения" for m in waiting]
    elif r == "risk_analyst":
        last = db.query(MonitoringReport).order_by(MonitoringReport.period.desc()).first()
        out["queues"] = []
        out["monitoring"] = None if last is None else {"period": last.period, "psi": last.psi, "gini": last.gini,
                                                       "gini_ref": last.gini_ref, "alerts": last.alerts}
        out["alerts"] = list(last.alerts) if last else []
        approved = db.query(ScoringModel).filter_by(status="approved").all()
        out["alerts"] += [f"Версия методики {m.version} утверждена — можно публиковать" for m in approved]
    else:
        errors = db.query(IntegrationLog).filter(IntegrationLog.status == "error",
                                                 IntegrationLog.created_at >= datetime.now() - timedelta(days=1)).count()
        backups = backup.listing()
        out["queues"] = []
        out["alerts"] = [f"Ошибок обмена за сутки: {errors}"] if errors else []
        out["admin"] = {"users": db.query(User).filter_by(active=True).count(),
                        "last_backup": backups[0] if backups else None}
    return out
