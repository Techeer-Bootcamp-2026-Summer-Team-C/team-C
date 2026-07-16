# 중앙 Endpoint 실데이터 통합 검증 설명서

이 문서는 Windows와 macOS의 실제 Agent가 수집한 OS 이벤트를 중앙 EC2로 전송하고, 중앙 Kafka·Worker·DB를 거쳐 Dashboard에 표시되는지 검증하는 절차를 설명한다.

검증 대상 경로는 다음과 같다.

```text
Windows Agent ─┐
               ├─ HTTPS + mTLS ─> EC2 Nginx :8443
macOS Agent ───┘                         │
                                        ▼
                              FastAPI Collector
                                        │
                                        ▼
                               Kafka telemetry.raw
                                        │
                                        ▼
                         Event Storage Worker → ClickHouse
                                        │
                                        ▼
                            Kafka telemetry.validated
                                        │
                                        ▼
                          Detection Worker → PostgreSQL
                                        │
                                        ▼
                         중앙 API :8080 → Dashboard
```

이 검증에서는 `tests/seed_frontend_qa.py`, `tools.seed_dashboard_long_range`, DB 직접 Event 삽입을 사용하지 않는다. Agent가 실제 OS에서 수집하여 전송한 Event만 검증 대상으로 인정한다.

## 1. 역할과 범위

| 위치 | 실행 대상 | 실행하지 않는 것 |
| --- | --- | --- |
| EC2 | Nginx, Backend, Worker, Kafka, PostgreSQL, ClickHouse | Endpoint Agent |
| Windows Endpoint | Windows Agent | 로컬 수집용 Compose |
| Mac Endpoint | macOS Agent | 로컬 수집용 Compose |
| 관리 PC | 중앙 API를 바라보는 Frontend | 로컬 DB를 바라보는 Dashboard |

Endpoint에서 로컬 Compose를 실행하면 해당 기기의 로컬 DB만 검증하게 된다. 중앙 검증에서는 Agent의 `collectorBaseUrl`이 반드시 EC2 Collector를 가리켜야 한다.

## 2. 사전 준비

### 2.1 변수

실제 값은 문서나 Git에 저장하지 않는다. 아래 변수는 작업 메모나 셸 환경에서만 관리한다.

```text
<COLLECTOR_HOST>       EC2 Tailscale MagicDNS 이름 또는 Tailscale IP
<EC2_SSH_HOST>        인증된 EC2 SSH/SSM 접속 대상
<ADMIN_LOGIN_ID>      중앙 Dashboard 관리자 로그인 ID
<WINDOWS_AGENT_ID>    예: windows-geonh-01
<MAC_AGENT_ID>        예: mac-geonha-01
```

권장 Collector URL:

```text
https://<COLLECTOR_HOST>:8443/api/v1
```

가능하면 Tailscale IP보다 안정적인 MagicDNS 이름을 사용한다. 이름을 사용하면 서버 인증서 SAN에도 같은 DNS 이름을 넣는다.

### 2.2 네트워크 확인

Windows PowerShell:

```powershell
Test-NetConnection <COLLECTOR_HOST> -Port 8443
Test-NetConnection <COLLECTOR_HOST> -Port 8080
```

Mac:

```bash
nc -G 5 -vz <COLLECTOR_HOST> 8443
nc -G 5 -vz <COLLECTOR_HOST> 8080
```

두 포트 모두 연결되어야 한다.

- `8443`: Agent mTLS Collector
- `8080`: 중앙 Dashboard API

EC2 보안 그룹과 호스트 방화벽은 `8443`과 `8080`을 인터넷 전체에 공개하지 않고 tailnet 경로로만 허용한다. 운영 Compose는 호스트 포트에 바인딩하므로 외부 노출 범위는 별도로 제한해야 한다.

### 2.3 운영 상태 확인

Portainer에서 다음을 확인한다.

| 스택 | 정상 상태 |
| --- | --- |
| `edr-c-infra` | PostgreSQL·ClickHouse·Kafka `healthy` |
| `edr-c-service` | Backend·Nginx `healthy`, Worker 2개 `running`, `app-init` `Exited (0)` |

