"""СППР «Кредитный скоринг», базовая редакция: оценка кредитоспособности заёмщиков небольшой кредитной организации.

Запуск: python app.py, затем открыть http://127.0.0.1:5000/
"""
import json
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

import db
import logic


def secret_key() -> str:
    """Ключ подписи сессии: из переменной SECRET_KEY или из файла secret.key, который создаётся при первом запуске."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = Path(__file__).parent / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="ascii")
    return path.read_text(encoding="ascii").strip()


app = Flask(__name__)
app.config["SECRET_KEY"] = secret_key()
app.config["DATABASE"] = str(Path(__file__).parent / "creditdss.db")
app.teardown_appcontext(db.close_db)

STATUSES = {"review": "На рассмотрении", "approved": "Одобрена", "rejected": "Отклонена"}


def login_required(view):
    """Пускает на страницу только после входа."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


@app.context_processor
def helpers():
    return {"statuses": STATUSES, "money": lambda v: "—" if v is None else f"{v:,.0f}".replace(",", " "),
            "percent": lambda v, d=1: "—" if v is None else f"{v * 100:.{d}f} %"}


# ---------- вход ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = db.get_db().execute(
            "SELECT * FROM users WHERE login = ?", (request.form["login"],)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session["user"] = user["login"]
            return redirect(url_for("applications"))
        flash("Неверный логин или пароль")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- заявки ----------

@app.route("/")
@login_required
def applications():
    status = request.args.get("status", "")
    sql = ("SELECT a.*, c.last_name || ' ' || c.first_name || ' ' || c.middle_name AS client, p.name AS product "
           "FROM applications a JOIN clients c ON c.id = a.client_id JOIN products p ON p.id = a.product_id")
    params = ()
    if status:
        sql += " WHERE a.status = ?"
        params = (status,)
    rows = db.get_db().execute(sql + " ORDER BY a.created_at DESC LIMIT 200", params).fetchall()
    return render_template("applications.html", rows=rows, status=status)


@app.route("/new", methods=["GET", "POST"])
@login_required
def new_application():
    conn = db.get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    if request.method == "GET":
        return render_template("new.html", products=products, form={})
    f = request.form
    errors = []
    # числа и дата проверяются и на сервере: форму можно отправить в обход проверок браузера
    try:
        product = conn.execute("SELECT * FROM products WHERE id = ?", (int(f["product_id"]),)).fetchone()
        amount, term = float(f["amount"]), int(f["term"])
        income, experience = float(f["income"]), int(f["experience"])
        extra = {k: int(f.get(k) or 0) for k in ("max_dpd", "current_dpd", "inquiries", "history_months")}
        payments = float(f.get("payments") or 0)
        birth = date.fromisoformat(f["birth_date"])
    except (KeyError, ValueError):
        flash("Проверьте анкету: суммы, сроки и сведения из кредитного отчёта — числа, дата рождения — дата")
        return render_template("new.html", products=products, form=f)
    if product is None:
        flash("Выберите кредитный продукт")
        return render_template("new.html", products=products, form=f)
    if min(amount, term, income, experience, payments, *extra.values()) < 0:
        errors.append("Суммы, сроки и сведения из кредитного отчёта не могут быть отрицательными")
    if not date(1900, 1, 1) < birth < date.today():
        errors.append("Неверная дата рождения")
    if not product["min_amount"] <= amount <= product["max_amount"]:
        errors.append(f"Сумма для продукта «{product['name']}» — от {product['min_amount']:,.0f} "
                      f"до {product['max_amount']:,.0f} руб.".replace(",", " "))
    if not product["min_term"] <= term <= product["max_term"]:
        errors.append(f"Срок — от {product['min_term']} до {product['max_term']} мес.")
    passport = f"{f['passport_series'].strip()} {f['passport_number'].strip()}"
    series, number = f["passport_series"].strip(), f["passport_number"].strip()
    if not (len(series) == 4 and series.isdigit() and len(number) == 6 and number.isdigit()):
        errors.append("Серия паспорта — 4 цифры, номер — 6 цифр")
    if "consent" not in f:
        errors.append("Без согласия клиента на обработку персональных данных и запрос в БКИ заявку не рассматривают")
    if errors:
        for e in errors:
            flash(e)
        return render_template("new.html", products=products, form=f)

    # клиент: новый или уже известный по паспорту
    client = conn.execute("SELECT * FROM clients WHERE passport = ?", (passport,)).fetchone()
    if client is None:
        cur = conn.execute(
            "INSERT INTO clients (last_name, first_name, middle_name, birth_date, passport, phone) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f["last_name"], f["first_name"], f["middle_name"], f["birth_date"], passport, f["phone"]))
        client_id = cur.lastrowid
    else:
        client_id = client["id"]

    anketa = {"age": logic.age(birth.isoformat(), date.today()), "term": term, "amount": amount,
              "income": income, "experience": experience, "payments": payments, **extra}
    r = logic.evaluate(anketa, dict(product))
    cur = conn.execute(
        "INSERT INTO applications (client_id, product_id, created_at, amount, term, income, experience, payments, "
        "max_dpd, current_dpd, inquiries, history_months, score, pd, risk_class, pdn, stop_factor, factors, "
        "recommendation, rec_amount, rec_rate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (client_id, product["id"], datetime.now().isoformat(timespec="minutes"), amount, term, anketa["income"],
         anketa["experience"], anketa["payments"], anketa["max_dpd"], anketa["current_dpd"], anketa["inquiries"],
         anketa["history_months"], r["score"], r["pd"], r["risk_class"], r["pdn"], r["stop_factor"],
         json.dumps(r["factors"], ensure_ascii=False), r["recommendation"], r["rec_amount"], r["rec_rate"]))
    conn.commit()
    flash("Заявка оценена")
    return redirect(url_for("card", app_id=cur.lastrowid))


