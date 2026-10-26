"""Версии методики оценки (ПР 7-8, СервисОбучения; С-13, С-14) и мониторинг качества (С-15).

Версия-кандидат создаётся копированием существующей и правится риск-аналитиком (баллы характеристик,
калибровка). Затем она проверяется на истории: заявки, по которым выданы кредиты и прошло 12 месяцев
(«созревшие»), оцениваются баллами кандидата и действующей версии; целевая переменная — просрочка 90+ дней
в течение 12 месяцев. Хуже действующей по Gini — на утверждение не отправляется (ПР 7-8, поток 4а).
"""
import copy
import random
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .. import appsettings, audit
from ..errors import Conflict, DomainError, NotFound
from ..models import Application, Loan, MonitoringReport, ScoringModel, ScoringResult, User
from ..scoring import metrics, scorecard

MIN_SAMPLE = 200
MIN_BAD = 10
REFERENCE_SIZE = 2000


def get(db: Session, model_id: int) -> ScoringModel:
    m = db.get(ScoringModel, model_id)
    if m is None:
        raise NotFound("Версия методики не найдена")
    return m


def published(db: Session) -> ScoringModel | None:
    return db.query(ScoringModel).filter_by(status="published").order_by(ScoringModel.version.desc()).first()


def create_candidate(db: Session, user: User, source_id: int, name: str = "", comment: str = "") -> ScoringModel:
    src = get(db, source_id)
    version = (db.query(ScoringModel.version).order_by(ScoringModel.version.desc()).first()[0]) + 1
    m = ScoringModel(version=version, name=name or f"{src.name} (версия {version})", algorithm=src.algorithm,
                     status="candidate", params=copy.deepcopy(src.params), metrics={}, comment=comment, created_by=user.id)
    db.add(m)
    db.flush()
    audit.log(db, user, f"Создана версия методики {version} на основе версии {src.version}", "model", version)
    return m


def update_candidate(db: Session, user: User, m: ScoringModel, params: dict | None, name: str | None,
                     comment: str | None) -> ScoringModel:
    if m.status != "candidate":
        raise Conflict("Изменять можно только версию-кандидат")
    changes = {}
    if params is not None:
        errors = scorecard.validate(params)
        if errors:
            raise DomainError("Ошибки в параметрах: " + "; ".join(errors), data={"errors": errors})
        changes["параметры"] = ["…", "изменены"]
        m.params = params
        m.metrics = {}        # после изменения версию нужно проверить заново
    if name is not None and name != m.name:
        changes["название"] = [m.name, name]
        m.name = name
    if comment is not None:
        m.comment = comment
    audit.log(db, user, f"Изменена версия методики {m.version}", "model", m.version, changes)
    return m


def matured_sample(db: Session, date_from: date | None = None, date_to: date | None = None):
    """Созревшие кредиты: выданы не позже чем 12 месяцев назад. Возвращает [(признаки, плохой)]."""
    cutoff = date.today() - timedelta(days=365)
    q = (db.query(Loan, Application).join(Application, Application.id == Loan.application_id)
         .filter(Loan.issued_at <= cutoff))
    if date_from:
        q = q.filter(Loan.issued_at >= date_from)
    if date_to:
        q = q.filter(Loan.issued_at <= date_to)
    rows = q.all()
    if not rows:
        return []
    ids = [a.id for _, a in rows]
    feats = {}
    for chunk in range(0, len(ids), 500):
        part = ids[chunk:chunk + 500]
        for sr in (db.query(ScoringResult).filter(ScoringResult.application_id.in_(part))
                   .order_by(ScoringResult.id).all()):
            feats[sr.application_id] = sr.features      # последняя оценка заявки перед решением
    return [(feats[a.id], loan.max_dpd_12m >= 90) for loan, a in rows if a.id in feats and feats[a.id]]


