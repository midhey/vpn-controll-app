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

Tooling decisions:

- Python 3.12+, `uv` for dependency management (`uv.lock` committed).
- `ruff` for lint and format.
- `pytest` + `pytest-asyncio`; API tests via `httpx.ASGITransport` against the app; agent calls always faked.
- `argon2-cffi` for password hashing, `cryptography` (Fernet) for secret encryption at rest.

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
GET    /health               no auth     -> 200
GET    /status               HMAC auth   -> 200
GET    /peers                HMAC auth   -> 200
POST   /peers                HMAC auth   -> 201 Created
DELETE /peers/{public_key}   HMAC auth   -> 200
```

Agent version currently returned by `/health`: `0.2.0`.

Contract facts the backend must respect:

- Signed endpoints cap the request body at 1 MiB.
- The agent decodes JSON with `DisallowUnknownFields`: any field other than the documented ones (or trailing JSON data) is a 400. `AgentClient` must serialize exactly the documented fields and nothing else.
- Agent errors always have this shape; parse it when mapping to domain errors:

```json
{
  "error": "invalid signature",
  "status": 401,
  "status_text": "Unauthorized"
}
```

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

Signing details that are easy to get wrong:

- `timestamp_rfc3339` is current UTC time in RFC3339. The agent rejects requests when `|agent_now - timestamp| > 60s` (default skew, not changed by the deploy script) with 401 `timestamp outside allowed skew`. Keep backend/VPS clocks NTP-synced and surface this specific 401 as a distinct, diagnosable error.
- `escaped_path_with_query` is the percent-encoded path exactly as sent on the wire (the agent verifies against Go `EscapedPath()` plus raw query). Compute the signature over the same encoded string `httpx` actually sends; never sign a decoded path.
- WireGuard public keys are standard base64 and may contain `+`, `/`, `=`. For `DELETE /peers/{public_key}` the key must be percent-encoded as a single path segment (`quote(key, safe="")`, so `/` -> `%2F`) and the signature computed over that encoded form.

Agent also enforces an IP allowlist and refuses to start when the allowlist is empty; the deploy default is `127.0.0.1,::1`. In production, either expose the agent only through a private network/VPN or combine a non-loopback `--listen` with a strict `--allow-ip` for the backend host (see setup worker section).

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

Current Go implementation reads `name`, `dns`, and `endpoint_host`. `metadata` is accepted by HTTP shape but not persisted by the agent, so reconciliation must key on `public_key` only; sending `backend_device_id` in `metadata` is still fine as forward compatibility.

`dns` is optional: when empty the agent falls back to `1.1.1.1`, `8.8.8.8`. Allowed fields are exactly `name`, `dns`, `endpoint_host`, `metadata` — anything else is a 400 (`DisallowUnknownFields`).

Success response is `201 Created`:

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

`public_key` must be percent-encoded as a single path segment (base64 keys contain `+`, `/`, `=`); the HMAC signature is computed over the encoded path.

Response:

```json
{
  "revoked": true,
  "public_key": "client-public-key"
}
```

### Agent GET /status

Returns diagnostics (`InspectResult` from `agent/internal/agent/service.go`):

```json
{
  "container": "amnezia-awg2",
  "container_running": true,
  "container_image": "...",
  "container_created": "...",
  "interface": "awg0",
  "runtime_interface": "awg0",
  "runtime_public_key": "...",
  "listen_port": "...",
  "config_path": "/opt/amnezia/awg/awg0.conf",
  "config_exists": true,
  "config_mode": "...",
  "config_size": 4096,
  "clients_table_path": "/opt/amnezia/awg/clientsTable",
  "clients_table_mode": "...",
  "peer_count_config": 3,
  "peer_count_runtime": 3,
  "warnings": []
}
```

`config_mode`, `config_size`, `clients_table_mode`, and `warnings` are omitted when empty.

The backend stores the whole payload in `server_nodes.last_status_payload` and derives `status`/`last_error` from `container_running`, config/runtime peer count mismatch, and `warnings`.

### Agent GET /peers

Returns merged peer info from `awg0.conf`, runtime `awg show`, and `clientsTable`:

```json
[
  {
    "public_key": "...",
    "name": "Alice iPhone",
    "allowed_ips_config": ["10.8.1.2/32"],
    "allowed_ips_runtime": ["10.8.1.2/32"],
    "in_config": true,
    "in_runtime": true,
    "in_clients_table": true,
    "endpoint": "198.51.100.7:54321",
    "latest_handshake": "1 minute, 3 seconds ago",
    "transfer_received": "1.2 MiB",
    "transfer_sent": "3.4 MiB",
    "user_data": {}
  }
]
```

`latest_handshake` and `transfer_*` are human-readable labels taken verbatim from `awg show` output, not machine timestamps — store them as labels (this is why `devices` uses `transfer_received_label`/`transfer_sent_label`; populate `last_handshake_at` only as best-effort parsing, nullable). Optional fields are omitted when empty.

Use it for reconciliation and device status sync keyed on `public_key`, not as the source of product truth.

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
- first admin is created by an idempotent bootstrap step (CLI command or startup hook) that reads `FIRST_ADMIN_LOGIN`/`FIRST_ADMIN_PASSWORD` and creates the admin only when no admin exists yet

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

All timestamps are `timestamptz` stored in UTC. Money amounts (`support_contributions.amount`, `monthly_cost_amount`, `reserve_amount`) are `numeric(10, 2)`.

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

Note: the `awg_*` and `clients_table_path` fields are deploy-time/informational metadata. The running agent reads its own settings from `/etc/vpn-agent/vpn-agent.env` on the node and does not accept them over HTTP; editing them in the backend does not reconfigure the node.

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

Decision for MVP: store `config`/`vpn_url` encrypted (Fernet with `ENCRYPTION_KEY`) with TTL from `ISSUE_RESULT_TTL_MINUTES` (default 15). The issue result may be read multiple times until `expires_at` — the same result backs the QR screen, copy, and download actions without re-provisioning. `consumed_at` records the first read for audit and does not block re-reads. After expiry the endpoint returns 404 with code `issue_result_expired`; the user must issue a new device config. Expired rows have their payload nulled/purged by periodic cleanup or lazily on access.

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
- `secret_encrypted` nullable — SSH key/password encrypted with `ENCRYPTION_KEY`; cleared once the job reaches a terminal status; never stored or logged in plaintext
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
- returns config/vpn_url while the issue result is unexpired; repeat reads within TTL are allowed
- sets `consumed_at` on first read (audit only, does not block re-reads)
- after `expires_at` returns 404 with code `issue_result_expired`

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
2. generate per-node credentials: `agent_key_id` (e.g. `backend-prod`) and a random secret of at least 32 bytes
3. run or orchestrate `agent/scripts/deploy-agent.sh` with explicit `--listen`, `--allow-ip`, `--endpoint-host`, `--hmac-key-id`, `--hmac-secret`
4. install systemd service with HMAC auth
5. create/update `server_nodes` (agent base URL derived from the `--listen` address/private network, secret stored encrypted)
6. call agent `/health`
7. call signed `/status`
8. mark server online or setup_failed; clear the stored SSH secret in both cases

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
- `--listen`
- `--allow-no-auth`

Backend must not use interactive flags (`--ask-password`) and must never use `--allow-no-auth`; it passes non-interactive inputs from encrypted secret handling.

Facts about the installed service the worker relies on:

- systemd unit name is `vpn-agent`; agent settings including the HMAC secret are written to root-only `/etc/vpn-agent/vpn-agent.env` and injected via `EnvironmentFile=` — the secret never appears in `ExecStart` or the process list.
- script defaults are `--listen 127.0.0.1:8090` and `--allow-ip 127.0.0.1,::1`: keeping them installs an agent the backend cannot reach. The worker must pass an explicit `--listen` (private/management address) and `--allow-ip` (backend address/CIDR, from `SETUP_BACKEND_ALLOW_IP`).

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
- timeouts: connect 3s; read 15s for health/status/peers; read 30s for issue/revoke (they run docker exec plus config sync on the node)
- HMAC sign signed endpoints with current UTC RFC3339 timestamp; sign the exact percent-encoded path+query that httpx sends
- percent-encode `public_key` as a single path segment in `DELETE /peers/{public_key}` (`quote(key, safe="")`)
- treat `201` as the success status for `POST /peers`
- never log `agent_secret`
- parse the agent error shape (`{"error", "status", "status_text"}`) and map to domain errors: network error/timeout/5xx -> `agent_unavailable`; 400/401/403/404/409 -> `agent_rejected` with the agent message preserved for admin diagnostics; surface the 401 skew case (`timestamp outside allowed skew`) explicitly
- store raw agent response in audit only after redacting sensitive fields; `config` and `vpn_url` are secrets and must never reach logs or audit

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
- `csrf_failed`
- `not_found`
- `validation_error`
- `device_limit_reached`
- `issue_result_expired`
- `server_unavailable`
- `agent_unavailable`
- `agent_rejected`
- `setup_job_failed`
- `secret_required`

## Security Requirements

- HttpOnly cookies for user sessions: `SameSite=Lax`, `Secure` outside local dev.
- CSRF: strict CORS allowlist from `CORS_ORIGINS`; on unsafe methods require a custom header (e.g. `X-Requested-With: XMLHttpRequest`) and validate `Origin` against the allowlist when present. The custom header forces a CORS preflight that cross-site forms cannot pass. Reject with 403 code `csrf_failed`.
- Passwords: argon2id via `argon2-cffi`; hashes only; never log passwords.
- Secret encryption at rest: Fernet from `cryptography`, key = `ENCRYPTION_KEY` (urlsafe base64, 32 bytes). Applies to `server_nodes.agent_secret_encrypted`, setup job SSH secrets, and `device_config_issues` payloads. Key rotation is out of MVP scope, but keep all encryption behind one helper module.
- Redact secrets from logs, error messages, audit metadata, and API responses.
- Do not store raw VPN client private config permanently by default; only the short-TTL encrypted issue result.
- Rate-limit login: e.g. 5+ failed attempts per login or per IP within 15 minutes -> 429 plus audit entry; an in-app counter is enough for MVP.
- Audit admin actions.
- Do not expose agent directly to browsers.
- Backend is the only caller of agent HTTP API.

## Testing Plan

Unit tests:

- password hashing/session creation
- role dependencies
- device limit enforcement
- support visibility rules
- HMAC signature generation, including escaped path with query and public keys containing `/`, `+`, `=`
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
ISSUE_RESULT_TTL_MINUTES=15
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
SETUP_AGENT_LISTEN=0.0.0.0:8090
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