중앙 API 상태는 저장소가 있는 관리 PC에서 다음 스크립트로 확인할 수 있다.

```powershell
powershell -File tools/verify_production_deployment.ps1 `
  -BaseUrl http://<COLLECTOR_HOST>:8080 `
  -SshHost macmini
```

## 3. 중앙 PKI 준비

### 3.1 안전 원칙

- 로컬 Compose가 만든 `compose-demo-agent` 인증서를 중앙 서버에 사용하지 않는다.
- 운영 Nginx의 `agent-ca.crt`와 Agent 인증서는 같은 CA 체인을 사용해야 한다.
- CA private key는 관리자 보안 경로에만 보관한다.
- CA private key를 EC2, Windows Endpoint, Mac Endpoint, Git에 복사하지 않는다.
- 기존 실제 Agent가 있다면 운영 CA를 임의로 교체하지 않는다.

먼저 기존 `/etc/edr-c/tls/agent-ca.crt`를 발급한 CA private key가 관리자 보안 저장소에 있는지 확인한다.

- 기존 CA private key가 있으면 같은 CA로 Windows·Mac 인증서를 발급한다.
- 기존 CA private key가 없고 실제 Agent가 없다면 새 CA, 서버 인증서, Agent 인증서를 함께 준비할 수 있다.
- 기존 실제 Agent가 있는데 CA private key가 없다면 기존 CA와 새 CA를 함께 신뢰하는 전환 계획을 먼저 수립한다. 즉시 교체하면 기존 Agent가 모두 끊긴다.

이 설명서의 CLI는 PoC용 중앙 PKI 절차다. 실제 장기 운영에서는 조직의 CA 또는 비밀관리 체계로 대체한다.

### 3.2 보안 디렉터리 준비

관리자 Mac의 저장소 루트에서 실행한다.

```bash
cd /absolute/path/to/team-C

export PKI="$HOME/.edr-c-pki"
install -d -m 700 "$PKI"
```

기존 CA를 재사용한다면 Agent 인증서를 발급하기 전에 아래 위치에 기존 파일이 있어야 한다.

```text
$PKI/ca/ca.crt
$PKI/ca/ca.key
```

### 3.3 Windows·Mac Agent 인증서 발급

Agent ID는 소문자 영문, 숫자, `.`, `_`, `-`만 사용한다.

```bash
python3 -m tools.provision_agent_cert \
  --agent-id <WINDOWS_AGENT_ID> \
  --output-dir "$PKI"

python3 -m tools.provision_agent_cert \
  --agent-id <MAC_AGENT_ID> \
  --output-dir "$PKI"
```

생성 파일:

```text
$PKI/ca/ca.crt
$PKI/ca/ca.key

$PKI/agents/<WINDOWS_AGENT_ID>/agent.p12
$PKI/agents/<WINDOWS_AGENT_ID>/agent.crt
$PKI/agents/<WINDOWS_AGENT_ID>/agent.key
$PKI/agents/<WINDOWS_AGENT_ID>/ca.crt

$PKI/agents/<MAC_AGENT_ID>/agent.crt
$PKI/agents/<MAC_AGENT_ID>/agent.key
$PKI/agents/<MAC_AGENT_ID>/ca.crt
```

인증서 SAN의 Agent ID와 각 Agent 설정의 `agentId`가 정확히 일치해야 한다.

### 3.4 원격 접속용 서버 인증서 생성

EC2 서버 인증서 SAN에 `<COLLECTOR_HOST>`가 포함되어야 한다. `localhost`, `nginx`, `127.0.0.1`만 들어 있는 인증서는 원격 Agent 연결에 사용할 수 없다.

```bash
install -d -m 700 "$PKI/server"
```

`$PKI/server/server-extensions.cnf`을 만든다.

Tailscale IP를 사용할 때:

```ini
[server]
basicConstraints=critical,CA:FALSE
subjectAltName=IP:<COLLECTOR_HOST>
extendedKeyUsage=serverAuth
keyUsage=critical,digitalSignature,keyEncipherment
```

MagicDNS 이름을 사용할 때:

```ini
[server]
basicConstraints=critical,CA:FALSE
subjectAltName=DNS:<COLLECTOR_HOST>
extendedKeyUsage=serverAuth
keyUsage=critical,digitalSignature,keyEncipherment
```

서버 key와 인증서를 생성한다.

```bash
openssl req \
  -new \
  -newkey rsa:2048 \
  -nodes \
  -sha256 \
  -subj "/CN=<COLLECTOR_HOST>" \
  -keyout "$PKI/server/server.key" \
  -out "$PKI/server/server.csr"

