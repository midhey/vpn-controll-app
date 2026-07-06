# Backend Plan for Claude: Подсос VPN / vpn-control-app

This document is the implementation brief for the FastAPI backend.

The repository already contains a Go VPS agent in `agent/`. The backend must become the product/control-plane above that agent.

## Product Context

`Подсос VPN` is a private VPN panel for the owner, friends, and family.

It is not a commercial SaaS, not a public VPN, not a subscription/billing platform.

Money-related UX must be framed only as optional support for VPS costs:

- Good: `поддержка сервера`, `можно поддержать VPS`, `резерв сервера`.
- Bad: `оплата`, `платеж`, `касса`, `долг`, `подписка`, `тариф`, `просрочено`.

Users do not self-register. Only an admin creates users.

Some users are free/family users and must never see support reminders. Device limits are configurable per user, including unlimited access for admin/owner.

## Current Repository State

Existing code:

```text
agent/                 Go agent for local AmneziaWG operations on VPS nodes
vpn-control-app.pen    Pencil design
plan.md                older high-level plan, partially outdated terminology
```

The FastAPI backend does not exist yet. Build it as a new backend application without modifying the Go agent unless absolutely required.

Recommended initial structure:

```text
backend/
  app/
    main.py
    core/
      config.py
      security.py
      errors.py
      logging.py
    db/
      base.py
      session.py
      migrations/
    models/
    schemas/
    api/
      deps.py
      routes/
        auth.py
        me.py
        devices.py
        servers.py
        support.py
        admin_users.py
        admin_servers.py
        admin_setup_jobs.py
    services/
      auth_service.py
      user_service.py
      device_service.py
      server_service.py
      support_service.py
      agent_client.py
      setup_job_service.py
    workers/
      setup_worker.py
    tests/
  pyproject.toml
  alembic.ini
```

Use FastAPI with `APIRouter` modules, Pydantic request/response schemas, dependencies for auth/role checks, SQLAlchemy 2 async, Alembic, PostgreSQL, and `httpx.AsyncClient` for agent calls.

## Existing Go Agent Contract

The backend talks to the agent over HTTP.

Agent code is in:

```text
agent/internal/httpapi/server.go
agent/internal/httpapi/auth.go
agent/internal/agent/service.go
agent/README.md
```

Agent endpoints:

```text
GET    /health               no auth
GET    /status               HMAC auth
GET    /peers                HMAC auth
POST   /peers                HMAC auth
DELETE /peers/{public_key}   HMAC auth
```

Agent version currently returned by `/health`: `0.2.0`.

### Agent Auth

Signed endpoints require:

```text
X-Agent-Key-Id
X-Agent-Timestamp
X-Agent-Signature
```

Signature algorithm from `agent/internal/httpapi/auth.go`:

```text
body_hash = sha256(body)
payload = METHOD + "\n" + escaped_path_with_query + "\n" + timestamp_rfc3339 + "\n" + hex(body_hash)
signature = hex(hmac_sha256(secret, payload))
```

Backend must implement this exactly in `services/agent_client.py`.

Agent also enforces IP allowlist. In production, either expose the agent only through a private network/VPN or configure allowlist for the backend host.

### Agent POST /peers

Request:

```json
{
  "name": "Alice iPhone",
  "dns": ["1.1.1.1", "8.8.8.8"],
  "endpoint_host": "203.0.113.10",
  "metadata": {
    "backend_device_id": "..."
  }
}
```

Current Go implementation reads `name`, `dns`, and `endpoint_host`. `metadata` is accepted by HTTP shape but not persisted by the agent.

Response:

```json
{
  "public_key": "client-public-key",
  "client_ip": "10.8.1.2",
  "config": "[Interface]\n...",
  "vpn_url": "vpn://..."
}
```

Important security note: the agent returns the generated client config and `vpn_url` once. The backend should not store raw private config long-term by default.

### Agent DELETE /peers/{public_key}

Response:

