"""Обращение к сервису скоринга (А-1, И-2).

CREDITDSS_SCORING_URL задан — оценка запрашивается у отдельного сервиса методом POST /score;
не задан — тот же расчёт выполняется в этом процессе. Если сервис недоступен, заявка оценивается
по резервной (балльной) методике — базовой экспертной карте — с пометкой в журнале (ПР 4, табл. 4.3).
"""
import httpx
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..scoring import engine, scorecard
from . import dossier


def compute(db: Session, app_id: int) -> dict:
    """Оценка опубликованной версией методики в этом процессе."""
    model = dossier.published_model(db)
    pol = dossier.policy(db)
    res = engine.evaluate(dossier.build(db, app_id), model.params, pol["stop_factors"], pol["classes"],
                          pol["matrix"])
    res["model_id"] = model.id
    res["model_version"] = model.version
    res["fallback"] = False
    return res


def fallback(db: Session, app_id: int) -> dict:
    pol = dossier.policy(db)
    res = engine.evaluate(dossier.build(db, app_id), scorecard.default_params(), pol["stop_factors"],
                          pol["classes"], pol["matrix"])
    res["model_id"] = None
    res["model_version"] = None
    res["fallback"] = True
    return res


def score(db: Session, app_id: int) -> dict:
    url = get_settings().scoring_url
    if not url:
        return compute(db, app_id)
    try:
        r = httpx.post(url.rstrip("/") + "/score", json={"application_id": app_id},
                       headers={"X-Service-Key": get_settings().scoring_key},
                       timeout=get_settings().scoring_timeout)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        audit.integration(db, "scoring", f"сервис скоринга недоступен ({e}); заявка {app_id} оценена "
                                         f"по резервной методике", status="error")
        return fallback(db, app_id)