openssl x509 \
  -req \
  -in "$PKI/server/server.csr" \
  -CA "$PKI/ca/ca.crt" \
  -CAkey "$PKI/ca/ca.key" \
  -CAserial "$PKI/ca/ca.srl" \
  -days 365 \
  -sha256 \
  -extfile "$PKI/server/server-extensions.cnf" \
  -extensions server \
  -out "$PKI/server/server.crt"

chmod 600 "$PKI/server/server.key"
```

`ca.srl`이 아직 없다면 첫 발급에서 `-CAserial "$PKI/ca/ca.srl"` 대신 `-CAcreateserial`을 사용한다. 앞 단계에서 Agent 인증서를 발급했다면 일반적으로 `ca.srl`이 이미 존재한다.

생성 결과를 확인한다.

```bash
openssl x509 -in "$PKI/server/server.crt" -noout -subject -issuer -dates -text
```

출력의 `Subject Alternative Name`에 실제 `<COLLECTOR_HOST>`가 있어야 한다.

## 4. EC2 TLS 적용

이 단계는 운영 Nginx를 재시작한다. 먼저 현재 파일과 운영 상태를 백업하고, PostgreSQL·ClickHouse·Kafka volume은 건드리지 않는다.

### 4.1 기존 TLS 백업

EC2에서:

```bash
sudo cp -a \
  /etc/edr-c/tls \
  "/etc/edr-c/tls.backup-$(date +%Y%m%d%H%M%S)"
```

백업 경로를 작업 기록에 남긴다.

### 4.2 적용 파일

관리자 Mac에서 인증된 SSH/SSM 경로로 아래 파일을 EC2 임시 경로에 전달한다.

| 관리자 Mac | EC2 최종 경로 | 권한 |
| --- | --- | --- |
| `$PKI/server/server.crt` | `/etc/edr-c/tls/server.crt` | `644` |
| `$PKI/server/server.key` | `/etc/edr-c/tls/server.key` | `600` |
| `$PKI/ca/ca.crt` | `/etc/edr-c/tls/agent-ca.crt` | `644` |

예시:

```bash
scp "$PKI/server/server.crt" <EC2_SSH_HOST>:/tmp/edr-server.crt
scp "$PKI/server/server.key" <EC2_SSH_HOST>:/tmp/edr-server.key
scp "$PKI/ca/ca.crt" <EC2_SSH_HOST>:/tmp/edr-agent-ca.crt
```

EC2에서:

```bash
sudo install -m 644 /tmp/edr-server.crt /etc/edr-c/tls/server.crt
sudo install -m 600 /tmp/edr-server.key /etc/edr-c/tls/server.key
sudo install -m 644 /tmp/edr-agent-ca.crt /etc/edr-c/tls/agent-ca.crt

sudo rm -f /tmp/edr-server.crt /tmp/edr-server.key /tmp/edr-agent-ca.crt
```

Portainer의 `edr-c-service` 스택에서 Nginx 컨테이너만 재시작한다. 인증서 변경만으로 PostgreSQL·ClickHouse·Kafka를 재배포하거나 volume을 교체하지 않는다.

### 4.3 mTLS handshake 확인

관리자 Mac에서 발급한 Mac Agent 인증서로 확인한다.

```bash
openssl s_client \
  -connect <COLLECTOR_HOST>:8443 \
  -CAfile "$PKI/ca/ca.crt" \
  -cert "$PKI/agents/<MAC_AGENT_ID>/agent.crt" \
  -key "$PKI/agents/<MAC_AGENT_ID>/agent.key" \
  -verify_return_error </dev/null
