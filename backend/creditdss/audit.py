"""Журнал аудита (С-18, П-13) и журнал обмена с внешними системами."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from .models import AuditLog, IntegrationLog, User


def _plain(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def diff(obj, values: dict) -> dict:
    """Изменённые значения «было → стало» для записи в журнал; сами значения присваиваются объекту."""
    changes = {}
    for k, new in values.items():
        old = getattr(obj, k)
        if _plain(old) != _plain(new):
            changes[k] = [_plain(old), _plain(new)]
            setattr(obj, k, new)
    return changes


def log(db: Session, user: User | None, action: str, entity: str = "", entity_id: object = "",
        changes: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, user_login=user.login if user else "система",
                    action=action[:200], entity=entity, entity_id=str(entity_id),
                    changes={k: [_plain(x) for x in v] if isinstance(v, (list, tuple)) else _plain(v)
                             for k, v in (changes or {}).items()}))


def integration(db: Session, system: str, message: str, status: str = "ok", direction: str = "out") -> None:
    db.add(IntegrationLog(system=system, message=message[:4000], status=status, direction=direction))
