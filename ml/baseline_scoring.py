"""Базовый прототип PD-модели (вероятность дефолта заёмщика).

Данные синтетические — генерируются скриптом, чтобы прототип запускался без доступа
к реальным (персональным) данным. В дипломной работе генератор заменяется на
обезличенную выборку заявок / открытый датасет (например, Home Credit Default Risk).

Сравниваются:
  * логистическая регрессия — интерпретируемая базовая модель (аналог скоринговой карты);
  * градиентный бустинг над деревьями — основная модель.
Метрики: ROC AUC, Gini = 2·AUC − 1, KS.

Запуск:  python ml/baseline_scoring.py
"""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

RNG = np.random.default_rng(42)


def make_dataset(n: int = 40_000) -> pd.DataFrame:
    """Синтетические заявки с нелинейной зависимостью риска от признаков."""
    age = RNG.integers(21, 70, n)
    income = np.round(RNG.lognormal(10.9, 0.45, n), -2)              # руб./мес.
    amount = np.round(RNG.uniform(50_000, 1_500_000, n), -3)
    term = RNG.choice([12, 24, 36, 48, 60], n)
    existing_payments = np.round(income * RNG.beta(2, 6, n), -2)
    rate = 0.18
    new_payment = amount * (rate / 12) / (1 - (1 + rate / 12) ** -term)
    pdn = (existing_payments + new_payment) / income                  # показатель долговой нагрузки
    max_delay = RNG.choice([0, 0, 0, 0, 5, 15, 30, 60, 90], n)        # макс. просрочка в КИ, дней
    inquiries_6m = RNG.poisson(1.5, n)                                # запросов в БКИ за 6 мес.
    employment_years = np.clip(RNG.exponential(5, n), 0, 40)
    education = RNG.choice(["среднее", "среднее_спец", "высшее"], n, p=[0.2, 0.4, 0.4])
    channel = RNG.choice(["офис", "онлайн"], n, p=[0.6, 0.4])

    logit = (-3.2
             + 2.2 * np.clip(pdn - 0.5, 0, None)                      # нелинейность: риск растёт при ПДН > 50 %
             + 0.025 * max_delay
             + 0.25 * inquiries_6m
             - 0.06 * employment_years
             + 0.002 * (age - 45) ** 2                                  # U-образная зависимость от возраста
             + 1.5 * ((pdn > 0.8) & (max_delay >= 30))                # совместное действие факторов
             - 0.35 * (education == "высшее")
             + 0.3 * (channel == "онлайн") * (inquiries_6m > 3))      # взаимодействие признаков
    default = RNG.random(n) < 1 / (1 + np.exp(-logit))
    return pd.DataFrame(dict(age=age, income=income, amount=amount, term=term, pdn=pdn,
                             max_delay=max_delay, inquiries_6m=inquiries_6m,
                             employment_years=employment_years, education=education,
                             channel=channel, default=default.astype(int)))


def ks_stat(y, p) -> float:
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def main() -> None:
    df = make_dataset()
    X, y = df.drop(columns="default"), df["default"]
    num = X.select_dtypes("number").columns.tolist()
    cat = [c for c in X.columns if c not in num]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=0)
    print(f"Заявок: {len(df)}, доля дефолтов: {y.mean():.1%}")

    models = {
        "Логистическая регрессия": Pipeline([
            ("prep", ColumnTransformer([("num", StandardScaler(), num),
                                        ("cat", OneHotEncoder(handle_unknown="ignore"), cat)])),
            ("clf", LogisticRegression(max_iter=1000))]),
        "Градиентный бустинг": Pipeline([
            ("prep", ColumnTransformer([("num", "passthrough", num),
                                        ("cat", OneHotEncoder(handle_unknown="ignore"), cat)])),
            ("clf", HistGradientBoostingClassifier(learning_rate=0.05, max_iter=400,
                                                   early_stopping=True, random_state=0))]),
    }
    print(f"{'Модель':<26}{'ROC AUC':>9}{'Gini':>8}{'KS':>8}")
    for name, m in models.items():
        m.fit(X_tr, y_tr)
        p = m.predict_proba(X_te)[:, 1]
        auc = roc_auc_score(y_te, p)
        print(f"{name:<26}{auc:>9.3f}{2 * auc - 1:>8.3f}{ks_stat(y_te, p):>8.3f}")


if __name__ == "__main__":
    main()