```

성공 기준:

```text
Verify return code: 0 (ok)
```

실패하면 Agent를 실행하지 말고 서버 SAN, CA chain, 인증서 유효기간부터 수정한다.

### 4.4 TLS rollback

새 인증서로 Nginx가 시작하지 못하면 4.1에서 만든 백업의 세 파일을 `/etc/edr-c/tls`로 복원하고 Nginx만 다시 시작한다. 백업 검증 전 기존 TLS 디렉터리를 삭제하지 않는다.

## 5. Windows Endpoint 실행

### 5.1 준비 파일

관리자 보안 경로에서 Windows로 다음 파일만 안전하게 전달한다.

```text
$PKI/agents/<WINDOWS_AGENT_ID>/agent.p12
$PKI/agents/<WINDOWS_AGENT_ID>/ca.crt
```

CA private key와 Mac Agent private key는 전달하지 않는다.

Windows 예시 경로:

```text
C:\ProgramData\EDR-C-Agent\secrets\agent.p12
C:\ProgramData\EDR-C-Agent\secrets\ca.crt
```

관리자 PowerShell에서 디렉터리를 만들고 접근권한을 제한한다.

```powershell
New-Item -ItemType Directory -Force C:\ProgramData\EDR-C-Agent\secrets
New-Item -ItemType Directory -Force C:\Users\Public\EDR-C-Watch
```

### 5.2 서버 CA 신뢰 등록

관리자 PowerShell:

```powershell
Import-Certificate `
  -FilePath C:\ProgramData\EDR-C-Agent\secrets\ca.crt `
  -CertStoreLocation Cert:\LocalMachine\Root
```

### 5.3 설정 파일

`C:\ProgramData\EDR-C-Agent\config.json`:

```json
{
  "agentId": "<WINDOWS_AGENT_ID>",
  "collectorBaseUrl": "https://<COLLECTOR_HOST>:8443/api/v1",
  "certificatePfxPath": "C:\\ProgramData\\EDR-C-Agent\\secrets\\agent.p12",
  "stateDirectory": "C:\\ProgramData\\EDR-C-Agent",
  "watchDirectory": "C:\\Users\\Public\\EDR-C-Watch",
  "captureInterface": "",
  "queueMaxEvents": 5000,
  "retryBaseSeconds": 1,
  "retryMaxSeconds": 60,
  "logLevel": "INFO"
}
```

### 5.4 빌드

저장소 루트의 PowerShell에서:

```powershell
cmake -S .\agents\windows -B .\agents\windows\build -A x64
cmake --build .\agents\windows\build --config Release
ctest --test-dir .\agents\windows\build -C Release --output-on-failure
```

Npcap SDK가 없어도 Process, Network, File, DNS 수집은 사용할 수 있다. Packet/L7 sensor는 `DEGRADED`일 수 있다.

### 5.5 실제 데이터 1회 전송

```powershell
.\agents\windows\build\Release\edr-windows-agent.exe `
  --config C:\ProgramData\EDR-C-Agent\config.json `
  --once
```

현재 실행 중인 실제 Windows 프로세스와 네트워크 연결이 수집된다. 별도의 Event JSON이나 DB seed를 만들지 않는다.

Agent 성공 기준:

```text
cycle pending=0 failed=0
```

## 6. Mac Endpoint 실행

중앙 검증에서는 Mac 로컬 Compose가 필요 없다. 이전에 실행한 로컬 Compose가 있다면 필요할 때 `docker compose down`으로 로컬 컨테이너만 종료할 수 있다. `-v`는 사용하지 않는다.

### 6.1 준비 파일

Mac Agent에 다음 파일만 배치한다.

```text
$PKI/agents/<MAC_AGENT_ID>/agent.crt
$PKI/agents/<MAC_AGENT_ID>/agent.key
$PKI/agents/<MAC_AGENT_ID>/ca.crt
```

```bash
mkdir -p "$HOME/.edr-c-agent/secrets"
mkdir -p "$HOME/.edr-c-agent/state"
mkdir -p "$HOME/.edr-c-agent/watch"
chmod 700 "$HOME/.edr-c-agent" "$HOME/.edr-c-agent/secrets"

