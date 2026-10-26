"""Планировщик задач: повторные запросы в БКИ и АБС (С-3), ежемесячный мониторинг методики (С-15),
ежедневная резервная копия БД (Н-1)."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import audit, db
from .config import get_settings

log = logging.getLogger("creditdss.scheduler")


def _job(name: str, mode: str = "immediate"):
    def wrap(fn):
        def run():
            s = db.session(mode)
            try:
                msg = fn(s)
                if msg:
                    audit.integration(s, "scheduler", f"{name}: {msg}")
                s.commit()
            except Exception as e:  # задача не должна ронять планировщик
                s.rollback()
                audit.integration(s, "scheduler", f"{name}: ошибка {e}", status="error")
                s.commit()
                log.exception(name)
            finally:
                s.close()
        run.__name__ = name
        return run
    return wrap


@_job("повторные запросы в БКИ и АБС")
def job_retry(s):
    from .services import applications
    n = applications.retry_due(s)
    return f"заявок: {n}" if n else ""


@_job("мониторинг методики", mode="deferred")
def job_monitor(s):
    from .services import methodology
    rep = methodology.monitor(s, methodology.previous_month())
    return f"{rep.period}: PSI {rep.psi}, Gini {rep.gini}, оповещений {len(rep.alerts)}"


@_job("резервная копия")
def job_backup(s):
    from .services import backup
    return f"создана {backup.make().name}"


def _add_jobs(sched) -> None:
    tz = get_settings().timezone
    sched.add_job(job_retry, IntervalTrigger(minutes=1), id="retry")
    sched.add_job(job_monitor, CronTrigger(day=1, hour=4, minute=0, timezone=tz), id="monitor", coalesce=True,
                  misfire_grace_time=24 * 3600)
    sched.add_job(job_backup, CronTrigger(hour=2, minute=0, timezone=tz), id="backup", coalesce=True,
                  misfire_grace_time=6 * 3600)


def start(paused: bool = False) -> BackgroundScheduler:
    """Планировщик внутри веб-сервера (однопроцессная установка, Windows-версия)."""
    sched = BackgroundScheduler(timezone=get_settings().timezone)
    _add_jobs(sched)
    sched.start(paused=paused)
    return sched


def run_forever() -> None:
    """Отдельный процесс-планировщик (docker-compose, сервис scheduler)."""
    logging.basicConfig(level=logging.INFO)
    sched = BlockingScheduler(timezone=get_settings().timezone)
    _add_jobs(sched)
    log.info("планировщик запущен: %s", ", ".join(j.id for j in sched.get_jobs()))
    sched.start()
