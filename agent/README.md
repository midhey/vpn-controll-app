# vpn-agent

`vpn-agent` - Go CLI/HTTP агент для управления peer-ами AmneziaWG на VPS с контейнером `amnezia-awg2`.

Агент работает через Docker как через единственную границу доступа: он не требует, чтобы `/opt/amnezia/awg` был смонтирован на хост, и читает/пишет файлы внутри контейнера через `docker exec`.

Текущий фокус агента:

- безопасно инспектировать состояние AmneziaWG;
- показывать peer-ы из трех источников: `awg0.conf`, runtime `awg show`, `clientsTable`;
- выпускать нового клиента с записью в `awg0.conf` и `clientsTable`;
- удалять клиента по public key;
- возвращать два формата клиентского конфига:
  - нативный AWG/WireGuard-style config;
  - `vpn://...` ссылку для импорта в Amnezia VPN client;
- опционально поднимать локальный HTTP API с HMAC-подписью.

## Статус

Это MVP агента для обновленного `amnezia-awg2`.

Он намеренно не решает задачи backend-пользователей, платежей, пулов тарифов, подписок, биллинга, панели администратора и публичного API. Эти слои должны вызывать агент как низкоуровневый control-plane компонент.

## Требования

На хосте, где запускается агент:

- Linux amd64 для production/VPS smoke test;
- Docker CLI;
- доступ пользователя агента к Docker;
- контейнер `amnezia-awg2`;
- внутри контейнера должны быть доступны:
  - `awg`;
  - `awg-quick`;
  - `bash`;
  - `sh`;
  - `stat`, `cat`, `chmod`, `mv`, `cp`, `sync`.

По умолчанию агент ожидает:

| Параметр | Значение |
| --- | --- |
| Docker container | `amnezia-awg2` |
| AWG interface | `awg0` |
| Config path | `/opt/amnezia/awg/awg0.conf` |
| clientsTable path | `/opt/amnezia/awg/clientsTable` |
| Host lock path | `/var/lock/vpn-agent.lock` |
| Server public key path | рядом с config: `wireguard_server_public_key.key` |
| Preshared key path | рядом с config: `wireguard_psk.key` |

Если `--config-path` указывает не в `/opt/amnezia/awg`, пути для server public key и PSK вычисляются от директории этого config path.

## Структура исходников

```text
agent/
  cmd/vpn-agent/main.go          # CLI entrypoint
  internal/agent/                # сервисный слой, Docker boundary, lock, transactions
  internal/awg/                  # парсинг/рендер AWG config, clientsTable, runtime, vpn://
  internal/cli/                  # команды и flags
  internal/httpapi/              # HTTP API и HMAC auth
  go.mod
```

## Сборка

Локальная сборка под текущую платформу:

```bash
cd agent
go build ./cmd/vpn-agent
```

Сборка Linux amd64 binary для VPS:

```bash
cd agent
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o /tmp/vpn-agent ./cmd/vpn-agent
```

Если sandbox или окружение не позволяет писать в стандартный Go build cache, укажи `GOCACHE`:

```bash
GOCACHE=$(pwd)/.gocache go test ./...
```

Под Windows пакет собирается и тесты проходят, но host lock реализован только для unix: mutating-команды на Windows-хосте вернут ошибку. Основной путь для production - кросс-сборка `GOOS=linux`.

## Deploy на VPS

Основной способ установки - CLI-скрипт:

```bash
agent/scripts/deploy-agent.sh --user root --host 203.0.113.10
```

Скрипт делает полный базовый deploy:

1. собирает Linux binary из локальных исходников;
2. копирует binary на сервер по SSH/SCP;
3. устанавливает его в `/usr/local/bin/vpn-agent`;
4. проверяет, что на сервере есть Docker;
5. запускает удаленный `vpn-agent inspect`.

### Deploy по SSH key

Если на машине, с которой запускается deploy, уже есть доступ по SSH key:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 203.0.113.10
```

Если нужен конкретный key:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 203.0.113.10 \
  --identity-file ~/.ssh/id_ed25519
```

### Deploy по паролю

Парольный режим использует стандартный механизм OpenSSH `SSH_ASKPASS`.
Дополнительная утилита `sshpass` не нужна; временный helper удаляется после команды.

С prompt:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 203.0.113.10 \
  --ask-password
```

С передачей пароля аргументом:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 203.0.113.10 \
  --password 'ssh-password'
```

Передавать пароль аргументом удобно для одноразовой автоматизации, но это хуже с точки зрения безопасности: пароль может попасть в shell history или список процессов. Для ручного запуска предпочтительнее `--ask-password`.

Парольный режим несовместим с `--identity-file`: он отключает pubkey authentication, поэтому скрипт отклонит такую комбинацию.

