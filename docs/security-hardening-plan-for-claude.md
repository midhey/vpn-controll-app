# План для Claude: безопасность добавления VPS и агента

## Контекст

Сейчас админ может создать setup job с фронта через `/admin/setup-jobs/new`, но это не реальная установка VPS.

Текущее состояние:

- `backend/app/workers/setup_worker.py` использует `StubSetupRunner`: SSH, установка агента и установка VPN только имитируются.
- `backend/app/main.py` всегда создаёт `PlaintextSecretBox`, который кодирует секреты в base64 и не является шифрованием.
- `AGENT_MODE=fake` по умолчанию использует `FakeAgentTransport`, поэтому health-check и выпуск peers могут проходить без реального агента.
- Go-агент уже поддерживает HMAC-подпись, timestamp skew и IP allowlist, но backend setup flow пока не разворачивает agent service на VPS.
- `agent/scripts/deploy-agent.sh` уже умеет собрать/загрузить агент, поставить systemd service, записать env-файл с HMAC secret и выставить `--allow-ip`.

Цель: сделать безопасный production-ready путь, где админ добавляет VPS с фронта, backend реально устанавливает агент на узел, сохраняет секреты безопасно, проверяет связь с агентом и только после этого делает сервер доступным для новых устройств.

## Основные риски, которые надо закрыть

1. SSH secret сейчас хранится через `PlaintextSecretBox`. Это недопустимо для реальных VPS-доступов.
2. Setup job сейчас создаёт иллюзию успешной установки, потому что runner stub.
3. Backend может работать в `AGENT_MODE=fake` в окружении, где админ ожидает реальный agent.
4. Agent endpoint может быть случайно выставлен публично без строгого allowlist.
5. Agent HMAC secret попадает в systemd env-файл на VPS; файл должен иметь права `0600`, а secret не должен попадать в process args, логи, audit и API responses.
6. После ошибки установки SSH secret должен очищаться всегда.
7. Сервер нельзя автоматически отдавать пользователям, пока реальный health-check/status не подтвердил рабочий агент.

## План реализации

### 1. Реальное шифрование секретов в backend

Заменить `PlaintextSecretBox` на production-реализацию.

Требования:

- Добавить `FernetSecretBox` на базе `cryptography.fernet.Fernet`.
- Добавить настройку `ENCRYPTION_KEY`.
- В `APP_ENV != local` backend должен падать при старте, если `ENCRYPTION_KEY` отсутствует или невалиден.
- В `APP_ENV=local` можно оставить явный fallback только для dev, но он должен логироваться как небезопасный режим.
- Не ломать существующий интерфейс `SecretBox`.
- Не логировать plaintext секреты.

Затронутые места:

- `backend/app/core/security.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/pyproject.toml`
- `backend/.env.example`
- `backend/README.md`

Тесты:

- unit-test encrypt/decrypt roundtrip.
- invalid `ENCRYPTION_KEY` fails fast in non-local env.
- setup job response не содержит `secret`.
- terminal setup job очищает `secret_encrypted`.

### 2. Запрет fake agent в production

Добавить защиту от случайного production запуска с fake transport.

Требования:

- Если `APP_ENV != local` и `AGENT_MODE != http`, backend должен падать при старте.
- В README явно описать, что `AGENT_MODE=fake` только для demo/test.
- Тест на fail-fast конфиг.

Затронутые места:

- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/README.md`

### 3. Реальный setup runner вместо StubSetupRunner

Добавить runner, который запускает `agent/scripts/deploy-agent.sh` для реальной VPS.

Минимальный вариант:

- Новый класс `DeployScriptSetupRunner`.
- Запускать script через `asyncio.create_subprocess_exec`, без shell.
- Передавать SSH key/password безопасно.
- Для SSH key: писать временный файл с mode `0600`, удалять в `finally`.
- Для password: по возможности передавать через env `SSHPASS`, а не через CLI args. Если текущий deploy script принимает только `--password`, доработать script так, чтобы он мог читать пароль из env/temporary secret file.
- Не писать SSH secret в логи, audit, events или exception details.
- Ограничить максимальную длительность установки таймаутом.
- Сохранять stdout/stderr только в redacted виде, либо писать в events короткие безопасные статусы.

Параметры runner:

- путь к `deploy-agent.sh`
- backend public/private IP для agent allowlist
- agent listen address
- agent public/private base URL
- service name
- timeout

Новые настройки:

- `SETUP_RUNNER=stub|deploy_script`
- `SETUP_DEPLOY_SCRIPT_PATH`
- `SETUP_AGENT_LISTEN`, default лучше не `0.0.0.0`, а private bind, если инфраструктура позволяет
- `SETUP_AGENT_BASE_URL_TEMPLATE`, например `http://{host}:8090`
- `SETUP_AGENT_ALLOW_IPS`
- `SETUP_TIMEOUT_SECONDS`

В production:

- `SETUP_RUNNER=stub` запрещён.
- `SETUP_AGENT_ALLOW_IPS` должен быть задан явно и не должен быть `0.0.0.0/0,::/0`, если нет отдельного override-флага.

