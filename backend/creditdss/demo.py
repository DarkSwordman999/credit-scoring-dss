"""Демонстрационные данные: сотрудники, клиенты, заявки за 30 месяцев с досье, оценками, решениями,
выданными кредитами и их обслуживанием, текущая очередь заявок, мониторинг методики.

Все клиенты и паспорта вымышлены. Исход кредита (просрочка 90+ дней за 12 месяцев) задаёт отдельная
«истинная» модель риска с собственными весами и случайностью — скоринговая карта её не знает, поэтому
качество методики на истории (ROC AUC, Gini) получается реалистичным, а не идеальным.
"""
import copy
import math
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from . import audit
from .bootstrap import ensure_base
from .models import (AbsData, Application, BkiRequest, Client, Consent, CreditReport, Decision, Employment, Loan,
                     Notification, Product, ScoringModel, ScoringResult, StopListEntry, User, Verification)
from .scoring import engine
from .scoring import features as feat
from .security import hash_password
from .services import dossier, methodology

DEMO_PASSWORD = "demo"

STAFF = [
    ("officer", "Смирнова Анна Сергеевна", "credit_officer", None),
    ("officer2", "Кузнецов Павел Андреевич", "credit_officer", None),
    ("underwriter", "Волкова Елена Игоревна", "underwriter", 1_000_000),
    ("underwriter2", "Морозов Денис Олегович", "underwriter", 500_000),
    ("head", "Лебедев Сергей Викторович", "head", None),
    ("analyst", "Новикова Мария Петровна", "risk_analyst", None),
]

MALE_FIRST = ["Александр", "Дмитрий", "Максим", "Сергей", "Андрей", "Алексей", "Артём", "Илья", "Кирилл", "Михаил",
              "Никита", "Иван", "Роман", "Егор", "Владимир", "Павел", "Олег", "Николай", "Евгений", "Виктор"]
FEMALE_FIRST = ["Анна", "Мария", "Елена", "Ольга", "Наталья", "Татьяна", "Ирина", "Екатерина", "Светлана", "Юлия",
                "Анастасия", "Дарья", "Марина", "Ксения", "Алина", "Виктория", "Полина", "Галина", "Людмила", "Вера"]
LAST = ["Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Васильев", "Соколов", "Михайлов", "Новиков",
        "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов",
        "Николаев", "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев"]
MALE_MID = ["Александрович", "Сергеевич", "Андреевич", "Дмитриевич", "Игоревич", "Олегович", "Викторович",
            "Николаевич", "Павлович", "Михайлович"]
FEMALE_MID = ["Александровна", "Сергеевна", "Андреевна", "Дмитриевна", "Игоревна", "Олеговна", "Викторовна",
              "Николаевна", "Павловна", "Михайловна"]
EMPLOYERS = ["ООО «Тульский завод»", "АО «Тулачермет»", "ГУЗ «Городская больница № 1»", "МБОУ «Школа № 12»",
             "ООО «Торговый дом»", "ИП Сергеев", "ПАО «Ростелеком»", "АО «Почта России»", "ООО «Логистик-Центр»",
             "ООО «СтройИнвест»", "ГУ МВД", "ООО «Агрохолдинг»"]
POSITIONS = ["инженер", "менеджер", "бухгалтер", "водитель", "врач", "учитель", "продавец", "специалист",
             "оператор", "мастер", "экономист", "программист"]
PURPOSES = ["ремонт", "покупка техники", "лечение", "образование", "отдых", "покупка автомобиля", "текущие нужды"]
STREETS = ["ул. Ленина", "пр. Красноармейский", "ул. Советская", "ул. Пушкинская", "ул. Октябрьская"]


def _person(rnd: random.Random) -> dict:
    male = rnd.random() < 0.48
    last = rnd.choice(LAST) + ("" if male else "а")
    return {"last_name": last, "first_name": rnd.choice(MALE_FIRST if male else FEMALE_FIRST),
            "middle_name": rnd.choice(MALE_MID if male else FEMALE_MID)}


