# Интеграция с внешними системами

Внешние системы подключаются через адаптеры (`backend/creditdss/services/integration.py`, Р-4). Режим каждого адаптера задаётся в «Администрирование → Параметры»:

- `demo` — встроенный имитатор: ответ строится детерминированно по паспорту, поэтому для одного клиента он всегда одинаков;
- `http` — запрос к API по указанному адресу в формате JSON.

## Бюро кредитных историй (С-3)

Запрос формируется только при действующем согласии клиента (С-2): `POST <bki_url>`

```json
{
  "subject": {"last_name": "Иванов", "first_name": "Иван", "middle_name": "Иванович", "birth_date": "1985-03-15",
              "passport_series": "7012", "passport_number": "123456"},
  "consent": {"signed_at": "2026-10-26", "valid_until": "2027-01-24"}
}
```

Ответ `200`:

```json
{"loans_count": 5, "active_loans": 2, "total_debt": 350000, "monthly_payments": 18000, "max_dpd": 15,
 "current_dpd": 0, "dpd30_12m": 0, "inquiries_6m": 2, "history_months": 84, "bankruptcy": false}
```

- `404` — субъект в бюро не найден: заявка оценивается как клиент без кредитной истории.
- `5xx` или сетевая ошибка — бюро недоступно: запрос повторяется по расписанию до `bki_retries` раз с интервалом `bki_retry_minutes` минут.

## АБС Банка (С-4)

**Данные о клиенте:** `POST <abs_url>` с `{"subject": {…}}`. Ответ:

```json
{"is_client": true, "client_since_months": 36, "salary_project": true, "salary_avg": 85000,
 "accounts_count": 2, "deposits_balance": 150000, "bank_loans_count": 1, "bank_monthly_payments": 7000}
```

По клиенту зарплатного проекта доход для ПДН берётся из зарплатных поступлений.

**Передача одобренной заявки:** `POST <abs_url>/contracts` с `{"number", "client", "amount", "term_months", "rate"}`. Ответ — `{"contract_number": "…"}`.

**Обслуживание выданных кредитов** (входящий обмен): АБС передаёт состояние кредитов, из которого формируется целевая переменная — просрочка 90+ дней за 12 месяцев:

```
POST /api/integration/abs/loans
X-API-Key: <CREDITDSS_ABS_API_KEY>

{"loans": [{"contract_number": "КД-2026-000123", "status": "active", "max_dpd_12m": 0}]}
```

`status` — `active`, `closed` или `default`.

## Сервис скоринга (А-1, И-2)

Отдельный процесс без состояния: `uvicorn creditdss.scoring_service:app --port 8001` или `creditdss scoring`.

```
POST /score
X-Service-Key: <CREDITDSS_SCORING_KEY>

{"application_id": 123}
```

Ответ: `pd`, `score`, `risk_class`, `pdn`, `stop_factors`, `factors` (по пять факторов, повышающих и снижающих риск, с текстом), `features` (40 признаков), `recommendation`, `rec_amount`, `rec_term`, `rec_rate`, `model_version`, `duration_ms`.

Если сервис недоступен, основной сервер оценивает заявку по резервной методике — базовой экспертной скоринговой карте. Оценка помечается в карточке, событие пишется в журнал обмена (ПР 4, табл. 4.3).

## Служба каталогов (В-1)

`CREDITDSS_LDAP_URL=ldap://dc.bank.local`, `CREDITDSS_LDAP_DOMAIN=BANK`. Пользователь входит паролем домена (`BANK\login`); роль и лимит полномочий берутся из его учётной записи в системе. Администратор `admin` всегда входит локальным паролем.

## REST API (И-1)

Полное описание — OpenAPI 3: `/api/docs` и `/api/openapi.json`. Аутентификация — `POST /api/auth/token` (логин и пароль), затем заголовок `Authorization: Bearer <токен>`.
