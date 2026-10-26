"""Справочники кредитной политики (С-12, П-12): продукты, стоп-факторы, матрица условий, классы риска,
стоп-лист. Стоп-факторы и пороги настраивает риск-аналитик, остальное — администратор."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import appsettings, audit
from ..db import get_db
from ..errors import Conflict, DomainError, NotFound
from ..models import Application, ConditionRule, Product, StopFactor, StopListEntry, User
from ..scoring.stopfactors import RULES
from ..security import current_user, require

router = APIRouter(prefix="/api/nsi", tags=["Справочники"])

ADMIN = require("admin")
POLICY = require("risk_analyst", "admin")


# ---------------------------------------------------------------- продукты

class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    min_amount: float = Field(gt=0)
    max_amount: float = Field(gt=0)
    min_term: int = Field(gt=0)
    max_term: int = Field(gt=0)
    base_rate: float = Field(gt=0, lt=100)
    active: bool = True


def _product_out(p: Product) -> dict:
    return {"id": p.id, "name": p.name, "min_amount": float(p.min_amount), "max_amount": float(p.max_amount),
            "min_term": p.min_term, "max_term": p.max_term, "base_rate": p.base_rate, "active": p.active}


@router.get("/products")
def products(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_product_out(p) for p in db.query(Product).order_by(Product.id).all()]


def _check_product(body: ProductIn):
    if body.min_amount > body.max_amount or body.min_term > body.max_term:
        raise DomainError("Минимум не может быть больше максимума")


@router.post("/products")
def create_product(body: ProductIn, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    _check_product(body)
    if db.query(Product).filter_by(name=body.name.strip()).first():
        raise Conflict("Продукт с таким названием уже есть")
    p = Product(**body.model_dump())
    db.add(p)
    db.flush()
    audit.log(db, user, "Добавлен кредитный продукт", "product", p.id, {k: [None, v] for k, v in body.model_dump().items()})
    db.commit()
    return _product_out(p)


@router.put("/products/{pid}")
def update_product(pid: int, body: ProductIn, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    _check_product(body)
    p = db.get(Product, pid)
    if p is None:
        raise NotFound("Продукт не найден")
    changes = audit.diff(p, body.model_dump())
    audit.log(db, user, "Изменён кредитный продукт", "product", p.id, changes)
    db.commit()
    return _product_out(p)


# ---------------------------------------------------------------- стоп-факторы

class StopFactorIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    description: str = Field(min_length=1, max_length=300)
    rule: str
    threshold: float | None = None
    active: bool = True


def _sf_out(s: StopFactor) -> dict:
    label, needs, _ = RULES.get(s.rule, (s.rule, False, None))
    return {"id": s.id, "code": s.code, "description": s.description, "rule": s.rule, "rule_name": label,
            "needs_threshold": needs, "threshold": s.threshold, "active": s.active}


@router.get("/stop-factors")
def stop_factors(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_sf_out(s) for s in db.query(StopFactor).order_by(StopFactor.code).all()]


@router.get("/stop-factor-rules")
def stop_factor_rules(user: User = Depends(current_user)):
    return [{"rule": k, "name": v[0], "needs_threshold": v[1]} for k, v in RULES.items()]


def _check_sf(body: StopFactorIn):
    if body.rule not in RULES:
        raise DomainError("Неизвестный тип условия")
    if RULES[body.rule][1] and body.threshold is None:
        raise DomainError("Для этого условия нужен порог")


@router.post("/stop-factors")
def create_sf(body: StopFactorIn, user: User = Depends(POLICY), db: Session = Depends(get_db)):
    _check_sf(body)
    if db.query(StopFactor).filter_by(code=body.code.strip()).first():
        raise Conflict("Стоп-фактор с таким кодом уже есть")
    s = StopFactor(**body.model_dump())
    db.add(s)
    db.flush()
    audit.log(db, user, "Добавлен стоп-фактор", "stop_factor", s.code, {k: [None, v] for k, v in body.model_dump().items()})
    db.commit()
    return _sf_out(s)


@router.put("/stop-factors/{sid}")
def update_sf(sid: int, body: StopFactorIn, user: User = Depends(POLICY), db: Session = Depends(get_db)):
    _check_sf(body)
    s = db.get(StopFactor, sid)
    if s is None:
        raise NotFound("Стоп-фактор не найден")
    changes = audit.diff(s, body.model_dump())
    audit.log(db, user, "Изменён стоп-фактор", "stop_factor", s.code, changes)
    db.commit()
    return _sf_out(s)


# ---------------------------------------------------------------- матрица условий и классы риска

class RuleIn(BaseModel):
    risk_class: str = Field(min_length=1, max_length=1)
    pdn_from: float = Field(ge=0)
    pdn_to: float = Field(gt=0)
    decision: Literal["approve", "approve_changed", "reject"]
    amount_factor: float = Field(default=1.0, ge=0, le=1)
    rate_add: float = Field(default=0.0, ge=-50, le=50)


@router.get("/conditions")
def conditions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"classes": appsettings.get(db, "risk_classes"),
            "rules": [{"id": r.id, "risk_class": r.risk_class, "pdn_from": r.pdn_from, "pdn_to": r.pdn_to,
                       "decision": r.decision, "amount_factor": r.amount_factor, "rate_add": r.rate_add}
                      for r in db.query(ConditionRule).order_by(ConditionRule.risk_class, ConditionRule.pdn_from)]}


class ConditionsIn(BaseModel):
    classes: list[list] | None = None
    rules: list[RuleIn]


@router.put("/conditions", summary="Сохранить классы риска и матрицу условий целиком")
def save_conditions(body: ConditionsIn, user: User = Depends(POLICY), db: Session = Depends(get_db)):
    classes = appsettings.get(db, "risk_classes")
    if body.classes is not None:
        classes = appsettings.set_(db, "risk_classes", body.classes)
    names = [c[0] for c in classes]
    by_class: dict[str, list[RuleIn]] = {}
    for r in body.rules:
        if r.risk_class not in names:
            raise DomainError(f"Класса {r.risk_class} нет среди классов риска")
        if r.pdn_from >= r.pdn_to:
            raise DomainError(f"Класс {r.risk_class}: ПДН «от» должен быть меньше «до»")
        by_class.setdefault(r.risk_class, []).append(r)
    for name in names:
        rows = sorted(by_class.get(name, []), key=lambda r: r.pdn_from)
        if not rows or rows[0].pdn_from != 0:
            raise DomainError(f"Класс {name}: интервалы ПДН должны начинаться с 0")
        for a, b in zip(rows, rows[1:]):
            if a.pdn_to != b.pdn_from:
                raise DomainError(f"Класс {name}: интервалы ПДН должны идти подряд без пропусков")
    db.query(ConditionRule).delete()
    db.add_all(ConditionRule(**r.model_dump()) for r in body.rules)
    audit.log(db, user, "Изменена матрица условий кредитной политики", "conditions", "",
              {"классы": [None, classes], "правил": [None, len(body.rules)]})
    db.commit()
    return conditions(user, db)


# ---------------------------------------------------------------- стоп-лист

class StopListIn(BaseModel):
    source: Literal["invalid_passport", "rosfin", "internal"]
    passport_series: str = ""
    passport_number: str = ""
    full_name: str = ""
    birth_date: date | None = None
    reason: str = ""


def _sl_out(e: StopListEntry) -> dict:
    return {"id": e.id, "source": e.source, "passport_series": e.passport_series, "passport_number": e.passport_number,
            "full_name": e.full_name, "birth_date": e.birth_date, "reason": e.reason, "created_at": e.created_at}


@router.get("/stoplist")
def stoplist(user: User = Depends(require("admin", "risk_analyst", "underwriter", "head")),
             db: Session = Depends(get_db)):
    return [_sl_out(e) for e in db.query(StopListEntry).order_by(StopListEntry.id.desc()).all()]


@router.post("/stoplist")
def add_stoplist(body: StopListIn, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    if not (body.passport_series and body.passport_number) and not body.full_name.strip():
        raise DomainError("Укажите паспорт или ФИО")
    e = StopListEntry(**body.model_dump())
    db.add(e)
    db.flush()
    audit.log(db, user, "Добавлена запись стоп-листа", "stoplist", e.id,
              {"источник": [None, e.source], "основание": [None, e.reason]})
    db.commit()
    return _sl_out(e)


@router.delete("/stoplist/{eid}")
def delete_stoplist(eid: int, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    e = db.get(StopListEntry, eid)
    if e is None:
        raise NotFound("Запись не найдена")
    db.delete(e)
    audit.log(db, user, "Удалена запись стоп-листа", "stoplist", eid,
              {"источник": [e.source, None], "основание": [e.reason, None]})
    db.commit()
    return {"ok": True}


@router.get("/usage/{pid}", include_in_schema=False)
def product_usage(pid: int, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    return {"applications": db.query(Application).filter_by(product_id=pid).count()}
