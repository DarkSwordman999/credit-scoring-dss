# -*- coding: utf-8 -*-
"""ER-диаграмма (по базе из app/schema.sql) и UML-диаграммы базовой редакции для руководств."""
import os
import sqlite3
import tempfile

import diagrams as dg
import er_auto

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA = os.path.join(ROOT, "app", "schema.sql")

NAMES = {"users": "Пользователи", "products": "Кредитные продукты", "clients": "Клиенты",
         "applications": "Заявки"}

DESCR = {
    "id": "Идентификатор записи",
    ("users", "login"): "Логин", ("users", "password_hash"): "Хэш пароля (werkzeug, PBKDF2/scrypt)",
    ("products", "name"): "Название продукта", ("products", "min_amount"): "Минимальная сумма, руб.",
    ("products", "max_amount"): "Максимальная сумма, руб.", ("products", "min_term"): "Минимальный срок, мес.",
    ("products", "max_term"): "Максимальный срок, мес.", ("products", "rate"): "Базовая ставка, % годовых",
    ("clients", "last_name"): "Фамилия", ("clients", "first_name"): "Имя", ("clients", "middle_name"): "Отчество",
    ("clients", "birth_date"): "Дата рождения (ГГГГ-ММ-ДД)", ("clients", "passport"): "Серия и номер паспорта",
    ("clients", "phone"): "Телефон",
    ("applications", "client_id"): "Клиент", ("applications", "product_id"): "Кредитный продукт",
    ("applications", "created_at"): "Дата и время подачи", ("applications", "amount"): "Запрошенная сумма, руб.",
    ("applications", "term"): "Срок, мес.", ("applications", "income"): "Подтверждённый доход, руб./мес.",
    ("applications", "experience"): "Стаж на текущем месте, мес.",
    ("applications", "payments"): "Платежи по действующим кредитам, руб./мес. (отчёт БКИ)",
    ("applications", "max_dpd"): "Максимальная просрочка в истории, дн. (отчёт БКИ)",
    ("applications", "current_dpd"): "Текущая просрочка, дн. (отчёт БКИ)",
    ("applications", "inquiries"): "Запросов в БКИ за 6 мес. (отчёт БКИ)",
    ("applications", "history_months"): "Длина кредитной истории, мес. (отчёт БКИ)",
    ("applications", "score"): "Скоринговый балл", ("applications", "pd"): "Вероятность дефолта, доля",
    ("applications", "risk_class"): "Класс риска A–E", ("applications", "pdn"): "ПДН, доля",
    ("applications", "stop_factor"): "Сработавший стоп-фактор", ("applications", "factors"): "Факторы оценки (JSON)",
    ("applications", "recommendation"): "Рекомендация: approve, reject",
    ("applications", "rec_amount"): "Рекомендуемая сумма, руб.", ("applications", "rec_rate"): "Рекомендуемая ставка, %",
    ("applications", "status"): "Состояние: review, approved, rejected",
    ("applications", "approved_amount"): "Одобренная сумма, руб.", ("applications", "comment"): "Обоснование решения",
    ("applications", "decided_at"): "Дата и время решения",
}

USECASE = r"""
left to right direction
actor "Кредитный\nспециалист" as KS
actor "Портал БКИ" as BKI <<система>>
rectangle "СППР «Кредитный скоринг» (базовая редакция)" {
  usecase "Войти в программу" as U0
  usecase "Ввести и оценить заявку" as U1
  usecase "Внести сведения\nиз кредитного отчёта" as U2
  usecase "Просмотреть оценку\nи факторы" as U3
  usecase "Принять решение" as U4
  usecase "Просмотреть заявки" as U5
  usecase "Сформировать отчёт" as U6
  usecase "Вести кредитные продукты" as U7
}
KS --> U0
KS --> U1
KS --> U4
KS --> U5
KS --> U6
KS --> U7
U1 ..> U2 : <<include>>
U1 ..> U3 : <<include>>
U2 ..> BKI : отчёт получен\nна портале
"""

STATE = r"""
hide empty description
state "На рассмотрении" as review
state "Одобрена" as approved
state "Отклонена" as rejected
[*] --> review : заявка оценена
review --> approved : одобрить\n[сумма в пределах продукта;\nкомментарий, если не по рекомендации]
review --> rejected : отказать\n[комментарий, если не по рекомендации]
approved --> [*]
rejected --> [*]
"""

DEPLOY = r"""
node "Компьютер специалиста\n(Windows 10/11, Python 3.11+)" as pc {
  artifact "Веб-браузер" as br
  component "app.py\n(Flask, 127.0.0.1:5000)" as app
  database "creditdss.db\n(SQLite)" as db
  file "secret.key" as key
}
br --> app : HTTP
app --> db : SQL
app --> key
"""

COMPONENTS = r"""
package "app" {
  component "run.bat, run.py\n(запуск, окружение,\nдемо-данные)" as c_run
  component "app.py\n(страницы, проверки ввода)" as c_app
  component "logic.py\n(стоп-факторы, ПДН, карта,\nPD, класс, рекомендация)" as c_logic
  component "db.py\n(подключение к SQLite)" as c_dbm
  component "templates, static\n(HTML-страницы, стили)" as c_tpl
  component "demo.py\n(демо-данные)" as c_demo
  component "schema.sql" as c_schema
}
database "creditdss.db" as c_db
c_run --> c_app
c_run --> c_demo
c_app --> c_logic
c_app --> c_dbm
c_app --> c_tpl
c_demo --> c_logic
c_demo --> c_dbm
c_dbm --> c_schema
c_dbm --> c_db
"""


def schema_db():
    """База из app/schema.sql во временном файле — по ней строится ER-диаграмма."""
    path = os.path.join(tempfile.mkdtemp(prefix="creditdss-basic-"), "schema.db")
    c = sqlite3.connect(path)
    with open(SCHEMA, encoding="utf-8") as f:
        c.executescript(f.read())
    c.close()
    return path


def make_all(out_dir, db_path=None):
    os.makedirs(out_dir, exist_ok=True)
    schema = er_auto.introspect(db_path or schema_db())
    figs = {"schema": schema,
            "er": dg.plantuml(er_auto.puml(schema, ["users", "products", "clients", "applications"], names=NAMES,
                                           direction="left to right"), os.path.join(out_dir, "er.png"))}
    for key, src in (("usecase", USECASE), ("state", STATE), ("deploy", DEPLOY), ("components", COMPONENTS)):
        figs[key] = dg.plantuml(src, os.path.join(out_dir, f"uml_{key}.png"))
    return figs


if __name__ == "__main__":
    f = make_all(os.path.join(os.path.dirname(__file__), "_out"))
    print({k: v for k, v in f.items() if k != "schema"})
