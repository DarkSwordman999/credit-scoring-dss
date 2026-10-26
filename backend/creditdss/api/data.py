"""Просмотр таблиц базы данных «как есть» — только чтение (для руководителя, риск-аналитика и администратора).

Персональные данные клиентов видит только руководитель кредитного отдела; администратору и риск-аналитику
они показываются скрытыми (Б-1). Хэши паролей не показываются никому.
"""
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import String, Text, cast, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..errors import DomainError, NotFound
from ..models import Base, User
from ..security import require

router = APIRouter(prefix="/api/data", tags=["Таблицы БД"])
VIEW = require("head", "risk_analyst", "admin")

HIDDEN = {("users", "password_hash")}
PII = {
    "clients": {"last_name", "first_name", "middle_name", "passport_number", "reg_address", "phone", "email",
                "birth_date"},
    "notifications": {"recipient", "text"},
    "stoplist": {"full_name", "passport_number"},
    "credit_reports": {"raw"},
    "abs_data": {"raw"},
    "documents": {"filename", "path"},
    "audit_log": {"changes"},
}


def _tables() -> dict:
    out = {}
    for mapper in Base.registry.mappers:
        t = mapper.local_table
        doc = (mapper.class_.__doc__ or "").strip().split("\n")[0]
        out[t.name] = {"table": t, "title": doc}
    return dict(sorted(out.items()))


def _masked(user: User) -> bool:
    return user.role != "head"


def _plain(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


@router.get("/tables", summary="Список таблиц с числом строк")
def tables(user: User = Depends(VIEW), db: Session = Depends(get_db)):
    out = []
    for name, info in _tables().items():
        n = db.execute(select(func.count()).select_from(info["table"])).scalar()
        out.append({"name": name, "title": info["title"], "rows": n,
                    "columns": len([c for c in info["table"].columns if (name, c.name) not in HIDDEN])})
    return out


@router.get("/tables/{name}", summary="Строки таблицы (по 100), отбор по значению столбца")
def rows(name: str, page: int = 1, size: int = 100, column: str = "", value: str = "",
         user: User = Depends(VIEW), db: Session = Depends(get_db)):
    info = _tables().get(name)
    if info is None:
        raise NotFound("Таблица не найдена")
    t = info["table"]
    masked = PII.get(name, set()) if _masked(user) else set()
    cols = [c for c in t.columns if (name, c.name) not in HIDDEN]
    q = select(*cols)
    if column and value.strip():
        if column not in t.c or (name, column) in HIDDEN or column in masked:
            raise DomainError("Отбор по этому столбцу недоступен")
        col = t.c[column]
        if isinstance(col.type, (String, Text)):
            q = q.where(col.ilike(f"%{value.strip()}%"))
        else:
            q = q.where(cast(col, String) == value.strip())
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar()
    size = max(1, min(size, 500))
    pk = list(t.primary_key.columns)
    if pk:
        q = q.order_by(*[c.desc() for c in pk])
    data = db.execute(q.offset((max(page, 1) - 1) * size).limit(size)).mappings().all()
    items = [{k: ("***" if k in masked and r[k] not in (None, "") else _plain(r[k])) for k in r.keys()} for r in data]
    if page == 1:
        audit.log(db, user, "Просмотр таблицы БД", "table", name)
        db.commit()
    return {"name": name, "title": info["title"], "total": total,
            "columns": [{"name": c.name, "type": str(c.type), "pk": c.primary_key,
                         "fk": next((f.target_fullname for f in c.foreign_keys), None),
                         "masked": c.name in masked} for c in cols],
            "items": items}
