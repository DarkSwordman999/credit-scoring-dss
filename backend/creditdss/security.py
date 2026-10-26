"""Аутентификация (JWT), хэши паролей, вход через службу каталогов (В-1) и разграничение доступа по ролям (Б-1)."""
import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .config import get_settings
from .db import session as db_session
from .models import User

_ITER = 200_000
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
log = logging.getLogger("creditdss.security")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def ldap_bind(login: str, password: str) -> bool:
    """Проверка пароля в службе каталогов (Active Directory / LDAP). Роль и лимит берутся из учётной записи
    в системе: в каталоге проверяется только пароль."""
    s = get_settings()
    if not s.ldap_url or not password:
        return False
    try:
        from ldap3 import Connection, Server
        user = f"{s.ldap_domain}\\{login}" if s.ldap_domain else login
        conn = Connection(Server(s.ldap_url, connect_timeout=s.ldap_timeout), user=user, password=password)
        ok = conn.bind()
        conn.unbind()
        return bool(ok)
    except Exception:  # каталог недоступен — пробуем локальный пароль
        log.exception("LDAP")
        return False


def check_credentials(user: User, password: str) -> bool:
    if get_settings().ldap_url and user.login != "admin" and ldap_bind(user.login, password):
        return True
    return bool(user.password_hash) and verify_password(password, user.password_hash)


def make_token(user: User) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=s.token_hours)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, s.token_secret, algorithm="HS256")


def current_user(token: str | None = Depends(oauth2)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход в систему",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, get_settings().token_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Сеанс истёк, войдите снова",
                            headers={"WWW-Authenticate": "Bearer"})
    with db_session("autocommit") as s:
        user = s.get(User, int(payload["sub"]))
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь заблокирован")
    return user


def require(*roles: str):
    """Зависимость: доступ только указанным ролям. Администратор управляет системой, но не принимает
    кредитных решений: ему доступны только явно перечисленные операции."""
    def dep(user: User = Depends(current_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для этой операции")
        return user
    return dep


def abs_key(x_api_key: str | None = Header(default=None)) -> str:
    """Ключ АБС для передачи сведений об обслуживании кредитов (заголовок X-API-Key)."""
    if not x_api_key or not hmac.compare_digest(x_api_key, get_settings().abs_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный ключ API")
    return "abs"
