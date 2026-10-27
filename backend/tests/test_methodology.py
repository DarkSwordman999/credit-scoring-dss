"""Методика оценки: проверка на истории (С-13), утверждение и публикация (С-14), откат, мониторинг (С-15);
отчёты (С-16), обмен с АБС, резервные копии (Н-1), демо-данные."""
import copy

import pytest

from creditdss.models import Loan, MonitoringReport, ScoringModel

pytestmark = pytest.mark.demo


def _models(client, login):
    return {m["version"]: m for m in client.get("/api/models", headers=login("analyst")).json()}


def test_demo_data_meets_quality_criterion(session):
    v1 = session.query(ScoringModel).filter_by(version=1).one()
    assert v1.status == "published"
    assert v1.metrics["n"] >= 200 and v1.metrics["bad"] >= 10
    assert v1.metrics["auc"] >= 0.7          # на небольшой тестовой истории; на полной демо-БД ≈ 0,79
    assert session.query(MonitoringReport).count() == 12


def test_candidate_lifecycle(client, login, session):
    ms = _models(client, login)
    assert ms[1]["status"] == "published" and ms[2]["status"] == "candidate"
    v2 = client.get(f"/api/models/{ms[2]['id']}", headers=login("analyst")).json()
    # правка параметров сбрасывает проверку
    params = copy.deepcopy(v2["params"])
    params["characteristics"][0]["bins"][2]["points"] = 36
    r = client.put(f"/api/models/{v2['id']}", json={"params": params}, headers=login("analyst"))
    assert r.status_code == 200 and r.json()["metrics"] == {}
    assert client.post(f"/api/models/{v2['id']}/submit", headers=login("analyst")).status_code == 400
    r = client.post(f"/api/models/{v2['id']}/validate", json={}, headers=login("analyst"))
    assert r.status_code == 200, r.text
    m = r.json()["metrics"]
    assert {"auc", "gini", "ks", "n", "published", "brier", "pd_mean", "calibration"} <= set(m)
    cal = m["calibration"]
    assert [c["risk_class"] for c in cal] == ["A", "B", "C", "D", "E"]
    assert sum(c["n"] for c in cal) == m["n"] and sum(c.get("bad", 0) for c in cal) == m["bad"]
    assert 0 <= m["brier"] <= 1
    if m["gini"] < m["published"]["gini"]:      # на малой истории кандидат может оказаться хуже — берём баллы v1
        assert client.post(f"/api/models/{v2['id']}/submit", headers=login("analyst")).status_code == 400
        v1 = client.get(f"/api/models/{ms[1]['id']}", headers=login("analyst")).json()
        client.put(f"/api/models/{v2['id']}", json={"params": v1["params"]}, headers=login("analyst"))
        client.post(f"/api/models/{v2['id']}/validate", json={}, headers=login("analyst"))
    r = client.post(f"/api/models/{v2['id']}/submit", headers=login("analyst"))
    assert r.json()["status"] == "approval"
    # публикует только риск-аналитик и только после утверждения руководителем (С-14)
    assert client.post(f"/api/models/{v2['id']}/publish", headers=login("analyst")).status_code == 409
    assert client.post(f"/api/models/{v2['id']}/approve", json={"approve": True},
                       headers=login("analyst")).status_code == 403
    assert client.post(f"/api/models/{v2['id']}/approve", json={"approve": True},
                       headers=login("head")).json()["status"] == "approved"
    assert client.post(f"/api/models/{v2['id']}/publish", headers=login("head")).status_code == 403
    assert client.post(f"/api/models/{v2['id']}/publish", headers=login("analyst")).json()["status"] == "published"
    ms = _models(client, login)
    assert ms[1]["status"] == "archived" and ms[2]["status"] == "published"
    # откат на предыдущую версию
    r = client.post(f"/api/models/{ms[1]['id']}/rollback", headers=login("analyst"))
    assert r.json()["status"] == "published"
    assert _models(client, login)[2]["status"] == "archived"