Первое подключение к новому хосту принимает его SSH host key автоматически (`StrictHostKeyChecking=accept-new`, модель trust-on-first-use). Если это неприемлемо, добавь host key в `known_hosts` заранее.

### Deploy под non-root пользователем

Если SSH user не `root`, скрипт по умолчанию использует `sudo` для установки в `/usr/local/bin` и `/etc/systemd`.

Пример с passwordless sudo:

```bash
agent/scripts/deploy-agent.sh \
  --user ubuntu \
  --host 203.0.113.10 \
  --identity-file ~/.ssh/id_ed25519
```

Если `sudo` требует пароль:

```bash
agent/scripts/deploy-agent.sh \
  --user ubuntu \
  --host 203.0.113.10 \
  --ask-password \
  --reuse-password-for-sudo
```

Или отдельный sudo password:

```bash
agent/scripts/deploy-agent.sh \
  --user ubuntu \
  --host 203.0.113.10 \
  --identity-file ~/.ssh/id_ed25519 \
  --ask-sudo-password
```

Отключить sudo можно явно:

```bash
agent/scripts/deploy-agent.sh \
  --user deploy \
  --host 203.0.113.10 \
  --no-sudo \
  --remote-path /home/deploy/bin/vpn-agent
```

### Deploy с systemd service

По умолчанию скрипт ставит только binary. Чтобы дополнительно поднять `vpn-agent serve` как systemd service:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 203.0.113.10 \
  --install-service \
  --endpoint-host 203.0.113.10 \
  --hmac-key-id backend \
  --hmac-secret 'change-me'
```

Будут созданы:

```text
/usr/local/bin/vpn-agent
/etc/vpn-agent/vpn-agent.env
/etc/systemd/system/vpn-agent.service
```

HMAC key id и secret попадают только в env-файл (mode `600`) и читаются агентом из переменных окружения `VPN_AGENT_KEY_ID`/`VPN_AGENT_SECRET`; в командную строку процесса (`/proc/<pid>/cmdline`) они не передаются. Локальный temporary env создаётся сразу с mode `0600`; remote artifacts размещаются в уникальном каталоге mode `0700`, а remote env также имеет `0600`. Они удаляются через trap при success, error и сигналах `HUP`/`INT`/`TERM`. `--keep-artifact` никогда не сохраняет secret env-файл.

Для автоматизации не передавайте секреты в аргументах процесса. Скрипт умеет
прочитать их из уже заданных environment variables:

```bash
VPN_AGENT_DEPLOY_SSH_PASSWORD='temporary-password' \
VPN_AGENT_DEPLOY_HMAC_SECRET='generated-hmac-secret' \
agent/scripts/deploy-agent.sh --user root --host 203.0.113.10 \
  --password-env VPN_AGENT_DEPLOY_SSH_PASSWORD \
  --install-service --hmac-key-id backend \
  --hmac-secret-env VPN_AGENT_DEPLOY_HMAC_SECRET \
  --allow-ip 10.0.0.5
```

Не используйте `0.0.0.0/0` для `--allow-ip`: firewall VPS также должен
разрешать порт агента только с IP/CIDR backend-а или private network.

Service слушает `127.0.0.1:8090` по умолчанию. Изменить:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 203.0.113.10 \
  --install-service \
  --listen 127.0.0.1:9090 \
  --hmac-key-id backend \
  --hmac-secret 'change-me'
```

Если HMAC secret не задан, service install требует явного `--allow-no-auth`:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 203.0.113.10 \
  --install-service \
  --allow-no-auth