```json
{
  "revoked": true,
  "public_key": "client-public-key"
}
```

### Agent GET /status

Returns diagnostics:

- container
- container_running
- runtime_interface
- listen_port
- config path/mode/size
- peer counts
- warnings

The backend should cache/display this as server health.

### Agent GET /peers

Returns merged peer info from:

- `awg0.conf`
- runtime `awg show`
- `clientsTable`

Use it for reconciliation and status, not as the source of product truth.

## Backend Responsibilities

The backend owns product state:

- auth/session handling
- users and roles
- admin-created accounts
- device limits
- server inventory
- server support prompts
- agent credentials and calls
- device issue/revoke workflows
- VPS setup jobs
- audit logs

The agent owns only local VPN node state.

## Roles and Permissions

Roles:

```text
admin
user
```

Admin can:

- create/edit/disable users
- set user device limits
- set user support visibility
- mark user as free/family/no-reminders
- view all users/devices/servers
- add/edit/remove server nodes
- start VPS setup jobs
- issue/revoke any user device
- view support history
- record support contributions manually
- view audit logs

User can:

- view own dashboard
- view own devices
- add own device if under limit
- revoke own device
- view own server support prompt only if enabled
- view own support history if enabled
- copy/download config or `vpn_url` immediately after issue

## Authentication

MVP should use server-side sessions with secure HttpOnly cookies.

Do not build public registration.

Login options for MVP:

- username/login + password
- admin creates initial user via seed/env/bootstrap command

Session model:

- store token hash, not raw token
- HttpOnly, Secure in production, SameSite=Lax
- sliding `last_seen_at`
- explicit logout

Password:

- use `argon2` or `bcrypt`
- never log password

## Database Model

Use UUID primary keys unless there is a strong reason not to.

Every table should have:

- `created_at`
- `updated_at` where mutable

Use enums where appropriate, but keep migrations manageable.

### users

Fields:

- `id`
- `login` unique, required
- `telegram_username` nullable
- `display_name` required
- `role`: `admin | user`
- `password_hash`
- `is_active`
- `device_limit` integer nullable
- `device_limit_unlimited` boolean
- `show_server_support` boolean
- `free_access` boolean
- `note` nullable
- `created_by_user_id` nullable FK users
- `created_at`
- `updated_at`

Rules:

- `free_access=true` implies no support reminders by default.
- Admin can still manually set `show_server_support=false`.
- Admin/owner can have `device_limit_unlimited=true`.

### sessions

Fields:

- `id`
- `user_id`
- `token_hash`
- `expires_at`
- `created_at`
- `last_seen_at`
- `user_agent`
- `ip_address`
- `revoked_at`

### server_nodes

Represents a VPS/VPN node.

Fields:

- `id`
- `name`
- `public_host`
- `public_port` nullable
- `region_note` nullable
- `provider` nullable
- `agent_base_url`
- `agent_key_id`
- `agent_secret_encrypted` or secret reference
- `agent_allowed_ip_note` nullable
- `status`: `draft | setup_pending | setup_running | online | warning | offline | disabled | setup_failed`
- `last_seen_at`
- `last_error`
- `last_status_payload` JSONB nullable
- `awg_container_name` default `amnezia-awg2`
- `awg_interface` default `awg0`
- `awg_config_path` default `/opt/amnezia/awg/awg0.conf`
- `clients_table_path` default `/opt/amnezia/awg/clientsTable`
- `is_available_for_new_devices` boolean
- `created_by_user_id`
- `created_at`
- `updated_at`

### devices

Represents a user's issued VPN config/device.

Fields:

- `id`
- `user_id`
- `server_node_id`
- `name`
- `public_key`
- `client_ip`
- `status`: `provisioning | active | revoked | failed`
- `last_config_issued_at`
- `last_handshake_at` nullable
- `transfer_received_label` nullable
- `transfer_sent_label` nullable
- `last_agent_sync_at` nullable
- `revoked_at` nullable
- `failure_message` nullable
- `created_at`
- `updated_at`

