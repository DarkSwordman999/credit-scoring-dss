"""Начальное наполнение пустой БД: администратор, кредитные продукты, стоп-факторы, матрица условий,
базовая версия методики оценки."""
from datetime import datetime

from sqlalchemy.orm import Session

from .models import ConditionRule, Product, ScoringModel, StopFactor, User
from .scoring import scorecard, stopfactors
from .scoring.engine import DEFAULT_MATRIX
from .security import hash_password

# ПР 3: потребительский кредит от 30 тыс. до 3 млн руб. на 6–84 мес., рефинансирование, кредитная карта
PRODUCTS = [
    ("Потребительский кредит", 30_000, 3_000_000, 6, 84, 19.9),
    ("Рефинансирование", 100_000, 3_000_000, 12, 84, 17.9),
    ("Кредитная карта", 30_000, 500_000, 12, 36, 29.9),
]


def ensure_base(db: Session, admin_password: str = "admin") -> list[str]:
    """Возвращает список сделанного (для вывода в консоль)."""
    done = []
    if db.query(User).count() == 0:
        db.add(User(login="admin", full_name="Администратор", role="admin",
                    password_hash=hash_password(admin_password)))
        done.append(f"создан пользователь admin (пароль: {admin_password}) — смените пароль после входа")
    if db.query(Product).count() == 0:
        db.add_all(Product(name=n, min_amount=a, max_amount=b, min_term=c, max_term=d, base_rate=r)
                   for n, a, b, c, d, r in PRODUCTS)
        done.append("заполнен справочник кредитных продуктов")
    if db.query(StopFactor).count() == 0:
        db.add_all(StopFactor(code=c, description=d, rule=r, threshold=t, active=a)
                   for c, d, r, t, a in stopfactors.DEFAULTS)
        done.append("заполнен справочник стоп-факторов")
    if db.query(ConditionRule).count() == 0:
        db.add_all(ConditionRule(risk_class=c, pdn_from=a, pdn_to=b, decision=d, amount_factor=k, rate_add=r)
                   for c, a, b, d, k, r in DEFAULT_MATRIX)
        done.append("заполнена матрица условий «класс риска × ПДН»")
    if db.query(ScoringModel).count() == 0:
        db.add(ScoringModel(version=1, name="Экспертная скоринговая карта", algorithm="scorecard",
                            status="published", params=scorecard.default_params(), published_at=datetime.now(),
                            comment="Базовая методика: экспертная скоринговая карта из 14 характеристик"))
        done.append("опубликована базовая версия методики оценки")
    db.commit()
    return done