def scored_features(db: Session, date_from: date | None, date_to: date | None) -> list[dict]:
    """Признаки заявок, оценённых моделью (без отказов по стоп-факторам), поданных в периоде выборки."""
    cutoff = datetime.combine(date.today() - timedelta(days=365), datetime.min.time())
    q = db.query(ScoringResult.features).filter(ScoringResult.pd.isnot(None))
    q = q.filter(ScoringResult.created_at <= (datetime.combine(date_to, datetime.max.time()) if date_to else cutoff))
    if date_from:
        q = q.filter(ScoringResult.created_at >= datetime.combine(date_from, datetime.min.time()))
    return [f for (f,) in q.all() if f]


def _pds(params: dict, features: list[dict]) -> list[float]:
    return [scorecard.pd_from_score(params, scorecard.score(params, f)[0]) for f in features]


def validate(db: Session, user: User, m: ScoringModel, date_from: date | None, date_to: date | None) -> dict:
    """С-13: метрики ROC AUC, Gini, KS на отложенной выборке созревших кредитов и сравнение с действующей версией."""
    sample = matured_sample(db, date_from, date_to)
    bad = [b for _, b in sample]
    if len(sample) < MIN_SAMPLE or sum(bad) < MIN_BAD:
        raise DomainError(f"Недостаточный объём данных: созревших кредитов {len(sample)}, из них с дефолтом "
                          f"{sum(bad)}; нужно не меньше {MIN_SAMPLE} и {MIN_BAD}")
    feats = [f for f, _ in sample]
    cand_pd = _pds(m.params, feats)
    res = {"period": [date_from.isoformat() if date_from else None, date_to.isoformat() if date_to else None],
           "checked_at": datetime.now().isoformat(timespec="seconds"), **metrics.evaluate(cand_pd, bad)}
    pub = published(db)
    if pub is not None and pub.id != m.id:
        res["published"] = {"version": pub.version, **metrics.evaluate(_pds(pub.params, feats), bad)}
    # эталон для PSI (С-15) — оценки всех заявок того же периода, а не только выданных кредитов
    ref = _pds(m.params, scored_features(db, date_from, date_to))
    rnd = random.Random(m.version)
    res["reference_pd"] = [round(p, 6) for p in (ref if len(ref) <= REFERENCE_SIZE
                                                  else rnd.sample(ref, REFERENCE_SIZE))]
    m.metrics = res
    audit.log(db, user, f"Проверка версии методики {m.version} на истории", "model", m.version,
              {"ROC AUC": [None, res["auc"]], "Gini": [None, res["gini"]], "KS": [None, res["ks"]],
               "выборка": [None, res["n"]]})
    return res


def _worse_than_published(m: ScoringModel) -> str | None:
    pub = m.metrics.get("published")
    if pub and pub.get("gini") is not None and m.metrics.get("gini") is not None and m.metrics["gini"] < pub["gini"]:
        return (f"Gini версии {m.version} ({m.metrics['gini']:.3f}) ниже, чем у действующей версии "
                f"{pub['version']} ({pub['gini']:.3f}): публикация запрещена")
    return None


def submit(db: Session, user: User, m: ScoringModel) -> ScoringModel:
    if m.status != "candidate":
        raise Conflict("На утверждение отправляется версия-кандидат")
    if m.metrics.get("gini") is None:
        raise DomainError("Сначала проверьте версию на истории выданных кредитов")
    worse = _worse_than_published(m)
    if worse:
        raise DomainError(worse)
    m.status = "approval"
    audit.log(db, user, f"Версия методики {m.version} отправлена на утверждение", "model", m.version,
              {"статус": ["candidate", "approval"]})
    return m


def approve(db: Session, user: User, m: ScoringModel, ok: bool, comment: str = "") -> ScoringModel:
    if m.status != "approval":
        raise Conflict("Версия не ожидает утверждения")
    if not ok and not (comment or "").strip():
        raise DomainError("Укажите причину отклонения")
    m.status = "approved" if ok else "rejected"
    m.approved_by = user.id
    m.approved_at = datetime.now()
    if comment:
        m.comment = (m.comment + "\n" if m.comment else "") + f"Руководитель: {comment}"
    audit.log(db, user, f"Версия методики {m.version} {'утверждена' if ok else 'отклонена'}", "model", m.version,
              {"статус": ["approval", m.status]})
    return m


