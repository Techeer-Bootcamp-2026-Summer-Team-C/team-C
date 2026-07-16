# EDR_C

Windows와 macOS 엔드포인트의 보안 이벤트를 수집하고 탐지 결과를 대시보드에서 확인하는 EDR PoC

## 프로젝트 소개

EDR_C는 단일 조직 환경을 대상으로 만든 Endpoint Detection & Response 프로젝트입니다.

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

이 명령 하나로 PostgreSQL, ClickHouse, Kafka, MinIO, 초기화 작업, FastAPI, 두 Worker, React 개발 서버와 Nginx를 같은 Compose 프로젝트에서 실행한다. Backend·Worker·Frontend를 호스트 프로세스로 따로 실행하지 않는다.

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
| Worker | Event Storage Worker + Detection Worker | `event-storage-worker`, `detection-worker` |
| Relational DB | PostgreSQL | `postgres` |
| Event DB | ClickHouse | `clickhouse` |
| Frontend | Vercel | 로컬에서만 `frontend` 컨테이너 |
| Object Storage | Amazon S3 | 로컬에서는 `minio` |

## 시연 데이터

대시보드 확인에 사용할 데이터를 생성합니다.

```powershell
uv run --env-file .env python .\tests\seed_frontend_qa.py
```

이 명령은 기존 로컬 데이터베이스를 초기화합니다.

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
