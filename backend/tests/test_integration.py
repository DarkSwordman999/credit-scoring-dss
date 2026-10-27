"""Адаптеры БКИ и АБС (С-3, С-4, Р-4) в режимах demo и http, проверки по стоп-листам, отдельный сервис
скоринга (А-1) и вход в систему (Б-1)."""
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from creditdss.config import get_settings
from creditdss.models import User
from creditdss.services import integration as it

SUBJ = it.Subject("Иванов", "Иван", "Иванович", "1985-04-12", "7015", "123456")


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("ошибка", request=httpx.Request("POST", "http://x"),
                                        response=httpx.Response(self.status_code))


def fake_post(response=None, error=None, calls=None):
    def post(url, json=None, timeout=None, **kw):
        if calls is not None:
            calls.append((url, json))
        if error:
            raise error
        return response
    return post


# ---------------------------------------------------------------- имитаторы
def test_demo_answers_are_deterministic_per_client():
    assert it.demo_bki(SUBJ) == it.demo_bki(SUBJ)
    assert it.demo_abs(SUBJ) == it.demo_abs(SUBJ)
    other = it.Subject("Петров", "Пётр", "", "1990-01-01", "4510", "654321")
    reports = [it.demo_bki(it.Subject("Х", "Х", "", "1990-01-01", "4510", f"{n:06d}")) for n in range(200)]
    assert any(r is None for r in reports) and any(r for r in reports)       # у части клиентов истории нет
    assert other.seed("bki") != SUBJ.seed("bki")


def test_demo_failure_rate_raises_unavailable():
    with pytest.raises(it.Unavailable):
        it.bki_report(SUBJ, {}, failure_rate=1.0)


def test_demo_contract_number():
    assert it.abs_send_approved({"number": "КЗ-2026-000123"}) == "КД-2026-000123"


# ---------------------------------------------------------------- режим http
def test_bki_http_normalizes_report(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "post", fake_post(FakeResponse(200, {"max_dpd": 35, "bankruptcy": 1, "extra": "x"}),
                                                 calls=calls))
    r = it.bki_report(SUBJ, {"kind": "bki"}, mode="http", url="http://bki/report")
    assert r["max_dpd"] == 35 and r["bankruptcy"] is True and r["loans_count"] == 0 and r["raw"]["extra"] == "x"
    assert calls[0][1]["subject"]["passport_number"] == "123456" and calls[0][1]["consent"] == {"kind": "bki"}


@pytest.mark.parametrize("response, error, outcome", [
    (FakeResponse(404), None, None),
    (FakeResponse(503), None, it.Unavailable),
    (None, httpx.ConnectError("нет связи"), it.Unavailable),
    (FakeResponse(400), None, httpx.HTTPStatusError),
])
def test_bki_http_errors(monkeypatch, response, error, outcome):
    monkeypatch.setattr(httpx, "post", fake_post(response, error))
    if outcome is None:
        assert it.bki_report(SUBJ, {}, mode="http", url="http://bki") is None
    else:
        with pytest.raises(outcome):
            it.bki_report(SUBJ, {}, mode="http", url="http://bki")


def test_abs_http(monkeypatch):
    monkeypatch.setattr(httpx, "post", fake_post(FakeResponse(200, {"is_client": True, "salary_avg": "85000",
                                                                    "accounts_count": None})))
    r = it.abs_client(SUBJ, mode="http", url="http://abs/client")
    assert r["is_client"] is True and r["salary_avg"] == 85000.0 and r["accounts_count"] == 0
    monkeypatch.setattr(httpx, "post", fake_post(FakeResponse(502)))
    with pytest.raises(it.Unavailable):
        it.abs_client(SUBJ, mode="http", url="http://abs/client")


def test_abs_send_approved_http(monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, "post", fake_post(FakeResponse(200, {"contract_number": "77-1"}), calls=calls))
    assert it.abs_send_approved({"number": "КЗ-1"}, mode="http", url="http://abs/") == "77-1"
    assert calls[0][0] == "http://abs/contracts"
    monkeypatch.setattr(httpx, "post", fake_post(error=httpx.ReadTimeout("долго")))
    with pytest.raises(it.Unavailable):
        it.abs_send_approved({"number": "КЗ-1"}, mode="http", url="http://abs")


