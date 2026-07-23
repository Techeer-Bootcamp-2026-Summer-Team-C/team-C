# OWLBY

Windows와 macOS Endpoint의 보안 Event를 수집하고, 탐지 결과를 Alert와 Incident까지 연결해 추적하는 EDR 플랫폼입니다.

![OWLBY EDR 플랫폼 소개 화면](assets/demo/00-demo-evidence-flow.png)

## 데모

### 종합 현황 및 Endpoint 모니터링

![종합 현황에서 Endpoint 상태와 위험 Endpoint 상세를 확인하는 과정](assets/demo/01-overview-endpoints.gif)

Endpoint의 수집 상태와 위험도를 확인하고, 위험 Endpoint의 Alert와 Incident로 바로 이동합니다.

### Event 검색 및 분석

![Process Event를 검색하고 Process Tree와 Raw Payload를 분석하는 과정](assets/demo/02-event-analysis.gif)

Event를 유형별로 검색하고, 원본 필드와 Process Tree, Raw Payload를 확인합니다.

### Alert 분류

![Alert 큐에서 위험도와 상태를 분류하고 Evidence chain을 확인하는 화면](assets/demo/03-alert-triage.png)

Severity, Risk, Status를 기준으로 Alert를 분류하고 `Endpoint → Event → Rule → Alert → Incident` 근거 체인을 추적합니다.

### Incident 조사

![Incident의 Investigation Graph를 조사하는 과정](assets/demo/04-incident-investigation.gif)

연결된 Alert와 Event를 Investigation Graph로 확장해 조사할 근거를 선택합니다.

### IP 및 Domain 분석

![Endpoint egress topology와 IP 및 Domain 상관관계를 분석하는 화면](assets/demo/05-ip-domain-correlation.png)

Endpoint의 외부 통신 관계를 비교하고, 관측된 IP 또는 Domain을 기준으로 관련 근거를 조회합니다.

### 운영 및 Archive 관리

![수집 및 탐지 파이프라인 상태와 Archive 조회 범위를 관리하는 화면](assets/demo/06-operations-archive.png)

Collector, Kafka, Worker, 저장소 상태를 점검하고 Endpoint와 기간을 지정해 Archive 복원 범위를 관리합니다.

## 프로젝트 소개

OWLBY는 단일 조직 환경을 대상으로 만든 Endpoint Detection & Response 프로젝트입니다.

Windows와 macOS Agent가 프로세스, 네트워크, 파일, DNS, L7 이벤트를 수집하고 탐지 결과를 대시보드에서 보여줍니다. 원본 패킷은 저장하지 않고 분석에 필요한 메타데이터만 수집합니다.

## 주요 기능

- Windows C++ Agent와 macOS Swift Agent
- HTTPS와 mTLS 기반 Agent 인증
- Kafka 기반 이벤트 수집 파이프라인
- RuleV1 YAML 기반 탐지 규칙
- MITRE ATT&CK 전술 및 기술 매핑
- Alert와 Incident 자동 생성
- Endpoint 상태와 위험도 조회
- 이벤트, 경고, 인시던트 통합 대시보드
- 실패 이벤트 저장 및 수동 재처리

## 시스템 구성

```text
Windows / macOS Agent
        │ HTTPS + mTLS
        ▼
 FastAPI Collector
        │
        ▼
Kafka telemetry.raw
        │
        ▼
Event Storage Worker ──────> ClickHouse
        │
        ▼
Kafka telemetry.validated
        │
        ▼
 Detection Worker ─────────> PostgreSQL
                                  │
Dashboard ──> Dashboard API ──────┘
```

## 기술 스택

| 구분 | 기술 |
| --- | --- |
| Agent | C++20, Swift, SQLite |
| Frontend | React, TypeScript, Vite, TanStack Query |
| Backend | Python, FastAPI, Uvicorn |
| Event Pipeline | Apache Kafka |
| Detection | RuleV1 YAML, MITRE ATT&CK |
| Database | PostgreSQL, ClickHouse |
| Object Storage | MinIO, Amazon S3 |
| Infrastructure | Docker Compose, Nginx |

## 실행 방법

### 준비 사항

- Docker Desktop

### 전체 개발환경 실행

```powershell
docker compose up -d --build --wait
```

이 명령 하나로 PostgreSQL, ClickHouse, Kafka, MinIO, 초기화 작업, FastAPI, 세 Worker, React 개발 서버와 Nginx를 같은 Compose 프로젝트에서 실행한다. Backend·Worker·Frontend를 호스트 프로세스로 따로 실행하지 않는다.

