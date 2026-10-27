# -*- coding: utf-8 -*-
"""ER-диаграммы (по реальной БД) и UML-диаграммы полной редакции для руководств."""
import os

import diagrams as dg
import er_auto

NAMES = {
    "users": "Сотрудники", "products": "Кредитные продукты", "clients": "Клиенты", "employments": "Занятость",
    "applications": "Заявки", "consents": "Согласия", "documents": "Документы", "bki_requests": "Запросы в БКИ",
    "credit_reports": "Кредитные отчёты", "abs_data": "Данные АБС", "verifications": "Проверки",
    "stoplist": "Стоп-лист", "stop_factors": "Стоп-факторы", "condition_rules": "Матрица условий",
    "scoring_models": "Версии методики", "scoring_results": "Результаты оценки", "decisions": "Решения",
    "loans": "Кредиты", "notifications": "Уведомления", "monitoring_reports": "Мониторинг",
    "app_settings": "Параметры", "audit_log": "Журнал аудита", "integration_log": "Журнал обмена",
}

AREAS = [
    ("Клиенты, заявки и решения",
     ["clients", "employments", "products", "applications", "consents", "documents", "decisions", "loans",
      "notifications"], ["users"]),
    ("Кредитное досье", ["bki_requests", "credit_reports", "abs_data", "verifications"], ["applications"]),
    ("Оценка и версии методики", ["scoring_results", "scoring_models", "monitoring_reports"],
     ["applications", "users"]),
    ("Справочники, параметры и журналы",
     ["users", "stop_factors", "condition_rules", "stoplist", "app_settings", "audit_log", "integration_log"], []),
]

