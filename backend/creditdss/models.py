"""Модель данных (ПР 4, рис. 4.3 «Информационная модель системы»; ПР 7-8, классы-сущности).

Сущности ER-диаграммы: Клиент, Занятость, Кредитный продукт, Заявка, Согласие, Кредитный отчёт, Модель,
Результат скоринга, Стоп-фактор, Решение, Сотрудник. Дополнительно: данные АБС, проверки, документы,
выданные кредиты (обслуживание — для целевой переменной), стоп-лист, журналы, мониторинг модели.
"""
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# С-17: ролевая модель
ROLES = {
    "credit_officer": "Кредитный специалист",
    "underwriter": "Андеррайтер",
    "head": "Руководитель кредитного отдела",
    "risk_analyst": "Риск-аналитик",
    "admin": "Администратор",
}

# ПР 7-8, табл. 7.10: состояния объекта «Заявка»
STATUSES = {
    "draft": "Черновик",
    "registered": "Зарегистрирована",
    "collecting": "Сбор данных",
    "docs_required": "Требуются документы",
    "scoring": "Скоринг",
    "review": "На рассмотрении",
    "committee": "На кредитном комитете",
    "approved": "Одобрена",
    "rejected": "Отклонена",
    "issued": "Выдана",
    "client_refused": "Отказ клиента",
}
FINAL_STATUSES = ("rejected", "issued", "client_refused")

RECOMMENDATIONS = {
    "approve": "Одобрить",
    "approve_changed": "Одобрить на изменённых условиях",
    "reject": "Отказать",
}

MODEL_STATUSES = {
    "candidate": "Кандидат",
    "approval": "На утверждении",
    "approved": "Утверждена",
    "published": "Опубликована",
    "archived": "В архиве",
    "rejected": "Отклонена",
}

Money = Numeric(14, 2)


def _now() -> datetime:
    return datetime.now()