def publish(db: Session, user: User, m: ScoringModel) -> ScoringModel:
    """С-14: публикует риск-аналитик после утверждения руководителем; предыдущая версия уходит в архив."""
    if m.status != "approved":
        raise Conflict("Опубликовать можно только утверждённую версию")
    worse = _worse_than_published(m)
    if worse:
        raise DomainError(worse)
    return _make_current(db, user, m, "Публикация")


def rollback(db: Session, user: User, m: ScoringModel) -> ScoringModel:
    """Откат на архивную версию, которая уже была опубликована раньше."""
    if m.status != "archived" or m.published_at is None:
        raise Conflict("Откатиться можно на архивную версию, которая раньше была опубликована")
    return _make_current(db, user, m, "Откат")


def _make_current(db: Session, user: User, m: ScoringModel, what: str) -> ScoringModel:
    prev = published(db)
    if prev is not None:
        prev.status = "archived"
    old = m.status
    m.status = "published"
    m.published_at = datetime.now()
    audit.log(db, user, f"{what} версии методики {m.version}", "model", m.version,
              {"статус": [old, "published"], "действовала": [prev.version if prev else None, m.version]})
    return m


# ---------------------------------------------------------------- мониторинг (С-15)

def _month_bounds(period: str) -> tuple[datetime, datetime]:
    y, mo = map(int, period.split("-"))
    start = datetime(y, mo, 1)
    end = datetime(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)
    return start, end


def monitor(db: Session, period: str, user: User | None = None) -> MonitoringReport:
    """PSI оценок за месяц относительно эталонной выборки версии и Gini на кредитах, созревших к концу месяца."""
    try:
        start, end = _month_bounds(period)
    except ValueError:
        raise DomainError("Период — в формате ГГГГ-ММ")
    m = published(db)
    if m is None:
        raise DomainError("Нет опубликованной версии методики")
    cur_feats = [sr.features for sr in db.query(ScoringResult)
                 .filter(ScoringResult.created_at >= start, ScoringResult.created_at < end,
                         ScoringResult.pd.isnot(None)).all() if sr.features]
    current = _pds(m.params, cur_feats)
    reference = m.metrics.get("reference_pd") or []
    psi = metrics.psi(reference, current) if current else None

    lo, hi = (start - timedelta(days=730)).date(), (end - timedelta(days=366)).date()
    sample = [(f, b) for f, b in matured_sample(db, lo, hi)]
    gini = None
    dr = None
    if sample:
        bad = [b for _, b in sample]
        ev = metrics.evaluate(_pds(m.params, [f for f, _ in sample]), bad)
        gini, dr = ev["gini"], ev["default_rate"]
    gini_ref = m.metrics.get("gini")
    st = appsettings.all_(db)
    alerts = []
    if psi is not None and psi > float(st["psi_alert"]):
        alerts.append(f"PSI {psi:.3f} больше порога {float(st['psi_alert']):.2f}: заметно изменился поток заявок")
    if gini is not None and gini_ref and (gini_ref - gini) / gini_ref > float(st["gini_drop_alert"]):
        alerts.append(f"Gini снизился с {gini_ref:.3f} до {gini:.3f} (более чем на "
                      f"{float(st['gini_drop_alert']) * 100:.0f} %): рассмотрите пересмотр методики")
    db.query(MonitoringReport).filter_by(period=period, model_id=m.id).delete()
    rep = MonitoringReport(period=period, model_id=m.id, n_scored=len(current), psi=psi, n_matured=len(sample),
                           gini=gini, gini_ref=gini_ref, default_rate=dr, alerts=alerts,
                           details={"matured_issued": [lo.isoformat(), hi.isoformat()], "version": m.version})
    db.add(rep)
    audit.log(db, user, f"Мониторинг методики за {period}", "model", m.version,
              {"PSI": [None, psi], "Gini": [None, gini], "оповещений": [None, len(alerts)]})
    return rep


def previous_month(today: date | None = None) -> str:
    d = (today or date.today()).replace(day=1) - timedelta(days=1)
    return f"{d.year}-{d.month:02d}"