```

Это сделано специально, чтобы случайно не поднять unsigned HTTP API.

### Deploy script options

Посмотреть все параметры:

```bash
agent/scripts/deploy-agent.sh --help
```

Ключевые параметры:

| Flag | Default | Описание |
| --- | --- | --- |
| `--user` | required | SSH username |
| `--host` | required | SSH host/IP |
| `--password` | empty | SSH password через временный `SSH_ASKPASS` helper |
| `--ask-password` | `false` | спросить SSH password интерактивно |
| `--identity-file` | empty | SSH key path |
| `--ssh-port` | `22` | SSH port |
| `--sudo` | auto for non-root | использовать sudo |
| `--no-sudo` | auto for root | не использовать sudo |
| `--sudo-password` | empty | password для `sudo -S` |
| `--ask-sudo-password` | `false` | спросить sudo password |
| `--reuse-password-for-sudo` | `false` | использовать SSH password как sudo password |
| `--remote-path` | `/usr/local/bin/vpn-agent` | куда установить binary |
| `--remote-tmp-dir` | `/tmp` | временная директория на сервере |
| `--arch` | `amd64` | target `GOARCH` |
| `--binary` | empty | загрузить готовый binary вместо сборки |
| `--skip-build` | `false` | не собирать, требует `--binary` |
| `--skip-inspect` | `false` | не запускать verify через `inspect` |
| `--preflight-only` | `false` | проверить реальный SSH-доступ без загрузки файлов |
| `--inspect-only` | `false` | выполнить inspect уже установленным агентом без сборки/загрузки |
| `--keep-artifact` | `false` | не удалять локальный build artifact |
| `--verbose` | `false` | печатать выполняемые команды |
| `--endpoint-host` | значение `--host` | публичный endpoint для клиентских конфигов |
| `--install-service` | `false` | установить systemd service |
| `--service-name` | `vpn-agent` | имя systemd service |
| `--listen` | `127.0.0.1:8090` | listen address для HTTP API |
| `--hmac-key-id` | empty | HTTP HMAC key id |
| `--hmac-secret` | empty | HTTP HMAC secret |
| `--password-env` | empty | имя environment variable с SSH password |
| `--hmac-secret-env` | empty | имя environment variable с HMAC secret |
| `--allow-ip` | `127.0.0.1,::1` | allowlist для HTTP API |
| `--allow-no-auth` | `false` | разрешить HTTP без подписи, только если secret пустой |

Username проверяется по строгому формату, а `ssh`/`scp` получают username и host
раздельно с явным завершением списка опций. Это не позволяет превратить значения
из setup API в локальные SSH options.

Если `--endpoint-host` не передан, deploy script использует значение `--host`. Для публичного VPN endpoint это удобно, но если SSH идет через внутренний адрес, передай публичный endpoint явно:

```bash
agent/scripts/deploy-agent.sh \
  --user root \
  --host 10.0.0.10 \
  --endpoint-host vpn.example.com
```

### Manual install

Если deploy script не подходит, можно поставить binary вручную.

Пример копирования бинаря:

```bash
scp /tmp/vpn-agent root@203.0.113.10:/usr/local/bin/vpn-agent
ssh root@203.0.113.10 'chmod 0755 /usr/local/bin/vpn-agent'
```

Быстрая проверка:

```bash
ssh root@203.0.113.10 '/usr/local/bin/vpn-agent inspect'
```

## CLI

Общий формат:

```bash
vpn-agent <command> [flags]
```

Команды:

```text
inspect
peers
issue --name NAME --endpoint-host HOST
revoke --public-key KEY
serve --hmac-key-id KEY_ID --hmac-secret SECRET
```

### Общие flags

Эти flags доступны для всех команд:

| Flag | Default | Описание |
| --- | --- | --- |
| `--container` | `amnezia-awg2` | Docker container с AmneziaWG |
| `--interface` | `awg0` | AWG interface для `awg show` и `syncconf` |
| `--config-path` | `/opt/amnezia/awg/awg0.conf` | Путь к config внутри контейнера |
| `--clients-table-path` | `/opt/amnezia/awg/clientsTable` | Путь к `clientsTable` внутри контейнера |
| `--lock-path` | `/var/lock/vpn-agent.lock` | Host lock file для mutating operations |
| `--endpoint-host` | empty | Публичный host/IP для generated client configs |
| `--json` | `false` | Машиночитаемый JSON output (для `serve` игнорируется) |

`--endpoint-host` можно заменить переменной окружения:

```bash
export VPN_AGENT_ENDPOINT_HOST=203.0.113.10
```

Для `issue` endpoint обязателен: либо `--endpoint-host`, либо `VPN_AGENT_ENDPOINT_HOST`.

### Exit codes

| Код | Значение |
| --- | --- |
| `0` | Успех |
| `1` | Runtime/operation error |
| `2` | Ошибка CLI usage или unknown command |

## `inspect`

Проверяет контейнер, runtime interface, config-файл и число peer-ов.

```bash
vpn-agent inspect
```

JSON:

```bash
vpn-agent inspect --json
```

Пример human-readable output:

```text
container: amnezia-awg2
container running: true
container image: ...
runtime interface: awg0
listen port: 49351
config: /opt/amnezia/awg/awg0.conf mode=600 size=1234
clientsTable: /opt/amnezia/awg/clientsTable mode=600
peers: config=2 runtime=2
```

JSON schema по текущей реализации:

```json
{
  "container": "amnezia-awg2",
  "container_running": true,
  "container_image": "image-name",
  "container_created": "2026-07-01T...",
  "interface": "awg0",
  "runtime_interface": "awg0",
  "runtime_public_key": "server-public-key",
  "listen_port": "49351",
  "config_path": "/opt/amnezia/awg/awg0.conf",
  "config_exists": true,
  "config_mode": "600",
  "config_size": 1234,
  "clients_table_path": "/opt/amnezia/awg/clientsTable",
  "clients_table_mode": "600",
  "peer_count_config": 2,
  "peer_count_runtime": 2,
  "warnings": []
}
```

Warnings появляются, если:

- `awg0.conf` отсутствует (тогда `config_exists=false`, `peer_count_config=0`);
- mode `awg0.conf` не `600`;
- mode `clientsTable` не `600`;
- runtime interface отличается от ожидаемого `--interface`.

Отсутствующий config - не ошибка для `inspect`: команда остаётся диагностической и возвращает состояние с warning.

## `peers`

Объединяет peer-ы из трех источников:

1. `awg0.conf`;
2. `awg show <interface>`;
3. `clientsTable`.

```bash
vpn-agent peers
```

JSON:

```bash
vpn-agent peers --json
```

Пример:

```json
[
  {
    "public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "name": "Admin laptop",
    "allowed_ips_config": ["10.8.1.1/32"],
    "allowed_ips_runtime": ["10.8.1.1/32"],
    "in_config": true,
    "in_runtime": true,
    "in_clients_table": true,
    "endpoint": "198.51.100.20:60581",
    "latest_handshake": "55 minutes, 52 seconds ago",
    "transfer_received": "26.80 KiB",
    "transfer_sent": "79.70 KiB",
    "user_data": {
      "clientName": "Admin laptop",
      "creationDate": "Wed Jul 1 20:10:19 2026"
    }
  }
]
```

Сортировка:

- сначала по первому IPv4 из `AllowedIPs`;
- если IP не удается извлечь, по `public_key`.

Это удобно для поиска расхождений:

- `in_config=true`, `in_runtime=false`: peer есть в файле, но не применен;
- `in_runtime=true`, `in_config=false`: runtime отличается от файла;
- `in_clients_table=false`: peer рабочий, но не отображается как клиент Amnezia user table.

## `issue`

Создает нового peer-а.

```bash
vpn-agent issue --name "Alice MacBook" --endpoint-host 203.0.113.10
```

С DNS:

```bash
vpn-agent issue \
  --name "Alice MacBook" \
  --endpoint-host 203.0.113.10 \
  --dns "1.1.1.1,8.8.8.8"
