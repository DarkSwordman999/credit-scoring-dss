"""Справочники кредитной политики (С-12): продукты, стоп-факторы, матрица условий, стоп-лист — права,
проверки ввода и журнал аудита."""
from creditdss.models import AuditLog
from creditdss.scoring.engine import DEFAULT_MATRIX

PRODUCT = {"name": "Тестовый кредит", "min_amount": 10000, "max_amount": 500000, "min_term": 6, "max_term": 60,
           "base_rate": 18.5}
RULES = [dict(zip(("risk_class", "pdn_from", "pdn_to", "decision", "amount_factor", "rate_add"), r))
         for r in DEFAULT_MATRIX]


def test_product_create_update_and_rights(client, login, session):
    assert client.post("/api/nsi/products", json=PRODUCT, headers=login("analyst")).status_code == 403
    r = client.post("/api/nsi/products", json=PRODUCT, headers=login("admin"))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    assert client.post("/api/nsi/products", json=PRODUCT, headers=login("admin")).status_code == 409
    bad = dict(PRODUCT, min_amount=600000)
    assert client.post("/api/nsi/products", json=dict(bad, name="Другой"), headers=login("admin")).status_code == 400
    r = client.put(f"/api/nsi/products/{pid}", json=dict(PRODUCT, base_rate=17.0), headers=login("admin"))
    assert r.status_code == 200 and r.json()["base_rate"] == 17.0
    assert client.put("/api/nsi/products/9999", json=PRODUCT, headers=login("admin")).status_code == 404
    assert session.query(AuditLog).filter_by(entity="product", entity_id=str(pid)).count() == 2


def test_product_rename_to_existing_name_is_conflict(client, login):
    names = [p["name"] for p in client.get("/api/nsi/products", headers=login("admin")).json()]
    pid = client.post("/api/nsi/products", json=PRODUCT, headers=login("admin")).json()["id"]
    r = client.put(f"/api/nsi/products/{pid}", json=dict(PRODUCT, name=names[0]), headers=login("admin"))
    assert r.status_code == 409
    # то же название у самого продукта — не конфликт
    assert client.put(f"/api/nsi/products/{pid}", json=PRODUCT, headers=login("admin")).status_code == 200


def test_product_usage(client, login):
    assert client.get("/api/nsi/usage/1", headers=login("admin")).json() == {"applications": 0}


def test_stop_factors_validation_and_rights(client, login):
    rules = client.get("/api/nsi/stop-factor-rules", headers=login("officer")).json()
    assert {"rule": "age_min", "name": "Возраст меньше порога, лет", "needs_threshold": True} in rules
    body = {"code": "SF99", "description": "Возраст меньше 25 лет", "rule": "age_min", "threshold": 25}
    assert client.post("/api/nsi/stop-factors", json=body, headers=login("officer")).status_code == 403
    assert client.post("/api/nsi/stop-factors", json=dict(body, rule="zodiac"), headers=login("analyst")).status_code == 400
    assert client.post("/api/nsi/stop-factors", json=dict(body, threshold=None), headers=login("analyst")).status_code == 400
    r = client.post("/api/nsi/stop-factors", json=body, headers=login("analyst"))
    assert r.status_code == 200 and r.json()["needs_threshold"] is True
    sid = r.json()["id"]
    assert client.post("/api/nsi/stop-factors", json=body, headers=login("analyst")).status_code == 409
    r = client.put(f"/api/nsi/stop-factors/{sid}", json=dict(body, active=False), headers=login("analyst"))
    assert r.status_code == 200 and r.json()["active"] is False
    assert client.put("/api/nsi/stop-factors/9999", json=body, headers=login("analyst")).status_code == 404


def test_stop_factor_code_change_to_existing_is_conflict(client, login):
    body = {"code": "SF99", "description": "x", "rule": "bankruptcy", "threshold": None}
    sid = client.post("/api/nsi/stop-factors", json=body, headers=login("analyst")).json()["id"]
    r = client.put(f"/api/nsi/stop-factors/{sid}", json=dict(body, code="SF01"), headers=login("analyst"))
    assert r.status_code == 409


def test_conditions_save_valid_matrix(client, login):
    rules = [dict(r) for r in RULES]
    for r in rules:
        if r["risk_class"] == "D" and r["pdn_from"] == 0.0:
            r["rate_add"] = 7.0
    r = client.put("/api/nsi/conditions", json={"rules": rules}, headers=login("analyst"))
    assert r.status_code == 200, r.text
    d = [x for x in r.json()["rules"] if x["risk_class"] == "D" and x["pdn_from"] == 0.0][0]
    assert d["rate_add"] == 7.0
    assert client.put("/api/nsi/conditions", json={"rules": rules}, headers=login("officer")).status_code == 403


def _without(rules, cls, pdn_from):
    return [r for r in rules if not (r["risk_class"] == cls and r["pdn_from"] == pdn_from)]


def test_conditions_rejects_broken_matrix(client, login):
    h = login("analyst")
    cases = {
        "нет класса": RULES + [dict(RULES[0], risk_class="Z")],
        "от больше до": [dict(r, pdn_from=0.9) if (r["risk_class"], r["pdn_from"]) == ("A", 0.5) else r for r in RULES],
        "не с нуля": _without(RULES, "B", 0.0),
        "пропуск": _without(RULES, "A", 0.5),
        "последний не открыт": _without(RULES, "E", 0.0) + [dict(RULES[-1], pdn_to=0.8)],
    }
    for name, rules in cases.items():
        r = client.put("/api/nsi/conditions", json={"rules": rules}, headers=h)
        assert r.status_code == 400, (name, r.text)
    r = client.put("/api/nsi/conditions", json={"rules": cases["последний не открыт"]}, headers=h)
    assert "открытым" in r.json()["detail"]
    # после отказов матрица прежняя
    saved = client.get("/api/nsi/conditions", headers=h).json()["rules"]
    assert len(saved) == len(RULES)


def test_conditions_with_new_classes(client, login):
    classes = [["A", 0.05], ["B", None]]
    rules = [{"risk_class": "A", "pdn_from": 0, "pdn_to": 99, "decision": "approve", "amount_factor": 1, "rate_add": 0},
             {"risk_class": "B", "pdn_from": 0, "pdn_to": 99, "decision": "reject", "amount_factor": 0, "rate_add": 0}]
    r = client.put("/api/nsi/conditions", json={"classes": classes, "rules": rules}, headers=login("analyst"))
    assert r.status_code == 200, r.text
    assert r.json()["classes"] == classes and len(r.json()["rules"]) == 2


def test_stoplist(client, login):
    h = login("admin")
    assert client.post("/api/nsi/stoplist", json={"source": "internal"}, headers=h).status_code == 400
    body = {"source": "internal", "passport_series": "7015", "passport_number": "123456", "reason": "мошенничество"}
    assert client.post("/api/nsi/stoplist", json=body, headers=login("analyst")).status_code == 403
    eid = client.post("/api/nsi/stoplist", json=body, headers=h).json()["id"]
    lst = client.get("/api/nsi/stoplist", headers=login("underwriter")).json()
    assert lst[0]["id"] == eid and lst[0]["reason"] == "мошенничество"
    assert client.get("/api/nsi/stoplist", headers=login("officer")).status_code == 403
    assert client.delete(f"/api/nsi/stoplist/{eid}", headers=h).json() == {"ok": True}
    assert client.delete(f"/api/nsi/stoplist/{eid}", headers=h).status_code == 404