def _true_pd(f: dict, rnd: random.Random, scale: float = 2.3, noise: float = 0.3,
             intercept: float = -3.2) -> float:
    """«Истинная» вероятность дефолта для генерации исходов: гладкие зависимости и признаки, которых
    нет в скоринговой карте (иждивенцы, вклады, задолженность к доходу)."""
    z = 0.0
    z += 2.2 * max(0.0, f["pdn"] - 0.3)
    z -= 0.012 * min(f["experience_months"], 72)
    z -= 0.45 * math.log(max(f["income"], 15000) / 50000)
    z += 0.018 * max(0, 30 - f["age"]) + 0.012 * max(0, f["age"] - 58)
    z += 0.012 * min(f["max_dpd"], 120)
    z += 0.55 * min(f["dpd30_12m"], 3)
    z += 0.11 * min(f["inquiries_6m"], 12)
    z += 0.10 * max(0, f["active_loans"] - 2)
    z -= 0.45 if f["salary_project"] else 0
    z -= 0.25 if f["housing"] == "own" else (-0.25 if f["housing"] == "rent" else 0)
    z -= 0.2 if f["education"] == "higher" else 0
    z += 0.12 * min(f["dependents"], 4)
    z -= 0.3 if f["deposits_balance"] > 100000 else 0
    z += 0.25 * min(f["debt_to_income"], 3)
    z -= 0.006 * min(f["history_months"], 60) if f["bki_found"] else -0.15
    z = intercept + scale * z + rnd.gauss(0, noise)       # шум — то, чего не видно в данных
    return 1 / (1 + math.exp(-z))


def _profile(rnd: random.Random, products: list[Product], when: date, drift: float = 0.0) -> dict:
    age = int(min(72, max(21, rnd.gauss(40, 11)))) if rnd.random() > 0.01 else 20
    etype = rnd.choices(["employee", "self_employed", "pensioner", "unemployed"], [80, 10, 8, 2])[0]
    if age >= 62 and rnd.random() < 0.6:
        etype = "pensioner"
    income = round(math.exp(rnd.gauss(math.log(52000), 0.5)) / 100) * 100
    if etype == "pensioner":
        income = round(income * 0.7 / 100) * 100
    if etype == "unemployed":
        income = 0
    product = rnd.choices(products, [70, 18, 12])[0]
    term = rnd.choice([t for t in (6, 12, 18, 24, 36, 48, 60, 84) if product.min_term <= t <= product.max_term])
    # сумма — от посильного для клиента платежа: доля дохода на новый кредит
    share = min(0.7, rnd.betavariate(2.2, 7) * (1 + drift))
    payment = max(income, 20000) * share
    amount = payment / feat.annuity(1.0, product.base_rate, term)
    amount = max(float(product.min_amount), min(float(product.max_amount), round(amount / 10000) * 10000 or 30000))
    return {
        "age": age, "employment_type": etype, "income": income, "product": product, "amount": amount, "term": term,
        "experience": 0 if etype in ("unemployed", "pensioner") else int(min(360, rnd.expovariate(1 / 40))),
        "education": rnd.choices(["higher", "secondary_special", "secondary"], [45, 40, 15])[0],
        "housing": rnd.choices(["own", "mortgage", "rent", "parents"], [50, 18, 22, 10])[0],
        "marital": rnd.choices(["single", "married", "divorced", "widowed"], [30, 50, 15, 5])[0],
        "dependents": rnd.choices([0, 1, 2, 3], [45, 30, 20, 5])[0],
        "channel": rnd.choices(["office", "online"], [55, 45])[0],
    }


def _bki(rnd: random.Random, income: float, drift: float = 0.0) -> dict | None:
    if rnd.random() < 0.08:
        return None
    risky = rnd.random() < 0.15 + drift
    active = rnd.choices([0, 1, 2, 3, 4, 5], [20, 32, 24, 13, 7, 4])[0]
    payments = round(sum(income * rnd.uniform(0.05, 0.16) for _ in range(active)) * (1.3 if risky else 1), -2)
    max_dpd = rnd.choices([0, 5, 20, 45, 95, 130], [62, 14, 10, 7, 5, 2] if not risky else [25, 15, 18, 20, 15, 7])[0]
    return {"loans_count": active + rnd.randint(0, 6), "active_loans": active, "total_debt": round(payments * rnd.uniform(6, 30), -2),
            "monthly_payments": payments, "max_dpd": max_dpd,
            "current_dpd": rnd.choice([0] * 40 + [12, 40]) if risky else 0,
            "dpd30_12m": 0 if max_dpd < 30 else rnd.choices([0, 1, 2, 3], [40, 35, 15, 10])[0],
            "inquiries_6m": rnd.choices(range(0, 13), [18, 20, 17, 13, 10, 7, 5, 3, 2, 2, 1, 1, 1])[0]
            + (rnd.randint(1, 4) if risky else 0),
            "history_months": rnd.randint(3, 200), "bankruptcy": rnd.random() < 0.004}