```

JSON:

```bash
vpn-agent issue \
  --name "Alice MacBook" \
  --endpoint-host 203.0.113.10 \
  --json
```

Human-readable output содержит:

- `public_key`;
- `client_ip`;
- `vpn_url`;
- нативный AWG config.

JSON response:

```json
{
  "public_key": "client-public-key",
  "client_ip": "10.8.1.2",
  "config": "[Interface]\n...",
  "vpn_url": "vpn://..."
}
```

### Что делает `issue`

1. Проверяет, что `--name` не пустой.
2. Определяет endpoint host:
   - `IssueRequest.EndpointHost` для HTTP;
   - `--endpoint-host` для CLI;
   - `VPN_AGENT_ENDPOINT_HOST`;
   - иначе ошибка.
3. Берет host lock через `flock` (non-blocking retry, до 10 секунд; если lock занят - ошибка).
4. Читает текущее состояние:
   - `awg0.conf`;
   - `clientsTable`;
   - `awg show awg0`.
5. Парсит и валидирует config.
6. Генерирует private key внутри контейнера:

   ```bash
   docker exec amnezia-awg2 awg genkey
   ```

7. Получает public key внутри контейнера:

   ```bash
   docker exec -i amnezia-awg2 awg pubkey
   ```

8. Проверяет, что public key не дублируется.
9. Выделяет первый свободный IPv4 `/32` из subnet server interface, учитывая peer-ы из config **и** из runtime.
10. Читает server public key и PSK из файлов рядом с config.
11. Добавляет `[Peer]` в config.
12. Добавляет/обновляет запись в `clientsTable`.
13. Рендерит:
    - нативный client config;
    - Amnezia `vpn://` share URI.
14. Создает backup обоих файлов внутри контейнера.
15. Пишет новые файлы atomically через temp file + `mv`.
16. Выставляет mode `600`.
17. Выполняет:

    ```bash
    awg syncconf awg0 <(awg-quick strip /opt/amnezia/awg/awg0.conf)
    ```

18. Проверяет через `awg show`, что peer появился в runtime.
19. При ошибке после backup восстанавливает оба файла и повторно запускает `syncconf`.

### Выделение IP

Агент использует IPv4 subnet из `[Interface] Address`.

Пример:

```ini
[Interface]
Address = 10.8.1.0/24
```

Алгоритм:

- subnet приводится к masked network;
- занятыми считаются:
  - адрес самого server interface (host-часть `Address`, если она задана);
  - IPv4 адреса из peer `AllowedIPs` в config;
  - IPv4 адреса из runtime `awg show` (peer, который есть только в runtime, не потеряет свой адрес);
- агент идет с первого usable адреса:
  - для `/24`: `10.8.1.1`, `10.8.1.2`, ...
- network и broadcast пропускаются для обычных subnet размером больше 2 адресов;
- выдается первый свободный `/32`.

Ограничение: allocation сейчас поддерживает только IPv4.

### Формат нативного client config

