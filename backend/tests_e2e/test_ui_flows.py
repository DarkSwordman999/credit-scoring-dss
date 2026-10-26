"""Сквозные тесты интерфейса (Playwright): основные варианты использования ПР 7-8 в браузере.

Запуск: pytest tests_e2e (нужны собранный интерфейс в creditdss/static и `playwright install chromium`;
E2E_CHANNEL=msedge — запуск в установленном Edge). Сервер поднимается на временной БД с демо-данными."""
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

pw = pytest.importorskip("playwright.sync_api")
STATIC = os.path.join(os.path.dirname(__file__), "..", "creditdss", "static", "index.html")
pytestmark = pytest.mark.skipif(not os.path.exists(STATIC), reason="интерфейс не собран (npm run build)")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("e2e")
    env = dict(os.environ, CREDITDSS_DATA_DIR=str(data), CREDITDSS_SCHEDULER_ENABLED="false", PYTHONIOENCODING="utf-8")
    prep = ("from creditdss import db, migrate\n"
            "from creditdss.demo import generate\n"
            "migrate.upgrade()\n"
            "s = db.session()\n"
            "generate(s, months=20, per_day=3, log=lambda m: None)\n")
    subprocess.run([sys.executable, "-c", prep], env=env, check=True, timeout=600)
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "creditdss.main:app", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(base + "/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield base
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        channel = os.environ.get("E2E_CHANNEL")
        b = p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ru-RU")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    yield pg
    ctx.close()
    assert not errors, errors


def login(page, base, user, password="demo"):
    page.goto(base + "/")
    page.evaluate("localStorage.clear()")
    page.goto(base + "/")
    page.fill("#login", user)
    page.fill("#password", password)
    page.click("button[type=submit]")
    page.wait_for_selector("text=Здравствуйте")


def pick(page, label, option):
    page.get_by_label(label, exact=True).click()
    page.locator(".ant-select-dropdown:visible .ant-select-item-option", has_text=option).first.click()


def test_register_decide_issue(server, page):
    """Специалист регистрирует заявку, андеррайтер одобряет, специалист фиксирует выдачу."""
    login(page, server, "officer")
    page.click("text=Новая заявка")
    page.get_by_label("Серия паспорта").fill("7099")
    page.get_by_label("Номер", exact=True).fill("123987")
    page.get_by_label("Фамилия").fill("Проверкин")
    page.get_by_label("Имя", exact=True).fill("Тест")
    page.get_by_label("Отчество").fill("Тестович")
    page.get_by_label("Дата рождения").fill("15.03.1985")
    page.keyboard.press("Enter")
    page.get_by_label("Телефон").fill("+7 900 111-22-33")
    page.get_by_label("Подтверждённый доход, руб./мес.").fill("150000")
    page.get_by_label("Стаж, мес.").fill("72")
    pick(page, "Кредитный продукт", "Потребительский кредит")
    page.get_by_label("Сумма, руб.").fill("200000")
    page.get_by_label("Срок, мес.").fill("36")
    page.click("button:has-text('Зарегистрировать заявку')")
    page.wait_for_selector("text=Оценка кредитоспособности")
    number = page.locator("h3").first.inner_text().replace("Заявка ", "").strip()
    assert number.startswith("КЗ-")
    page.wait_for_selector("text=Вероятность дефолта")

    login(page, server, "underwriter")
    page.goto(server + "/applications")
    page.get_by_placeholder("Номер, фамилия или номер паспорта").fill(number)
    page.keyboard.press("Enter")
    page.click(f"a:has-text('{number}')")
    page.wait_for_selector("text=Факторы, повлиявшие на оценку")
    page.click("button:has-text('Принять решение')")
    dialog = page.locator(".ant-modal")
    dialog.get_by_label("Одобрить", exact=True).check()
    dialog.get_by_label("Сумма, руб.").fill("200000")
    dialog.get_by_label("Ставка, %").fill("19.9")
    comment = dialog.get_by_label("Комментарий", exact=False)
    comment.fill("Стабильный доход, длинная положительная кредитная история")
    page.click("button:has-text('Сохранить решение')")
    page.wait_for_selector(".ant-tag:has-text('Одобрена')")

    login(page, server, "officer")
    page.goto(server + "/applications")
    page.get_by_placeholder("Номер, фамилия или номер паспорта").fill(number)
    page.keyboard.press("Enter")
    page.click(f"a:has-text('{number}')")
    page.click("button:has-text('Кредит выдан')")
    page.click(".ant-popconfirm button:has-text('OK')")
    page.wait_for_selector("text=Кредитный договор")


def test_validation_errors_shown(server, page):
    login(page, server, "officer")
    page.click("text=Новая заявка")
    page.get_by_label("Серия паспорта").fill("7098")
    page.get_by_label("Номер", exact=True).fill("555555")
    page.get_by_label("Фамилия").fill("Безсогласий")
    page.get_by_label("Имя", exact=True).fill("Иван")
    page.get_by_label("Дата рождения").fill("01.01.1990")
    page.keyboard.press("Enter")
    page.get_by_label("Подтверждённый доход, руб./мес.").fill("80000")
    pick(page, "Кредитный продукт", "Потребительский кредит")
    page.get_by_label("Сумма, руб.").fill("100000")
    page.get_by_label("Согласие на обработку персональных данных (152-ФЗ)").uncheck()
    page.click("button:has-text('Зарегистрировать заявку')")
    page.wait_for_selector("text=Заявку нельзя зарегистрировать")
    assert page.locator("text=нет действующего согласия на обработку персональных данных").count() == 1


def test_methodology_and_reports(server, page):
    login(page, server, "analyst")
    page.click("text=Методика оценки")
    page.wait_for_selector("text=Действует версия 1")
    page.click("text=Мониторинг (С-15)")
    page.wait_for_selector("text=Оповещения")
    page.click("text=Отчёты")
    page.click("button:has-text('Сформировать')")
    page.wait_for_selector("text=Уровень одобрения по классам риска")


def test_committee_queue_and_audit(server, page):
    login(page, server, "head")
    page.wait_for_selector("text=Кредитный комитет")
    page.click("text=Журнал аудита")
    page.wait_for_selector("text=Записи журнала не изменяются")


def test_admin(server, page):
    login(page, server, "admin", "admin")
    page.click("text=Администрирование")
    page.wait_for_selector("text=Лимит полномочий")
    page.click("text=Резервные копии")
    page.click("button:has-text('Создать копию сейчас')")
    page.wait_for_selector("text=creditdss-")


def test_registry_portfolio_and_tables(server, page):
    """Руководитель: реестр заёмщиков → карточка клиента → кредитный портфель → таблицы БД."""
    login(page, server, "head")
    page.wait_for_selector("text=Последние решения")
    page.click("aside >> text=Заёмщики")
    page.check("text=Только с кредитами")
    page.locator("table a[href^='/clients/']").first.click()
    page.wait_for_selector("text=Заявки клиента")
    page.wait_for_selector("text=Кредиты клиента")
    page.click("aside >> text=Кредитный портфель")
    page.wait_for_selector("text=Качество портфеля по классам риска")
    page.click("aside >> text=Таблицы БД")
    page.wait_for_selector("text=Таблицы базы данных")
    page.locator("li:has-text('loans')").first.click()
    page.wait_for_selector("th:has-text('contract_number')")


def test_admin_demo_users_login_as(server, page):
    """Администратор видит демо-пользователей и входит под ролью руководителя."""
    login(page, server, "admin", "admin")
    page.wait_for_selector("text=пользователи демонстрационной базы")
    page.locator("tr:has-text('Руководитель') >> text=Войти под этой ролью").click()
    page.wait_for_selector("text=Последние решения")