# Описания полей для словаря данных; общие имена — без таблицы
DESCR = {
    "id": "Идентификатор записи", "created_at": "Дата и время создания", "updated_at": "Дата и время изменения",
    "application_id": "Заявка", "client_id": "Клиент", "user_id": "Сотрудник", "active": "Действует",
    "comment": "Комментарий", "status": "Состояние", "raw": "Исходный ответ внешней системы (JSON)",
    "message": "Сообщение", "rule": "Тип условия", "threshold": "Порог срабатывания",
    ("users", "login"): "Логин", ("users", "full_name"): "ФИО сотрудника",
    ("users", "role"): "Роль: credit_officer, underwriter, head, risk_analyst, admin",
    ("users", "limit_amount"): "Лимит полномочий, руб. (пусто — без ограничения)",
    ("users", "password_hash"): "Хэш пароля (PBKDF2)",
    ("products", "name"): "Название продукта", ("products", "min_amount"): "Минимальная сумма, руб.",
    ("products", "max_amount"): "Максимальная сумма, руб.", ("products", "min_term"): "Минимальный срок, мес.",
    ("products", "max_term"): "Максимальный срок, мес.", ("products", "base_rate"): "Базовая ставка, % годовых",
    ("clients", "last_name"): "Фамилия", ("clients", "first_name"): "Имя", ("clients", "middle_name"): "Отчество",
    ("clients", "birth_date"): "Дата рождения", ("clients", "passport_series"): "Серия паспорта",
    ("clients", "passport_number"): "Номер паспорта", ("clients", "passport_issued"): "Дата выдачи паспорта",
    ("clients", "citizenship"): "Гражданство", ("clients", "reg_address"): "Адрес регистрации",
    ("clients", "phone"): "Телефон", ("clients", "email"): "Электронная почта",
    ("employments", "employment_type"): "Тип занятости", ("employments", "employer"): "Работодатель",
    ("employments", "position"): "Должность", ("employments", "experience_months"): "Стаж, мес.",
    ("employments", "income_confirmed"): "Подтверждённый доход, руб./мес.",
    ("applications", "number"): "Номер заявки (КЗ-ГГГГ-NNNNNN)", ("applications", "product_id"): "Кредитный продукт",
    ("applications", "employment_id"): "Сведения о занятости на дату заявки",
    ("applications", "amount"): "Запрошенная сумма, руб.", ("applications", "term_months"): "Срок, мес.",
    ("applications", "purpose"): "Цель кредита", ("applications", "channel"): "Канал обращения",
    ("applications", "marital_status"): "Семейное положение", ("applications", "dependents"): "Число иждивенцев",
    ("applications", "education"): "Образование", ("applications", "housing"): "Жильё",
    ("applications", "status"): "Состояние заявки", ("applications", "officer_id"): "Кредитный специалист",
    ("applications", "registered_at"): "Дата регистрации", ("applications", "decided_at"): "Дата решения",
    ("consents", "kind"): "Вид согласия: pd — обработка ПДн, bki — запрос в БКИ",
    ("consents", "signed_at"): "Дата подписания", ("consents", "valid_until"): "Действует до",
    ("documents", "kind"): "Вид документа", ("documents", "filename"): "Имя файла",
    ("documents", "content_type"): "Тип содержимого", ("documents", "size"): "Размер, байт",
    ("documents", "stored_name"): "Имя файла в хранилище", ("documents", "uploaded_by"): "Кто прикрепил",
    ("documents", "uploaded_at"): "Когда прикреплён",
    ("bki_requests", "attempts"): "Число попыток", ("bki_requests", "status"): "ok, pending, failed",
    ("bki_requests", "next_attempt_at"): "Время следующей попытки",
    ("credit_reports", "received_at"): "Дата получения", ("credit_reports", "found"): "Субъект найден в БКИ",
    ("credit_reports", "loans_count"): "Кредитов в истории", ("credit_reports", "active_loans"): "Действующих кредитов",
    ("credit_reports", "total_debt"): "Общая задолженность, руб.",
    ("credit_reports", "monthly_payments"): "Ежемесячные платежи, руб.",
    ("credit_reports", "max_dpd"): "Максимальная просрочка, дн.", ("credit_reports", "current_dpd"): "Текущая просрочка, дн.",
    ("credit_reports", "dpd30_12m"): "Просрочек 30+ за 12 мес.", ("credit_reports", "inquiries_6m"): "Запросов за 6 мес.",
    ("credit_reports", "history_months"): "Длина кредитной истории, мес.", ("credit_reports", "bankruptcy"): "Банкротство",
    ("abs_data", "received_at"): "Дата получения", ("abs_data", "is_client"): "Клиент Банка",
    ("abs_data", "client_since_months"): "Клиент Банка, мес.", ("abs_data", "salary_project"): "Зарплатный проект",
    ("abs_data", "salary_avg"): "Средние поступления зарплаты, руб.", ("abs_data", "accounts_count"): "Число счетов",
    ("abs_data", "deposits_balance"): "Остаток на вкладах, руб.", ("abs_data", "bank_loans_count"): "Кредитов в Банке",
    ("abs_data", "bank_monthly_payments"): "Платежи по кредитам Банка, руб./мес.",
    ("verifications", "check"): "Проверка: паспорт, стоп-лист, Росфинмониторинг",
    ("verifications", "passed"): "Пройдена", ("verifications", "checked_at"): "Время проверки",
    ("stoplist", "source"): "Источник: internal, rosfin", ("stoplist", "full_name"): "ФИО",
    ("stoplist", "passport_series"): "Серия паспорта", ("stoplist", "passport_number"): "Номер паспорта",
    ("stoplist", "birth_date"): "Дата рождения", ("stoplist", "reason"): "Основание",
    ("stop_factors", "code"): "Код правила (SF01…)", ("stop_factors", "description"): "Описание",
    ("condition_rules", "risk_class"): "Класс риска A–E", ("condition_rules", "pdn_from"): "ПДН от (доля)",
    ("condition_rules", "pdn_to"): "ПДН до (доля, не включая)", ("condition_rules", "decision"): "Рекомендация",
    ("condition_rules", "amount_factor"): "Множитель суммы", ("condition_rules", "rate_add"): "Надбавка к ставке, п. п.",
    ("scoring_models", "version"): "Номер версии", ("scoring_models", "name"): "Название",
    ("scoring_models", "algorithm"): "Алгоритм (scorecard)", ("scoring_models", "status"): "Состояние версии",
    ("scoring_models", "params"): "Скоринговая карта (JSON)", ("scoring_models", "metrics"): "ROC AUC, Gini, KS (JSON)",
    ("scoring_models", "created_by"): "Автор", ("scoring_models", "approved_by"): "Кто утвердил",
    ("scoring_models", "approved_at"): "Дата утверждения", ("scoring_models", "published_at"): "Дата публикации",
    ("scoring_results", "model_id"): "Версия методики", ("scoring_results", "pd"): "Вероятность дефолта",
    ("scoring_results", "score"): "Скоринговый балл", ("scoring_results", "risk_class"): "Класс риска",
    ("scoring_results", "pdn"): "ПДН (доля)", ("scoring_results", "stop_factors"): "Сработавшие стоп-факторы (JSON)",
    ("scoring_results", "factors"): "Факторы оценки (JSON)", ("scoring_results", "features"): "Признаки (JSON)",
    ("scoring_results", "recommendation"): "Рекомендация", ("scoring_results", "rec_amount"): "Рекомендуемая сумма",
    ("scoring_results", "rec_term"): "Рекомендуемый срок", ("scoring_results", "rec_rate"): "Рекомендуемая ставка",
    ("scoring_results", "fallback"): "Оценка резервной методикой", ("scoring_results", "duration_ms"): "Время расчёта, мс",
    ("decisions", "stage"): "Этап: underwriter, committee", ("decisions", "recommendation"): "Рекомендация системы",
    ("decisions", "outcome"): "Решение", ("decisions", "amount"): "Сумма, руб.", ("decisions", "term_months"): "Срок, мес.",
    ("decisions", "rate"): "Ставка, %",
    ("loans", "contract_number"): "Номер договора", ("loans", "issued_at"): "Дата выдачи",
    ("loans", "amount"): "Сумма, руб.", ("loans", "term_months"): "Срок, мес.", ("loans", "rate"): "Ставка, %",
    ("loans", "status"): "active, closed, default", ("loans", "max_dpd_12m"): "Максимальная просрочка за 12 мес., дн.",
    ("notifications", "channel"): "Канал: sms, email", ("notifications", "recipient"): "Получатель",
    ("notifications", "text"): "Текст уведомления",
    ("monitoring_reports", "period"): "Месяц (ГГГГ-ММ)", ("monitoring_reports", "model_id"): "Версия методики",
    ("monitoring_reports", "n_scored"): "Оценено заявок", ("monitoring_reports", "psi"): "PSI",
    ("monitoring_reports", "n_matured"): "Созревших кредитов", ("monitoring_reports", "gini"): "Gini за период",
    ("monitoring_reports", "gini_ref"): "Gini при проверке", ("monitoring_reports", "default_rate"): "Доля дефолтов",
    ("monitoring_reports", "alerts"): "Оповещения (JSON)", ("monitoring_reports", "details"): "Подробности (JSON)",
    ("app_settings", "key"): "Имя параметра", ("app_settings", "value"): "Значение (JSON)",
    ("audit_log", "user_login"): "Логин", ("audit_log", "action"): "Действие", ("audit_log", "entity"): "Объект",
    ("audit_log", "entity_id"): "Идентификатор объекта", ("audit_log", "changes"): "Изменения «было → стало» (JSON)",
    ("audit_log", "user_id"): "Сотрудник (без внешнего ключа: запись сохраняется при удалении)",
    ("integration_log", "system"): "Система: bki, abs, scoring, notify, scheduler",
    ("integration_log", "direction"): "Направление обмена",
}

