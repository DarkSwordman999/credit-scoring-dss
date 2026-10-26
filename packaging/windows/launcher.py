"""СППР «Кредитный скоринг» для Windows: запуск без установки.

КредитныйСкоринг.exe            — подготовить БД (data\\creditdss.db рядом с программой), запустить сервер, открыть браузер;
КредитныйСкоринг.exe demo       — загрузить демонстрационные данные (в пустую БД);
КредитныйСкоринг.exe <команда>  — любая команда creditdss (init-db, backup, create-user, monitor, …).
"""
import os
import socket
import sys
import threading
import time
import webbrowser


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _ask_demo() -> bool:
    from creditdss import db
    from creditdss.models import Application
    with db.session() as s:
        if s.query(Application).count() > 0:
            return False
    try:
        ans = input("База пуста. Загрузить демонстрационные данные (около минуты)? [Д/н]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("", "д", "да", "y", "yes")


def main() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    from creditdss.cli import main as cli
    args = sys.argv[1:]
    if args:
        cli(args)
        return
    cli(["init-db"])
    if _ask_demo():
        cli(["demo"])
    from creditdss.config import get_settings
    st = get_settings()
    port = st.port
    while not _port_free(port):
        port += 1
    ssl = st.ssl
    url = f"{'https' if ssl else 'http'}://127.0.0.1:{port}/"
    print(f"\nСППР «Кредитный скоринг» работает: {url}\nНе закрывайте это окно, пока работаете с программой.\n")
    if not st.no_browser:
        threading.Thread(target=lambda: (time.sleep(2), webbrowser.open(url)), daemon=True).start()
    import uvicorn
    from creditdss.main import app
    uvicorn.run(app, host=st.host, port=port, log_level="warning", **ssl)


if __name__ == "__main__":
    main()