def _abs(rnd: random.Random, income: float) -> dict:
    if rnd.random() < 0.55:
        return {"is_client": False, "client_since_months": 0, "salary_project": False, "salary_avg": 0,
                "accounts_count": 0, "deposits_balance": 0, "bank_loans_count": 0, "bank_monthly_payments": 0}
    salary = rnd.random() < 0.5 and income > 0
    return {"is_client": True, "client_since_months": rnd.randint(1, 120), "salary_project": salary,
            "salary_avg": round(income * rnd.uniform(0.95, 1.1), -2) if salary else 0,
            "accounts_count": rnd.randint(1, 4), "deposits_balance": rnd.choice([0, 0, 0, 20000, 80000, 250000, 700000]),
            "bank_loans_count": rnd.choice([0, 0, 1, 2]), "bank_monthly_payments": 0}


class _Gen:
    def __init__(self, db: Session, rnd: random.Random):
        self.db, self.rnd = db, rnd
        self.products = db.query(Product).order_by(Product.id).all()
        self.users = {u.login: u for u in db.query(User).all()}
        self.model = dossier.published_model(db)
        self.policy = dossier.policy(db)
        self.passports: set[tuple[str, str]] = set()
        self.seq: dict[int, int] = {}
        self.clients: list[tuple[int, datetime]] = []   # (клиент, дата последней заявки)
        self.returning_share = 0.22                     # доля повторных обращений

    def returning(self, when: datetime) -> Client | None:
        """Повторное обращение: клиент, подававший заявку не раньше чем за 3 месяца до этой и не моложе 21 года."""
        if not self.clients or self.rnd.random() >= self.returning_share:
            return None
        for _ in range(5):
            i = self.rnd.randrange(len(self.clients))
            cid, last = self.clients[i]
            if (when - last).days >= 90:
                c = self.db.get(Client, cid)
                age = (when.date() - c.birth_date).days / 365.25
                if 21 <= age <= 68:
                    self.clients.pop(i)
                    return c
        return None

    def number(self, year: int) -> str:
        self.seq[year] = self.seq.get(year, 0) + 1
        return f"КЗ-{year}-{self.seq[year]:06d}"

    def passport(self) -> tuple[str, str]:
        while True:
            p = (f"70{self.rnd.randint(1, 99):02d}", f"{self.rnd.randint(100000, 999999)}")
            if p not in self.passports:
                self.passports.add(p)
                return p

    def application(self, when: datetime, status_hint: str | None = None, drift: float = 0.0) -> Application:
        rnd, db = self.rnd, self.db
        pr = _profile(rnd, self.products, when.date(), drift)
        client = self.returning(when)
        if client is None:
            person = _person(rnd)
            series, number = self.passport()
            birth = when.date() - timedelta(days=pr["age"] * 365 + rnd.randint(0, 360))
            # паспорт выдан в 14 или 20 лет и не позже даты обращения
            issued = birth + timedelta(days=(20 if pr["age"] >= 21 else 14) * 365 + rnd.randint(0, 3000))
            issued = max(birth + timedelta(days=14 * 365), min(issued, when.date() - timedelta(days=rnd.randint(30, 400))))
            client = Client(**person, birth_date=birth, passport_series=series, passport_number=number,
                            passport_issued=issued,
                            citizenship="РФ" if rnd.random() > 0.01 else "Республика Беларусь",
                            reg_address=f"г. Тула, {rnd.choice(STREETS)}, д. {rnd.randint(1, 120)}, кв. {rnd.randint(1, 200)}",
                            phone=f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}",
                            email=(f"client{rnd.randint(1000, 9999)}@mail.ru" if rnd.random() < 0.4 else ""),
                            created_at=when)
            db.add(client)
            db.flush()
        self.clients.append((client.id, when))
        emp = Employment(client_id=client.id, employment_type=pr["employment_type"],
                         employer="" if pr["employment_type"] in ("unemployed", "pensioner") else rnd.choice(EMPLOYERS),
                         position="" if pr["employment_type"] in ("unemployed", "pensioner") else rnd.choice(POSITIONS),
                         experience_months=pr["experience"], income_confirmed=pr["income"], created_at=when)
        db.add(emp)
        db.flush()
        officer = self.users["officer" if rnd.random() < 0.6 else "officer2"]
        app = Application(number=self.number(when.year), client_id=client.id, product_id=pr["product"].id,
                          employment_id=emp.id, amount=pr["amount"], term_months=pr["term"],
                          purpose=rnd.choice(PURPOSES), channel=pr["channel"], marital_status=pr["marital"],
                          dependents=pr["dependents"], education=pr["education"], housing=pr["housing"],
                          status="draft", officer_id=officer.id, created_at=when, updated_at=when)
        db.add(app)
        db.flush()
        for kind in ("pd", "bki"):
            db.add(Consent(application_id=app.id, kind=kind, signed_at=when.date(),
                           valid_until=when.date() + timedelta(days=90)))
        self._app_profile = pr
        return app

    def dossier(self, app: Application, when: datetime, drift: float = 0.0) -> None:
        rnd, db = self.rnd, self.db
        pr = self._app_profile
        app.registered_at = when
        rep = _bki(rnd, pr["income"] or 20000, drift)
        if rep is None:
            db.add(CreditReport(application_id=app.id, found=False, received_at=when, raw={"message": "не найден"}))
        else:
            db.add(CreditReport(application_id=app.id, found=True, received_at=when, raw={"bureau": "демо"}, **rep))
        a = _abs(rnd, pr["income"])
        db.add(AbsData(application_id=app.id, received_at=when, raw={"system": "демо"}, **a))
        stop = rnd.random() < 0.004
        for check, passed, msg in (("passport", True, "паспорт действителен"),
                                   ("rosfin", True, "в перечне не найден"),
                                   ("stoplist", not stop, "в стоп-листе не найден" if not stop else
                                    "найден во внутреннем стоп-листе Банка")):
            db.add(Verification(application_id=app.id, check=check, passed=passed, message=msg, checked_at=when))
        db.add(BkiRequest(application_id=app.id, attempts=1, status="ok", message="кредитное досье сформировано",
                          created_at=when, updated_at=when))
        db.flush()

    def score(self, app: Application, when: datetime) -> ScoringResult:
        d = dossier.build(self.db, app.id)
        res = engine.evaluate(d, self.model.params, self.policy["stop_factors"], self.policy["classes"],
                              self.policy["matrix"])
        sr = ScoringResult(application_id=app.id, model_id=self.model.id, created_at=when, pd=res["pd"],
                           score=res["score"], risk_class=res["risk_class"], pdn=res["pdn"],
                           stop_factors=res["stop_factors"], factors=res["factors"], features=res["features"],
                           recommendation=res["recommendation"], rec_amount=res["rec_amount"],
                           rec_term=res["rec_term"], rec_rate=res["rec_rate"], duration_ms=res["duration_ms"])
        self.db.add(sr)
        app.status = "review"
        return sr

    def decide(self, app: Application, sr: ScoringResult, when: datetime) -> Decision:
        rnd = self.rnd
        uw = self.users["underwriter" if rnd.random() < 0.55 else "underwriter2"]
        outcome, amount, term, rate, comment = sr.recommendation, sr.rec_amount, sr.rec_term, sr.rec_rate, ""
        if sr.recommendation != "reject" and rnd.random() < 0.05:
            outcome, amount, term, rate = "reject", None, None, None
            comment = "Сомнения в достоверности сведений о доходе по итогам звонка работодателю"
        elif sr.recommendation == "reject" and not sr.stop_factors and rnd.random() < 0.06:
            outcome = "approve_changed"
            amount = float(max(float(app.product.min_amount), round(float(app.amount) * 0.5, -4)))
            term, rate = app.term_months, round(app.product.base_rate + 5, 2)
            comment = "Подтверждён дополнительный доход от сдачи квартиры в аренду, сумма снижена вдвое"
        committee = outcome != "reject" and uw.limit_amount is not None and float(amount) > float(uw.limit_amount)
        d = Decision(application_id=app.id, user_id=uw.id, stage="underwriter", recommendation=sr.recommendation,
                     outcome="committee" if committee else outcome, amount=amount, term_months=term, rate=rate,
                     comment=comment, created_at=when)
        self.db.add(d)
        if committee:
            app.status = "committee"
            head = self.users["head"]
            when2 = when + timedelta(hours=rnd.randint(4, 30))
            final = outcome if rnd.random() < 0.85 else "reject"
            d2 = Decision(application_id=app.id, user_id=head.id, stage="committee", recommendation=sr.recommendation,
                          outcome=final, amount=amount if final != "reject" else None,
                          term_months=term if final != "reject" else None, rate=rate if final != "reject" else None,
                          comment="" if final == outcome else "Кредитный комитет: высокая концентрация риска, отказать",
                          created_at=when2)
            self.db.add(d2)
            d, outcome, when = d2, final, when2
        app.status = "rejected" if outcome == "reject" else "approved"
        app.decided_at = when
        cl = app.client
        self.db.add(Notification(application_id=app.id, channel="sms", recipient=cl.phone, created_at=when,
                                 text=f"По заявке {app.number} принято решение: "
                                      f"{'кредит одобрен' if outcome != 'reject' else 'отказ'}."))
        return d

    def issue(self, app: Application, d: Decision, sr: ScoringResult, when: datetime, today: date) -> None:
        rnd = self.rnd
        if rnd.random() < 0.12:
            app.status = "client_refused"
            return
        app.status = "issued"
        issued = (when + timedelta(days=rnd.randint(0, 3))).date()
        f = sr.features
        p = _true_pd(f, rnd)
        months = (today - issued).days / 30.4
        seen = min(1.0, months / 12)
        default = rnd.random() < p * seen
        max_dpd = rnd.randint(90, 200) if default else rnd.choices([0, 5, 15, 40], [80, 10, 7, 3])[0] if seen else 0
        status = "default" if default else ("closed" if months > d.term_months else "active")
        self.db.add(Loan(application_id=app.id, contract_number="КД-" + app.number.removeprefix("КЗ-"),
                         issued_at=issued, amount=d.amount,
                         term_months=d.term_months, rate=d.rate, status=status, max_dpd_12m=max_dpd))