class User(Base):
    """Сотрудник: ФИО, роль, лимит полномочий."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32))
    # лимит полномочий, руб. (С-12); пусто — без ограничения (кредитный комитет)
    limit_amount: Mapped[float | None] = mapped_column(Money, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Product(Base):
    """Кредитный продукт: диапазоны суммы и срока, базовая ставка."""
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    min_amount: Mapped[float] = mapped_column(Money)
    max_amount: Mapped[float] = mapped_column(Money)
    min_term: Mapped[int] = mapped_column(Integer)
    max_term: Mapped[int] = mapped_column(Integer)
    base_rate: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Client(Base):
    """Клиент — физическое лицо, заёмщик."""
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("passport_series", "passport_number", name="uq_client_passport"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str] = mapped_column(String(100), default="")
    birth_date: Mapped[date] = mapped_column(Date)
    passport_series: Mapped[str] = mapped_column(String(4))
    passport_number: Mapped[str] = mapped_column(String(6))
    passport_issued: Mapped[date | None] = mapped_column(Date, nullable=True)
    citizenship: Mapped[str] = mapped_column(String(50), default="РФ")
    reg_address: Mapped[str] = mapped_column(String(300), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


class Employment(Base):
    """Сведения о месте работы и доходах клиента (на дату заявки)."""
    __tablename__ = "employments"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    employment_type: Mapped[str] = mapped_column(String(30), default="employee")
    employer: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[str] = mapped_column(String(200), default="")
    experience_months: Mapped[int] = mapped_column(Integer, default=0)
    income_confirmed: Mapped[float] = mapped_column(Money, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Application(Base):
    """Заявка — центральный объект системы."""
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    employment_id: Mapped[int] = mapped_column(ForeignKey("employments.id"))
    amount: Mapped[float] = mapped_column(Money)
    term_months: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(200), default="")
    channel: Mapped[str] = mapped_column(String(20), default="office")
    # анкета
    marital_status: Mapped[str] = mapped_column(String(20), default="single")
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    education: Mapped[str] = mapped_column(String(20), default="secondary")
    housing: Mapped[str] = mapped_column(String(20), default="own")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    officer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    client: Mapped[Client] = relationship()
    product: Mapped[Product] = relationship()
    employment: Mapped[Employment] = relationship()
    officer: Mapped[User | None] = relationship()


class Consent(Base):
    """Согласие клиента: на обработку ПДн (pd) и на запрос кредитного отчёта (bki)."""
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    signed_at: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)


class Document(Base):
    """Копия документа клиента (PDF, JPG, PNG до 20 МБ, П-3)."""
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    stored_name: Mapped[str] = mapped_column(String(100))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class BkiRequest(Base):
    """Запрос кредитного отчёта: попытки и повторы при недоступности БКИ (С-3)."""
    __tablename__ = "bki_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")   # pending | ok | not_found | failed
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CreditReport(Base):
    """Кредитный отчёт БКИ на дату рассмотрения (не более одного актуального на заявку)."""
    __tablename__ = "credit_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    found: Mapped[bool] = mapped_column(Boolean, default=True)
    loans_count: Mapped[int] = mapped_column(Integer, default=0)
    active_loans: Mapped[int] = mapped_column(Integer, default=0)
    total_debt: Mapped[float] = mapped_column(Money, default=0)
    monthly_payments: Mapped[float] = mapped_column(Money, default=0)
    max_dpd: Mapped[int] = mapped_column(Integer, default=0)
    current_dpd: Mapped[int] = mapped_column(Integer, default=0)
    dpd30_12m: Mapped[int] = mapped_column(Integer, default=0)
    inquiries_6m: Mapped[int] = mapped_column(Integer, default=0)
    history_months: Mapped[int] = mapped_column(Integer, default=0)
    bankruptcy: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class AbsData(Base):
    """Данные АБС: счета, зарплатные поступления, действующие кредиты в Банке (С-4)."""
    __tablename__ = "abs_data"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    is_client: Mapped[bool] = mapped_column(Boolean, default=False)
    client_since_months: Mapped[int] = mapped_column(Integer, default=0)
    salary_project: Mapped[bool] = mapped_column(Boolean, default=False)
    salary_avg: Mapped[float] = mapped_column(Money, default=0)
    accounts_count: Mapped[int] = mapped_column(Integer, default=0)
    deposits_balance: Mapped[float] = mapped_column(Money, default=0)
    bank_loans_count: Mapped[int] = mapped_column(Integer, default=0)
    bank_monthly_payments: Mapped[float] = mapped_column(Money, default=0)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class Verification(Base):
    """Проверка паспорта и стоп-листов (ПР 5-6, работа 2.3)."""
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    check: Mapped[str] = mapped_column(String(30))     # passport | stoplist | rosfin
    passed: Mapped[bool] = mapped_column(Boolean)
    message: Mapped[str] = mapped_column(String(300), default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class StopListEntry(Base):
    """Стоп-листы: недействительные паспорта, перечень Росфинмониторинга, внутренний стоп-лист Банка."""
    __tablename__ = "stoplist"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))    # invalid_passport | rosfin | internal
    passport_series: Mapped[str] = mapped_column(String(4), default="")
    passport_number: Mapped[str] = mapped_column(String(6), default="")
    full_name: Mapped[str] = mapped_column(String(300), default="")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class StopFactor(Base):
    """Стоп-фактор — формальное правило кредитной политики (код, описание, условие, признак активности)."""
    __tablename__ = "stop_factors"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    description: Mapped[str] = mapped_column(String(300))
    rule: Mapped[str] = mapped_column(String(30))          # тип условия, см. scoring.stopfactors.RULES
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ConditionRule(Base):
    """Матрица кредитной политики «класс риска × ПДН» → рекомендация и условия (С-10)."""
    __tablename__ = "condition_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    risk_class: Mapped[str] = mapped_column(String(1))
    pdn_from: Mapped[float] = mapped_column(Float)     # доля, включительно
    pdn_to: Mapped[float] = mapped_column(Float)       # доля, не включительно
    decision: Mapped[str] = mapped_column(String(20))
    amount_factor: Mapped[float] = mapped_column(Float, default=1.0)
    rate_add: Mapped[float] = mapped_column(Float, default=0.0)


class ScoringModel(Base):
    """Модель (версия методики оценки): версия, алгоритм, дата, метрики, статус."""
    __tablename__ = "scoring_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    algorithm: Mapped[str] = mapped_column(String(30), default="scorecard")
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    params: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScoringResult(Base):
    """Результат скоринга: PD, балл, класс риска, ПДН, сработавшие стоп-факторы, вклад факторов."""
    __tablename__ = "scoring_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("scoring_models.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    pd: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_class: Mapped[str | None] = mapped_column(String(1), nullable=True)
    pdn: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_factors: Mapped[list] = mapped_column(JSON, default=list)
    factors: Mapped[list] = mapped_column(JSON, default=list)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str] = mapped_column(String(20))
    rec_amount: Mapped[float | None] = mapped_column(Money, nullable=True)
    rec_term: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rec_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    model: Mapped[ScoringModel | None] = relationship()


class Decision(Base):
    """Решение по заявке: рекомендация, итог, условия, комментарий; этап — андеррайтер или кредитный комитет."""
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stage: Mapped[str] = mapped_column(String(20))           # underwriter | committee
    recommendation: Mapped[str] = mapped_column(String(20), default="")
    outcome: Mapped[str] = mapped_column(String(20))         # approve | approve_changed | reject | committee | docs
    amount: Mapped[float | None] = mapped_column(Money, nullable=True)
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped[User] = relationship()


class Loan(Base):
    """Выданный кредит и его обслуживание: из этих данных формируется целевая переменная (просрочка 90+ за 12 мес)."""
    __tablename__ = "loans"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    contract_number: Mapped[str] = mapped_column(String(40), default="")
    issued_at: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Money)
    term_months: Mapped[int] = mapped_column(Integer)
    rate: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="active")   # active | closed | default
    max_dpd_12m: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Notification(Base):
    """Уведомление клиента о решении (почта / SMS-шлюз)."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    recipient: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class MonitoringReport(Base):
    """Отчёт о качестве и стабильности модели за месяц (С-15)."""
    __tablename__ = "monitoring_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), index=True)   # ГГГГ-ММ
    model_id: Mapped[int] = mapped_column(ForeignKey("scoring_models.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    n_scored: Mapped[int] = mapped_column(Integer, default=0)
    psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_matured: Mapped[int] = mapped_column(Integer, default=0)
    gini: Mapped[float | None] = mapped_column(Float, nullable=True)
    gini_ref: Mapped[float | None] = mapped_column(Float, nullable=True)
    default_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    alerts: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AppSetting(Base):
    """Параметры системы (пороги классов риска, режимы интеграций)."""
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict | list | str | float | int | bool | None] = mapped_column(JSON)


class AuditLog(Base):
    """Журнал аудита (С-18): пользователь, время, действие, объект, изменённые значения. Записи не изменяются —
    это обеспечивают триггеры БД (миграция 0001)."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, server_default=func.current_timestamp(),
                                                 index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_login: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(200))
    entity: Mapped[str] = mapped_column(String(50), default="")
    entity_id: Mapped[str] = mapped_column(String(50), default="")
    changes: Mapped[dict] = mapped_column(JSON, default=dict)


class IntegrationLog(Base):
    """Журнал обмена с внешними системами (БКИ, АБС, сервис скоринга, уведомления, планировщик)."""
    __tablename__ = "integration_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    system: Mapped[str] = mapped_column(String(30))
    direction: Mapped[str] = mapped_column(String(5), default="out")
    status: Mapped[str] = mapped_column(String(10), default="ok")
    message: Mapped[str] = mapped_column(Text)
