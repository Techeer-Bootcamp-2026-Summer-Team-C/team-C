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

- Python 3.12 또는 3.13
- uv
- Docker Desktop
- Node.js와 npm
- OpenSSL

### Windows PowerShell

```powershell
py -3.13 -m tools.local_demo up
```

### macOS / Linux

```bash
python3 -m tools.local_demo up
```

실행이 완료되면 터미널에 관리자 계정과 비밀번호가 출력됩니다.

- Dashboard: http://127.0.0.1:5173
- Swagger: http://127.0.0.1:8000/docs

상태 확인과 종료:

```powershell
py -3.13 -m tools.local_demo status
py -3.13 -m tools.local_demo down
```

## 시연 데이터

대시보드 확인에 사용할 데이터를 생성합니다.

```powershell
uv run --env-file .env python .\tests\seed_frontend_qa.py
```

이 명령은 기존 로컬 데이터베이스를 초기화합니다.

```text
ADMIN
frontend-admin@example.com
frontend-admin-password
```