```ini
[Interface]
Address = 10.8.1.2/32
DNS = 1.1.1.1, 8.8.8.8
PrivateKey = <client-private-key>
Jc = ...
Jmin = ...
Jmax = ...
S1 = ...
S2 = ...
S3 = ...
S4 = ...
H1 = ...
H2 = ...
H3 = ...
H4 = ...
I1 = ...
I2 =
I3 =
I4 =
I5 =

[Peer]
PublicKey = <server-public-key>
PresharedKey = <psk>
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = 203.0.113.10:<listen-port>
PersistentKeepalive = 25
```

AWG obfuscation fields копируются из server `[Interface]`:

- `Jc`;
- `Jmin`;
- `Jmax`;
- `S1`-`S4`;
- `H1`-`H4`;
- `I1`-`I5`.

### Формат `vpn://`

`vpn_url` предназначен для импорта в Amnezia VPN client.

Формат:

```text
vpn://<base64url(qCompress(json))>
```

Где `qCompress` совместим с Qt:

- первые 4 байта: big-endian длина исходного JSON;
- далее zlib stream level 8;
- base64url без trailing `=`.

Root JSON содержит self-hosted user config:

```json
{
  "hostName": "203.0.113.10",
  "description": "Alice MacBook",
  "defaultContainer": "amnezia-awg2",
  "dns1": "1.1.1.1",
  "dns2": "8.8.8.8",
  "containers": [
    {
      "container": "amnezia-awg2",
      "awg": {
        "port": "49351",
        "transport_proto": "udp",
        "protocol_version": "2",
        "subnet_address": "10.8.1.0",
        "subnet_cidr": "24",
        "last_config": "{\"config\":\"...\"}"
      }
    }
  ]
}
```

Внутри `awg.last_config` лежит compact JSON `AwgClientConfig`:

```json
{
  "config": "[Interface]\n...",
  "hostName": "203.0.113.10",
  "port": 49351,
  "client_ip": "10.8.1.2",
  "client_priv_key": "...",
  "client_pub_key": "...",
  "server_pub_key": "...",
  "psk_key": "...",
  "clientId": "...",
  "allowed_ips": ["0.0.0.0/0", "::/0"],
  "persistent_keep_alive": "25",
  "mtu": "1376",
  "Jc": "...",
  "Jmin": "...",
  "Jmax": "...",
  "S1": "...",
  "S2": "...",
  "S3": "...",
  "S4": "...",
  "H1": "...",
  "H2": "...",
  "H3": "...",
  "H4": "...",
  "I1": "...",
  "I2": "",
  "I3": "",
  "I4": "",
  "I5": ""
}
```

Важно: Go JSON encoder настроен с `SetEscapeHTML(false)`, чтобы значения вида `<r 2><b ...>` в `I1` не превращались в `\u003c...`.

## `revoke`

Удаляет peer по public key.

```bash
vpn-agent revoke --public-key "client-public-key"
```

JSON:

```bash
vpn-agent revoke --public-key "client-public-key" --json
```

Response:

```json
{
  "revoked": true,
  "public_key": "client-public-key"
}
```

### Что делает `revoke`

1. Проверяет, что public key не пустой.
2. Берет host lock через `flock`.
3. Читает `awg0.conf`, `clientsTable`, runtime.
4. Проверяет, что peer есть в config.
5. Валидирует config.
6. Создает backup config и `clientsTable`.
7. Удаляет `[Peer]` из config.
8. Удаляет запись из `clientsTable`.
9. Пишет оба файла atomically.
10. Выполняет `syncconf`.
11. Проверяет через `awg show`, что peer исчез из runtime.
12. При ошибке после backup восстанавливает оба файла и повторно выполняет `syncconf`.

## Работа с файлами внутри контейнера

Агент не читает `/opt/amnezia/awg` напрямую с host filesystem.

Чтение:

```bash
docker exec amnezia-awg2 cat /opt/amnezia/awg/awg0.conf
docker exec amnezia-awg2 cat /opt/amnezia/awg/clientsTable
```

Запись:

1. temp file создается рядом с целевым файлом:

   ```text
   /opt/amnezia/awg/.awg0.conf.tmp.<unix-nano>
   ```

2. данные пишутся через stdin;
3. temp file получает нужный mode;
4. выполняется `mv -f temp target`;
5. mode целевого файла выставляется повторно;
6. выполняется `sync`.

Для `awg0.conf` и `clientsTable` целевой mode всегда `600`.

## Транзакции, backup и rollback

Mutating команды `issue` и `revoke` защищены host lock:

```text
/var/lock/vpn-agent.lock
```

Lock нужен, чтобы два процесса агента не выпустили один и тот же IP и не перезаписали изменения друг друга.

