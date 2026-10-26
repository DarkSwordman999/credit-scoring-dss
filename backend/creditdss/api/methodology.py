"""Методика оценки: версии скоринговой карты, проверка на истории, утверждение, публикация, мониторинг
(ПР 7-8, варианты «Обучить и опубликовать модель», «Мониторить качество модели»; С-13 – С-15)."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db, get_db_long
from ..models import MODEL_STATUSES, MonitoringReport, ScoringModel, User
from ..scoring import features as feat
from ..security import require
from ..services import methodology as svc

router = APIRouter(prefix="/api/models", tags=["Методика оценки"])

ANALYST = require("risk_analyst")
VIEW = require("risk_analyst", "head", "underwriter")


def _users(db: Session) -> dict[int, str]:
    return {u.id: u.full_name for u in db.query(User).all()}


def model_out(m: ScoringModel, names: dict[int, str], full: bool = False) -> dict:
    metrics = {k: v for k, v in (m.metrics or {}).items() if k != "reference_pd"}
    d = {"id": m.id, "version": m.version, "name": m.name, "algorithm": m.algorithm, "status": m.status,
         "status_name": MODEL_STATUSES.get(m.status, m.status), "metrics": metrics, "comment": m.comment,
         "created_at": m.created_at, "created_by": names.get(m.created_by, "система"),
         "approved_by": names.get(m.approved_by) if m.approved_by else None, "approved_at": m.approved_at,
         "published_at": m.published_at, "characteristics": len(m.params.get("characteristics", []))}
    if full:
        d["params"] = m.params
    return d


@router.get("", summary="Версии методики")
def list_models(user: User = Depends(VIEW), db: Session = Depends(get_db)):
    names = _users(db)
    return [model_out(m, names) for m in db.query(ScoringModel).order_by(ScoringModel.version.desc()).all()]


@router.get("/features", summary="Признаки, доступные характеристикам скоринговой карты")
def features_list(user: User = Depends(VIEW)):
    return [{"name": k, "label": v} for k, v in feat.LABELS.items()]


@router.get("/monitoring", summary="Отчёты мониторинга качества и стабильности (С-15)")
def monitoring(user: User = Depends(VIEW), db: Session = Depends(get_db)):
    versions = {m.id: m.version for m in db.query(ScoringModel).all()}
    return [{"period": r.period, "version": versions.get(r.model_id), "n_scored": r.n_scored, "psi": r.psi,
             "n_matured": r.n_matured, "gini": r.gini, "gini_ref": r.gini_ref, "default_rate": r.default_rate,
             "alerts": r.alerts, "created_at": r.created_at}
            for r in db.query(MonitoringReport).order_by(MonitoringReport.period.desc(), MonitoringReport.id.desc())
            .limit(60).all()]


class MonitorIn(BaseModel):
    period: str | None = None


@router.post("/monitoring", summary="Рассчитать мониторинг за месяц")
def run_monitoring(body: MonitorIn, user: User = Depends(ANALYST), db: Session = Depends(get_db_long)):
    rep = svc.monitor(db, body.period or svc.previous_month(), user)
    db.commit()
    return {"period": rep.period, "psi": rep.psi, "gini": rep.gini, "alerts": rep.alerts}


@router.get("/{model_id}", summary="Версия методики с параметрами")
def get_model(model_id: int, user: User = Depends(VIEW), db: Session = Depends(get_db)):
    return model_out(svc.get(db, model_id), _users(db), full=True)


class CandidateIn(BaseModel):
    source_id: int
    name: str = ""
    comment: str = ""


@router.post("", summary="Создать версию-кандидат на основе существующей")
def create(body: CandidateIn, user: User = Depends(ANALYST), db: Session = Depends(get_db)):
    m = svc.create_candidate(db, user, body.source_id, body.name, body.comment)
    db.commit()
    return model_out(m, _users(db), full=True)


class UpdateIn(BaseModel):
    params: dict | None = None
    name: str | None = None
    comment: str | None = None


@router.put("/{model_id}", summary="Изменить версию-кандидат")
def update(model_id: int, body: UpdateIn, user: User = Depends(ANALYST), db: Session = Depends(get_db)):
    m = svc.update_candidate(db, user, svc.get(db, model_id), body.params, body.name, body.comment)
    db.commit()
    return model_out(m, _users(db), full=True)


class ValidateIn(BaseModel):
    date_from: date | None = None
    date_to: date | None = None


@router.post("/{model_id}/validate", summary="Проверить версию на созревших кредитах: ROC AUC, Gini, KS (С-13)")
def validate(model_id: int, body: ValidateIn, user: User = Depends(ANALYST), db: Session = Depends(get_db_long)):
    m = svc.get(db, model_id)
    svc.validate(db, user, m, body.date_from, body.date_to)
    db.commit()
    return model_out(m, _users(db), full=True)


@router.post("/{model_id}/submit", summary="Отправить на утверждение руководителю")
def submit(model_id: int, user: User = Depends(ANALYST), db: Session = Depends(get_db)):
    m = svc.submit(db, user, svc.get(db, model_id))
    db.commit()
    return model_out(m, _users(db))


class ApproveIn(BaseModel):
    approve: bool
    comment: str = ""


@router.post("/{model_id}/approve", summary="Утвердить или отклонить версию (руководитель)")
def approve(model_id: int, body: ApproveIn, user: User = Depends(require("head")), db: Session = Depends(get_db)):
    m = svc.approve(db, user, svc.get(db, model_id), body.approve, body.comment)
    db.commit()
    return model_out(m, _users(db))


@router.post("/{model_id}/publish", summary="Опубликовать утверждённую версию (С-14)")
def publish(model_id: int, user: User = Depends(ANALYST), db: Session = Depends(get_db)):
    m = svc.publish(db, user, svc.get(db, model_id))
    db.commit()
    return model_out(m, _users(db))


@router.post("/{model_id}/rollback", summary="Откатиться на архивную версию")
def rollback(model_id: int, user: User = Depends(ANALYST), db: Session = Depends(get_db)):
    m = svc.rollback(db, user, svc.get(db, model_id))
    db.commit()
    return model_out(m, _users(db))