USECASE = r"""
left to right direction
skinparam packageStyle rectangle
actor "Кредитный\nспециалист" as KS
actor "Андеррайтер" as UW
actor "Руководитель\nкредитного отдела" as HD
actor "Риск-аналитик" as RA
actor "Администратор" as AD
actor "БКИ" as BKI <<система>>
actor "АБС" as ABS <<система>>
rectangle "СППР «Кредитный скоринг»" {
  usecase "Зарегистрировать заявку" as U1
  usecase "Собрать кредитное досье" as U2
  usecase "Оценить заявку" as U3
  usecase "Принять решение\nпо заявке" as U4
  usecase "Решение кредитного\nкомитета" as U5
  usecase "Зафиксировать выдачу\nили отказ клиента" as U6
  usecase "Просмотреть заёмщиков\nи портфель" as U7
  usecase "Изменить версию\nметодики" as U8
  usecase "Утвердить версию\nметодики" as U9
  usecase "Мониторинг методики" as U10
  usecase "Сформировать отчёт" as U11
  usecase "Управлять пользователями,\nпараметрами, копиями" as U12
  usecase "Вести справочники" as U13
  usecase "Просмотреть журнал аудита" as U14
}
KS --> U1
KS --> U6
KS --> U7
UW --> U4
UW --> U7
HD --> U5
HD --> U9
HD --> U11
HD --> U14
HD --> U7
RA --> U8
RA --> U10
RA --> U11
RA --> U13
AD --> U12
U1 ..> U2 : <<include>>
U2 ..> U3 : <<include>>
U2 --> BKI
U2 --> ABS
U6 --> ABS
U5 .> U4 : <<extend>>
"""

