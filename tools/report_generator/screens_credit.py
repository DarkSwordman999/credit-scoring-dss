# -*- coding: utf-8 -*-
"""Снимки экранов полной редакции для руководства пользователя.

Запуск интерпретатором backend/.venv (нужны playwright и пакет creditdss):
    python screens_credit.py <папка с демо-данными> <папка для снимков>
Демо-данные копируются во временную папку — исходная база не меняется. Браузер (Edge или Chromium)
работает без окна, на экран пользователя ничего не выводится."""
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import httpx
from playwright.sync_api import sync_playwright

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _targets(db):
    c = sqlite3.connect(db)
    q = lambda sql: c.execute(sql).fetchone()
    review = q("SELECT a.id FROM applications a JOIN scoring_results s ON s.application_id = a.id "
               "WHERE a.status = 'review' AND s.stop_factors = '[]' AND s.recommendation <> 'reject' "
               "ORDER BY a.id DESC LIMIT 1")[0]
    stop = q("SELECT a.id FROM applications a JOIN scoring_results s ON s.application_id = a.id "
             "WHERE a.status = 'rejected' AND s.stop_factors <> '[]' ORDER BY a.id DESC LIMIT 1")[0]
    client = q("SELECT a.client_id FROM applications a JOIN loans l ON l.application_id = a.id "
               "GROUP BY a.client_id ORDER BY COUNT(*) DESC, a.client_id DESC LIMIT 1")[0]
    cand = q("SELECT id FROM scoring_models WHERE status = 'candidate' ORDER BY id DESC LIMIT 1")
    pub = q("SELECT id FROM scoring_models WHERE status = 'published'")[0]
    c.close()
    return {"review": review, "stop": stop, "client": client, "candidate": cand[0] if cand else pub, "published": pub}


