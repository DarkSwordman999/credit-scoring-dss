"""Кредитные заявки: регистрация, досье, оценка, решения, документы (ПР 7-8, варианты использования
«Зарегистрировать заявку», «Просмотреть оценку и факторы», «Принять решение по заявке»,
«Утвердить решение кредитным комитетом»)."""
import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..errors import Conflict, DomainError, NotFound
from ..models import (MODEL_STATUSES, RECOMMENDATIONS, ROLES, STATUSES, AbsData, Application, AuditLog, BkiRequest,
                      Client, Consent, CreditReport, Decision, Document, Loan, Notification, ScoringResult, User,
                      Verification)
from ..scoring.features import CHOICES, LABELS, display
from ..security import require
from ..services import applications as svc

router = APIRouter(prefix="/api/applications", tags=["Заявки"])

STAFF = ("credit_officer", "underwriter", "head", "risk_analyst")
OFFICER = require("credit_officer")
VIEW = require(*STAFF)

ALLOWED_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}


class ClientIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str = Field(default="", max_length=100)
    birth_date: date
    passport_series: str = Field(min_length=4, max_length=4)
    passport_number: str = Field(min_length=6, max_length=6)
    passport_issued: date | None = None
    citizenship: str = "РФ"
    reg_address: str = ""
    phone: str = ""
    email: str = ""


class EmploymentIn(BaseModel):
    employment_type: Literal["employee", "self_employed", "pensioner", "unemployed"] = "employee"
    employer: str = ""
    position: str = ""
    experience_months: int = Field(default=0, ge=0, le=900)
    income_confirmed: float = Field(default=0, ge=0)


class AppFieldsIn(BaseModel):
    product_id: int
    amount: float = Field(gt=0)
    term_months: int = Field(gt=0, le=600)
    purpose: str = ""
    channel: Literal["office", "online"] = "office"
    marital_status: Literal["single", "married", "divorced", "widowed"] = "single"
    dependents: int = Field(default=0, ge=0, le=20)
    education: Literal["higher", "secondary_special", "secondary"] = "secondary"
    housing: Literal["own", "mortgage", "rent", "parents"] = "own"


class ConsentIn(BaseModel):
    kind: Literal["pd", "bki"]
    signed_at: date
    valid_until: date


class ApplicationIn(BaseModel):
    client: ClientIn
    employment: EmploymentIn
    application: AppFieldsIn
    consents: list[ConsentIn] = []


class DecisionIn(BaseModel):
    outcome: Literal["approve", "approve_changed", "reject", "docs"]
    amount: float | None = None
    term_months: int | None = None
    rate: float | None = None
    comment: str = ""


class CommentIn(BaseModel):
    comment: str = ""