@app.route("/app/<int:app_id>", methods=["GET", "POST"])
@login_required
def card(app_id):
    conn = db.get_db()
    a = conn.execute(
        "SELECT a.*, c.last_name, c.first_name, c.middle_name, c.birth_date, c.passport, c.phone, "
        "p.name AS product, p.rate FROM applications a JOIN clients c ON c.id = a.client_id "
        "JOIN products p ON p.id = a.product_id WHERE a.id = ?", (app_id,)).fetchone()
    if a is None:
        return redirect(url_for("applications"))
    if request.method == "POST" and a["status"] == "review":
        decision = request.form.get("decision")
        comment = request.form.get("comment", "").strip()
        product = conn.execute("SELECT * FROM products WHERE id = ?", (a["product_id"],)).fetchone()
        amount = None
        if decision == "approve":
            try:
                amount = float(request.form.get("amount") or 0)
            except ValueError:
                amount = 0
        if decision not in ("approve", "reject"):
            flash("Выберите решение")
        elif decision == "approve" and not product["min_amount"] <= amount <= product["max_amount"]:
            flash(f"Сумма одобрения — от {product['min_amount']:,.0f} до {product['max_amount']:,.0f} руб."
                  .replace(",", " "))
        # решение не по рекомендации системы нужно обосновать
        elif decision != a["recommendation"] and len(comment) < 20:
            flash("Решение отличается от рекомендации системы: напишите обоснование (не короче 20 символов)")
        else:
            conn.execute("UPDATE applications SET status = ?, approved_amount = ?, comment = ?, decided_at = ? "
                         "WHERE id = ?", ("approved" if decision == "approve" else "rejected", amount, comment,
                                          datetime.now().isoformat(timespec="minutes"), app_id))
            conn.commit()
            flash("Решение сохранено")
        return redirect(url_for("card", app_id=app_id))
    return render_template("card.html", a=a, factors=json.loads(a["factors"]))


# ---------- отчёт ----------

@app.route("/report")
@login_required
def report():
    days = request.args.get("days", "90")
    days = int(days) if days.isdigit() and 1 <= int(days) <= 3650 else 90
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="minutes")
    rows = db.get_db().execute(
        "SELECT COALESCE(risk_class, 'стоп-фактор') AS cls, COUNT(*) AS total, "
        "SUM(status = 'approved') AS approved, SUM(status = 'rejected') AS rejected, "
        "SUM(CASE WHEN status = 'approved' THEN approved_amount ELSE 0 END) AS amount "
        "FROM applications WHERE created_at >= ? GROUP BY cls ORDER BY cls", (since,)).fetchall()
    total = sum(r["total"] for r in rows)
    approved = sum(r["approved"] for r in rows)
    decided = approved + sum(r["rejected"] for r in rows)
    return render_template("report.html", rows=rows, days=days, total=total, approved=approved,
                           rate=approved / decided if decided else None,
                           amount=sum(r["amount"] or 0 for r in rows))


# ---------- кредитные продукты ----------

@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    conn = db.get_db()
    if request.method == "POST":
        f = request.form
        try:
            nums = [float(f["min_amount"]), float(f["max_amount"]), int(f["min_term"]), int(f["max_term"]),
                    float(f["rate"])]
        except (KeyError, ValueError):
            flash("Границы суммы и срока и ставка — числа")
            return redirect(url_for("products"))
        if not f["name"].strip() or min(nums) <= 0:
            flash("Укажите название, а границы и ставку — больше нуля")
            return redirect(url_for("products"))
        if nums[0] > nums[1] or nums[2] > nums[3]:
            flash("Нижняя граница суммы и срока не может быть больше верхней")
            return redirect(url_for("products"))
        try:
            conn.execute("INSERT INTO products (name, min_amount, max_amount, min_term, max_term, rate) "
                         "VALUES (?, ?, ?, ?, ?, ?)",
                         (f["name"].strip(), float(f["min_amount"]), float(f["max_amount"]), int(f["min_term"]),
                          int(f["max_term"]), float(f["rate"])))
            conn.commit()
            flash("Продукт добавлен")
        except sqlite3.IntegrityError:
            flash(f"Продукт «{f['name'].strip()}» уже есть в справочнике")
        return redirect(url_for("products"))
    return render_template("products.html", products=conn.execute("SELECT * FROM products ORDER BY id").fetchall())


if __name__ == "__main__":
    db.create_tables(app.config["DATABASE"])
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