Lock берется в non-blocking режиме с retry: если за 10 секунд получить его не удалось, операция завершается ошибкой `lock ... is held by another process`. Это защищает HTTP API от вечно висящих запросов при зависшем держателе lock.

Перед мутацией агент создает backup внутри контейнера:

```text
/opt/amnezia/awg/awg0.conf.bak.<UTC timestamp>.<unix-nano>
/opt/amnezia/awg/clientsTable.bak.<UTC timestamp>.<unix-nano>
```

Если `clientsTable` отсутствует, backup создается как JSON `[]`.

Rollback запускается при ошибке после backup:

1. восстановить `awg0.conf`;
2. восстановить `clientsTable` (если файла не было до мутации - удалить созданный файл, а не оставлять пустой);
3. выставить mode `600`;
4. выполнить `sync`;
5. выполнить `awg syncconf`.

Если rollback успешен, ошибка возвращается с suffix:

```text
rollback completed
```

Если rollback сам сломался, ошибка содержит детали:

```text
rollback failed: restore config: ...; restore clientsTable: ...; sync restored config: ...
```

## Парсинг `awg0.conf`

Поддерживаются секции:

- `[Interface]`;
- `[Peer]`.

Любая другая секция считается ошибкой.

Для `[Interface]` агент сохраняет исходные строки как есть, включая:

- порядок;
- пустые строки внутри interface;
- комментарии;
- AWG fields;
- закомментированные `I1`-`I5`.

При рендере config:

- `[Interface]` выводится первым;
- затем все сохраненные interface lines;
- затем peer blocks;
- peer blocks рендерятся в нормализованном виде:

```ini
[Peer]
PublicKey = ...
PresharedKey = ...
AllowedIPs = ...
```

Управляемые peer fields:

- `PublicKey`;
- `PresharedKey` или `PreSharedKey`;
- `AllowedIPs`.

Остальные строки peer-блока (например `PersistentKeepalive`, комментарии, ручные правки) агент не интерпретирует, но сохраняет как есть и выводит обратно после управляемых полей - перезапись config их не теряет.

## Валидация config

Перед записью агент проверяет:

- есть `[Interface] Address`;
- есть `[Interface] ListenPort`;
- каждый peer имеет `PublicKey`;
- public keys не дублируются;
- каждый peer имеет `AllowedIPs`;
- каждый `AllowedIPs` является валидным prefix;
- `AllowedIPs` разных peer-ов не пересекаются (не только точные дубликаты: `10.8.1.0/24` у одного peer и `10.8.1.2/32` у другого - тоже ошибка).

## `clientsTable`

Агент поддерживает два формата чтения.

Основной формат - массив:

```json
[
  {
    "clientId": "client-public-key",
    "userData": {
      "clientName": "Alice MacBook",
      "allowedIps": "10.8.1.2/32",
      "creationDate": "Wed Jul 1 21:08:04 2026"
    }
  }
]
```

Legacy формат - объект:

```json
{
  "client-public-key": {
    "clientName": "Alice MacBook",
    "creationDate": "Wed Jul 1 21:08:04 2026"
  }
}
```

При записи агент всегда пишет основной формат массива с indent 4 spaces и newline в конце.

При `issue`:

- если запись по `clientId` уже есть, обновляется `clientName`;
- обновляется `allowedIps`, если он известен;
- `creationDate` сохраняется, если уже был;
- если записи нет, создается новая.

При `revoke` запись удаляется по `clientId == public_key`.

Все неизвестные поля внутри `userData` сохраняются.

## HTTP API

Команда `serve` поднимает HTTP API поверх того же service layer.

```bash
vpn-agent serve \
  --listen 127.0.0.1:8090 \
  --hmac-key-id local \
  --hmac-secret 'change-me'
```

Environment variables:

| Env | Default | Описание |
| --- | --- | --- |
| `VPN_AGENT_LISTEN` | `127.0.0.1:8090` | listen address |
| `VPN_AGENT_KEY_ID` | empty | HMAC key id |
| `VPN_AGENT_SECRET` | empty | HMAC secret |
| `VPN_AGENT_ALLOW_IPS` | `127.0.0.1,::1` | allowlist IP/CIDR |
| `VPN_AGENT_ENDPOINT_HOST` | empty | endpoint host для issue |

Дополнительные flags для `serve`:

| Flag | Default | Описание |
| --- | --- | --- |
| `--listen` | env `VPN_AGENT_LISTEN` или `127.0.0.1:8090` | HTTP listen address |
| `--hmac-key-id` | env `VPN_AGENT_KEY_ID` | HMAC key id |
| `--hmac-secret` | env `VPN_AGENT_SECRET` | HMAC secret |
| `--allow-ip` | env `VPN_AGENT_ALLOW_IPS` или loopback | comma-separated allowed IPs/CIDRs |
| `--allow-no-auth` | `false` | разрешить unsigned requests, только если secret пустой |