def _get(db: Session, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if app is None:
        raise NotFound("Заявка не найдена")
    return app


def _mask(user: User) -> bool:
    """Риск-аналитику персональные данные клиента не нужны — показываются обезличенными (Б-1)."""
    return user.role == "risk_analyst"


def _client_name(c: Client, masked: bool) -> str:
    if masked:
        return f"{c.last_name[:1]}*** {c.first_name[:1]}. {(c.middle_name or ' ')[:1]}."
    return c.full_name


def actions(user: User, app: Application) -> list[str]:
    """Какие действия доступны пользователю по заявке — интерфейс показывает только их."""
    r, s = user.role, app.status
    out = []
    if r == "credit_officer":
        if s == "draft":
            out += ["edit", "register", "upload"]
        if s in ("registered", "collecting"):
            out += ["collect"]
        if s == "docs_required":
            out += ["upload", "return"]
        if s in ("review", "committee"):
            out += ["upload"]
        if s == "approved":
            out += ["issue", "refuse"]
    if r == "underwriter" and s == "review":
        out += ["decide", "rescore"]
    if r == "head" and s == "committee":
        out += ["committee"]
    return out


def _list_item(app: Application, sr: ScoringResult | None, masked: bool, decisions: list[Decision] | None = None,
               loan: Loan | None = None) -> dict:
    return {"id": app.id, "number": app.number, "created_at": app.created_at, "status": app.status,
            "status_name": STATUSES[app.status], "client_id": app.client_id, "client": _client_name(app.client, masked),
            "product": app.product.name, "amount": float(app.amount), "term_months": app.term_months,
            "channel": app.channel, "risk_class": sr.risk_class if sr else None,
            "pd": sr.pd if sr else None, "score": round(sr.score) if sr and sr.score is not None else None,
            "pdn": sr.pdn if sr else None, "recommendation": sr.recommendation if sr else None,
            "officer": app.officer.full_name if app.officer else "", "decided_at": app.decided_at,
            "loan_status": loan.status if loan else None,
            **svc.decision_summary(app, sr, decisions or [])}


def latest_by_app(db: Session, apps: list[Application]) -> tuple[dict, dict, dict]:
    """Последняя оценка, решения и кредит по каждой заявке — тремя запросами на страницу."""
    ids = [a.id for a in apps]
    scor, decs, loans = {}, {}, {}
    if ids:
        for sr in db.query(ScoringResult).filter(ScoringResult.application_id.in_(ids)).order_by(ScoringResult.id):
            scor[sr.application_id] = sr
        for d in db.query(Decision).filter(Decision.application_id.in_(ids)).order_by(Decision.id):
            decs.setdefault(d.application_id, []).append(d)
        for ln in db.query(Loan).filter(Loan.application_id.in_(ids)):
            loans[ln.application_id] = ln
    return scor, decs, loans


@router.get("", summary="Список заявок с отбором")
def list_applications(status: list[str] | None = Query(default=None), q: str = "", date_from: date | None = None,
                      date_to: date | None = None, mine: bool = False, page: int = 1, size: int = 50,
                      product_id: int | None = None, risk_class: list[str] | None = Query(default=None),
                      user: User = Depends(VIEW), db: Session = Depends(get_db)):
    query = db.query(Application).join(Client, Client.id == Application.client_id)
    if product_id:
        query = query.filter(Application.product_id == product_id)
    if risk_class:
        last = (db.query(func.max(ScoringResult.id)).group_by(ScoringResult.application_id)).scalar_subquery()
        query = query.filter(Application.id.in_(
            db.query(ScoringResult.application_id).filter(ScoringResult.id.in_(last),
                                                         ScoringResult.risk_class.in_(risk_class))))
    if status:
        query = query.filter(Application.status.in_(status))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Application.number.ilike(like), Client.last_name.ilike(like),
                                 Client.passport_number == q.strip()))
    if date_from:
        query = query.filter(Application.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Application.created_at <= datetime.combine(date_to, datetime.max.time()))
    if mine and user.role == "credit_officer":
        query = query.filter(Application.officer_id == user.id)
    total = query.count()
    size = max(1, min(size, 200))
    apps = query.order_by(Application.created_at.desc()).offset((max(page, 1) - 1) * size).limit(size).all()
    scor, decs, loans = latest_by_app(db, apps)
    return {"total": total, "items": [_list_item(a, scor.get(a.id), _mask(user), decs.get(a.id), loans.get(a.id))
                                      for a in apps]}


@router.get("/dictionaries", summary="Справочные значения анкеты, статусы, роли")
def dictionaries(user: User = Depends(require(*STAFF, "admin"))):
    return {"statuses": STATUSES, "recommendations": RECOMMENDATIONS, "choices": CHOICES, "labels": LABELS,
            "roles": ROLES, "model_statuses": MODEL_STATUSES}


@router.get("/clients/search", summary="Найти клиента по паспорту (для заполнения анкеты)")
def find_client(passport_series: str, passport_number: str, user: User = Depends(OFFICER),
                db: Session = Depends(get_db)):
    c = db.query(Client).filter_by(passport_series=passport_series.strip(),
                                   passport_number=passport_number.strip()).first()
    if c is None:
        return None
    apps = db.query(Application).filter_by(client_id=c.id).order_by(Application.created_at.desc()).limit(10).all()
    return {"client": _client_out(c, False),
            "applications": [{"id": a.id, "number": a.number, "created_at": a.created_at,
                              "status_name": STATUSES[a.status], "amount": float(a.amount)} for a in apps]}


