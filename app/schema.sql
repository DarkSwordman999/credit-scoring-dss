-- СППР «Кредитный скоринг», базовая редакция: таблицы базы данных SQLite

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    login         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

-- кредитные продукты: диапазоны суммы и срока, базовая ставка
CREATE TABLE IF NOT EXISTS products (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    min_amount REAL NOT NULL,
    max_amount REAL NOT NULL,
    min_term   INTEGER NOT NULL,
    max_term   INTEGER NOT NULL,
    rate       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY,
    last_name   TEXT NOT NULL,
    first_name  TEXT NOT NULL,
    middle_name TEXT NOT NULL DEFAULT '',
    birth_date  TEXT NOT NULL,             -- ГГГГ-ММ-ДД
    passport    TEXT NOT NULL UNIQUE,      -- серия и номер: «7012 123456»
    phone       TEXT NOT NULL DEFAULT ''
);

-- заявка: анкета, сведения из кредитного отчёта БКИ, результат оценки и решение
CREATE TABLE IF NOT EXISTS applications (
    id                INTEGER PRIMARY KEY,
    client_id         INTEGER NOT NULL REFERENCES clients(id),
    product_id        INTEGER NOT NULL REFERENCES products(id),
    created_at        TEXT NOT NULL,
    amount            REAL NOT NULL,
    term              INTEGER NOT NULL,     -- срок, мес.
    income            REAL NOT NULL,        -- подтверждённый доход в месяц
    experience        INTEGER NOT NULL,     -- стаж на текущем месте, мес.
    -- из кредитного отчёта БКИ (вносится по отчёту с портала бюро)
    payments          REAL NOT NULL DEFAULT 0,   -- платежи по действующим кредитам в месяц
    max_dpd           INTEGER NOT NULL DEFAULT 0, -- максимальная просрочка в истории, дн.
    current_dpd       INTEGER NOT NULL DEFAULT 0, -- текущая просрочка, дн.
    inquiries         INTEGER NOT NULL DEFAULT 0, -- запросов в БКИ за 6 месяцев
    history_months    INTEGER NOT NULL DEFAULT 0, -- длина кредитной истории, мес.
    -- оценка
    score             REAL,
    pd                REAL,                 -- вероятность дефолта, доля
    risk_class        TEXT,                 -- A..E
    pdn               REAL NOT NULL,        -- показатель долговой нагрузки, доля
    stop_factor       TEXT,                 -- сработавший стоп-фактор (тогда отказ)
    factors           TEXT NOT NULL DEFAULT '[]',  -- JSON: факторы, повлиявшие на оценку
    recommendation    TEXT NOT NULL,        -- approve | reject
    rec_amount        REAL,
    rec_rate          REAL,
    -- решение
    status            TEXT NOT NULL DEFAULT 'review',  -- review | approved | rejected
    approved_amount   REAL,
    comment           TEXT NOT NULL DEFAULT '',
    decided_at        TEXT
);
