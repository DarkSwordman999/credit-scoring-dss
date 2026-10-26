"""Командная строка: creditdss init-db | run | demo | create-user | scheduler | scoring | backup | restore | monitor"""
import argparse
import sys


def cmd_init_db(args) -> None:
    from . import db, migrate
    from .bootstrap import ensure_base
    migrate.upgrade()
    with db.session() as s:
        for line in ensure_base(s, args.admin_password):
            print("  ·", line)
    print("БД готова:", _safe_url())


def cmd_run(args) -> None:
    import uvicorn
    from .config import get_settings
    cmd_init_db(argparse.Namespace(admin_password="admin"))
    ssl = get_settings().ssl
    print(f"СППР «Кредитный скоринг»: {'https' if ssl else 'http'}://{args.host}:{args.port}/   (API: /api/docs)")
    uvicorn.run("creditdss.main:app", host=args.host, port=args.port, log_level="info", **ssl)


def cmd_scoring(args) -> None:
    import uvicorn
    print(f"Сервис скоринга: http://{args.host}:{args.port}/score")
    uvicorn.run("creditdss.scoring_service:app", host=args.host, port=args.port, log_level="info")


def cmd_create_user(args) -> None:
    from . import db
    from .models import ROLES, User
    from .security import hash_password
    if args.role not in ROLES:
        sys.exit(f"роль: одна из {', '.join(ROLES)}")
    with db.session() as s:
        if s.query(User).filter(User.login == args.login).first():
            sys.exit("такой логин уже есть")
        s.add(User(login=args.login, full_name=args.name or args.login, role=args.role, limit_amount=args.limit,
                   password_hash=hash_password(args.password)))
        s.commit()
    print("создан", args.login)


def cmd_demo(args) -> None:
    import time
    from . import db, migrate
    from .demo import DEMO_PASSWORD, generate, reset
    t0 = time.time()
    migrate.upgrade()
    s = db.session()
    if args.reset:
        reset(s)
        s = db.session()
    try:
        r = generate(s, months=args.months, log=lambda m: print("  ·", m, flush=True))
    except RuntimeError as e:
        sys.exit(str(e))
    finally:
        s.close()
    v1 = r["v1"]
    print(f"Демо-данные загружены за {time.time() - t0:.0f} с: заявок {r['applications']}, кредитов {r['loans']}.")
    print(f"Методика v1 на истории: ROC AUC {v1['auc']:.3f}, Gini {v1['gini']:.3f}.")
    print(f"Пользователи: admin/admin и officer, underwriter, underwriter2, head, analyst — пароль «{DEMO_PASSWORD}»")


def cmd_scheduler(args) -> None:
    from .scheduler import run_forever
    run_forever()


def cmd_backup(args) -> None:
    from .services import backup
    print("резервная копия:", backup.make())


def cmd_restore(args) -> None:
    from .errors import DomainError
    from .services import backup
    try:
        src = backup.resolve(args.file)
    except DomainError as e:
        sys.exit(str(e))
    print(f"Восстановление БД {_safe_url()} из копии {src}.")
    print("Все изменения после создания копии будут потеряны. Программа и планировщик должны быть остановлены.")
    if not args.yes:
        try:
            ans = input("Продолжить? [д/Н]: ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("д", "да", "y", "yes"):
            sys.exit("отменено")
    try:
        safety = backup.restore(src)
    except DomainError as e:
        sys.exit(f"ошибка: {e}")
    print("БД восстановлена. Состояние до восстановления сохранено в", safety)


def cmd_monitor(args) -> None:
    from . import db
    from .services import methodology
    with db.session() as s:
        rep = methodology.monitor(s, args.period or methodology.previous_month())
        s.commit()
        print(f"{rep.period}: PSI {rep.psi}, Gini {rep.gini}; оповещения: {'; '.join(rep.alerts) or 'нет'}")


def _safe_url() -> str:
    from .config import get_settings
    url = get_settings().db_url
    if "@" in url:
        head, tail = url.split("@", 1)
        url = head.split("://")[0] + "://***@" + tail
    return url


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="creditdss", description="СППР «Кредитный скоринг»")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("init-db", help="создать или обновить схему БД, завести администратора")
    a.add_argument("--admin-password", default="admin")
    a.set_defaults(func=cmd_init_db)

    a = sub.add_parser("run", help="запустить веб-сервер")
    a.add_argument("--host", default="127.0.0.1")
    a.add_argument("--port", type=int, default=8000)
    a.set_defaults(func=cmd_run)

    a = sub.add_parser("scoring", help="запустить сервис скоринга отдельным процессом")
    a.add_argument("--host", default="127.0.0.1")
    a.add_argument("--port", type=int, default=8001)
    a.set_defaults(func=cmd_scoring)

    a = sub.add_parser("create-user", help="добавить пользователя")
    a.add_argument("login")
    a.add_argument("password")
    a.add_argument("role")
    a.add_argument("--name", default="")
    a.add_argument("--limit", type=float, default=None, help="лимит полномочий, руб.")
    a.set_defaults(func=cmd_create_user)

    a = sub.add_parser("demo", help="загрузить демонстрационные данные (в пустую БД)")
    a.add_argument("--reset", action="store_true", help="сначала удалить все данные")
    a.add_argument("--months", type=int, default=30, help="глубина истории, мес.")
    a.set_defaults(func=cmd_demo)

    sub.add_parser("scheduler", help="планировщик задач отдельным процессом").set_defaults(func=cmd_scheduler)
    sub.add_parser("backup", help="резервная копия БД").set_defaults(func=cmd_backup)
    a = sub.add_parser("restore", help="восстановить БД из резервной копии")
    a.add_argument("file", help="имя копии из папки backup или путь к файлу")
    a.add_argument("--yes", action="store_true", help="не спрашивать подтверждение")
    a.set_defaults(func=cmd_restore)
    a = sub.add_parser("monitor", help="рассчитать мониторинг методики за месяц")
    a.add_argument("period", nargs="?", help="ГГГГ-ММ, по умолчанию прошлый месяц")
    a.set_defaults(func=cmd_monitor)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