STATE = r"""
hide empty description
state "Черновик" as draft
state "Зарегистрирована" as registered
state "Сбор данных" as collecting
state "Скоринг" as scoring
state "На рассмотрении" as review
state "Требуются документы" as docs
state "На кредитном комитете" as committee
state "Одобрена" as approved
state "Отклонена" as rejected
state "Выдана" as issued
state "Отказ клиента" as refused
[*] --> draft
draft --> registered : зарегистрировать\n[проверки С-1, С-2 пройдены]
registered --> collecting : запросы в БКИ и АБС
collecting --> collecting : повтор через 5 мин\n[внешняя система недоступна]
collecting --> scoring : досье сформировано
scoring --> review : оценка рассчитана
review --> review : пересчитать оценку
review --> docs : запросить документы
docs --> review : документы получены
review --> committee : сумма > лимита\nполномочий
review --> approved : одобрить
review --> rejected : отказать
committee --> approved : одобрить
committee --> rejected : отказать
approved --> issued : кредит выдан
approved --> refused : отказ клиента
issued --> [*]
rejected --> [*]
refused --> [*]
"""

MODEL_STATE = r"""
hide empty description
state "Кандидат" as candidate
state "На утверждении" as approval
state "Утверждена" as approved
state "Отклонена" as rejected
state "Опубликована" as published
state "В архиве" as archived
[*] --> candidate : создать на основе\nдействующей
candidate --> candidate : изменить баллы,\nпроверить
candidate --> approval : отправить\n[Gini не ниже действующей]
approval --> approved : утвердить
approval --> rejected : отклонить
approved --> published : опубликовать
published --> archived : опубликована\nдругая версия
archived --> published : откат
rejected --> [*]
"""

DEPLOY_DOCKER = r"""
node "АРМ сотрудника" as pc {
  artifact "Веб-браузер" as br
}
node "Сервер приложений\n<<Linux, Docker Compose>>" as app {
  component "proxy\n(Caddy, HTTPS)" as px
  component "web\n(nginx, интерфейс React)" as web
  component "api\n(FastAPI, creditdss)" as api
  component "scoring\n(сервис скоринга)" as sc
  component "scheduler\n(планировщик)" as sch
  database "db\n(PostgreSQL 16)" as db
  folder "том data\n(документы, копии)" as vol
}
node "БКИ" as bki
node "АБС Банка" as abs
node "Контроллер домена" as ldap
br --> px : HTTPS 443
px --> web : HTTP
web --> api : /api
api --> sc : REST, X-Service-Key
api --> db : SQL
sch --> db : SQL
api --> vol
sch --> vol
api --> bki : HTTPS
api --> abs : HTTPS
api --> ldap : LDAP
"""

DEPLOY_WIN = r"""
node "Компьютер Windows 10/11 x64" as pc {
  artifact "Веб-браузер" as br
  component "КредитныйСкоринг.exe\n(веб-сервер, расчёт оценки,\nпланировщик)" as exe
  database "data\\creditdss.db\n(SQLite)" as db
  folder "data\\documents,\ndata\\backup" as fs
}
br --> exe : HTTP 127.0.0.1:8000
exe --> db
exe --> fs
"""

COMPONENTS = r"""
package "frontend (React, Ant Design)" {
  [Страницы: заявки, заёмщики,\nпортфель, методика, отчёты,\nсправочники, администрирование] as ui
}
package "backend/creditdss" {
  [api\n(REST-маршруты)] as api
  [services\n(заявки, досье, методика,\nотчёты, резервные копии)] as srv
  [scoring\n(признаки, стоп-факторы,\nскоринговая карта, метрики)] as sc
  [scoring_service\n(отдельный сервис)] as ss
  [models + db\n(SQLAlchemy, Alembic)] as m
  [audit, security\n(журналы, JWT, роли)] as sec
  [scheduler] as sch
}
database "БД" as db
ui --> api : HTTP/JSON
api --> srv
api --> sec
srv --> sc
srv --> ss : REST
ss --> sc
srv --> m
sch --> srv
m --> db
"""


def make_all(db_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    schema = er_auto.introspect(db_path)
    figs = {"schema": schema}
    all_tables = sorted(schema)
    figs["er_overview"] = dg.plantuml(er_auto.puml(schema, all_tables, names=NAMES, compact=True),
                                      os.path.join(out_dir, "er_overview.png"))
    for k, (title, tabs, refs) in enumerate(AREAS, 1):
        figs[f"er_{k}"] = dg.plantuml(er_auto.puml(schema, tabs, refs, names=NAMES),
                                      os.path.join(out_dir, f"er_{k}.png"))
    for key, src in (("usecase", USECASE), ("state", STATE), ("model_state", MODEL_STATE),
                     ("deploy_docker", DEPLOY_DOCKER), ("deploy_win", DEPLOY_WIN), ("components", COMPONENTS)):
        figs[key] = dg.plantuml(src, os.path.join(out_dir, f"uml_{key}.png"))
    return figs


if __name__ == "__main__":
    import sys
    f = make_all(sys.argv[1], os.path.join(os.path.dirname(__file__), "_out"))
    print({k: v for k, v in f.items() if k != "schema"})
