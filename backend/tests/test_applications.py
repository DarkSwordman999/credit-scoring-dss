"""Жизненный цикл заявки через API: регистрация (С-1, С-2), сбор данных и повторы (С-3, С-4), скоринг,
решения (С-11, С-12), комитет, документы (П-3), выдача, уведомление, роли (С-17), журнал (С-18)."""
from datetime import date, datetime, timedelta

import pytest

from creditdss import appsettings
from creditdss.models import Application, AuditLog, BkiRequest, Loan, Notification
from creditdss.services import integration

from factories import application_body

CLEAN_BKI = {"loans_count": 2, "active_loans": 1, "total_debt": 50000, "monthly_payments": 5000, "max_dpd": 0,
             "current_dpd": 0, "dpd30_12m": 0, "inquiries_6m": 1, "history_months": 48, "bankruptcy": False}


@pytest.fixture(autouse=True)
def clean_bureau(monkeypatch):
    """Детерминированные ответы БКИ и АБС для проверок процесса."""
    monkeypatch.setattr(integration, "demo_bki", lambda subject: dict(CLEAN_BKI, raw={"test": True}))
    monkeypatch.setattr(integration, "demo_abs", lambda subject: integration._normalize_abs(
        {"is_client": True, "client_since_months": 30, "salary_project": True, "salary_avg": 120000}))


def create(api, login, **over):
    r = api.post("/api/applications", json=application_body(**over), headers=login("officer"))
    assert r.status_code == 200, r.text
    return r.json()


def register(client, login, app_id):
    return client.post(f"/api/applications/{app_id}/register", headers=login("officer"))