Затронутые места:

- `backend/app/workers/setup_worker.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `agent/scripts/deploy-agent.sh`
- `backend/README.md`

Тесты:

- unit-test runner builds subprocess args without leaking secret.
- subprocess failure переводит setup job в `failed`.
- timeout переводит setup job в `failed`.
- success creates server node only after deploy runner success.
- `verify_before_install=false` не должен отключать финальный agent health-check.

### 4. Безопасная конфигурация Go-агента

Проверить и усилить agent service configuration.

Требования:

- Agent service должен стартовать с HMAC secret.
- Unsigned endpoints разрешать только при явном `--allow-no-auth`, и это должно быть запрещено setup runner в production.
- `VPN_AGENT_SECRET` должен храниться в `/etc/vpn-agent/<service>.env` с mode `0600`.
- HMAC secret не должен попадать в `ExecStart` command line.
- `--allow-ip` должен быть узким: IP backend или private subnet, а не весь интернет.
- `/health` остаётся unsigned, но не должен раскрывать чувствительные данные.
- Документировать firewall правило: открыть agent port только для backend/VPN/private network.

Затронутые места:

- `agent/scripts/deploy-agent.sh`
- `agent/internal/httpapi/auth.go`
- `agent/internal/httpapi/server.go`
- `agent/README.md`
- `backend/README.md`

Тесты:

- Go tests на HMAC required.
- Go tests на allowlist required.
- Go tests на invalid timestamp/signature/key id.
- Go tests, что service unit не содержит plaintext secret в `ExecStart`.

### 5. Корректный lifecycle setup job

Сделать статусы честными и безопасными.

Требования:

- Создание setup job сразу ставит задачу в очередь только если worker включён.
- Если worker выключен, job должен оставаться draft/queued с явным сообщением, а UI должен показывать, что установка не запущена.
- После успешного deploy:
  - создать `server_node` со статусом `setup_running` или `draft`;
  - выполнить реальный `health_check`;
  - только при `online` или `warning` завершить job как `success`;
  - если `available_for_new_devices=true`, сервер всё равно не должен попасть в пользовательский список до успешного health-check.
- На `failed`, `cancelled`, `success` очищать SSH secret.
- Audit log не должен содержать SSH secret, HMAC secret, client config или `vpn_url`.

Затронутые места:

- `backend/app/services/setup_job_service.py`
- `backend/app/workers/setup_worker.py`
- `backend/app/services/server_service.py`
- `backend/app/services/audit_service.py`
- `frontend/src/pages/admin/AdminSetupJobDetailView.vue`

Тесты:

- success flow.
- failed SSH/deploy flow.
- cancelled flow.
- audit redaction test.
- user-facing `/servers` не показывает draft/setup/offline серверы.

### 6. Frontend safety UX

Обновить UI, чтобы админ понимал разницу между ручным сервером и реальной установкой VPS.

Требования:

- На `/admin/setup-jobs/new` явно написать, что вводится SSH secret и он будет использован для установки агента.
- Добавить предупреждение: использовать одноразовый SSH key или временный пароль, после установки удалить доступ.
- Для `auth_method=ssh_key` лучше подсказать passphrase-less temporary key или support passphrase, если будет реализовано.
- Показывать, какой agent base URL будет настроен, какой allowlist будет применён.
- После success дать ссылку на созданный server node и подсказать запустить/посмотреть health-check.
- Не показывать secret обратно ни в каком виде.

Затронутые места:

- `frontend/src/pages/admin/AdminSetupJobCreateView.vue`
- `frontend/src/pages/admin/AdminSetupJobDetailView.vue`
- `frontend/src/pages/admin/AdminServerDetailView.vue`

Проверки:

- `npm run build`.
- Manual UI smoke: create setup job, observe status polling, success/fail state.

## Definition of Done

Claude должен открыть PR только когда выполнено:

- В production нельзя запуститься с fake agent transport.
- В production нельзя запуститься без настоящего `ENCRYPTION_KEY`.
- Setup runner может реально вызвать deploy script без shell и без утечки SSH secret в args/logs.
- Agent ставится как systemd service с HMAC и узким allowlist.
- Server node создаётся и становится доступным для новых устройств только после реального agent health-check.
- Все SSH secrets очищаются на terminal status.
- API responses, setup events и audit logs не содержат secrets.
- Backend tests зелёные.
- Agent Go tests зелёные.
- Frontend build зелёный.
- README обновлён с безопасным production flow.

## Команды проверки

```bash
cd backend
.venv/bin/pytest app/tests

cd ../agent
go test ./...

cd ../frontend
npm run build
```

## Вопросы перед реализацией, если потребуется

- Как backend будет видеть VPS agent: public IP, private network или VPN overlay?
- Какой IP/CIDR backend надо прописывать в `SETUP_AGENT_ALLOW_IPS`?
- Нужна ли поддержка SSH key passphrase в MVP?
- Должен ли setup runner устанавливать AWG с нуля или только агент поверх уже установленного AmneziaWG?