Do not store raw client private key/config by default.

For UX, create a one-time issue result:

### device_config_issues

Fields:

- `id`
- `device_id`
- `issued_to_user_id`
- `config_encrypted` nullable
- `vpn_url_encrypted` nullable
- `expires_at`
- `consumed_at` nullable
- `created_at`

MVP option: store encrypted config for a short TTL such as 15 minutes so the frontend can show QR/download after creation. After TTL, config is not available; user must regenerate/reissue.

### support_contributions

Friendly server support history. Not payments.

Fields:

- `id`
- `user_id`
- `amount`
- `currency` default `RUB`
- `period_label` nullable, e.g. `июль 2026`
- `comment` nullable
- `recorded_by_user_id`
- `recorded_at`
- `created_at`

No required due date. No debt/overdue logic.

### server_support_settings

Global support/contact settings.

Fields:

- `id`
- `title`
- `description`
- `sbp_phone`
- `bank_name`
- `extra_contact`
- `monthly_cost_amount` nullable
- `reserve_amount` nullable
- `is_enabled`
- `updated_by_user_id`
- `updated_at`

This can be singleton for MVP.

### setup_jobs

Represents adding a VPS through SSH/setup script.

Fields:

- `id`
- `server_node_id` nullable until server row created, or create draft server first
- `created_by_user_id`
- `status`: `draft | queued | checking_ssh | installing_agent | installing_vpn | verifying | success | failed | cancelled`
- `server_name`
- `host`
- `ssh_port`
- `ssh_username`
- `auth_method`: `ssh_key | password`
- `secret_ref` nullable, never store raw secret in plaintext
- `region_note`
- `install_awg` boolean
- `available_for_new_devices` boolean
- `verify_before_install` boolean
- `current_step`
- `error_message`
- `result_payload` JSONB nullable
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

### setup_job_events

Fields:

- `id`
- `setup_job_id`
- `level`: `info | warning | error`
- `step`
- `message`
- `metadata` JSONB nullable
- `created_at`

### audit_logs

Fields:

- `id`
- `actor_user_id`
- `action`
- `target_type`
- `target_id`
- `metadata` JSONB nullable
- `ip_address`
- `user_agent`
- `created_at`

Log at least:

- login success/failure
- user create/update/disable
- device issue/revoke
- server create/update/disable
- agent call failure
- setup job start/success/failure
- support contribution record/delete

## API Design

Prefix all API routes with:

```text
/api/v1
```

Use JSON only.

Use response models for every endpoint.

Use `APIRouter` by domain:

```text
/auth
/me
/devices
/servers
/support
/admin/users
/admin/servers
/admin/setup-jobs
/admin/audit-logs
```

### Auth API

```text
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/session
```

`POST /auth/login` request:

```json
{
  "login": "alexey",
  "password": "..."
}
```

Response:

```json
{
  "user": {
    "id": "...",
    "login": "alexey",
    "display_name": "Алексей",
    "role": "admin"
  }
}
```

### Current User API

```text
GET /api/v1/me
GET /api/v1/me/dashboard
```

Dashboard response should contain enough data for `Mobile/Home/AllOk`, `SupportHint`, and `DeviceLimit`:

```json
{
  "user": {},
  "access": {
    "is_active": true,
    "message": "Твой доступ активен"
  },
  "device_limit": {
    "used": 2,
    "limit": 5,
    "unlimited": false
  },
  "support": {
    "visible": true,
    "hint": "Можно поддержать сервер"
  },
  "recent_devices": []
}
```

### User Devices API

```text
GET    /api/v1/devices
POST   /api/v1/devices
GET    /api/v1/devices/{device_id}
DELETE /api/v1/devices/{device_id}
GET    /api/v1/devices/{device_id}/issue-result
```

`POST /devices` request:

```json
{
  "name": "iPhone 15",
  "server_node_id": "optional-admin-selected-or-auto"
}
```

Rules:

- enforce active user
- enforce device limit before calling agent
- select available server if not provided
- create `devices` row as `provisioning`
- call agent `POST /peers`
- store public key/client IP
- set device `active`
- create short-lived `device_config_issues`
- audit log

Failure:

- set device `failed`
- save failure message
- return a user-safe error
- do not leak agent secret/internal stack

`GET /devices/{device_id}/issue-result`:

- only owner or admin
- returns config/vpn_url only while issue result is unexpired
- mark `consumed_at` if desired

Response:

```json
{
  "device_id": "...",
  "config": "[Interface]\n...",
  "vpn_url": "vpn://...",
  "expires_at": "..."
}
```

`DELETE /devices/{device_id}`:

- call agent `DELETE /peers/{public_key}` if device is active
- mark revoked
- audit

### Servers API for Users

```text
GET /api/v1/servers
GET /api/v1/servers/{server_id}
```

Only return servers available to the user.

### Support API

```text
GET /api/v1/support
GET /api/v1/support/history
```

If `user.show_server_support=false` or `free_access=true`, return:

```json
{
  "visible": false
}
```

Otherwise return support copy/contact/settings/history.

No user endpoint for "pay" in MVP. Admin records support manually.

### Admin Users API

```text
GET    /api/v1/admin/users
POST   /api/v1/admin/users
GET    /api/v1/admin/users/{user_id}
PATCH  /api/v1/admin/users/{user_id}
POST   /api/v1/admin/users/{user_id}/reset-password
POST   /api/v1/admin/users/{user_id}/disable
POST   /api/v1/admin/users/{user_id}/enable
GET    /api/v1/admin/users/{user_id}/devices
POST   /api/v1/admin/users/{user_id}/support-contributions
```

Create user request:

```json
{
  "display_name": "Дмитрий",
  "login": "dima_c",
  "telegram_username": "@dima_c",
  "role": "user",
  "password": "temporary-password",
  "device_limit": 5,
  "device_limit_unlimited": false,
  "show_server_support": true,
  "free_access": false,
  "note": "Заметка"
}
```

### Admin Servers API

```text
GET    /api/v1/admin/servers
POST   /api/v1/admin/servers
GET    /api/v1/admin/servers/{server_id}
PATCH  /api/v1/admin/servers/{server_id}
POST   /api/v1/admin/servers/{server_id}/health-check
GET    /api/v1/admin/servers/{server_id}/peers
POST   /api/v1/admin/servers/{server_id}/disable
POST   /api/v1/admin/servers/{server_id}/enable
```

`health-check` calls:

- `GET /health`
- signed `GET /status`

Update:

- `last_seen_at`
- `last_status_payload`
- `status`
- `last_error`

### Admin VPS Setup Jobs API

This powers the `Добавить VPS` UI from the design.

```text
POST /api/v1/admin/setup-jobs
GET  /api/v1/admin/setup-jobs
GET  /api/v1/admin/setup-jobs/{job_id}
POST /api/v1/admin/setup-jobs/{job_id}/start
POST /api/v1/admin/setup-jobs/{job_id}/cancel
GET  /api/v1/admin/setup-jobs/{job_id}/events
```

Create/start can be combined for MVP:

```text
POST /api/v1/admin/setup-jobs
```

Request:

```json
{
  "server_name": "Helsinki-VPS-2",
  "host": "95.217.10.42",
  "ssh_port": 22,
  "ssh_username": "root",
  "auth_method": "ssh_key",
  "secret": "PRIVATE KEY OR PASSWORD",
  "region_note": "Финляндия, Hetzner, новый узел",
  "install_awg": true,
  "available_for_new_devices": true,
  "verify_before_install": true
}
```

Security:

- do not persist raw `secret`
- encrypt it immediately or store in a short-lived secret store
- redact it from logs, errors, audit metadata, and API responses

Response:

```json
{
  "id": "...",
  "status": "queued",
  "current_step": "queued"
}
```

Job response:

```json
{
  "id": "...",
  "status": "installing_agent",
  "current_step": "Устанавливаем агент",
  "server_name": "Helsinki-VPS-2",
  "host": "95.217.10.42",
  "created_at": "...",
  "started_at": "..."
}
```

Events response:

```json
[
  {
    "level": "info",
    "step": "checking_ssh",
    "message": "SSH подключение установлено",
    "created_at": "..."
  }
]
```

#### Setup Job Worker

Do not run a real VPS install inside the HTTP request.

Use one of:

- MVP: a simple async worker process polling `setup_jobs` from PostgreSQL
- Later: Redis/RQ/Arq/Celery

The UI needs statuses:

```text
checking_ssh
installing_agent
installing_vpn
verifying
success
failed
```

Backend worker responsibilities:

1. validate SSH connection
2. run or orchestrate `agent/scripts/deploy-agent.sh`
3. install systemd service with HMAC auth
4. create/update `server_nodes`
5. call agent `/health`
6. call signed `/status`
7. mark server online or setup_failed

For first backend MVP, it is acceptable to implement this as a stubbed worker that simulates the steps and creates a draft/online server row. Keep the service interface ready for the real script.

Real script boundary:

```text
agent/scripts/deploy-agent.sh
```

Script supports:

- `--user`
- `--host`
- `--ssh-port`
- `--identity-file`
- `--password`
- `--ask-password`
- `--install-service`
- `--endpoint-host`
- `--hmac-key-id`
- `--hmac-secret`
- `--allow-ip`

Backend should not use interactive flags. It must pass non-interactive inputs from encrypted secret handling.

## Agent Client Service

Implement `AgentClient` with:

```python
health(server_node) -> AgentHealth
status(server_node) -> AgentStatus
peers(server_node) -> list[AgentPeer]
issue_peer(server_node, name, dns, endpoint_host, metadata) -> AgentIssueResult
revoke_peer(server_node, public_key) -> AgentRevokeResult
```

Requirements:

- use `httpx.AsyncClient`
- short timeouts, e.g. connect 3s/read 15s for status, longer for issue/revoke if needed
- HMAC sign signed endpoints
- never log `agent_secret`
- map agent errors to domain errors
- store raw agent response in audit only after redacting sensitive fields

## Backend Service Rules

### Device Issue

Algorithm:

1. load current user
2. check active
3. count active devices
4. enforce user limit unless unlimited
5. choose server node:
   - active
   - available for new devices
   - online or not known-offline
6. create device row `provisioning`
7. call agent `POST /peers`
8. update device row `active`
9. create short-lived config issue
10. audit log
11. return device + issue result

### Device Revoke

Algorithm:

1. check ownership/admin
2. if already revoked, return idempotent success
3. call agent delete if public key exists
4. mark revoked
5. audit log

### Server Health Sync

Algorithm:

1. call `/health`
2. call signed `/status`
3. update status fields
4. store warnings
5. audit only on meaningful status transition or failure

### Support

No automatic disabling. No debt logic.

Support prompt visibility:

```text
visible = global_support_enabled
          and user.show_server_support
          and not user.free_access
```

## Frontend-Driven Screens to Support

The design currently includes:

- Mobile home all-ok
- Mobile home support hint
- Mobile home device limit
- Devices list/empty/add/QR/success
- Server support disabled/enabled
- More instructions/support/security
- Admin overview
- Admin add member
- Admin user details
- Admin add VPS form
- Admin add VPS checking/installing/success/error states
- Desktop user dashboard
- Desktop admin overview
- Desktop admin add VPS modal
- UI kit/states

Backend endpoints should be shaped so these screens can be implemented without frontend-only fake logic.

## Error Handling

Use consistent error shape:

```json
{
  "error": {
    "code": "device_limit_reached",
    "message": "Лимит устройств закончился",
    "details": {}
  }
}
```

