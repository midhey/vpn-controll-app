# Подсос VPN — backend

FastAPI-бэкенд поверх Go-агента из `../agent`. Если `DATABASE_URL` или
`DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` не заданы, backend работает в
in-memory режиме для локального smoke-теста. Если данные БД заданы, используется
PostgreSQL + SQLAlchemy + Alembic.

Полное ТЗ: [`../backend-fastapi-plan-for-claude.md`](../backend-fastapi-plan-for-claude.md).

## Запуск

Нужен Python 3.11+ (прод-цель — 3.12). Через `uv`:

```bash
cd backend
uv sync --group dev
cp .env.example .env            # файл уже в .gitignore
# Заполни DB_HOST/DB_NAME/DB_USER/DB_PASSWORD или DATABASE_URL.
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Swagger: <http://127.0.0.1:8000/api/docs>.

При первом старте создаётся админ `FIRST_ADMIN_LOGIN` (по умолчанию `midhey`).
Если `FIRST_ADMIN_PASSWORD` не задан — пароль генерируется и печатается в лог.
Переменные окружения — в [.env.example](.env.example). Для PostgreSQL можно
задать одну строку:

```dotenv
DATABASE_URL=postgresql://vpn_user:password@db-host:5432/vpn_control
```

Или раздельные поля:

```dotenv
DB_HOST=db-host
DB_PORT=5432
DB_NAME=vpn_control
DB_USER=vpn_user
DB_PASSWORD=password
```

Тесты: `uv run pytest` (агент и установка — фейки, сеть не нужна).

## Что настоящее, а что заглушка

| Часть | Сейчас | На интеграции |
|---|---|---|
| Хранилище | PostgreSQL при заданной БД; иначе in-memory fallback | боевой backup/monitoring БД |
| Пароли | PBKDF2 (stdlib) | argon2id (`argon2-cffi`), формат хеша самоописываемый |
| Шифрование секретов | `PlaintextSecretBox` (base64-пометка, не защита) | Fernet (`cryptography`) c `ENCRYPTION_KEY` |
| Агент | `FakeAgentTransport` — имитация узла на каждый URL | `HttpxAgentTransport` уже написан (`AGENT_MODE=http`) |
| Установка VPS | `StubSetupRunner` — имитация шагов | запуск `agent/scripts/deploy-agent.sh` по SSH |
| HMAC-подпись запросов к агенту | **настоящая**, байт-в-байт как в `agent/internal/httpapi/auth.go`, закреплена тестами | без изменений |
| Сессии, роли, лимиты, аудит, CSRF, rate-limit входа | настоящие | без изменений |

Демо-поведение фейков:
- узел с любым `agent_base_url` «существует» и отвечает как настоящий агент;
- setup-джоба с хостом, содержащим `fail`, падает на шаге проверки SSH — удобно
  смотреть экран ошибки;
- задержка шагов установки — `SETUP_STEP_DELAY_SECONDS` (по умолчанию 1.2 с, чтобы
  статусы в UI были видны).

## Быстрый сценарий руками (через Swagger)

1. `POST /api/v1/auth/login` — логин `midhey` + пароль из лога/env.
2. `POST /api/v1/admin/servers` — добавить узел (`agent_base_url` любой, например
   `http://demo:8090`, `agent_secret` любой) → `POST .../health-check` → станет `online`.
   Либо `POST /api/v1/admin/setup-jobs` — «установить VPS» и следить за шагами.
3. `POST /api/v1/admin/users` — завести участника.
4. Перелогиниться участником → `POST /api/v1/devices` — получить конфиг и `vpn://`-ссылку.

## Структура

```text
app/
  main.py            сборка приложения, контейнер сервисов, bootstrap админа
  core/              настройки, формат ошибок, пароли/токены/шифрование, логи
  domain/models.py   доменные модели (поля = будущие таблицы из плана)
  storage/memory.py  in-memory хранилище — единственная точка замены на PostgreSQL
  schemas/           Pydantic-схемы запросов/ответов
  services/          вся бизнес-логика (роутеры тонкие)
    agent_client.py  клиент Go-агента: подпись HMAC, fake/httpx транспорты
  api/routes/        ручки /api/v1/...
  workers/           фоновый воркер setup-джоб
  tests/             smoke-тесты API + пин алгоритма подписи
```

## Ручки

- `auth`: login / logout / session
- `me`: профиль, dashboard (лимит устройств, подсказка поддержки, последние устройства)
- `devices`: список, выпуск, карточка, отзыв, issue-result (конфиг+QR, TTL 15 мин,
  повторное чтение до истечения)
- `servers`: список доступных серверов глазами участника
- `support`: блок «поддержать сервер» + своя история (виден только тем, кому включено)
- `admin/users`: CRUD, reset-password, enable/disable, устройства участника, взносы
- `admin/servers`: CRUD, health-check, пиры с узла, enable/disable
- `admin/setup-jobs`: создание, статус по шагам, события, отмена
- `admin/support-settings`: глобальные настройки поддержки
- `admin/audit-logs`: журнал действий
- `health`: живость API

Формат ошибок единый: `{"error": {"code", "message", "details"}}`, коды — из плана
(`device_limit_reached`, `issue_result_expired`, `agent_unavailable`, ...).