def _client_out(c: Client, masked: bool) -> dict:
    d = {"id": c.id, "last_name": c.last_name, "first_name": c.first_name, "middle_name": c.middle_name,
         "full_name": _client_name(c, masked), "birth_date": c.birth_date, "passport_series": c.passport_series,
         "passport_number": c.passport_number, "passport_issued": c.passport_issued, "citizenship": c.citizenship,
         "reg_address": c.reg_address, "phone": c.phone, "email": c.email}
    if masked:
        d.update({"last_name": c.last_name[:1] + "***", "first_name": c.first_name[:1] + ".",
                  "middle_name": (c.middle_name or " ")[:1] + ".", "passport_number": "******",
                  "reg_address": "***", "phone": "***", "email": "***",
                  "birth_date": date(c.birth_date.year, 1, 1)})
    return d


def card(db: Session, app: Application, user: User) -> dict:
    masked = _mask(user)
    emp, prod = app.employment, app.product
    scorings = (db.query(ScoringResult).filter_by(application_id=app.id).order_by(ScoringResult.id.desc()).all())
    rep = db.query(CreditReport).filter_by(application_id=app.id).first()
    abs_ = db.query(AbsData).filter_by(application_id=app.id).first()
    req = db.query(BkiRequest).filter_by(application_id=app.id).first()
    loan = db.query(Loan).filter_by(application_id=app.id).first()
    sr = scorings[0] if scorings else None
    return {
        "id": app.id, "number": app.number, "status": app.status, "status_name": STATUSES[app.status],
        "created_at": app.created_at, "registered_at": app.registered_at, "decided_at": app.decided_at,
        "officer": app.officer.full_name if app.officer else "",
        "client": _client_out(app.client, masked),
        "employment": {"employment_type": emp.employment_type, "employer": emp.employer, "position": emp.position,
                       "experience_months": emp.experience_months, "income_confirmed": float(emp.income_confirmed)},
        "application": {"product_id": prod.id, "product": prod.name, "amount": float(app.amount),
                        "term_months": app.term_months, "purpose": app.purpose, "channel": app.channel,
                        "marital_status": app.marital_status, "dependents": app.dependents,
                        "education": app.education, "housing": app.housing, "base_rate": prod.base_rate},
        "consents": [{"kind": c.kind, "signed_at": c.signed_at, "valid_until": c.valid_until}
                     for c in db.query(Consent).filter_by(application_id=app.id).all()],
        "documents": [{"id": d.id, "kind": d.kind, "filename": d.filename, "size": d.size, "uploaded_at": d.uploaded_at}
                      for d in db.query(Document).filter_by(application_id=app.id).order_by(Document.id).all()],
        "collection": None if req is None else {"status": req.status, "attempts": req.attempts,
                                                "next_attempt_at": req.next_attempt_at, "message": req.message},
        "credit_report": None if rep is None else {
            "found": rep.found, "received_at": rep.received_at, "loans_count": rep.loans_count,
            "active_loans": rep.active_loans, "total_debt": float(rep.total_debt),
            "monthly_payments": float(rep.monthly_payments), "max_dpd": rep.max_dpd, "current_dpd": rep.current_dpd,
            "dpd30_12m": rep.dpd30_12m, "inquiries_6m": rep.inquiries_6m, "history_months": rep.history_months,
            "bankruptcy": rep.bankruptcy},
        "abs": None if abs_ is None else {
            "is_client": abs_.is_client, "client_since_months": abs_.client_since_months,
            "salary_project": abs_.salary_project, "salary_avg": float(abs_.salary_avg),
            "accounts_count": abs_.accounts_count, "deposits_balance": float(abs_.deposits_balance),
            "bank_loans_count": abs_.bank_loans_count, "bank_monthly_payments": float(abs_.bank_monthly_payments)},
        "verifications": [{"check": v.check, "passed": v.passed, "message": v.message}
                          for v in db.query(Verification).filter_by(application_id=app.id).all()],
        "scoring": None if sr is None else _scoring_out(sr),
        "scoring_history": [{"id": s.id, "created_at": s.created_at, "pd": s.pd, "risk_class": s.risk_class,
                             "recommendation": s.recommendation, "model_version": s.model.version if s.model else None,
                             "fallback": s.fallback} for s in scorings],
        "decisions": [{"id": d.id, "stage": d.stage, "outcome": d.outcome, "recommendation": d.recommendation,
                       "amount": float(d.amount) if d.amount is not None else None, "term_months": d.term_months,
                       "rate": d.rate, "comment": d.comment, "created_at": d.created_at, "user": d.user.full_name}
                      for d in db.query(Decision).filter_by(application_id=app.id).order_by(Decision.id).all()],
        "loan": None if loan is None else {"contract_number": loan.contract_number, "issued_at": loan.issued_at,
                                           "amount": float(loan.amount), "term_months": loan.term_months,
                                           "rate": loan.rate, "status": loan.status, "max_dpd_12m": loan.max_dpd_12m},
        "notifications": [{"channel": n.channel, "recipient": "***" if masked else n.recipient, "text": n.text,
                           "created_at": n.created_at}
                          for n in db.query(Notification).filter_by(application_id=app.id).all()],
        "refusal_reasons": svc.refusal_reasons(db, app.id) if app.status == "rejected" else [],
        "actions": actions(user, app),
        "user_limit": float(user.limit_amount) if user.limit_amount is not None else None,
    }