install -m 644 \
  "$PKI/agents/<MAC_AGENT_ID>/agent.crt" \
  "$HOME/.edr-c-agent/secrets/agent.crt"

install -m 600 \
  "$PKI/agents/<MAC_AGENT_ID>/agent.key" \
  "$HOME/.edr-c-agent/secrets/agent.key"

install -m 644 \
  "$PKI/agents/<MAC_AGENT_ID>/ca.crt" \
  "$HOME/.edr-c-agent/secrets/ca.crt"

chmod 600 "$HOME/.edr-c-agent/secrets/agent.key"
```

### 6.2 설정 파일

`$HOME/.edr-c-agent/config.json`:

```json
{
  "agentId": "<MAC_AGENT_ID>",
  "collectorBaseUrl": "https://<COLLECTOR_HOST>:8443/api/v1",
  "certificatePath": "/Users/<USER>/.edr-c-agent/secrets/agent.crt",
  "privateKeyPath": "/Users/<USER>/.edr-c-agent/secrets/agent.key",
  "caCertificatePath": "/Users/<USER>/.edr-c-agent/secrets/ca.crt",
  "stateDirectory": "/Users/<USER>/.edr-c-agent/state",
  "watchDirectory": "/Users/<USER>/.edr-c-agent/watch",
  "captureInterface": "en0",
  "queueMaxEvents": 5000,
  "retryBaseSeconds": 1,
  "retryMaxSeconds": 60,
  "logLevel": "INFO"
}
```

기본 네트워크 interface가 `en0`이 아니면 다음 결과로 바꾼다.

```bash
route get default | awk '/interface:/{print $2}'
```

### 6.3 빌드와 테스트

```bash
cd agents/macos

DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift build
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test
```

### 6.4 실제 데이터 1회 전송

```bash
.build/debug/edr-macos-agent \
  --config "$HOME/.edr-c-agent/config.json" \
  --once \
  --collect-seconds 5
```

성공 기준:

```text
collected=<1 이상> accepted=<1 이상> pending=0 failed=0
```

`tcpdump` 권한이 없으면 Packet/L7 sensor가 `DEGRADED`일 수 있다. Process/Event 전송이 성공하면 이번 검증을 실패로 처리하지 않는다.

## 7. 중앙 Dashboard 확인

운영 Nginx의 `8080`은 중앙 API이며 Frontend 화면을 제공하지 않는다. Frontend를 관리 PC에서 실행하고 Vite proxy만 중앙 API로 지정한다. 이 방식에서도 Event 저장과 처리는 EC2에서 수행된다.

기존 로컬 Compose Dashboard `http://127.0.0.1:8080`은 로컬 DB를 보므로 중앙 검증 증거로 사용하지 않는다.

### 7.1 Windows에서 Frontend 실행

저장소 루트의 PowerShell에서:

```powershell
npm.cmd --prefix frontend ci

$env:EDR_BACKEND_PROXY_TARGET='http://<COLLECTOR_HOST>:8080'

npm.cmd --prefix frontend run dev -- --port 5174
```

접속 주소:

```text
http://127.0.0.1:5174
```

### 7.2 Mac에서 Frontend 실행

```bash
npm --prefix frontend ci

EDR_BACKEND_PROXY_TARGET=http://<COLLECTOR_HOST>:8080 \
  npm --prefix frontend run dev -- --port 5174
```

Frontend는 Windows와 Mac 중 한 곳에서만 실행해도 된다.

### 7.3 중앙 관리자 계정

기존 중앙 ADMIN 계정을 사용한다. 계정이 없다면 Portainer의 Backend 컨테이너 Console에서 다음 명령을 실행하고 비밀번호를 대화형으로 입력한다.

```bash
python -m tools.create_admin \
  --login-id <ADMIN_LOGIN_ID> \
  --name "Mentor Demo"
```

비밀번호를 명령행, 문서, Git, 채팅에 남기지 않는다.

### 7.4 화면 확인

Worker의 비동기 처리를 고려해 Agent 실행 후 최대 30초 정도 기다린다.

`Endpoints`:

- `<WINDOWS_AGENT_ID>`와 OS `WINDOWS`
- `<MAC_AGENT_ID>`와 OS `MACOS`
- 실행 직후에는 `ONLINE`; `--once` 종료 후 2분이 지나면 `OFFLINE`

`Events`:

- 두 Agent ID로 필터
- 실행 시간 직후의 `PROCESS_EXECUTION`
- 가능한 경우 `NETWORK_CONNECTION`, `FILE_EVENT`, `DNS_QUERY`

`Overview`:

- Endpoint 수 증가
- Event 수가 0보다 큼

일반적인 실제 활동은 현재 탐지 규칙에 걸리지 않을 수 있으므로 Alert와 Incident가 0이어도 이번 검증은 성공이다.

## 8. 합격 기준과 증거

| 구간 | 합격 기준 | 권장 증거 |
| --- | --- | --- |
| 네트워크 | Endpoint에서 EC2 `8443` 접근 가능 | `Test-NetConnection` 또는 `nc` |
| TLS | 서버 SAN 일치, client cert 검증 성공 | `Verify return code: 0` |
| Windows Agent | `pending=0`, `failed=0` | Agent 콘솔 |
| Mac Agent | `accepted>0`, `pending=0`, `failed=0` | Agent 콘솔 |
| 중앙 수집 | 등록·heartbeat·telemetry 성공 | Nginx/Backend 로그 |
| 중앙 저장 | Endpoint와 Event 조회 가능 | Dashboard `Endpoints`, `Events` |
| 중앙 표시 | Overview Event 수 증가 | Dashboard 화면 |

최종 증거에는 다음을 남긴다.

- 검증 날짜와 UTC/KST 시간 범위
- Backend/Nginx 이미지 commit SHA
- Windows/Mac Agent ID
- Agent 콘솔 성공 출력
- Dashboard Endpoint 2대 화면
- 실제 Event 목록과 발생 시각
- `seed` 또는 DB 직접 Event 삽입을 사용하지 않았다는 기록
- `DEGRADED` sensor가 있다면 원인

인증서 private key, 비밀번호, JWT, Tailscale credential은 캡처하거나 첨부하지 않는다.

## 9. 검증 종료와 연결 해제

### 9.1 임시 연결 해제

다시 검증할 가능성이 있다면 이 방법을 사용한다.

`--once` 실행은 이미 Agent가 종료된 상태다. 계속 실행 중이면 Agent 콘솔에서 `Ctrl+C`를 누른다.

Windows 확인:

```powershell
Get-Process edr-windows-agent -ErrorAction SilentlyContinue
```

Mac 확인:

```bash
pgrep -fl edr-macos-agent
```

프로세스가 없고 마지막 heartbeat 이후 2분이 지나면 중앙 Endpoint 상태가 자동으로 `OFFLINE`이 된다. 기존 Event는 그대로 남고 새 Event만 들어오지 않는다. 같은 Agent를 다시 실행하면 동일 인증서로 `ONLINE`으로 복귀한다.

### 9.2 Frontend 종료

Frontend 터미널에서 `Ctrl+C`를 누른다.

Windows 환경 변수 제거:

```powershell
Remove-Item Env:EDR_BACKEND_PROXY_TARGET -ErrorAction SilentlyContinue
```

Mac에서 별도로 export했다면:

```bash
unset EDR_BACKEND_PROXY_TARGET
```

Frontend 종료는 중앙 서비스와 저장 데이터에 영향을 주지 않는다.

### 9.3 영구 재접속 차단

현재 Endpoint retirement REST API는 없다. 다시 사용할 계획이 없을 때만 운영자가 PostgreSQL에서 인증서를 revoke하고 Endpoint를 `RETIRED`로 바꾼다.

`RETIRED` 처리 전에 대상 Agent ID와 상태를 조회하고 PostgreSQL 백업 정책을 확인한다.

Portainer의 PostgreSQL 컨테이너 Console:

```bash
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

대상 확인:

```sql
SELECT endpoint_id, agent_id, hostname, os_type, status, last_seen_at
FROM endpoints
WHERE agent_id IN ('<WINDOWS_AGENT_ID>', '<MAC_AGENT_ID>')
  AND is_delete = FALSE;