접속 주소:

- Dashboard: http://127.0.0.1:8080
- Swagger: http://127.0.0.1:8080/docs
- Collector: https://127.0.0.1:8443 (mTLS 전용)
- MinIO Console: http://127.0.0.1:59001

최초 실행 시 관리자 계정은 `runtime/demo/credentials.json`, 로컬 Agent 인증서는 `runtime/compose/cert-authority/agents/compose-demo-agent`에 생성된다. 두 경로는 Git에 포함하지 않는다.

상태 확인과 종료:

```powershell
docker compose ps
docker compose down
```

`docker compose down`은 데이터 volume을 보존한다. Python 3.12/3.13이 설치된 개발자는 동일 작업을 wrapper로 실행할 수도 있다.

```powershell
py -3.13 -m tools.local_demo up
py -3.13 -m tools.local_demo status
py -3.13 -m tools.local_demo down
```

### 실제 배포 서버 경계

로컬 Compose 컨테이너 개수와 실제 배포 서버 개수는 별개다. 실제 배포는 다음 7개 경계로 분리한다.

| 서버 경계 | 배포 컴포넌트 | 로컬 Compose 대응 |
| --- | --- | --- |
| Edge/API | Nginx + FastAPI | `nginx`, `backend` |
| Event Broker | Kafka | `kafka` |
| Worker | Event Storage Worker + Detection Worker + Storage Lifecycle Worker | `event-storage-worker`, `detection-worker`, `storage-lifecycle-worker` |
| Relational DB | PostgreSQL | `postgres` |
| Event DB | ClickHouse | `clickhouse` |
| Frontend | Vercel | 로컬에서만 `frontend` 컨테이너 |
| Object Storage | Amazon S3 | 로컬에서는 `minio` |

### 실제 Endpoint 상시 연결

Agent는 실행될 때 중앙 Collector에 자동 등록·재등록하고, 실행 중 수집한 Event와 heartbeat를 중앙 서버로 전송한다. `--once`는 1회 검증용이므로 상시 운영에서는 사용하지 않는다. 인증서 발급, 설정 파일과 권한 준비는 [중앙 Endpoint 실제 데이터 검증](docs/operations/CENTRAL_ENDPOINT_REAL_DATA_VALIDATION.md)을 먼저 따른다.

설정의 `collectorBaseUrl`은 로컬 주소가 아니라 중앙 Collector를 지정해야 한다.

```text
https://<COLLECTOR_HOST>:8443/api/v1
```

#### Windows Service

Release 실행파일과 필요한 runtime DLL을 `C:\Program Files\EDR-C-Agent`에 배치하고, 설정과 인증서는 `C:\ProgramData\EDR-C-Agent`에 둔다. 관리자 PowerShell에서 서비스를 등록한다.

```powershell
New-Service `
  -Name 'EDR-C-Agent' `
  -BinaryPathName '"C:\Program Files\EDR-C-Agent\edr-windows-agent.exe" --service' `
  -DisplayName 'EDR-C Agent' `
  -StartupType Automatic

Start-Service EDR-C-Agent
Get-Service EDR-C-Agent
```

중지하거나 서비스 등록을 제거할 때는 다음 명령을 사용한다.

```powershell
Stop-Service EDR-C-Agent
sc.exe delete EDR-C-Agent
```

#### macOS LaunchDaemon

Release binary를 plist가 가리키는 위치에 설치한다.

```bash
cd agents/macos
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift build -c release

sudo install -d -m 755 /usr/local/libexec
sudo install -m 755 .build/release/edr-macos-agent /usr/local/libexec/edr-macos-agent
sudo install -d -o root -g wheel -m 700 "/Library/Application Support/EDR-C-Agent"
sudo install -o root -g wheel -m 600 /absolute/path/to/config.json \
  "/Library/Application Support/EDR-C-Agent/config.json"
sudo install -o root -g wheel -m 600 /absolute/path/to/agent.key \
  "/Library/Application Support/EDR-C-Agent/agent.key"
sudo install -o root -g wheel -m 644 /absolute/path/to/agent.crt \
  "/Library/Application Support/EDR-C-Agent/agent.crt"
sudo install -o root -g wheel -m 644 /absolute/path/to/ca.crt \
  "/Library/Application Support/EDR-C-Agent/ca.crt"
sudo install -o root -g wheel -m 644 \
  com.edr-c.agent.plist \
  /Library/LaunchDaemons/com.edr-c.agent.plist

sudo launchctl bootstrap system /Library/LaunchDaemons/com.edr-c.agent.plist
sudo launchctl kickstart -k system/com.edr-c.agent
sudo launchctl print system/com.edr-c.agent
```

