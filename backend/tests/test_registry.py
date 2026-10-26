"""Реестр заёмщиков, кредитный портфель, причины решений в списке заявок, просмотр таблиц БД, демо-подсказка входа."""
import pytest

from creditdss import appsettings

pytestmark = pytest.mark.demo


def test_application_list_has_decision_and_reason(client, login):
    r = client.get("/api/applications", params={"status": ["rejected"], "size": 20}, headers=login("head")).json()
    assert r["total"] > 0
    for a in r["items"]:
        assert a["decision"] == "reject" and a["decided_by"]
        assert a["reason"], a["number"]
    approved = client.get("/api/applications", params={"status": ["issued"], "size": 5}, headers=login("head")).json()
    assert all(a["decision"] in ("approve", "approve_changed") for a in approved["items"])


def test_application_filters_by_class_and_product(client, login):
    r = client.get("/api/applications", params={"risk_class": ["A"], "size": 50}, headers=login("head")).json()
    assert r["total"] > 0 and {a["risk_class"] for a in r["items"]} == {"A"}
    products = client.get("/api/nsi/products", headers=login("head")).json()
    pid = products[0]["id"]
    r = client.get("/api/applications", params={"product_id": pid, "size": 50}, headers=login("head")).json()
    assert {a["product"] for a in r["items"]} == {products[0]["name"]}


def test_clients_registry_and_card(client, login):
    h = login("head")
    r = client.get("/api/clients", params={"with_loans": True, "size": 10}, headers=h).json()
    assert r["total"] > 0 and all(c["loans"] > 0 for c in r["items"])
    repeat = client.get("/api/clients", params={"size": 200}, headers=h).json()["items"]
    assert any(c["applications"] > 1 for c in repeat), "в демо-данных есть повторные обращения"
    cid = r["items"][0]["id"]
    card = client.get(f"/api/clients/{cid}", headers=h).json()
    assert card["client"]["passport_number"] != "******"
    assert card["stats"]["loans"] == len(card["loans"]) >= 1
    assert all(a["client_id"] == cid for a in card["applications"])
    found = client.get("/api/clients", params={"q": card["client"]["passport_number"]}, headers=h).json()
    assert [c["id"] for c in found["items"]] == [cid]


def test_analyst_sees_clients_masked(client, login):
    r = client.get("/api/clients", params={"size": 1}, headers=login("analyst")).json()["items"][0]
    assert "***" in r["full_name"] and r["passport"].endswith("******") and r["phone"] == "***"
    card = client.get(f"/api/clients/{r['id']}", headers=login("analyst")).json()
    assert card["client"]["passport_number"] == "******"


def test_admin_has_no_access_to_clients(client, login):
    assert client.get("/api/clients", headers=login("admin")).status_code == 403
    assert client.get("/api/loans", headers=login("admin")).status_code == 403


def test_loan_portfolio(client, login):
    r = client.get("/api/loans", params={"size": 10}, headers=login("head")).json()
    s = r["summary"]
    assert r["total"] == s["count"] > 0
    assert sum(v["count"] for v in s["by_status"].values()) == s["count"]
    assert sum(c["count"] for c in s["by_class"]) == s["count"]
    assert abs(sum(v["amount"] for v in s["by_status"].values()) - s["amount"]) < 1
    d = client.get("/api/loans", params={"status": ["default"]}, headers=login("head")).json()
    assert d["total"] == s["by_status"].get("default", {}).get("count", 0)
    assert all(x["status"] == "default" for x in d["items"])
    od = client.get("/api/loans", params={"overdue": True}, headers=login("head")).json()
    assert all(x["max_dpd_12m"] > 0 for x in od["items"])


def test_data_tables_masking_and_hidden_columns(client, login):
    tables = {t["name"]: t for t in client.get("/api/data/tables", headers=login("admin")).json()}
    assert {"applications", "clients", "loans", "audit_log"} <= set(tables)
    users = client.get("/api/data/tables/users", headers=login("admin")).json()
    assert "password_hash" not in [c["name"] for c in users["columns"]]
    masked = client.get("/api/data/tables/clients", headers=login("admin")).json()
    assert masked["items"][0]["last_name"] == "***"
    open_ = client.get("/api/data/tables/clients", headers=login("head")).json()
    assert open_["items"][0]["last_name"] != "***"
    flt = client.get("/api/data/tables/loans", params={"column": "status", "value": "default"},
                     headers=login("head")).json()
    assert flt["total"] == tables["loans"]["rows"] - client.get(
        "/api/data/tables/loans", params={"column": "status", "value": "active"}, headers=login("head")).json()["total"] \
        - client.get("/api/data/tables/loans", params={"column": "status", "value": "closed"},
                     headers=login("head")).json()["total"]
    bad = client.get("/api/data/tables/clients", params={"column": "last_name", "value": "Ив"}, headers=login("admin"))
    assert bad.status_code == 400
    assert client.get("/api/data/tables", headers=login("officer")).status_code == 403


def test_demo_users_hint(client, session):
    appsettings.set_(session, "demo_hint", False)
    session.commit()
    assert client.get("/api/auth/demo-users").json() == []
    appsettings.set_(session, "demo_hint", True)
    session.commit()
    logins = {u["login"]: u for u in client.get("/api/auth/demo-users").json()}
    # в тестах пароли officer, underwriter, head, analyst заменены — их подсказка не показывается
    assert set(logins) == {"admin", "officer2", "underwriter2"}
    assert logins["admin"]["password"] == "admin" and logins["officer2"]["password"] == "demo"
