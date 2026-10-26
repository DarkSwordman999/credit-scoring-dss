"""Администрирование (П-12, П-13, Н-1): пользователи и роли, лимиты полномочий, параметры системы,
журнал аудита, журнал обмена, резервное копирование."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import appsettings, audit
from ..db import get_db
from ..errors import Conflict, DomainError, NotFound
from ..models import ROLES, AuditLog, IntegrationLog, User
from ..security import hash_password, require, verify_password
from ..services import backup, xlsx
from .auth import user_out

router = APIRouter(prefix="/api/admin", tags=["Администрирование"])

ADMIN = require("admin")


class UserIn(BaseModel):
    login: str = Field(min_length=2, max_length=64)
    full_name: str = Field(min_length=1, max_length=200)
    role: str
    limit_amount: float | None = Field(default=None, ge=0)
    password: str | None = None
    active: bool = True


@router.get("/users")
def users(user: User = Depends(require("admin", "head")), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.role, User.login).all()]


@router.post("/users")
def create_user(body: UserIn, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    if body.role not in ROLES:
        raise DomainError("Неизвестная роль")
    if db.query(User).filter_by(login=body.login.strip()).first():
        raise Conflict("Такой логин уже есть")
    if not body.password or len(body.password) < 6:
        raise DomainError("Пароль должен быть не короче 6 символов")
    u = User(login=body.login.strip(), full_name=body.full_name.strip(), role=body.role,
             limit_amount=body.limit_amount, active=body.active, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.log(db, user, "Создан пользователь", "user", u.login,
              {"роль": [None, u.role], "лимит": [None, body.limit_amount]})
    db.commit()
    return user_out(u)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if u is None:
        raise NotFound("Пользователь не найден")
    if body.role not in ROLES:
        raise DomainError("Неизвестная роль")
    if u.id == user.id and (not body.active or body.role != "admin"):
        raise DomainError("Нельзя заблокировать себя или снять с себя роль администратора")
    if body.login.strip() != u.login and db.query(User).filter_by(login=body.login.strip()).first():
        raise Conflict("Такой логин уже есть")
    changes = audit.diff(u, {"login": body.login.strip(), "full_name": body.full_name.strip(), "role": body.role,
                             "limit_amount": body.limit_amount, "active": body.active})
    if body.password:
        if len(body.password) < 6:
            raise DomainError("Пароль должен быть не короче 6 символов")
        u.password_hash = hash_password(body.password)
        changes["пароль"] = ["***", "изменён"]
    audit.log(db, user, "Изменён пользователь", "user", u.login, changes)
    db.commit()
    return user_out(u)


@router.get("/settings")
def get_settings_(user: User = Depends(require("admin", "risk_analyst", "head", "underwriter", "credit_officer")),
                  db: Session = Depends(get_db)):
    return {"values": appsettings.all_(db), "labels": appsettings.LABELS}


@router.put("/settings")
def put_settings(body: dict, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    old = appsettings.all_(db)
    changes = {}
    for k, v in body.items():
        new = appsettings.set_(db, k, v)
        if old.get(k) != new:
            changes[k] = [old.get(k), new]
    audit.log(db, user, "Изменены параметры системы", "settings", "", changes)
    db.commit()
    return {"values": appsettings.all_(db), "labels": appsettings.LABELS}


def _audit_query(db: Session, date_from, date_to, login, action, entity):
    q = db.query(AuditLog)
    if date_from:
        q = q.filter(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))
    if login:
        q = q.filter(AuditLog.user_login == login)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if entity:
        q = q.filter(AuditLog.entity_id.ilike(f"%{entity}%"))
    return q.order_by(AuditLog.id.desc())


@router.get("/audit", summary="Журнал аудита (С-18)")
def audit_log(date_from: date | None = None, date_to: date | None = None, login: str = "", action: str = "",
              entity: str = "", page: int = 1, size: int = 100, xlsx_: bool = Query(False, alias="xlsx"),
              user: User = Depends(require("admin", "head")), db: Session = Depends(get_db)):
    q = _audit_query(db, date_from, date_to, login, action, entity)
    if xlsx_:
        rows = [[r.created_at, r.user_login, r.action, r.entity, r.entity_id,
                 "; ".join(f"{k}: {v}" for k, v in (r.changes or {}).items())] for r in q.limit(50000).all()]
        data = xlsx.build("Журнал аудита", ["Время", "Пользователь", "Действие", "Объект", "Номер", "Изменения"], rows,
                          [("Период", f"{date_from or '…'} — {date_to or '…'}")], sheet="Журнал")
        return xlsx.response(data, "Журнал аудита.xlsx")
    total = q.count()
    size = max(1, min(size, 500))
    items = q.offset((max(page, 1) - 1) * size).limit(size).all()
    return {"total": total, "items": [{"id": r.id, "created_at": r.created_at, "user": r.user_login,
                                       "action": r.action, "entity": r.entity, "entity_id": r.entity_id,
                                       "changes": r.changes} for r in items]}


@router.get("/integration-log", summary="Журнал обмена с внешними системами")
def integration_log(system: str = "", status: str = "", user: User = Depends(require("admin", "risk_analyst")),
                    db: Session = Depends(get_db)):
    q = db.query(IntegrationLog)
    if system:
        q = q.filter(IntegrationLog.system == system)
    if status:
        q = q.filter(IntegrationLog.status == status)
    return [{"id": r.id, "created_at": r.created_at, "system": r.system, "direction": r.direction,
             "status": r.status, "message": r.message} for r in q.order_by(IntegrationLog.id.desc()).limit(300).all()]


@router.get("/backups")
def backups(user: User = Depends(ADMIN)):
    return backup.listing()


@router.post("/backups", summary="Создать резервную копию БД (Н-1)")
def make_backup(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    p = backup.make()
    audit.log(db, user, "Создана резервная копия", "backup", p.name)
    db.commit()
    return {"name": p.name}


@router.get("/backups/{name}")
def download_backup(name: str, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    p = backup.path_of(name)
    audit.log(db, user, "Скачана резервная копия", "backup", name)
    db.commit()
    return FileResponse(p, filename=p.name, media_type="application/octet-stream")


_checked: dict[str, bool] = {}


def _is_default(password: str, stored: str) -> bool:
    """Проверка дорогая (PBKDF2) — результат запоминается по хэшу пароля."""
    if stored not in _checked:
        _checked[stored] = verify_password(password, stored)
    return _checked[stored]


@router.get("/demo-users", summary="Демо-пользователи с неизменёнными паролями (сведения администратору)")
def demo_users(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    from ..demo import DEMO_PASSWORD, STAFF
    out = []
    for login, _name, role, limit in STAFF:
        u = db.query(User).filter_by(login=login, active=True).first()
        # пароль показываем, только пока его не сменили — значит, это демонстрационная база
        if u is not None and _is_default(DEMO_PASSWORD, u.password_hash):
            out.append({"login": u.login, "full_name": u.full_name, "role": u.role,
                        "role_name": ROLES.get(u.role, u.role), "password": DEMO_PASSWORD,
                        "limit_amount": float(u.limit_amount) if u.limit_amount is not None else None})
    return out
