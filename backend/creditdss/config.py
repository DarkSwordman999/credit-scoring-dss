"""Настройки системы: переменные окружения с префиксом CREDITDSS_ или файл .env."""
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_SECRETS = {"change-me", "длинная-случайная-строка-для-подписи-токенов"}
_secret_cache: dict[Path, str] = {}


def _default_data_dir() -> Path:
    # в собранной Windows-версии данные лежат рядом с exe, иначе — в backend/data
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent.parent / "data"


def _env_files() -> tuple[str, ...]:
    if getattr(sys, "frozen", False):
        return (str(Path(sys.executable).resolve().parent / ".env"), ".env")
    return (".env",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CREDITDSS_", env_file=_env_files(), extra="ignore")

    data_dir: Path = _default_data_dir()
    # postgresql+psycopg://user:pass@host:5432/credit_db  или sqlite:///путь.db
    database_url: str = ""
    # ключ подписи токенов входа; не задан — создаётся случайный и хранится в data/secret.key
    secret_key: str = ""
    token_hours: int = 12

    # сервис скоринга (А-1, И-2): пусто — расчёт в этом же процессе; иначе адрес сервиса, например http://scoring:8001
    scoring_url: str = ""
    scoring_timeout: float = 10.0
    # ключ, которым основной сервер подписывает запросы к сервису скоринга (заголовок X-Service-Key)
    scoring_key: str = ""

    # ключ, с которым АБС передаёт сведения об обслуживании кредитов (заголовок X-API-Key)
    abs_api_key: str = "abs-demo-key"

    # вход через службу каталогов (В-1): пусто — только локальные учётные записи
    ldap_url: str = ""            # ldap://dc.bank.local
    ldap_domain: str = ""         # BANK — вход как BANK\login
    ldap_timeout: int = 5

    # максимальный размер прикрепляемого файла, МБ (П-3)
    max_upload_mb: int = 20

    # HTTPS прямо в сервере (Б-1): сертификат и закрытый ключ в формате PEM
    ssl_certfile: str = ""
    ssl_keyfile: str = ""

    host: str = "127.0.0.1"
    port: int = 8000
    no_browser: bool = False

    scheduler_enabled: bool = True
    timezone: str = "Europe/Moscow"
    cors_origins: str = ""

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'creditdss.db').as_posix()}"

    @property
    def token_secret(self) -> str:
        """Ключ подписи токенов (Б-1). Без CREDITDSS_SECRET_KEY создаётся один раз и хранится в data/secret.key."""
        if self.secret_key and self.secret_key not in _WEAK_SECRETS:
            return self.secret_key
        path = self.data_dir / "secret.key"
        cached = _secret_cache.get(path)
        if cached:
            return cached
        self.ensure_dirs()
        try:
            with open(path, "x", encoding="ascii") as f:
                f.write(secrets.token_urlsafe(48))
        except FileExistsError:
            pass
        key = path.read_text(encoding="ascii").strip()
        if not key:
            raise RuntimeError(f"Пустой файл ключа {path}: удалите его, ключ создастся заново")
        _secret_cache[path] = key
        return key

    @property
    def ssl(self) -> dict:
        if not self.ssl_certfile:
            return {}
        return {"ssl_certfile": self.ssl_certfile, "ssl_keyfile": self.ssl_keyfile or None}

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backup"

    @property
    def outbox_dir(self) -> Path:
        return self.data_dir / "outbox"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.documents_dir, self.backup_dir, self.outbox_dir):
            os.makedirs(d, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