Пустой allowlist - ошибка запуска: молча разрешить всех нельзя. Если действительно нужен доступ с любых адресов, передай `--allow-ip '0.0.0.0/0,::/0'` явно.

### Endpoints

| Method | Path | Auth | Описание |
| --- | --- | --- | --- |
| `GET` | `/health` | no | liveness и версия |
| `GET` | `/status` | yes | аналог `inspect --json` |
| `GET` | `/peers` | yes | аналог `peers --json` |
| `POST` | `/peers` | yes | аналог `issue --json` |
| `DELETE` | `/peers/{public_key}` | yes | аналог `revoke --json` |

Версия HTTP API сейчас:

```text
0.2.0
```

### `GET /health`

Request:

```bash
curl http://127.0.0.1:8090/health
```

Response:

```json
{
  "status": "ok",
  "version": "0.2.0"
}
```

### `GET /status`

Response shape совпадает с `InspectResult`.

### `GET /peers`

Response shape совпадает с `[]PeerView`.

### `POST /peers`

Request:

```json
{
  "name": "Alice MacBook",
  "dns": ["1.1.1.1", "8.8.8.8"],
  "endpoint_host": "203.0.113.10"
}
```

Response:

```json
{
  "public_key": "client-public-key",
  "client_ip": "10.8.1.2",
  "config": "[Interface]\n...",
  "vpn_url": "vpn://..."
}
```

Поле `metadata` в request schema сейчас парсится, но service layer его не использует.

### `DELETE /peers/{public_key}`

Public key должен быть URL-escaped.

Пример:

```bash
python3 -c 'import urllib.parse; print(urllib.parse.quote("abc/def=", safe=""))'
```

Response:

```json
{
  "revoked": true,
  "public_key": "abc/def="
}
```

## HMAC authentication

Все endpoints кроме `/health` проходят:

1. IP allowlist;
2. HMAC auth.

Если `--hmac-secret`/`VPN_AGENT_SECRET` пустой:

- по умолчанию authenticated endpoints возвращают `401`;
- `--allow-no-auth` разрешает unsigned requests.

Headers:

| Header | Описание |
| --- | --- |
| `X-Agent-Key-Id` | key id, должен совпадать с configured key id |
| `X-Agent-Timestamp` | RFC3339 timestamp |
| `X-Agent-Signature` | hex HMAC-SHA256 |

Allowed timestamp skew:

```text
60 seconds
```

Signature payload:

```text
METHOD + "\n" +
PATH_WITH_QUERY + "\n" +
TIMESTAMP + "\n" +
HEX_SHA256(RAW_BODY)
```

Signature:

```text
hex(HMAC_SHA256(secret, payload))
```

Для empty body hash:

```text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

Пример подписи на Python:

```python
import datetime
import hashlib
import hmac

secret = b"change-me"
method = "GET"
path = "/peers"
body = b""
timestamp = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
body_hash = hashlib.sha256(body).hexdigest()
payload = "\n".join([method, path, timestamp, body_hash]).encode()
signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()

print("X-Agent-Timestamp:", timestamp)
print("X-Agent-Signature:", signature)
```

## Security notes

### Секреты

`issue` возвращает private key клиента:

- в `config`;
- внутри `vpn_url`.

Это нормальное поведение для выдачи клиентского профиля, но output должен считаться секретным.

Не логируй `issue` response в публичные логи.

### Docker access

Пользователь, запускающий агент, фактически имеет доступ к Docker на VPS. Это высокий уровень привилегий.

Рекомендуемая deployment-модель:

- запускать агент на самом VPS;
- слушать HTTP только на `127.0.0.1`;
- наружу отдавать не агент напрямую, а backend на другом security boundary;
- backend вызывает агент локально или через защищенный private channel.

### HTTP exposure

Не публикуй `vpn-agent serve` напрямую в интернет без дополнительного слоя защиты.

Минимум:

- HMAC secret;
- короткий timestamp skew;
- IP allowlist;
- TLS/reverse proxy, если запросы идут не по loopback;
- rate limiting на backend/reverse proxy.

### Replay

Подпись не содержит nonce: перехваченный подписанный запрос можно повторить в пределах timestamp skew (60 секунд). Для `POST /peers` это означает создание дополнительных peer-ов. Митигируется loopback-моделью, IP allowlist и TLS на транспортном уровне; idempotency keys запланированы в backend-интеграции (см. roadmap). Не выноси API за пределы доверенного канала без этого учета.

### File modes

Агент выставляет:

```text
awg0.conf: 600
clientsTable: 600
```

`inspect` предупредит, если mode отличается.

## Smoke test на VPS

Цель: проверить, что binary работает с реальным `amnezia-awg2`, и что `issue + revoke` не ломают существующий admin peer.

### 1. Build

```bash
cd agent
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -o /tmp/vpn-agent ./cmd/vpn-agent
```

### 2. Copy

```bash
scp /tmp/vpn-agent root@203.0.113.10:/tmp/vpn-agent
ssh root@203.0.113.10 'chmod 0755 /tmp/vpn-agent'
```

### 3. Inspect

```bash
ssh root@203.0.113.10 '/tmp/vpn-agent inspect'
```

Ожидаем:

- container running: `true`;
- runtime interface: `awg0`;
- config exists;
- listen port не пустой;
- peer counts разумные;
- нет неожиданных warnings.

### 4. Peers

```bash
ssh root@203.0.113.10 '/tmp/vpn-agent peers --json'
```

Проверить, что admin peer:

- `in_config=true`;
- `in_runtime=true`;
- `in_clients_table=true`.

### 5. Issue test peer

```bash
ssh root@203.0.113.10 \
  '/tmp/vpn-agent issue --name "Codex smoke test" --endpoint-host 203.0.113.10 --json'