def _scoring_out(sr: ScoringResult) -> dict:
    feats = [{"name": k, "label": LABELS.get(k, k), "value": display(k, v)} for k, v in (sr.features or {}).items()]
    return {"id": sr.id, "created_at": sr.created_at, "pd": sr.pd, "score": sr.score, "risk_class": sr.risk_class,
            "pdn": sr.pdn, "stop_factors": sr.stop_factors, "factors": sr.factors, "features": feats,
            "recommendation": sr.recommendation, "recommendation_name": RECOMMENDATIONS[sr.recommendation],
            "rec_amount": float(sr.rec_amount) if sr.rec_amount is not None else None, "rec_term": sr.rec_term,
            "rec_rate": sr.rec_rate, "fallback": sr.fallback, "duration_ms": sr.duration_ms,
            "model_version": sr.model.version if sr.model else None,
            "model_name": sr.model.name if sr.model else "Резервная методика (базовая скоринговая карта)"}


@router.post("", summary="Создать заявку (черновик)")
def create(body: ApplicationIn, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    svc.ensure_product(db, body.application.product_id)
    app = svc.create_draft(db, user, body.model_dump())
    db.commit()
    return card(db, app, user)


@router.get("/{app_id}", summary="Карточка заявки: досье, оценка, факторы, решения")
def get_card(app_id: int, user: User = Depends(VIEW), db: Session = Depends(get_db)):
    return card(db, _get(db, app_id), user)


@router.put("/{app_id}", summary="Изменить черновик заявки")
def update(app_id: int, body: ApplicationIn, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    svc.ensure_product(db, body.application.product_id)
    app = svc.update_draft(db, user, _get(db, app_id), body.model_dump())
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/register", summary="Зарегистрировать заявку и собрать данные (С-1, С-2)")
def register(app_id: int, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    app = svc.register(db, user, _get(db, app_id))
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/collect", summary="Повторить запрос в БКИ и АБС")
def collect(app_id: int, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    app = svc.collect(db, _get(db, app_id), user, manual=True)
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/rescore", summary="Пересчитать оценку")
def rescore(app_id: int, user: User = Depends(require("underwriter")), db: Session = Depends(get_db)):
    app = _get(db, app_id)
    svc.rescore(db, user, app)
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/decision", summary="Решение андеррайтера (С-11, С-12)")
def decision(app_id: int, body: DecisionIn, user: User = Depends(require("underwriter")),
             db: Session = Depends(get_db)):
    app = _get(db, app_id)
    svc.decide(db, user, app, body.outcome, body.amount, body.term_months, body.rate, body.comment)
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/committee", summary="Решение кредитного комитета")
def committee(app_id: int, body: DecisionIn, user: User = Depends(require("head")), db: Session = Depends(get_db)):
    app = _get(db, app_id)
    if body.outcome == "docs":
        raise DomainError("Кредитный комитет принимает решение: одобрить или отказать")
    svc.committee_decide(db, user, app, body.outcome, body.amount, body.term_months, body.rate, body.comment)
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/return", summary="Документы получены — вернуть на рассмотрение")
def return_to_review(app_id: int, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    app = svc.return_to_review(db, user, _get(db, app_id))
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/issue", summary="Кредит выдан (передача в АБС)")
def issue(app_id: int, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    app = _get(db, app_id)
    svc.issue(db, user, app)
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/refuse", summary="Клиент отказался от кредита")
def refuse(app_id: int, body: CommentIn, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    app = svc.client_refused(db, user, _get(db, app_id), body.comment)
    db.commit()
    return card(db, app, user)


@router.post("/{app_id}/documents", summary="Прикрепить копию документа (PDF, JPG, PNG, до 20 МБ)")
async def upload(app_id: int, kind: str = Form(...), file: UploadFile = File(...), user: User = Depends(OFFICER),
                 db: Session = Depends(get_db)):
    app = _get(db, app_id)
    if "upload" not in actions(user, app):
        raise Conflict("В этом состоянии заявки документы не прикрепляются")
    ext = ALLOWED_TYPES.get(file.content_type or "")
    if ext is None:
        raise DomainError("Допустимые форматы: PDF, JPG, PNG")
    s = get_settings()
    limit = s.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise DomainError(f"Файл больше {s.max_upload_mb} МБ")
    if not data:
        raise DomainError("Пустой файл")
    s.ensure_dirs()
    stored = uuid.uuid4().hex + ext
    (s.documents_dir / stored).write_bytes(data)
    doc = Document(application_id=app.id, kind=kind.strip()[:50] or "документ", filename=(file.filename or stored)[:255],
                   content_type=file.content_type, size=len(data), stored_name=stored, uploaded_by=user.id)
    db.add(doc)
    audit.log(db, user, "Прикреплён документ", "application", app.number,
              {"документ": [None, f"{doc.kind}: {doc.filename}"]})
    db.commit()
    return card(db, app, user)


@router.get("/{app_id}/documents/{doc_id}", summary="Скачать документ")
def download(app_id: int, doc_id: int, user: User = Depends(require("credit_officer", "underwriter", "head")),
             db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if doc is None or doc.application_id != app_id:
        raise NotFound("Документ не найден")
    path = get_settings().documents_dir / doc.stored_name
    if not path.is_file():
        raise NotFound("Файл документа не найден в хранилище")
    audit.log(db, user, "Просмотр документа", "application", _get(db, app_id).number,
              {"документ": [None, doc.filename]})
    db.commit()
    return FileResponse(path, media_type=doc.content_type, filename=doc.filename)


@router.delete("/{app_id}/documents/{doc_id}", summary="Удалить документ (черновик или запрос документов)")
def delete_document(app_id: int, doc_id: int, user: User = Depends(OFFICER), db: Session = Depends(get_db)):
    app = _get(db, app_id)
    if app.status not in ("draft", "docs_required"):
        raise Conflict("Удалять документы можно только в черновике или при запросе документов")
    doc = db.get(Document, doc_id)
    if doc is None or doc.application_id != app_id:
        raise NotFound("Документ не найден")
    (get_settings().documents_dir / doc.stored_name).unlink(missing_ok=True)
    db.delete(doc)
    audit.log(db, user, "Удалён документ", "application", app.number, {"документ": [doc.filename, None]})
    db.commit()
    return card(db, app, user)


@router.get("/{app_id}/history", summary="Журнал действий по заявке")
def history(app_id: int, user: User = Depends(VIEW), db: Session = Depends(get_db)):
    app = _get(db, app_id)
    rows = (db.query(AuditLog).filter(AuditLog.entity == "application", AuditLog.entity_id == app.number)
            .order_by(AuditLog.id).all())
    return [{"created_at": r.created_at, "user": r.user_login, "action": r.action, "changes": r.changes} for r in rows]
