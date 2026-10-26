"""Отчёты за произвольный период с выгрузкой в XLSX и PDF (С-16; ПР 7-8, вариант «Сформировать отчёт»)."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db_long
from ..models import User
from ..security import require
from ..services import pdf, reports, xlsx

router = APIRouter(prefix="/api/reports", tags=["Отчёты"])


@router.get("", summary="Виды отчётов")
def kinds(user: User = Depends(require("head", "risk_analyst"))):
    return [{"kind": k, "title": v} for k, v in reports.KINDS.items()]


@router.get("/{kind}", summary="Сформировать отчёт; format=xlsx или pdf — выгрузка в файл")
def report(kind: str, date_from: date, date_to: date, format: Literal["json", "xlsx", "pdf"] = "json",
           user: User = Depends(require("head", "risk_analyst")), db: Session = Depends(get_db_long)):
    rep = reports.build(db, kind, date_from, date_to, masked=user.role == "risk_analyst")
    if format == "json":
        return rep
    audit.log(db, user, f"Выгрузка отчёта «{rep['title']}» в {format.upper()}", "report", kind,
              {"период": [None, f"{date_from} — {date_to}"]})
    db.commit()
    name = f"{rep['title']} {date_from:%d.%m.%Y}-{date_to:%d.%m.%Y}"
    if format == "xlsx":
        return xlsx.response(xlsx.build_tables(rep["title"], rep["meta"], rep["summary"], rep["tables"]), name + ".xlsx")
    return pdf.response(pdf.build(rep["title"], rep["meta"] + [(k, str(v)) for k, v in rep["summary"]],
                                  rep["tables"]), name + ".pdf")
