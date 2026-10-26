"""Вход в систему (вариант использования «Авторизоваться») и сведения о текущем пользователе."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import appsettings, audit
from ..db import get_db
from ..db import session as db_session
from ..models import ROLES, User
from ..security import check_credentials, current_user, hash_password, make_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["Вход"])


class UserOut(BaseModel):
    id: int
    login: str
    full_name: str
    role: str
    role_name: str
    limit_amount: float | None
    active: bool = True


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, login=u.login, full_name=u.full_name, role=u.role, role_name=ROLES.get(u.role, u.role),
                   limit_amount=float(u.limit_amount) if u.limit_amount is not None else None, active=u.active)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/token", response_model=TokenOut, summary="Получить токен по логину и паролю")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    with db_session("autocommit") as s:
        user = s.query(User).filter(User.login == form.username.strip()).first()
    if user is None or not user.active or not check_credentials(user, form.password):
        raise HTTPException(401, "Неверный логин или пароль")
    audit.log(db, user, "Вход в систему")
    db.commit()
    return TokenOut(access_token=make_token(user), user=user_out(user))


_checked: dict[str, bool] = {}


def _is_default(password: str, stored: str) -> bool:
    """Проверка дорогая (PBKDF2), а страница входа открыта всем — результат запоминается по хэшу пароля."""
    if stored not in _checked:
        _checked[stored] = verify_password(password, stored)
    return _checked[stored]


@router.get("/demo-users", summary="Демо-пользователи для страницы входа (если включено в параметрах)")
def demo_users(db: Session = Depends(get_db)):
    if not appsettings.get(db, "demo_hint"):
        return []
    from ..demo import DEMO_PASSWORD, STAFF
    logins = [s[0] for s in STAFF] + ["admin"]
    users = {u.login: u for u in db.query(User).filter(User.login.in_(logins), User.active.is_(True)).all()}
    out = []
    for login in logins:
        u = users.get(login)
        pwd = "admin" if login == "admin" else DEMO_PASSWORD
        # пароль показываем, только пока его не сменили
        if u is not None and _is_default(pwd, u.password_hash):
            out.append({"login": u.login, "full_name": u.full_name, "role_name": ROLES.get(u.role, u.role),
                        "password": pwd})
    return out


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/password", summary="Сменить свой пароль")
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "Текущий пароль указан неверно")
    if len(body.new_password) < 6:
        raise HTTPException(400, "Пароль должен быть не короче 6 символов")
    u = db.get(User, user.id)
    u.password_hash = hash_password(body.new_password)
    audit.log(db, u, "Смена пароля", "user", u.login)
    db.commit()
    return {"ok": True}
