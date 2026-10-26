"""Заполняет базу демонстрационными данными: кредитные продукты, около 150 заявок за полгода с оценкой и решениями.

Запуск: python demo.py  (старая база удаляется). Вход: admin / admin. Все клиенты вымышлены.
"""
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

import db
import logic

DB_PATH = Path(__file__).parent / "creditdss.db"

PRODUCTS = [
    ("Потребительский заём", 10000, 500000, 3, 36, 24.9),
    ("Заём до зарплаты", 5000, 50000, 1, 3, 36.5),
    ("Заём для пайщиков кооператива", 30000, 1000000, 6, 60, 19.9),
]

LAST = ["Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Васильев", "Соколов", "Михайлов", "Новиков",
        "Фёдоров", "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов"]
MALE = [("Александр", "Сергеевич"), ("Дмитрий", "Андреевич"), ("Максим", "Игоревич"), ("Сергей", "Олегович"),
        ("Андрей", "Викторович"), ("Алексей", "Николаевич"), ("Иван", "Павлович"), ("Роман", "Дмитриевич")]
FEMALE = [("Анна", "Сергеевна"), ("Мария", "Андреевна"), ("Елена", "Игоревна"), ("Ольга", "Олеговна"),
          ("Наталья", "Викторовна"), ("Татьяна", "Николаевна"), ("Ирина", "Павловна"), ("Юлия", "Дмитриевна")]


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()
    db.create_tables(DB_PATH)
    conn = db.connect(DB_PATH)
    conn.execute("INSERT INTO users (login, password_hash) VALUES (?, ?)", ("admin", generate_password_hash("admin")))
    for p in PRODUCTS:
        conn.execute("INSERT INTO products (name, min_amount, max_amount, min_term, max_term, rate) "
                     "VALUES (?, ?, ?, ?, ?, ?)", p)
    products = [dict(r) for r in conn.execute("SELECT * FROM products ORDER BY id")]

    rnd = random.Random(2026)
    today = date.today()
    for i in range(150):
        male = rnd.random() < 0.5
        first, middle = rnd.choice(MALE if male else FEMALE)
        last = rnd.choice(LAST) + ("" if male else "а")
        age = rnd.randint(19, 68)
        birth = today - timedelta(days=age * 365 + rnd.randint(0, 360))
        passport = f"70{rnd.randint(10, 99)} {rnd.randint(100000, 999999)}"
        cur = conn.execute("INSERT INTO clients (last_name, first_name, middle_name, birth_date, passport, phone) "
                           "VALUES (?, ?, ?, ?, ?, ?)",
                           (last, first, middle, birth.isoformat(), passport,
                            f"+7 9{rnd.randint(10, 99)} {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}"))
        product = rnd.choices(products, [60, 25, 15])[0]
        income = round(rnd.lognormvariate(10.7, 0.45), -3)
        term = rnd.randint(product["min_term"], product["max_term"])
        amount = round(min(product["max_amount"], max(product["min_amount"], income * rnd.uniform(0.3, 4))), -3)
        has_history = rnd.random() < 0.85
        anketa = {"age": age, "term": term, "amount": amount, "income": income,
                  "experience": rnd.choice([3, 8, 14, 24, 40, 70, 120]),
                  "payments": round(income * rnd.choice([0, 0, 0.1, 0.2, 0.3, 0.45]), -2) if has_history else 0,
                  "max_dpd": rnd.choice([0, 0, 0, 0, 10, 25, 45, 100]) if has_history else 0,
                  "current_dpd": rnd.choice([0] * 19 + [15]) if has_history else 0,
                  "inquiries": rnd.choice([0, 1, 1, 2, 3, 4, 7]),
                  "history_months": rnd.randint(6, 150) if has_history else 0}
        r = logic.evaluate(anketa, product)
        created = datetime.combine(today - timedelta(days=rnd.randint(0, 180) if i >= 12 else rnd.randint(0, 6)),
                                   datetime.min.time()) + timedelta(hours=rnd.randint(9, 18), minutes=rnd.randint(0, 59))
        status, approved_amount, comment, decided = "review", None, "", None
        if created.date() < today - timedelta(days=7) or rnd.random() < 0.3:   # свежие — часть на рассмотрении
            follow = rnd.random() < 0.93
            approve = (r["recommendation"] == "approve") == follow
            if approve and r["stop_factor"]:
                approve = False
            status = "approved" if approve else "rejected"
            approved_amount = (r["rec_amount"] or amount) if approve else None
            if not follow and not r["stop_factor"]:
                comment = ("Подтверждён дополнительный доход, клиент давно пайщик кооператива" if approve
                           else "Не удалось подтвердить место работы по телефону")
            decided = (created + timedelta(hours=rnd.randint(1, 30))).isoformat(timespec="minutes")
        conn.execute(
            "INSERT INTO applications (client_id, product_id, created_at, amount, term, income, experience, payments, "
            "max_dpd, current_dpd, inquiries, history_months, score, pd, risk_class, pdn, stop_factor, factors, "
            "recommendation, rec_amount, rec_rate, status, approved_amount, comment, decided_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cur.lastrowid, product["id"], created.isoformat(timespec="minutes"), amount, term, income,
             anketa["experience"], anketa["payments"], anketa["max_dpd"], anketa["current_dpd"], anketa["inquiries"],
             anketa["history_months"], r["score"], r["pd"], r["risk_class"], r["pdn"], r["stop_factor"],
             json.dumps(r["factors"], ensure_ascii=False), r["recommendation"], r["rec_amount"], r["rec_rate"],
             status, approved_amount, comment, decided))
    conn.commit()
    conn.close()
    print("Демо-данные загружены. Вход: admin / admin")


if __name__ == "__main__":
    main()