def test_worse_candidate_cannot_be_submitted(client, login):
    ms = _models(client, login)
    r = client.post("/api/models", json={"source_id": ms[1]["id"], "name": "Плохая версия"}, headers=login("analyst"))
    m = r.json()
    params = copy.deepcopy(m["params"])
    for ch in params["characteristics"]:        # переворачиваем баллы: модель станет хуже случайной
        for b in ch["bins"]:
            b["points"] = -b["points"]
    client.put(f"/api/models/{m['id']}", json={"params": params}, headers=login("analyst"))
    v = client.post(f"/api/models/{m['id']}/validate", json={}, headers=login("analyst")).json()
    assert v["metrics"]["gini"] < v["metrics"]["published"]["gini"]
    r = client.post(f"/api/models/{m['id']}/submit", headers=login("analyst"))
    assert r.status_code == 400 and "запрещена" in r.json()["detail"]


def test_invalid_params_rejected(client, login):
    ms = _models(client, login)
    v2 = client.get(f"/api/models/{ms[2]['id']}", headers=login("analyst")).json()
    params = copy.deepcopy(v2["params"])
    params["pdo"] = -1
    r = client.put(f"/api/models/{v2['id']}", json={"params": params}, headers=login("analyst"))
    assert r.status_code == 400 and r.json()["errors"]


def test_monitoring(client, login):
    r = client.post("/api/models/monitoring", json={}, headers=login("analyst"))
    assert r.status_code == 200 and "psi" in r.json()
    rows = client.get("/api/models/monitoring", headers=login("head")).json()
    assert rows and {"psi", "gini", "alerts"} <= set(rows[0])
    assert client.post("/api/models/monitoring", json={"period": "2026-13"}, headers=login("analyst")).status_code == 400


@pytest.mark.parametrize("kind", ["applications", "decisions", "portfolio", "model"])
def test_reports(client, login, kind):
    params = {"date_from": "2025-01-01", "date_to": "2026-12-31"}
    r = client.get(f"/api/reports/{kind}", params=params, headers=login("head"))
    assert r.status_code == 200 and r.json()["tables"]
    x = client.get(f"/api/reports/{kind}", params={**params, "format": "xlsx"}, headers=login("head"))
    assert x.status_code == 200 and x.content[:2] == b"PK"
    p = client.get(f"/api/reports/{kind}", params={**params, "format": "pdf"}, headers=login("head"))
    assert p.status_code == 200 and p.content[:4] == b"%PDF"
    assert client.get(f"/api/reports/{kind}", params=params, headers=login("officer")).status_code == 403


def test_analyst_report_masks_names(client, login):
    r = client.get("/api/reports/applications", params={"date_from": "2025-01-01", "date_to": "2026-12-31"},
                   headers=login("analyst")).json()
    rows = [t for t in r["tables"] if t["title"] == "Заявки"][0]["rows"]
    assert all(row[2].endswith("***") for row in rows[:20])


def test_abs_loan_servicing(client, session):
    loan = session.query(Loan).filter_by(status="active").first()
    body = {"loans": [{"contract_number": loan.contract_number, "status": "default", "max_dpd_12m": 95},
                      {"contract_number": "нет-такого", "status": "closed", "max_dpd_12m": 0}]}
    assert client.post("/api/integration/abs/loans", json=body).status_code == 401
    r = client.post("/api/integration/abs/loans", json=body, headers={"X-API-Key": "abs-demo-key"})
    assert r.json() == {"updated": 1, "not_found": ["нет-такого"]}
    session.expire_all()
    assert session.get(Loan, loan.id).max_dpd_12m == 95


def test_backup_and_audit_export(client, login):
    h = login("admin")
    name = client.post("/api/admin/backups", headers=h).json()["name"]
    assert name in [b["name"] for b in client.get("/api/admin/backups", headers=h).json()]
    assert client.get(f"/api/admin/backups/{name}", headers=h).status_code == 200
    a = client.get("/api/admin/audit", params={"xlsx": True}, headers=h)
    assert a.status_code == 200 and a.content[:2] == b"PK"
    rows = client.get("/api/admin/audit", params={"action": "Проверка версии"}, headers=h).json()
    assert rows["total"] >= 1


def test_dashboards(client, login):
    for user in ("officer", "underwriter", "head", "analyst", "admin"):
        r = client.get("/api/dashboard", headers=login(user))
        assert r.status_code == 200 and "counts" in r.json()
    assert client.get("/api/dashboard", headers=login("underwriter")).json()["queues"][0]["items"]