```

Сохранить `public_key`.

Проверить:

```bash
ssh root@203.0.113.10 '/tmp/vpn-agent peers --json'
```

Новый peer должен быть:

- в config;
- в runtime;
- в `clientsTable`.

### 6. Revoke test peer

```bash
ssh root@203.0.113.10 \
  '/tmp/vpn-agent revoke --public-key "<public_key>"'
```

Проверить:

```bash
ssh root@203.0.113.10 '/tmp/vpn-agent peers --json'
```

Новый peer должен исчезнуть, admin peer должен остаться.

## Unit tests

Запуск:

```bash
cd agent
go test ./...
```

Если нужен отдельный cache:

```bash
GOCACHE=$(pwd)/.gocache go test ./...
```

Покрытые области:

- парсер/рендер AWG config;
- add/remove peer;
- allocation free IPv4;
- `clientsTable` parse/update/render;
- client config rendering with AWG fields;
- Amnezia `vpn://` rendering and qCompress-compatible decoding;
- HTTP route shapes and auth behavior.

## Operational runbook

### Посмотреть состояние

```bash
vpn-agent inspect
vpn-agent peers
```

### Выпустить клиента

```bash
vpn-agent issue --name "Client name" --endpoint-host 203.0.113.10
```

Отдать пользователю `vpn_url`.

Если Amnezia client не импортирует `vpn_url`, проверить:

1. строка скопирована целиком, без переносов и лишних символов;
2. строка начинается с `vpn://`;
3. `vpn-agent issue --json` содержит непустой `vpn_url`;
4. `vpn-agent peers --json` показывает нового peer-а в трех источниках;
5. Amnezia client версии поддерживает `amnezia-awg2`.

### Удалить клиента

```bash
vpn-agent revoke --public-key "<client-public-key>"
```

### Найти backup

Внутри контейнера:

```bash
docker exec amnezia-awg2 sh -lc 'ls -la /opt/amnezia/awg/*.bak.*'
```

### Ручное восстановление backup

Обычно это не нужно: агент делает rollback сам.

Если нужен ручной restore:

```bash
docker exec amnezia-awg2 sh -lc '
  cp -p /opt/amnezia/awg/awg0.conf.bak.YYYYMMDDTHHMMSS.NNN /opt/amnezia/awg/awg0.conf &&
  cp -p /opt/amnezia/awg/clientsTable.bak.YYYYMMDDTHHMMSS.NNN /opt/amnezia/awg/clientsTable &&
  chmod 600 /opt/amnezia/awg/awg0.conf /opt/amnezia/awg/clientsTable &&
  awg syncconf awg0 <(awg-quick strip /opt/amnezia/awg/awg0.conf)
'
```

## Known limitations

- IPv4 allocation only.
- Только один server config/interface в рамках вызова.
- Управляются только `PublicKey`, `PresharedKey`, `AllowedIPs`; остальные peer-поля сохраняются как есть, но не интерпретируются.
- HMAC подпись без nonce: replay возможен в пределах timestamp skew.
- `clientsTable` metadata из HTTP request пока игнорируется.
- Нет persistent audit log.
- Нет встроенного HTTP TLS.
- Нет встроенного user/payment/subscription layer.
- Нет автоматической чистки backup-файлов.
- Endpoint auto-detection не реализован: для `issue` нужно передавать endpoint host явно или через env.

## Recommended next milestones

1. Сделать HTTP API стабильным публичным контрактом:
   - versioned routes;
   - request IDs;
   - structured error codes;
   - audit log.
2. Добавить backend integration:
   - users;
   - payments;
   - subscription status;
   - idempotency keys for issue/revoke.
3. Добавить pool/lease model:
   - reserved IPs;
   - reusable client slots;
   - expiry.
4. Добавить backup retention:
   - оставить последние N;
   - отдельная команда cleanup.
5. Добавить systemd unit и hardening profile.