```

확인 후 transaction으로 처리한다.

```sql
BEGIN;

UPDATE agent_auth_keys
SET revoked_at = NOW(),
    updated_at = NOW()
WHERE endpoint_id IN (
    SELECT endpoint_id
    FROM endpoints
    WHERE agent_id IN ('<WINDOWS_AGENT_ID>', '<MAC_AGENT_ID>')
      AND is_delete = FALSE
)
AND is_delete = FALSE
AND revoked_at IS NULL;

UPDATE endpoints
SET status = 'RETIRED',
    updated_at = NOW()
WHERE agent_id IN ('<WINDOWS_AGENT_ID>', '<MAC_AGENT_ID>')
  AND is_delete = FALSE;

COMMIT;
```

결과 확인:

```sql
SELECT agent_id, status, last_seen_at
FROM endpoints
WHERE agent_id IN ('<WINDOWS_AGENT_ID>', '<MAC_AGENT_ID>');

SELECT e.agent_id, a.cert_fingerprint, a.revoked_at
FROM endpoints e
JOIN agent_auth_keys a ON a.endpoint_id = e.endpoint_id
WHERE e.agent_id IN ('<WINDOWS_AGENT_ID>', '<MAC_AGENT_ID>')
ORDER BY a.agent_auth_key_id DESC;
```

성공 기준:

- Endpoint 상태가 `RETIRED`
- 활성 인증서의 `revoked_at`이 설정됨
- 같은 Agent의 등록·heartbeat·telemetry가 `403 ENDPOINT_RETIRED`
- 기존 Event 데이터는 삭제되지 않음

`RETIRED`는 영구 종료 상태다. 같은 Agent ID를 다시 사용할 계획이면 이 절차 대신 `OFFLINE` 상태로 둔다.

### 9.4 Endpoint 로컬 인증서 제거

영구 차단을 완료하고 Agent buffer가 `pending=0`, `failed=0`일 때만 로컬 인증서를 제거한다.

Windows에서는 CA 파일을 삭제하기 전에 정확한 thumbprint로 신뢰를 제거한다.

```powershell
$caPath = 'C:\ProgramData\EDR-C-Agent\secrets\ca.crt'
$ca = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($caPath)
$thumbprint = $ca.Thumbprint

Remove-Item -LiteralPath "Cert:\LocalMachine\Root\$thumbprint"
```

그 다음 아래 Agent 전용 파일을 제거한다.

```text
C:\ProgramData\EDR-C-Agent\config.json
C:\ProgramData\EDR-C-Agent\secrets\agent.p12
C:\ProgramData\EDR-C-Agent\secrets\ca.crt
```

Mac에서는 아래 Agent 전용 파일을 제거한다.

```text
~/.edr-c-agent/config.json
~/.edr-c-agent/secrets/agent.crt
~/.edr-c-agent/secrets/agent.key
~/.edr-c-agent/secrets/ca.crt
```

Agent state directory에는 ACK 전 SQLite buffer가 있으므로 전송 완료 확인 전 삭제하지 않는다.

### 9.5 제거하면 안 되는 항목

개별 Agent 두 대를 끊기 위해 다음 항목을 삭제하거나 되돌리지 않는다.

- EC2 `/etc/edr-c/tls/server.crt`
- EC2 `/etc/edr-c/tls/server.key`
- EC2 `/etc/edr-c/tls/agent-ca.crt`
- 관리자 보안 저장소의 중앙 CA private key
- PostgreSQL·ClickHouse·Kafka volume
- 중앙에 저장된 Endpoint와 Event 데이터

중앙 CA를 제거하면 같은 CA로 발급한 모든 Agent가 영향을 받는다. 개별 해제는 Endpoint retirement와 인증서 revoke로 처리한다.

## 10. 문제 해결

### 10.1 `certificate verify failed` 또는 `NETWORK_OR_TLS_FAILURE`

확인 순서:

1. Agent의 `collectorBaseUrl` 호스트와 서버 인증서 SAN이 같은지 확인한다.
2. Agent가 신뢰하는 `ca.crt`와 서버 인증서 issuer가 같은지 확인한다.
3. Agent certificate/key 또는 P12가 올바른 Agent ID로 발급됐는지 확인한다.
4. 인증서 유효기간과 시스템 시간을 확인한다.

### 10.2 `401 INVALID_AGENT_CERTIFICATE`

- Agent ID와 certificate SAN이 다른지 확인한다.
- 첫 등록 후 다른 인증서로 바뀌지 않았는지 확인한다.
- 중앙 `agent_auth_keys`의 fingerprint와 `revoked_at`을 확인한다.

### 10.3 `403 ENDPOINT_RETIRED`

해당 Agent ID는 영구 종료 상태다. 기존 Agent ID를 임의로 되살리지 말고 운영 판단 후 새 Agent ID와 새 인증서를 사용한다.

### 10.4 Agent는 성공했지만 Dashboard가 비어 있음

1. `http://127.0.0.1:8080`이 아니라 중앙 API proxy를 사용하는 `5174` Frontend인지 확인한다.
2. Agent 실행 시간과 Dashboard time range가 겹치는지 확인한다.
3. 최대 30초 기다린다.
4. Portainer에서 `event-storage-worker`, `detection-worker`, Backend 로그를 확인한다.
5. Kafka consumer lag가 증가한 상태인지 확인한다.

