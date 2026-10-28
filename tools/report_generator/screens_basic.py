# -*- coding: utf-8 -*-
"""Снимки экранов базовой редакции для руководства пользователя.

Запуск интерпретатором, в котором установлены Flask (app/requirements.txt) и playwright:
    python screens_basic.py <папка для снимков>
Программа копируется во временную папку, там же создаются демо-данные — рабочая база не меняется.
Браузер (Edge или Chromium) работает без окна."""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "app"))


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    work = os.path.join(tempfile.mkdtemp(prefix="creditdss-basic-shots-"), "app")
    shutil.copytree(APP, work, ignore=shutil.ignore_patterns(".venv", "wheels", "__pycache__", "creditdss.db",
                                                             "secret.key"))
    subprocess.run([sys.executable, "demo.py"], cwd=work, check=True, stdout=subprocess.DEVNULL)
    sys.path.insert(0, work)
    os.chdir(work)
    import app as A
    import logging
    from werkzeug.serving import make_server
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    srv = make_server("127.0.0.1", 0, A.app)
    base = f"http://127.0.0.1:{srv.server_port}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    done = []
    try:
        with sync_playwright() as p:
            try:
                b = p.chromium.launch(channel="msedge")
            except Exception:
                b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1000, "height": 760}, locale="ru-RU", device_scale_factor=1.25)

            def shot(name, full=False):
                pg.wait_for_load_state("networkidle")
                time.sleep(0.3)
                pg.screenshot(path=os.path.join(out_dir, f"scr_{name}.png"), full_page=full)
                done.append(name)

            pg.goto(base + "/login")
            pg.fill("input[name=login]", "admin")
            pg.fill("input[name=password]", "admin")
            shot("login")
            pg.click("button")
            shot("apps")
            pg.select_option("select[name=status]", "review")
            pg.click("form.inline button")
            shot("apps_review")

            def fill(**kw):
                for k, v in kw.items():
                    pg.fill(f"input[name={k}]", v)

            pg.goto(base + "/new")
            fill(last_name="Образцов", first_name="Пётр", middle_name="Ильич", birth_date="1985-03-15",
                 passport_series="7099", passport_number="123987", phone="+7 900 111-22-33", income="85000",
                 experience="40", amount="150000", term="24", payments="12000", history_months="48", max_dpd="0",
                 current_dpd="0", inquiries="1")
            pg.check("input[name=consent]")
            shot("form", full=True)
            pg.click("form.box button")
            shot("card", full=True)
            pg.fill("textarea[name=comment]", "")
            pg.click("form.box button")
            shot("decided", full=True)

            # заявка со стоп-фактором и решение не по рекомендации без обоснования
            pg.goto(base + "/new")
            fill(last_name="Петрова", first_name="Анна", middle_name="Сергеевна", birth_date="1990-07-01",
                 passport_series="7100", passport_number="654321", income="40000", experience="12", amount="200000",
                 term="36", payments="25000", history_months="30", max_dpd="45", current_dpd="15", inquiries="4")
            pg.check("input[name=consent]")
            pg.click("form.box button")
            pg.select_option("select[name=decision]", "approve")
            pg.click("form.box button")
            shot("card_stop", full=True)

            # ошибка ввода: сумма вне продукта, нет согласия
            pg.goto(base + "/new")
            fill(last_name="Тестов", first_name="Иван", birth_date="1980-01-01", passport_series="7101",
                 passport_number="111222", income="60000", experience="10", amount="5000000", term="12")
            pg.click("form.box button")
            shot("form_errors")

            pg.goto(base + "/report?days=180")
            shot("report")
            pg.goto(base + "/products")
            shot("products", full=True)
            b.close()
    finally:
        srv.shutdown()
    print("снимки:", ", ".join(done))


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
