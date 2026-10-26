"""Жизненный цикл кредитной заявки (ПР 7-8: КонтроллерЗаявок, КонтроллерРешений; табл. 7.10 — состояния).

Черновик → Зарегистрирована → Сбор данных → Скоринг → На рассмотрении → Одобрена / Отклонена /
На кредитном комитете → Выдана / Отказ клиента. Из «На рассмотрении» андеррайтер может запросить документы.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import appsettings, audit
from ..errors import Conflict, DomainError
from ..models import (RECOMMENDATIONS, STATUSES, AbsData, Application, BkiRequest, Client, Consent, CreditReport,
                      Decision, Employment, Loan, Notification, Product, ScoringResult, StopListEntry, User,
                      Verification)
from . import integration, scoring_client

PASSPORT_SERIES = re.compile(r"^\d{4}$")
PASSPORT_NUMBER = re.compile(r"^\d{6}$")


# ---------------------------------------------------------------- черновик и регистрация

def next_number(db: Session) -> str:
    year = date.today().year
    prefix = f"КЗ-{year}-"
    last = db.query(func.max(Application.number)).filter(Application.number.like(prefix + "%")).scalar()
    n = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{n:06d}"


def _client(db: Session, c: dict) -> Client:
    series, number = str(c["passport_series"]).strip(), str(c["passport_number"]).strip()
    client = db.query(Client).filter_by(passport_series=series, passport_number=number).first()
    fields = {k: c[k] for k in ("last_name", "first_name", "middle_name", "birth_date", "passport_issued",
                                "citizenship", "reg_address", "phone", "email") if k in c}
    for k in ("last_name", "first_name", "middle_name", "citizenship", "reg_address", "phone", "email"):
        if k in fields and isinstance(fields[k], str):
            fields[k] = fields[k].strip()
    if client is None:
        client = Client(passport_series=series, passport_number=number, **fields)
        db.add(client)
        db.flush()
    else:
        for k, v in fields.items():
            setattr(client, k, v)
    return client


def _check_draft_input(data: dict) -> None:
    c = data["client"]
    if not PASSPORT_SERIES.match(str(c.get("passport_series", "")).strip()) or \
            not PASSPORT_NUMBER.match(str(c.get("passport_number", "")).strip()):
        raise DomainError("Серия паспорта — 4 цифры, номер — 6 цифр")


def create_draft(db: Session, user: User, data: dict) -> Application:
    _check_draft_input(data)
    client = _client(db, data["client"])
    emp = Employment(client_id=client.id, **data["employment"])
    db.add(emp)
    db.flush()
    app = Application(number=next_number(db), client_id=client.id, employment_id=emp.id, officer_id=user.id,
                      status="draft", **data["application"])
    db.add(app)
    db.flush()
    _set_consents(db, app, data.get("consents") or [])
    audit.log(db, user, "Создание заявки", "application", app.number,
              {"сумма": [None, float(app.amount)], "срок": [None, app.term_months]})
    return app


def _set_consents(db: Session, app: Application, consents: list[dict]) -> None:
    db.query(Consent).filter_by(application_id=app.id).delete()
    for c in consents:
        if c.get("kind") not in ("pd", "bki"):
            raise DomainError("Вид согласия: pd (обработка ПДн) или bki (запрос в БКИ)")
        db.add(Consent(application_id=app.id, kind=c["kind"], signed_at=c["signed_at"], valid_until=c["valid_until"]))


def update_draft(db: Session, user: User, app: Application, data: dict) -> Application:
    if app.status != "draft":
        raise Conflict("Изменять можно только черновик заявки")
    _check_draft_input(data)
    client = _client(db, data["client"])
    app.client_id = client.id
    changes = audit.diff(app.employment, data["employment"])
    changes.update(audit.diff(app, data["application"]))
    _set_consents(db, app, data.get("consents") or [])
    audit.log(db, user, "Изменение черновика заявки", "application", app.number, changes)
    return app


def validate_for_registration(db: Session, app: Application) -> list[str]:
    """С-1: обязательные поля, форматы и диапазоны; С-2: действующие согласия на обработку ПДн и запрос в БКИ."""
    errors = []
    cl, emp, prod = app.client, app.employment, app.product
    for label, v in (("фамилия", cl.last_name), ("имя", cl.first_name)):
        if not (v or "").strip():
            errors.append(f"не указана {label} клиента")
    today = date.today()
    if cl.birth_date is None or not (date(1900, 1, 1) < cl.birth_date < today):
        errors.append("неверная дата рождения")
    elif (today - cl.birth_date).days < 18 * 365:
        errors.append("клиенту нет 18 лет")
    if not PASSPORT_SERIES.match(cl.passport_series or "") or not PASSPORT_NUMBER.match(cl.passport_number or ""):
        errors.append("серия паспорта — 4 цифры, номер — 6 цифр")
    if not prod.active:
        errors.append(f"продукт «{prod.name}» не действует")
    if not float(prod.min_amount) <= float(app.amount) <= float(prod.max_amount):
        errors.append(f"сумма для продукта «{prod.name}» — от {float(prod.min_amount):,.0f} до "
                      f"{float(prod.max_amount):,.0f} руб.".replace(",", " "))
    if not prod.min_term <= app.term_months <= prod.max_term:
        errors.append(f"срок для продукта «{prod.name}» — от {prod.min_term} до {prod.max_term} мес.")
    if emp.employment_type != "unemployed" and float(emp.income_confirmed or 0) <= 0:
        errors.append("не указан подтверждённый доход")
    if not cl.phone and not cl.email:
        errors.append("нужен телефон или e-mail клиента для уведомления о решении")
    kinds = {c.kind for c in db.query(Consent).filter_by(application_id=app.id).all()
             if c.signed_at <= today <= c.valid_until}
    if "pd" not in kinds:
        errors.append("нет действующего согласия на обработку персональных данных")
    if "bki" not in kinds:
        errors.append("нет действующего согласия на запрос кредитного отчёта в БКИ")
    return errors


def register(db: Session, user: User, app: Application) -> Application:
    if app.status != "draft":
        raise Conflict("Зарегистрировать можно только черновик")
    errors = validate_for_registration(db, app)
    if errors:
        raise DomainError("Заявку нельзя зарегистрировать: " + "; ".join(errors), data={"errors": errors})
    app.status = "registered"
    app.registered_at = datetime.now()
    audit.log(db, user, "Регистрация заявки", "application", app.number, {"статус": ["draft", "registered"]})
    db.flush()
    collect(db, app, user)
    return app


# ---------------------------------------------------------------- сбор данных (ПР 5-6, блок A2)

def _subject(app: Application) -> integration.Subject:
    c = app.client
    return integration.Subject(c.last_name, c.first_name, c.middle_name or "", c.birth_date.isoformat(),
                               c.passport_series, c.passport_number)


def collect(db: Session, app: Application, user: User | None = None, manual: bool = False) -> Application:
    """Параллельно: запрос отчёта в БКИ, проверка паспорта и стоп-листов, данные АБС (перекрёсток «И» J1);
    досье формируется, когда получено всё (J2). Если БКИ или АБС недоступны — повтор по расписанию (С-3)."""
    st = appsettings.all_(db)
    if app.status not in ("registered", "collecting"):
        raise Conflict("Сбор данных уже выполнен")
    prev = app.status
    app.status = "collecting"
    subject = _subject(app)
    stoplist = [{"source": e.source, "passport_series": e.passport_series, "passport_number": e.passport_number,
                 "full_name": e.full_name, "birth_date": e.birth_date.isoformat() if e.birth_date else None,
                 "reason": e.reason} for e in db.query(StopListEntry).all()]
    consent = db.query(Consent).filter_by(application_id=app.id, kind="bki").first()
    consent_info = {"signed_at": consent.signed_at.isoformat(), "valid_until": consent.valid_until.isoformat()} \
        if consent else {}
    need_bki = db.query(CreditReport).filter_by(application_id=app.id).first() is None
    need_abs = db.query(AbsData).filter_by(application_id=app.id).first() is None

    def run_bki():
        if not need_bki:
            return "skip", None
        try:
            return "ok", integration.bki_report(subject, consent_info, st["bki_mode"], st["bki_url"],
                                                st["bki_demo_failure_rate"])
        except integration.Unavailable as e:
            return "unavailable", str(e)

    def run_abs():
        if not need_abs:
            return "skip", None
        try:
            return "ok", integration.abs_client(subject, st["abs_mode"], st["abs_url"])
        except integration.Unavailable as e:
            return "unavailable", str(e)

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_bki, f_abs = pool.submit(run_bki), pool.submit(run_abs)
        f_ver = pool.submit(integration.verify, subject, stoplist)
        bki_res, abs_res, ver = f_bki.result(), f_abs.result(), f_ver.result()

    db.query(Verification).filter_by(application_id=app.id).delete()
    for check, (passed, msg) in ver.items():
        db.add(Verification(application_id=app.id, check=check, passed=passed, message=msg))

    req = db.query(BkiRequest).filter_by(application_id=app.id).first()
    if req is None:
        req = BkiRequest(application_id=app.id, attempts=0)
        db.add(req)
    if manual:
        req.attempts = 0
    problems = []
    if bki_res[0] == "ok":
        rep = bki_res[1]
        if rep is None:
            db.add(CreditReport(application_id=app.id, found=False, raw={"message": "субъект не найден"}))
            audit.integration(db, "bki", f"{app.number}: субъект не найден, кредитной истории нет")
        else:
            raw = rep.pop("raw", {})
            db.add(CreditReport(application_id=app.id, found=True, raw=raw, **rep))
            audit.integration(db, "bki", f"{app.number}: кредитный отчёт получен")
    elif bki_res[0] == "unavailable":
        problems.append(bki_res[1])
        audit.integration(db, "bki", f"{app.number}: {bki_res[1]}", status="error")
    if abs_res[0] == "ok":
        d = abs_res[1]
        raw = d.pop("raw", {})
        db.add(AbsData(application_id=app.id, raw=raw, **d))
        audit.integration(db, "abs", f"{app.number}: данные клиента получены")
    elif abs_res[0] == "unavailable":
        problems.append(abs_res[1])
        audit.integration(db, "abs", f"{app.number}: {abs_res[1]}", status="error")

    if problems:
        req.attempts += 1
        if req.attempts >= int(st["bki_retries"]):
            req.status = "failed"
            req.next_attempt_at = None
            req.message = (f"данные не получены после {req.attempts} попыток: " + "; ".join(problems) +
                           ". Повторите запрос вручную")
        else:
            req.status = "pending"
            req.next_attempt_at = datetime.now() + timedelta(minutes=int(st["bki_retry_minutes"]))
            req.message = "; ".join(problems) + f". Повтор в {req.next_attempt_at:%H:%M}"
        if prev != "collecting":
            audit.log(db, user, "Сбор данных: ожидание внешних систем", "application", app.number,
                      {"статус": [prev, "collecting"]})
        return app
    req.status = "ok"
    req.next_attempt_at = None
    req.message = "кредитное досье сформировано"
    audit.log(db, user, "Кредитное досье сформировано", "application", app.number, {"статус": [prev, "scoring"]})
    app.status = "scoring"
    db.flush()
    run_scoring(db, app, user)
    return app


def retry_due(db: Session) -> int:
    """Повторные запросы по расписанию (вызывается планировщиком каждую минуту)."""
    due = (db.query(BkiRequest).join(Application, Application.id == BkiRequest.application_id)
           .filter(BkiRequest.status == "pending", BkiRequest.next_attempt_at <= datetime.now(),
                   Application.status == "collecting").all())
    for req in due:
        collect(db, db.get(Application, req.application_id))
    return len(due)


# ---------------------------------------------------------------- скоринг (ПР 5-6, блок A3)

def run_scoring(db: Session, app: Application, user: User | None = None) -> ScoringResult:
    res = scoring_client.score(db, app.id)
    sr = ScoringResult(application_id=app.id, model_id=res.get("model_id"), pd=res["pd"], score=res["score"],
                       risk_class=res["risk_class"], pdn=res["pdn"], stop_factors=res["stop_factors"],
                       factors=res["factors"], features=res["features"], recommendation=res["recommendation"],
                       rec_amount=res["rec_amount"], rec_term=res["rec_term"], rec_rate=res["rec_rate"],
                       fallback=res.get("fallback", False), duration_ms=res.get("duration_ms", 0))
    db.add(sr)
    prev = app.status
    app.status = "review"
    note = " (резервная методика)" if sr.fallback else ""
    audit.log(db, user, f"Скоринг заявки{note}: {RECOMMENDATIONS[sr.recommendation]}", "application", app.number,
              {"статус": [prev, "review"], "PD": [None, sr.pd], "класс": [None, sr.risk_class],
               "ПДН": [None, sr.pdn]})
    db.flush()
    return sr


def latest_scoring(db: Session, app_id: int) -> ScoringResult | None:
    return (db.query(ScoringResult).filter_by(application_id=app_id)
            .order_by(ScoringResult.id.desc()).first())


def rescore(db: Session, user: User, app: Application) -> ScoringResult:
    if app.status != "review":
        raise Conflict("Повторная оценка возможна для заявки «На рассмотрении»")
    return run_scoring(db, app, user)


# ---------------------------------------------------------------- решения (ПР 7-8, вариант «Принять решение»)

def _differs(sr: ScoringResult, outcome: str, amount, rate) -> bool:
    if sr is None:
        return True
    if outcome != sr.recommendation:
        return True
    if outcome in ("approve", "approve_changed"):
        if sr.rec_amount is not None and amount is not None and float(amount) > float(sr.rec_amount) + 0.005:
            return True
        if sr.rec_rate is not None and rate is not None and float(rate) < float(sr.rec_rate) - 0.005:
            return True
    return False


def _check_terms(app: Application, outcome: str, amount, term, rate) -> None:
    if outcome not in ("approve", "approve_changed"):
        return
    prod = app.product
    if amount is None or term is None or rate is None:
        raise DomainError("Для одобрения укажите сумму, срок и ставку")
    if not float(prod.min_amount) <= float(amount) <= float(prod.max_amount):
        raise DomainError("Сумма вне диапазона продукта")
    if not prod.min_term <= int(term) <= prod.max_term:
        raise DomainError("Срок вне диапазона продукта")
    if not 0 < float(rate) < 100:
        raise DomainError("Неверная ставка")


def decide(db: Session, user: User, app: Application, outcome: str, amount=None, term=None, rate=None,
           comment: str = "") -> Decision:
    """Решение андеррайтера: одобрить, одобрить на изменённых условиях, отказать или запросить документы."""
    if app.status != "review":
        raise Conflict("Решение принимается по заявке в статусе «На рассмотрении»")
    if outcome not in ("approve", "approve_changed", "reject", "docs"):
        raise DomainError("Неизвестное решение")
    comment = (comment or "").strip()
    sr = latest_scoring(db, app.id)
    if outcome == "docs":
        if not comment:
            raise DomainError("Укажите, какие документы нужны")
        d = Decision(application_id=app.id, user_id=user.id, stage="underwriter",
                     recommendation=sr.recommendation if sr else "", outcome="docs", comment=comment)
        db.add(d)
        app.status = "docs_required"
        audit.log(db, user, "Запрос дополнительных документов", "application", app.number,
                  {"статус": ["review", "docs_required"], "комментарий": [None, comment]})
        return d
    _check_terms(app, outcome, amount, term, rate)
    min_len = int(appsettings.get(db, "comment_min"))
    if _differs(sr, outcome, amount, rate) and len(comment) < min_len:
        raise DomainError(f"Решение отличается от рекомендации системы: нужен комментарий не короче "
                          f"{min_len} символов (С-11)")
    over_limit = outcome != "reject" and user.limit_amount is not None and float(amount) > float(user.limit_amount)
    d = Decision(application_id=app.id, user_id=user.id, stage="underwriter",
                 recommendation=sr.recommendation if sr else "", outcome="committee" if over_limit else outcome,
                 amount=amount if outcome != "reject" else None, term_months=term if outcome != "reject" else None,
                 rate=rate if outcome != "reject" else None, comment=comment)
    db.add(d)
    if over_limit:
        # С-12: сумма больше лимита полномочий — заявка уходит на кредитный комитет
        app.status = "committee"
        audit.log(db, user, "Заявка передана на кредитный комитет (сумма сверх лимита полномочий)", "application",
                  app.number, {"статус": ["review", "committee"], "сумма": [None, float(amount)],
                               "лимит": [None, float(user.limit_amount)]})
        return d
    _finish(db, user, app, outcome, d)
    return d


def committee_decide(db: Session, user: User, app: Application, outcome: str, amount=None, term=None, rate=None,
                     comment: str = "") -> Decision:
    if app.status != "committee":
        raise Conflict("Заявка не на кредитном комитете")
    if outcome not in ("approve", "approve_changed", "reject"):
        raise DomainError("Неизвестное решение")
    comment = (comment or "").strip()
    _check_terms(app, outcome, amount, term, rate)
    sr = latest_scoring(db, app.id)
    min_len = int(appsettings.get(db, "comment_min"))
    if _differs(sr, outcome, amount, rate) and len(comment) < min_len:
        raise DomainError(f"Решение отличается от рекомендации системы: нужен комментарий не короче "
                          f"{min_len} символов (С-11)")
    if outcome != "reject" and user.limit_amount is not None and float(amount) > float(user.limit_amount):
        raise DomainError("Сумма превышает и ваш лимит полномочий")
    d = Decision(application_id=app.id, user_id=user.id, stage="committee",
                 recommendation=sr.recommendation if sr else "", outcome=outcome,
                 amount=amount if outcome != "reject" else None, term_months=term if outcome != "reject" else None,
                 rate=rate if outcome != "reject" else None, comment=comment)
    db.add(d)
    _finish(db, user, app, outcome, d)
    return d


def _finish(db: Session, user: User, app: Application, outcome: str, d: Decision) -> None:
    prev = app.status
    app.status = "rejected" if outcome == "reject" else "approved"
    app.decided_at = datetime.now()
    changes = {"статус": [prev, app.status]}
    if d.amount is not None:
        changes.update({"сумма": [None, float(d.amount)], "срок": [None, d.term_months], "ставка": [None, d.rate]})
    stage = "Кредитный комитет" if d.stage == "committee" else "Решение андеррайтера"
    audit.log(db, user, f"{stage}: {STATUSES[app.status].lower()}", "application", app.number, changes)
    db.flush()
    notify_client(db, app, d)


def refusal_reasons(db: Session, app_id: int, n: int = 3) -> list[str]:
    """Причины отказа для клиента (П-5, уточнение аттестации): стоп-факторы или главные факторы риска."""
    sr = latest_scoring(db, app_id)
    if sr is None:
        return []
    if sr.stop_factors:
        return [s["description"] for s in sr.stop_factors]
    return [f"{x['label']}: {x['bin']}" for x in sr.factors if x.get("effect") == "risk_up"][:n]


def notify_client(db: Session, app: Application, d: Decision) -> Notification:
    cl = app.client
    if app.status == "approved":
        text = (f"Уважаемый(ая) {cl.first_name} {cl.middle_name}! По заявке {app.number} одобрен кредит "
                f"{float(d.amount):,.0f} руб. на {d.term_months} мес. под {d.rate:.2f} % годовых. "
                f"Ждём вас в офисе Банка для оформления договора.").replace(",", " ")
    else:
        reasons = refusal_reasons(db, app.id)
        text = (f"Уважаемый(ая) {cl.first_name} {cl.middle_name}! По заявке {app.number} Банк принял решение "
                f"об отказе в кредите.")
        if reasons:
            text += " Основные причины: " + "; ".join(reasons).lower() + "."
    channel, recipient = ("sms", cl.phone) if cl.phone else ("email", cl.email)
    n = Notification(application_id=app.id, channel=channel, recipient=recipient, text=text, status="sent")
    db.add(n)
    audit.integration(db, "notify", f"{app.number}: уведомление клиенту ({channel} {recipient})")
    return n


def return_to_review(db: Session, user: User, app: Application) -> Application:
    """Документы получены — заявка снова на рассмотрении, оценка пересчитывается."""
    if app.status != "docs_required":
        raise Conflict("Заявка не ожидает документов")
    app.status = "review"
    audit.log(db, user, "Документы предоставлены, заявка возвращена на рассмотрение", "application", app.number,
              {"статус": ["docs_required", "review"]})
    run_scoring(db, app, user)
    return app


def issue(db: Session, user: User, app: Application) -> Loan:
    """Кредит выдан: заявка передаётся в АБС для оформления договора (ПР 3, интеграция с АБС)."""
    if app.status != "approved":
        raise Conflict("Выдать можно только одобренную заявку")
    d = (db.query(Decision).filter(Decision.application_id == app.id,
                                   Decision.outcome.in_(("approve", "approve_changed")))
         .order_by(Decision.id.desc()).first())
    st = appsettings.all_(db)
    payload = {"number": app.number, "client": app.client.full_name, "amount": float(d.amount),
               "term_months": d.term_months, "rate": d.rate}
    try:
        contract = integration.abs_send_approved(payload, st["abs_mode"], st["abs_url"])
    except integration.Unavailable as e:
        audit.integration(db, "abs", f"{app.number}: {e}", status="error")
        raise DomainError(f"Не удалось передать заявку в АБС: {e}", status=503)
    loan = Loan(application_id=app.id, contract_number=contract, issued_at=date.today(), amount=d.amount,
                term_months=d.term_months, rate=d.rate)
    db.add(loan)
    app.status = "issued"
    audit.integration(db, "abs", f"{app.number}: передана в АБС, договор {contract}")
    audit.log(db, user, "Кредит выдан", "application", app.number,
              {"статус": ["approved", "issued"], "договор": [None, contract]})
    return loan


def client_refused(db: Session, user: User, app: Application, comment: str = "") -> Application:
    if app.status != "approved":
        raise Conflict("Отказ клиента фиксируется по одобренной заявке")
    app.status = "client_refused"
    audit.log(db, user, "Отказ клиента от кредита", "application", app.number,
              {"статус": ["approved", "client_refused"], "комментарий": [None, comment]})
    return app


def queue_counts(db: Session) -> dict:
    rows = db.query(Application.status, func.count()).group_by(Application.status).all()
    return {s: n for s, n in rows}


def ensure_product(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id)
    if p is None:
        raise DomainError("Кредитный продукт не найден")
    return p