`config.json`의 인증서·private key·state 경로는 위 설치 위치의 절대 경로로 설정한다. LaunchDaemon은
`tcpdump` 권한 때문에 현재 전체 프로세스를 root로 실행하므로 config/private key/state는 root 전용 권한을
강제하며 plist는 `umask 077`을 적용한다. 별도 packet-capture helper로 권한을 분리하는 구조는 아직 구현하지
않았다. 등록을 제거할 때는 다음 명령을 사용한다.

```bash
sudo launchctl bootout system /Library/LaunchDaemons/com.edr-c.agent.plist
sudo rm /Library/LaunchDaemons/com.edr-c.agent.plist
```

설치 후 [운영 Dashboard](https://tukproject.dev)에 로그인해 다음을 확인한다.

- `Endpoints`에서 Agent ID가 `ONLINE`인지 확인
- `Events`에서 실행 직후 실제 Event가 들어오는지 확인
- Agent 재시작 후 동일 Endpoint로 재등록되는지 확인
- Agent를 중지했을 때 2분 뒤 `OFFLINE`이 되고 기존 Event는 유지되는지 확인

## 시연 데이터

대시보드 확인에 사용할 데이터를 생성합니다.

```powershell
uv run --env-file .env python .\tests\seed_frontend_qa.py --confirm-reset
```

이 명령은 기존 로컬 데이터베이스를 초기화합니다. 모든 destructive seed는 `EDR_ENV=local|qa`,
허용된 demo database 이름, local host 또는 `EDR_SEED_ALLOWED_QA_HOSTS`에 정확히 명시한 QA host를 함께 확인합니다.

```text
ADMIN
frontend-admin
frontend-admin-password
```

### 7~31일 다중 Endpoint 시연 데이터

Overview의 장기 추세, Endpoint 목록, Intelligence Topology, Alert/Incident 분포를 확인하려면 먼저 생성 규모를
미리 봅니다. `--dry-run`은 데이터베이스를 변경하지 않습니다.

```powershell
uv run --env-file .env python -m tools.seed_dashboard_long_range `
  --days 7 `
  --endpoints 20 `
  --events-per-endpoint-day 100 `
  --seed 20260715 `
  --dry-run
```

확인한 규모로 실제 시드 데이터를 생성합니다. 이 명령은 기존 로컬 PostgreSQL과 ClickHouse QA 데이터를
초기화하므로 `--confirm-reset`을 명시해야 합니다.

```powershell
uv run --env-file .env python -m tools.seed_dashboard_long_range `
  --days 7 `
  --endpoints 20 `
  --events-per-endpoint-day 100 `
  --seed 20260715 `
  --confirm-reset
```

기본 예시는 20개 Endpoint, 약 14,000개 Event, 280개 Alert, 40개 Incident와 Failure/Storage 상태를 만든다.
생성 후 Dashboard에서 `최근 7일`을 선택하고 다음 계정으로 로그인합니다.

```text
ADMIN  frontend-admin / frontend-admin-password
VIEWER frontend-viewer / frontend-viewer-password
```

## 팀원 소개

|                     황 건 하                      |                     박 소 연                      |                     이 혜 령                      |                     이 주 호                      |
| :--------------------------------------------: | :--------------------------------------------: | :--------------------------------------------: | :--------------------------------------------: |
| <img src="assets/team/04-hwang-geonha.jpg" width="180" alt="황건하"> | <img src="assets/team/01-park-soyeon.jpg" width="180" alt="박소연"> | <img src="assets/team/03-lee-hyeryeong.jpg" width="180" alt="이혜령"> | <img src="assets/team/02-lee-juho.jpg" width="180" alt="이주호"> |
| [@altius03](https://github.com/altius03) | [@yoskrap](https://github.com/yoskrap) | [@hyernglee](https://github.com/hyernglee) | [@coder072](https://github.com/coder072) |
|              Team Leader<br>Full Stack              |                Full Stack<br>DevOps                |               Frontend<br>Design               |                    Backend                     |