# ---------------------------------------------------------------- стоп-листы
def entry(source, **kw):
    e = {"source": source, "passport_series": "", "passport_number": "", "full_name": "", "birth_date": None,
         "reason": ""}
    e.update(kw)
    return e


def test_verify_clean():
    assert all(ok for ok, _ in it.verify(SUBJ, []).values())


def test_verify_by_passport_with_reason():
    r = it.verify(SUBJ, [entry("invalid_passport", passport_series="7015", passport_number="123456",
                               reason="утрачен")])
    assert r["passport"] == (False, "паспорт в базе недействительных паспортов: утрачен")
    assert r["rosfin"][0] and r["stoplist"][0]


def test_verify_by_name_and_birth_date():
    name = "иванов иван иванович"
    assert not it.verify(SUBJ, [entry("rosfin", full_name="Иванов Иван Иванович")])["rosfin"][0]
    assert not it.verify(SUBJ, [entry("internal", full_name=name, birth_date="1985-04-12")])["stoplist"][0]
    assert it.verify(SUBJ, [entry("internal", full_name=name, birth_date="1990-01-01")])["stoplist"][0]


def test_invalid_passport_list_ignores_names_and_unknown_sources():
    r = it.verify(SUBJ, [entry("invalid_passport", full_name="Иванов Иван Иванович"), entry("other", full_name="x")])
    assert all(ok for ok, _ in r.values())


# ---------------------------------------------------------------- сервис скоринга
@pytest.fixture
def scoring_api(session, monkeypatch):
    from creditdss import scoring_service
    monkeypatch.setattr(get_settings(), "scoring_key", "s3cret")
    return TestClient(scoring_service.app)


def test_scoring_service_health_and_key(scoring_api):
    assert scoring_api.get("/health").json()["status"] == "ok"
    assert scoring_api.post("/score", json={"application_id": 1}).status_code == 401
    assert scoring_api.post("/score", json={"application_id": 1}, headers={"X-Service-Key": "wrong"}).status_code == 401


def test_scoring_service_unknown_application(scoring_api):
    r = scoring_api.post("/score", json={"application_id": 999999}, headers={"X-Service-Key": "s3cret"})
    assert r.status_code == 404 and r.json()["detail"]


# ---------------------------------------------------------------- вход в систему
def test_expired_token_and_blocked_user(client, login, session):
    u = session.query(User).filter_by(login="officer").one()
    old = jwt.encode({"sub": str(u.id), "role": u.role, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                     get_settings().token_secret, algorithm="HS256")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"})
    assert r.status_code == 401 and "истёк" in r.json()["detail"]
    h = login("officer")
    u.active = False
    session.commit()
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 401 and "заблокирован" in r.json()["detail"]
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password(client):
    r = client.post("/api/auth/token", data={"username": "officer", "password": "wrong-pass"})
    assert r.status_code in (400, 401)


def test_ldap_password_check(client, session, monkeypatch):
    from creditdss import security
    monkeypatch.setattr(get_settings(), "ldap_url", "ldap://dc.bank.local")
    monkeypatch.setattr(security, "ldap_bind", lambda login, pw: pw == "domain-pass")
    assert client.post("/api/auth/token", data={"username": "officer", "password": "domain-pass"}).status_code == 200
    # каталог не подтвердил — проверяется локальный пароль
    assert client.post("/api/auth/token", data={"username": "officer", "password": "secret1"}).status_code == 200
    # admin всегда входит по локальному паролю
    assert client.post("/api/auth/token", data={"username": "admin", "password": "domain-pass"}).status_code != 200


def test_ldap_bind_without_directory_is_false(monkeypatch):
    from creditdss import security
    monkeypatch.setattr(get_settings(), "ldap_url", "")
    assert security.ldap_bind("officer", "x") is False
    monkeypatch.setattr(get_settings(), "ldap_url", "ldap://127.0.0.1:1")
    monkeypatch.setattr(get_settings(), "ldap_timeout", 1)
    assert security.ldap_bind("officer", "") is False