def test_full_cycle_approve_and_issue(client, login, session):
    app = create(client, login)
    assert app["status"] == "draft" and app["number"].startswith("КЗ-")
    r = register(client, login, app["id"])
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["status"] == "review"
    assert card["credit_report"]["found"] and card["abs"]["salary_project"]
    assert {v["check"] for v in card["verifications"]} == {"passport", "stoplist", "rosfin"}
    sc = card["scoring"]
    assert sc["recommendation"] == "approve" and sc["risk_class"] in ("A", "B") and sc["pd"] < 0.05
    assert len(sc["features"]) >= 30
    assert card["actions"] == ["upload"]

    uw = client.get(f"/api/applications/{app['id']}", headers=login("underwriter")).json()
    assert "decide" in uw["actions"]
    r = client.post(f"/api/applications/{app['id']}/decision", headers=login("underwriter"),
                    json={"outcome": "approve", "amount": sc["rec_amount"], "term_months": sc["rec_term"],
                          "rate": sc["rec_rate"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    n = session.query(Notification).filter_by(application_id=app["id"]).one()
    assert "одобрен" in n.text and n.channel == "sms"

    r = client.post(f"/api/applications/{app['id']}/issue", headers=login("officer"))
    assert r.json()["status"] == "issued"
    loan = session.query(Loan).filter_by(application_id=app["id"]).one()
    assert loan.contract_number == "КД-" + app["number"].removeprefix("КЗ-")
    actions = [a.action for a in session.query(AuditLog).filter_by(entity_id=app["number"]).order_by(AuditLog.id)]
    assert actions[0] == "Создание заявки" and "Кредит выдан" in actions


def test_registration_requires_consents_and_valid_fields(client, login):
    app = create(client, login, consents=[], application={"amount": 10_000_000})
    r = register(client, login, app["id"])
    assert r.status_code == 400
    errors = r.json()["errors"]
    assert any("персональных данных" in e for e in errors)
    assert any("БКИ" in e for e in errors)
    assert any("сумма" in e for e in errors)
    expired = (date.today() - timedelta(days=1)).isoformat()
    app = create(client, login, consents=[{"kind": "pd", "signed_at": "2025-01-01", "valid_until": expired},
                                          {"kind": "bki", "signed_at": "2025-01-01", "valid_until": expired}])
    assert register(client, login, app["id"]).status_code == 400


def test_bad_passport_format_rejected(client, login):
    body = application_body(client={"passport_series": "70AB"})
    r = client.post("/api/applications", json=body, headers=login("officer"))
    assert r.status_code == 400


def test_bki_unavailable_retries_then_scores(client, login, session, monkeypatch):
    def down(subject):
        raise integration.Unavailable("БКИ: сервис временно недоступен")
    monkeypatch.setattr(integration, "demo_bki", down)
    app = create(client, login)
    card = register(client, login, app["id"]).json()
    assert card["status"] == "collecting"
    assert card["collection"]["status"] == "pending" and card["collection"]["attempts"] == 1

    from creditdss import db
    from creditdss.services import applications
    with db.session() as s:            # время повтора ещё не пришло
        assert applications.retry_due(s) == 0
        req = s.query(BkiRequest).filter_by(application_id=app["id"]).one()
        req.next_attempt_at = datetime.now() - timedelta(seconds=1)
        s.commit()
        assert applications.retry_due(s) == 1
        s.commit()
        req = s.query(BkiRequest).filter_by(application_id=app["id"]).one()
        assert req.attempts == 2 and req.status == "pending"
        req.next_attempt_at = datetime.now() - timedelta(seconds=1)
        s.commit()
        applications.retry_due(s)
        s.commit()
        req = s.query(BkiRequest).filter_by(application_id=app["id"]).one()
        assert req.attempts == 3 and req.status == "failed"   # три попытки (С-3)

    monkeypatch.setattr(integration, "demo_bki", lambda subject: dict(CLEAN_BKI, raw={}))
    r = client.post(f"/api/applications/{app['id']}/collect", headers=login("officer"))
    assert r.json()["status"] == "review"


def test_decision_differs_requires_comment(client, login):
    app = create(client, login)
    sc = register(client, login, app["id"]).json()["scoring"]
    url = f"/api/applications/{app['id']}/decision"
    r = client.post(url, headers=login("underwriter"), json={"outcome": "reject", "comment": "коротко"})
    assert r.status_code == 400 and "С-11" in r.json()["detail"]
    r = client.post(url, headers=login("underwriter"),
                    json={"outcome": "approve", "amount": sc["rec_amount"], "term_months": 36,
                          "rate": sc["rec_rate"] - 3, "comment": "мало"})
    assert r.status_code == 400
    r = client.post(url, headers=login("underwriter"),
                    json={"outcome": "reject", "comment": "Клиент не подтвердил место работы по телефону"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["refusal_reasons"] is not None


def test_over_limit_goes_to_committee(client, login, session):
    app = create(client, login, application={"amount": 800000, "term_months": 60})
    sc = register(client, login, app["id"]).json()["scoring"]
    assert sc["recommendation"] != "reject"
    amount = sc["rec_amount"]
    assert amount > 500000
    r = client.post(f"/api/applications/{app['id']}/decision", headers=login("underwriter"),
                    json={"outcome": sc["recommendation"], "amount": amount, "term_months": 60, "rate": sc["rec_rate"]})
    assert r.json()["status"] == "committee"
    # андеррайтер больше не решает, решает руководитель
    assert client.post(f"/api/applications/{app['id']}/committee", headers=login("underwriter"),
                       json={"outcome": "approve"}).status_code == 403
    r = client.post(f"/api/applications/{app['id']}/committee", headers=login("head"),
                    json={"outcome": sc["recommendation"], "amount": amount, "term_months": 60,
                          "rate": sc["rec_rate"]})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    stages = [d["stage"] for d in r.json()["decisions"]]
    assert stages == ["underwriter", "committee"]


def test_stop_factor_reject_reason_for_client(client, login, session):
    app = create(client, login, client={"birth_date": (date.today() - timedelta(days=19 * 366)).isoformat()})
    sc = register(client, login, app["id"]).json()["scoring"]
    assert sc["recommendation"] == "reject" and sc["stop_factors"][0]["code"] == "SF01"
    r = client.post(f"/api/applications/{app['id']}/decision", headers=login("underwriter"), json={"outcome": "reject"})
    assert r.json()["status"] == "rejected"
    n = session.query(Notification).filter_by(application_id=app["id"]).one()
    assert "возраст" in n.text.lower()


def test_documents_and_request_docs(client, login):
    app = create(client, login)
    files = {"file": ("паспорт.pdf", b"%PDF-1.4 test", "application/pdf")}
    r = client.post(f"/api/applications/{app['id']}/documents", headers=login("officer"), data={"kind": "паспорт"},
                    files=files)
    assert r.status_code == 200 and r.json()["documents"][0]["filename"] == "паспорт.pdf"
    bad = client.post(f"/api/applications/{app['id']}/documents", headers=login("officer"), data={"kind": "x"},
                      files={"file": ("a.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400
    doc_id = r.json()["documents"][0]["id"]
    dl = client.get(f"/api/applications/{app['id']}/documents/{doc_id}", headers=login("underwriter"))
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 test"

    register(client, login, app["id"])
    r = client.post(f"/api/applications/{app['id']}/decision", headers=login("underwriter"),
                    json={"outcome": "docs", "comment": "Справка 2-НДФЛ за 6 месяцев"})
    assert r.json()["status"] == "docs_required"
    r = client.post(f"/api/applications/{app['id']}/documents", headers=login("officer"), data={"kind": "справка"},
                    files={"file": ("справка.png", b"\x89PNG", "image/png")})
    assert r.status_code == 200
    r = client.post(f"/api/applications/{app['id']}/return", headers=login("officer"))
    assert r.json()["status"] == "review" and len(r.json()["scoring_history"]) == 2


def test_roles(client, login):
    app = create(client, login)
    assert client.post("/api/applications", json=application_body(), headers=login("underwriter")).status_code == 403
    assert client.get(f"/api/applications/{app['id']}", headers=login("admin")).status_code == 403
    masked = client.get(f"/api/applications/{app['id']}", headers=login("analyst")).json()
    assert masked["client"]["passport_number"] == "******"
    register(client, login, app["id"])
    assert client.post(f"/api/applications/{app['id']}/decision", headers=login("head"),
                       json={"outcome": "reject"}).status_code == 403


def test_edit_only_draft(client, login):
    app = create(client, login)
    body = application_body(application={"amount": 400000})
    r = client.put(f"/api/applications/{app['id']}", json=body, headers=login("officer"))
    assert r.status_code == 200 and r.json()["application"]["amount"] == 400000
    register(client, login, app["id"])
    assert client.put(f"/api/applications/{app['id']}", json=body, headers=login("officer")).status_code == 409


def test_scoring_service_fallback(client, login, session, monkeypatch):
    """Сервис скоринга недоступен — оценка по резервной методике с пометкой (ПР 4, табл. 4.3)."""
    from creditdss.config import get_settings
    monkeypatch.setattr(get_settings(), "scoring_url", "http://127.0.0.1:9")
    app = create(client, login)
    sc = register(client, login, app["id"]).json()["scoring"]
    assert sc["fallback"] is True and sc["model_version"] is None


def test_list_and_search(client, login):
    a = create(client, login)
    r = client.get("/api/applications", params={"q": a["number"]}, headers=login("underwriter")).json()
    assert r["total"] == 1 and r["items"][0]["number"] == a["number"]
    r = client.get("/api/applications", params={"status": ["draft"]}, headers=login("officer")).json()
    assert r["total"] >= 1
    found = client.get("/api/applications/clients/search", headers=login("officer"),
                       params={"passport_series": "7015",
                               "passport_number": application_body()["client"]["passport_number"]})
    assert found.status_code == 200


def test_audit_log_is_read_only(session):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    session.execute(text("INSERT INTO audit_log (created_at, user_login, action, entity, entity_id, changes) "
                         "VALUES (CURRENT_TIMESTAMP, 't', 'проверка', '', '', '{}')"))
    with pytest.raises(DBAPIError):
        session.execute(text("UPDATE audit_log SET action = 'подмена'"))
    with pytest.raises(DBAPIError):
        session.execute(text("DELETE FROM audit_log"))


def test_settings_validation(client, login, session):
    h = login("admin")
    assert client.put("/api/admin/settings", json={"bki_retries": 0}, headers=h).status_code == 400
    assert client.put("/api/admin/settings", json={"risk_classes": [["A", 0.5], ["B", 0.1], ["C", None]]},
                      headers=h).status_code == 400
    r = client.put("/api/admin/settings", json={"bki_retries": 5}, headers=h)
    assert r.status_code == 200 and r.json()["values"]["bki_retries"] == 5
    assert appsettings.get(session, "bki_retries") == 5
