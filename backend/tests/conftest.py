"""Общие фикстуры: временная БД (SQLite или CREDITDSS_TEST_DATABASE_URL), клиент API, вход по ролям,
шаблон БД с небольшими демо-данными для проверок методики и отчётов."""
import os
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

os.environ.setdefault("CREDITDSS_SCHEDULER_ENABLED", "false")

from creditdss import db, migrate  # noqa: E402
from creditdss.bootstrap import ensure_base  # noqa: E402
from creditdss.config import get_settings  # noqa: E402
from creditdss.models import User  # noqa: E402
from creditdss.security import hash_password  # noqa: E402

# логин: (роль, лимит полномочий)
STAFF = {"officer": ("credit_officer", None), "underwriter": ("underwriter", 500_000), "head": ("head", None),
         "analyst": ("risk_analyst", None)}
PG = os.environ.get("CREDITDSS_TEST_DATABASE_URL")


def _prepare(url: str, demo: bool = False) -> None:
    migrate.upgrade(url)
    db.configure(url)
    with db.session() as s:
        ensure_base(s)
        if demo:
            from creditdss.demo import generate
            generate(s, months=20, per_day=4, seed=7, log=lambda m: None)
        for login, (role, limit) in STAFF.items():
            u = s.query(User).filter_by(login=login).first()
            if u is None:
                s.add(User(login=login, full_name=login, role=role, limit_amount=limit,
                           password_hash=hash_password("secret1")))
            else:      # демо-пользователи: тот же пароль, что и у остальных тестовых
                u.password_hash = hash_password("secret1")
        s.commit()
    db.engine().dispose()


def _pg_url(name: str) -> str:
    return PG.rsplit("/", 1)[0] + "/" + name


def _pg_exec(sql: str) -> None:
    admin = create_engine(PG, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(sql))
    admin.dispose()


@pytest.fixture(scope="session")
def templates(tmp_path_factory):
    """Шаблоны БД: пустая (справочники и пользователи) и с демо-данными; каждый тест получает копию."""
    out = {}
    for kind in ("base", "demo"):
        if PG:
            name = f"cd_tpl_{kind}_{uuid.uuid4().hex[:6]}"
            _pg_exec(f"CREATE DATABASE {name}")
            out[kind] = name
        else:
            out[kind] = tmp_path_factory.mktemp("tpl") / f"{kind}.db"
    out["_prepared"] = set()
    yield out
    if PG:
        for kind in ("base", "demo"):
            _pg_exec(f"DROP DATABASE IF EXISTS {out[kind]} WITH (FORCE)")


def _make_db(templates, kind, tmp_path):
    if kind not in templates["_prepared"]:
        url = _pg_url(templates[kind]) if PG else f"sqlite:///{templates[kind].as_posix()}"
        _prepare(url, demo=kind == "demo")
        templates["_prepared"].add(kind)
    if PG:
        name = "cd_test_" + uuid.uuid4().hex[:10]
        _pg_exec(f"CREATE DATABASE {name} TEMPLATE {templates[kind]}")
        return _pg_url(name), name
    path = tmp_path / "test.db"
    shutil.copy(templates[kind], path)
    return f"sqlite:///{path.as_posix()}", None


@pytest.fixture
def db_url(request, tmp_path, monkeypatch, templates):
    monkeypatch.setenv("CREDITDSS_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    kind = "demo" if request.node.get_closest_marker("demo") else "base"
    url, pg_name = _make_db(templates, kind, tmp_path)
    yield url
    db.engine().dispose()
    if pg_name:
        _pg_exec(f"DROP DATABASE IF EXISTS {pg_name} WITH (FORCE)")
    get_settings.cache_clear()


@pytest.fixture
def session(db_url):
    db.configure(db_url)
    s = db.session("autocommit")
    yield s
    s.close()
    db.engine().dispose()


@pytest.fixture
def client(session):
    from creditdss.main import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def login(client):
    """login("officer") -> заголовки авторизации."""
    cache = {}

    def _login(user: str, password: str | None = None) -> dict:
        pw = password or ("admin" if user == "admin" else "secret1")
        if (user, pw) not in cache:
            r = client.post("/api/auth/token", data={"username": user, "password": pw})
            assert r.status_code == 200, r.text
            cache[(user, pw)] = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return cache[(user, pw)]
    return _login


def pytest_configure(config):
    config.addinivalue_line("markers", "demo: тест на копии БД с демо-данными")