### 10.5 Endpoint는 보이지만 Alert·Incident가 없음

정상일 수 있다. Endpoint 등록과 Event 저장은 실제 수집 검증이고, Alert·Incident는 Event가 활성 탐지 규칙을 만족할 때만 생성된다.

### 10.6 일부 sensor가 `DEGRADED`

- Windows Npcap SDK/driver가 없으면 Packet/L7이 `DEGRADED`일 수 있다.
- Mac tcpdump 권한이 없으면 Packet/L7이 `DEGRADED`일 수 있다.
- Process/Event 수집과 중앙 표시가 성공했다면 원인을 기록하고 이번 실데이터 검증과 분리한다.

## 11. 최종 체크리스트

### 중앙 준비

- [ ] EC2 `8080`, `8443`이 tailnet에서 접근 가능하다.
- [ ] 인터넷 전체에 `8080`, `8443`이 공개되지 않았다.
- [ ] Backend/Nginx가 `healthy`, Worker가 `running`이다.
- [ ] 서버 인증서 SAN이 `<COLLECTOR_HOST>`와 일치한다.
- [ ] mTLS handshake가 `Verify return code: 0`이다.

### Windows

- [ ] Agent ID와 certificate SAN이 같다.
- [ ] CA를 정확한 LocalMachine Root에 설치했다.
- [ ] `--once` 실행 후 `pending=0`, `failed=0`이다.
- [ ] 중앙 Dashboard에 Windows Endpoint와 Event가 보인다.

### Mac

- [ ] Agent ID와 certificate SAN이 같다.
- [ ] private key 권한이 `600`이다.
- [ ] `accepted>0`, `pending=0`, `failed=0`이다.
- [ ] 중앙 Dashboard에 Mac Endpoint와 Event가 보인다.

### 종료

- [ ] 임시 종료면 Agent를 중지하고 2분 후 `OFFLINE`을 확인했다.
- [ ] 영구 종료면 인증서를 revoke하고 Endpoint를 `RETIRED`로 변경했다.
- [ ] 중앙 Event 데이터와 운영 volume은 보존했다.
- [ ] private key와 비밀번호가 문서·캡처·Git에 포함되지 않았다.

## 12. 관련 소스 오브 트루스

- 운영 서비스 Compose: `deploy/portainer/compose.service.yaml`
- 운영 Nginx mTLS 설정: `deploy/nginx/nginx.prod.conf`
- 운영 배포 절차: `deploy/portainer/README.md`
- Agent 인증서 발급 CLI: `tools/provision_agent_cert.py`
- Windows Agent: `agents/windows/README.md`
- macOS Agent: `agents/macos/README.md`
- Agent 인증 계약: `docs/contracts/API_SPEC.md`
- Endpoint·인증서 상태 모델: `docs/architecture/EDR_DATA_MODEL.md`