def reset(db: Session) -> None:
    """Удаляет все данные и создаёт схему заново (журнал аудита иначе не очистить — он защищён триггерами)."""
    from . import migrate
    from .db import Base
    url = db.get_bind().url.render_as_string(hide_password=False)
    db.close()
    from . import db as dbm
    eng = dbm.engine()
    Base.metadata.drop_all(eng)
    with eng.begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrate.upgrade(url)


def generate(db: Session, months: int = 30, per_day: float = 8.0, seed: int = 2026, log=print) -> dict:
    rnd = random.Random(seed)
    ensure_base(db)
    if db.query(Application).count():
        raise RuntimeError("В БД уже есть заявки: демо-данные загружаются в пустую БД (creditdss demo --reset)")
    for login, name, role, limit in STAFF:
        if not db.query(User).filter_by(login=login).first():
            db.add(User(login=login, full_name=name, role=role, limit_amount=limit,
                        password_hash=hash_password(DEMO_PASSWORD)))
    db.add_all([
        StopListEntry(source="invalid_passport", passport_series="7000", passport_number="000001",
                      reason="утрачен (демо)"),
        StopListEntry(source="rosfin", full_name="Подставной Иван Иванович", birth_date=date(1980, 1, 1),
                      reason="перечень Росфинмониторинга (демо)"),
        StopListEntry(source="internal", passport_series="7000", passport_number="000002",
                      reason="мошенничество при подаче заявки (демо)"),
    ])
    db.commit()
    g = _Gen(db, rnd)
    today = date.today()
    start = today - timedelta(days=int(months * 30.4))
    n = 0
    day = start
    while day < today - timedelta(days=1):
        drift = 0.08 if (today - day).days < 60 else 0.0     # в последние два месяца поток заявок рискованнее
        for _ in range(_poisson(rnd, per_day * (0.4 if day.weekday() >= 5 else 1.0))):
            when = datetime.combine(day, time(rnd.randint(9, 19), rnd.randint(0, 59)))
            app = g.application(when, drift=drift)
            g.dossier(app, when + timedelta(minutes=2), drift)
            sr = g.score(app, when + timedelta(minutes=3))
            d = g.decide(app, sr, when + timedelta(hours=rnd.randint(1, 20)))
            if app.status == "approved" and (today - day).days > 3:
                g.issue(app, d, sr, d.created_at, today)
            n += 1
        if day.day == 1:
            db.commit()
            log(f"{day:%m.%Y}: заявок {n}")
        day += timedelta(days=1)
    db.commit()

    # текущая очередь: заявки сегодняшнего дня в разных состояниях
    now = datetime.now().replace(second=0, microsecond=0)
    plan = ["draft"] * 2 + ["review"] * 12 + ["committee"] * 2 + ["docs_required"] * 2 + ["collecting"]
    for i, state in enumerate(plan):
        when = now - timedelta(minutes=20 * (len(plan) - i))
        app = g.application(when)
        if state == "draft":
            continue
        if state == "collecting":
            app.status = "collecting"
            app.registered_at = when
            db.add(BkiRequest(application_id=app.id, attempts=1, status="pending",
                              next_attempt_at=now + timedelta(minutes=3),
                              message="БКИ: сервис временно недоступен (имитация). Повтор по расписанию"))
            continue
        g.dossier(app, when)
        sr = g.score(app, when + timedelta(minutes=1))
        if state == "committee":
            uw = g.users["underwriter2"]
            app.amount = max(float(app.amount), 600000.0)
            amt = float(app.amount)
            db.add(Decision(application_id=app.id, user_id=uw.id, stage="underwriter", recommendation=sr.recommendation,
                            outcome="committee", amount=amt, term_months=app.term_months,
                            rate=sr.rec_rate or app.product.base_rate,
                            comment="Сумма превышает лимит полномочий андеррайтера", created_at=when))
            app.status = "committee"
        elif state == "docs_required":
            db.add(Decision(application_id=app.id, user_id=g.users["underwriter"].id, stage="underwriter",
                            recommendation=sr.recommendation, outcome="docs",
                            comment="Нужна справка о доходах за 6 месяцев", created_at=when))
            app.status = "docs_required"
    db.commit()
    log(f"заявок всего: {db.query(Application).count()}, кредитов: {db.query(Loan).count()}")

    # проверка опубликованной версии на истории, кандидат версии 2 и мониторинг за последние 12 месяцев
    analyst = g.users["analyst"]
    v1 = g.model
    methodology.validate(db, analyst, v1, None, None)
    db.commit()
    log(f"методика v1: ROC AUC {v1.metrics['auc']:.3f}, Gini {v1.metrics['gini']:.3f}, KS {v1.metrics['ks']:.3f} "
        f"на {v1.metrics['n']} созревших кредитах (дефолтов {v1.metrics['bad']})")
    v2 = methodology.create_candidate(db, analyst, v1.id, "Скоринговая карта: усиление веса ПДН и просрочек",
                                      "Пример версии-кандидата: больше баллов за низкую долговую нагрузку")
    params = copy.deepcopy(v2.params)
    for ch in params["characteristics"]:
        if ch["feature"] == "pdn":
            for b, pts in zip(ch["bins"], (55, 32, 8, -10)):
                b["points"] = pts
        if ch["feature"] == "dpd30_12m":
            for b, pts in zip(ch["bins"], (32, 5, -15)):
                b["points"] = pts
    methodology.update_candidate(db, analyst, v2, params, None, None)
    methodology.validate(db, analyst, v2, None, None)
    db.commit()
    for k in range(12, 0, -1):
        y, m = today.year, today.month - k
        while m <= 0:
            y, m = y - 1, m + 12
        methodology.monitor(db, f"{y}-{m:02d}")
    audit.log(db, None, "Загружены демонстрационные данные", "system", "demo")
    db.commit()
    return {"applications": db.query(Application).count(), "loans": db.query(Loan).count(),
            "v1": v1.metrics, "v2": v2.metrics}


def _poisson(rnd: random.Random, lam: float) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p < l:
            return k
        k += 1
