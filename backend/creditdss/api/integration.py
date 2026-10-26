"""Входящий обмен с АБС: сведения об обслуживании выданных кредитов — из них формируется целевая переменная
(просрочка 90+ дней за 12 месяцев) для проверки и мониторинга методики."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import Loan
from ..security import abs_key

router = APIRouter(prefix="/api/integration", tags=["Интеграция с АБС"])


class LoanStateIn(BaseModel):
    contract_number: str
    status: Literal["active", "closed", "default"]
    max_dpd_12m: int = Field(ge=0)


class LoansIn(BaseModel):
    loans: list[LoanStateIn]


@router.post("/abs/loans", summary="Сведения об обслуживании кредитов (АБС, заголовок X-API-Key)")
def loans_state(body: LoansIn, _: str = Depends(abs_key), db: Session = Depends(get_db)):
    found, missing = 0, []
    for item in body.loans:
        loan = db.query(Loan).filter_by(contract_number=item.contract_number).first()
        if loan is None:
            missing.append(item.contract_number)
            continue
        loan.status = item.status
        loan.max_dpd_12m = max(loan.max_dpd_12m, item.max_dpd_12m)
        found += 1
    audit.integration(db, "abs", f"обслуживание кредитов: обновлено {found}, не найдено {len(missing)}",
                      direction="in", status="ok" if not missing else "warn")
    db.commit()
    return {"updated": found, "not_found": missing}