def main(src_data, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="creditdss-shots-")
    data = os.path.join(work, "data")
    shutil.copytree(src_data, data)
    t = _targets(os.path.join(data, "creditdss.db"))
    env = dict(os.environ, CREDITDSS_DATA_DIR=data, CREDITDSS_SCHEDULER_ENABLED="false", PYTHONIOENCODING="utf-8")
    port = _port()
    py = os.path.join(BACKEND, ".venv", "Scripts", "python.exe")
    proc = subprocess.Popen([py, "-m", "uvicorn", "creditdss.main:app", "--port", str(port)], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            if httpx.get(base + "/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    done, failed = [], []
    try:
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel="msedge")
            except Exception:
                b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 1440, "height": 860}, locale="ru-RU", device_scale_factor=1.25)
            pg = ctx.new_page()

            def shot(name, full=False):
                pg.wait_for_load_state("networkidle")
                time.sleep(0.6)
                pg.screenshot(path=os.path.join(out_dir, f"scr_{name}.png"), full_page=full)
                done.append(name)

            def login(user, password="demo"):
                pg.goto(base + "/")
                pg.evaluate("localStorage.clear()")
                pg.goto(base + "/")
                pg.fill("#login", user)
                pg.fill("#password", password)
                pg.click("button[type=submit]")
                pg.wait_for_selector("text=Здравствуйте")

            def go(path):
                pg.goto(base + path)
                pg.wait_for_load_state("networkidle")

            def step(name, fn):
                try:
                    fn()
                except Exception as e:  # снимок не получился — остальные продолжаем
                    failed.append(f"{name}: {e}"[:300])

            def s_login():
                pg.goto(base + "/")
                pg.evaluate("localStorage.clear()")
                pg.goto(base + "/")
                pg.wait_for_selector("#login")
                shot("login")
            step("login", s_login)

            login("officer")
            step("dash_officer", lambda: (go("/"), shot("dash_officer")))
            step("apps", lambda: (go("/applications"), shot("apps")))

            def s_form():
                go("/applications/new")
                pg.get_by_label("Серия паспорта").fill("7099")
                pg.get_by_label("Номер", exact=True).fill("123987")
                pg.get_by_label("Фамилия").fill("Образцов")
                pg.get_by_label("Имя", exact=True).fill("Пётр")
                pg.get_by_label("Отчество").fill("Ильич")
                pg.get_by_label("Дата рождения").fill("15.03.1985")
                pg.keyboard.press("Enter")
                pg.get_by_label("Телефон").fill("+7 900 111-22-33")
                pg.get_by_label("Подтверждённый доход, руб./мес.").fill("150000")
                pg.get_by_label("Стаж, мес.").fill("72")
                pg.get_by_label("Кредитный продукт", exact=True).click()
                pg.locator(".ant-select-dropdown:visible .ant-select-item-option",
                           has_text="Потребительский кредит").first.click()
                pg.get_by_label("Сумма, руб.").fill("200000")
                pg.get_by_label("Срок, мес.").fill("36")
                pg.mouse.click(5, 300)
                pg.evaluate("document.querySelectorAll('*').forEach(e => { if (e.scrollTop) e.scrollTop = 0; });"
                            "window.scrollTo(0, 0)")
                shot("form")
                pg.click("button:has-text('Зарегистрировать заявку')")
                pg.wait_for_selector("text=Вероятность дефолта")
                shot("registered")
            step("form", s_form)
            step("clients", lambda: (go("/clients"), shot("clients")))
            step("client_card", lambda: (go(f"/clients/{t['client']}"), shot("client_card")))
            step("loans", lambda: (go("/loans"), shot("loans")))

            login("underwriter")
            step("dash_uw", lambda: (go("/"), shot("dash_uw")))

            def s_card():
                go(f"/applications/{t['review']}")
                pg.wait_for_selector("text=Факторы, повлиявшие на оценку")
                shot("card")
                pg.get_by_text("Кредитное досье").first.evaluate("e => e.scrollIntoView({block: 'start'})")
                shot("card_dossier")
                pg.click("button:has-text('Принять решение')")
                pg.wait_for_selector(".ant-modal")
                shot("decision")
                pg.keyboard.press("Escape")
            step("card", s_card)

            def s_stop():
                go(f"/applications/{t['stop']}")
                pg.wait_for_selector("text=Стоп-факторы")
                pg.get_by_text("Стоп-факторы").first.scroll_into_view_if_needed()
                shot("card_stop")
            step("card_stop", s_stop)

            login("head")
            step("dash_head", lambda: (go("/"), shot("dash_head")))
            def s_reports():
                go("/reports")
                pg.click("button:has-text('Сформировать')")
                pg.wait_for_selector(".ant-table-row")
                shot("reports")
            step("reports", s_reports)
            step("audit", lambda: (go("/audit"), shot("audit")))
            step("data", lambda: (go("/data"), shot("data")))

            login("analyst")
            step("models", lambda: (go("/models"), shot("models")))
            step("model_card", lambda: (go(f"/models/{t['candidate']}"), shot("model_card")))

            def s_monitor():
                go("/models")
                pg.click("text=Мониторинг (С-15)")
                shot("monitoring")
            step("monitoring", s_monitor)

            def s_nsi():
                go("/nsi")
                shot("nsi_products")
                pg.click(".ant-tabs-tab:has-text('Стоп-факторы')")
                shot("nsi_stop")
                pg.click(".ant-tabs-tab:has-text('Классы риска и условия')")
                shot("nsi_classes")
            step("nsi", s_nsi)

            login("admin", "admin")
            step("dash_admin", lambda: (go("/"), shot("dash_admin")))

            def s_admin():
                go("/admin")
                shot("admin_users")
                for tab, name in (("Параметры", "admin_settings"), ("Журнал обмена", "admin_integration"),
                                  ("Резервные копии", "admin_backups")):
                    pg.click(f".ant-tabs-tab:has-text('{tab}')")
                    if name == "admin_backups":
                        pg.click("button:has-text('Создать копию сейчас')")
                        pg.wait_for_selector("text=creditdss-")
                    shot(name)
            step("admin", s_admin)
            b.close()
    finally:
        proc.terminate()
        proc.wait(10)
        shutil.rmtree(work, ignore_errors=True)
    print("снимки:", ", ".join(done))
    if failed:
        print("не получились:", *failed, sep="\n  ")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
