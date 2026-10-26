"""Сервис скоринга (ПР 7-8, компонент scoring-service; А-1, И-2, Р-1).

Отдельный процесс: принимает идентификатор заявки и возвращает PD, класс риска, ПДН, стоп-факторы и вклад
факторов. Состояния не хранит — читает досье и опубликованную версию методики из БД, поэтому можно запускать
несколько экземпляров за балансировщиком. Запуск: uvicorn creditdss.scoring_service:app --port 8001.
Сервис рассчитан на внутреннюю сеть; CREDITDSS_SCORING_KEY задаёт ключ, без которого запросы отклоняются.
"""
import hmac

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import __version__, db
from .config import get_settings
from .errors import DomainError
from .services import scoring_client

app = FastAPI(title="СППР «Кредитный скоринг» — сервис скоринга", version=__version__,
              docs_url="/docs", openapi_url="/openapi.json")


class ScoreIn(BaseModel):
    application_id: int


@app.exception_handler(DomainError)
async def _domain(_, exc: DomainError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


@app.post("/score", summary="Оценить заявку: PD, класс риска, ПДН, факторы")
def score(body: ScoreIn, x_service_key: str = Header(default="")):
    key = get_settings().scoring_key
    if key and not hmac.compare_digest(x_service_key, key):
        raise HTTPException(401, "Неверный ключ сервиса")
    with db.session() as s:
        return scoring_client.compute(s, body.application_id)


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}