Common codes:

- `unauthorized`
- `forbidden`
- `not_found`
- `validation_error`
- `device_limit_reached`
- `server_unavailable`
- `agent_unavailable`
- `agent_rejected`
- `setup_job_failed`
- `secret_required`

## Security Requirements

- HttpOnly cookies for user sessions.
- CSRF protection if cookie auth is used for unsafe methods.
- Password hashes only.
- Encrypt agent secrets and setup SSH secrets.
- Redact secrets from logs.
- Do not store raw VPN client private config permanently by default.
- Rate-limit login.
- Audit admin actions.
- Do not expose agent directly to browsers.
- Backend is the only caller of agent HTTP API.

## Testing Plan

Unit tests:

- password hashing/session creation
- role dependencies
- device limit enforcement
- support visibility rules
- HMAC signature generation
- agent client request paths/signing
- device issue success/failure state transitions
- setup job state transitions

Integration tests:

- auth login/session/logout
- admin creates user
- user issues device with fake agent
- device limit blocks extra device
- revoke device with fake agent
- admin creates setup job
- setup worker success/failure with fake runner

Use fake agent responses; do not require a real VPS in backend tests.

## Implementation Phases

### Phase 1: Backend Skeleton

- Create `backend/`.
- Configure FastAPI app.
- Configure settings/env.
- Configure async SQLAlchemy.
- Configure Alembic.
- Add health endpoint.
- Add test setup.

### Phase 2: Auth and Users

- Users model.
- Sessions model.
- Password hashing.
- Login/logout/session endpoints.
- Admin user CRUD.
- Role dependencies.
- Seed/bootstrap first admin.

### Phase 3: Servers and Agent Client

- Server node model.
- Agent HMAC client.
- Admin server CRUD.
- Health check endpoint.
- Fake agent tests.

### Phase 4: Devices

- Device model.
- Device issue/revoke endpoints.
- Short-lived config issue model.
- Device limits.
- User dashboard endpoint.

### Phase 5: Support

- Support settings.
- Support history/contributions.
- Support visibility rules.
- Admin manual contribution recording.

### Phase 6: VPS Setup Jobs

- Setup job model/events.
- API for create/start/status/events.
- Worker abstraction.
- Stub runner first.
- Real deploy script runner later.

### Phase 7: Hardening

- CSRF.
- Rate limiting.
- Secret encryption.
- Audit coverage.
- Reconciliation job: backend devices vs agent peers.
- Docker Compose for local dev.

## Non-Goals for MVP

- Public registration.
- Real billing.
- Automatic VPN cutoff for non-support.
- Multiple organizations/tenants.
- Complex server pools unless needed by frontend.
- Native mobile app.

## Environment Variables Draft

```text
APP_ENV=local
APP_SECRET_KEY=...
DATABASE_URL=postgresql+asyncpg://...
SESSION_COOKIE_NAME=vca_session
SESSION_TTL_DAYS=30
CORS_ORIGINS=http://localhost:5173
ENCRYPTION_KEY=...
FIRST_ADMIN_LOGIN=midhey
FIRST_ADMIN_PASSWORD=...
```

For setup worker:

```text
SETUP_WORKER_ENABLED=true
SETUP_DEPLOY_SCRIPT_PATH=../agent/scripts/deploy-agent.sh
SETUP_BACKEND_ALLOW_IP=...
```

## Notes for Claude

- Preserve Russian product copy and friendly tone.
- Avoid SaaS/payment terminology in model/API names where possible.
- Prefer `support_contributions` over `payments`.
- Prefer `server_nodes` over vague `servers` internally if that prevents confusion.
- Keep agent-specific code isolated in `AgentClient`.
- Keep business logic in services, not routers.
- Every endpoint should have Pydantic request/response schemas.
- Do not call the Go agent from tests directly; use fakes/mocks.
- Do not implement frontend in this task unless explicitly asked.
