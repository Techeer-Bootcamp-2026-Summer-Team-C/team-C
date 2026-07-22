# EDR_C 최종 발표 공동 기획서

- 작성일: 2026-07-21
- 발표 시간: 약 8분
- 대상 청중: 시니어·수석 개발자, 주니어 개발자, 교수, 기업 관계자, 학생 개발자
- 문서 목적: 발표 방향, 영상, 시연, 기술 설명, 트러블슈팅, 역할 분담을 팀 전체가 같은 기준으로 준비하기 위한 공유 문서

> 이 문서는 발표 대본의 최종본이 아니다. 팀이 합의한 발표 전략과 사실 관계를 고정하는 기준 문서이며, 슬라이드와 대본은 이 문서를 바탕으로 별도 제작한다.

작성 원칙:

- 현재 구현 코드를 최우선 source of truth로 사용한다.
- 설계 문서와 코드가 다르면 코드의 현재 동작을 발표 기준으로 삼고 불일치는 별도 해결한다.
- QA 시드가 만든 화면과 실제 Worker가 생성하는 결과를 구분한다.
- 아직 구현하지 않은 기능은 발표 성과가 아니라 현재 한계 또는 후속 범위로 표시한다.

## 1. 발표 목표

발표가 끝났을 때 청중에게 다음 인상을 남기는 것을 목표로 한다.

- 기술적으로 완성도가 높은 프로젝트다.
- 기능만 나열하지 않고 문제와 해결 과정을 명확하게 설명한 팀이다.
- Endpoint 수집부터 비동기 처리, 탐지, 저장, 조사 Dashboard까지 실제로 연결했다.
- 성능뿐 아니라 보안 분석 결과의 정확성과 시스템 한계까지 검토했다.

발표 전체를 관통하는 핵심 문장은 다음과 같다.

> 수많은 Endpoint Event를 빠르게 처리하면서도, 잘못된 공격 관계를 만들지 않는 EDR을 구현했다.

마지막에는 다음 문장으로 의미를 회수한다.

> 저희는 단순히 위험을 경고하는 시스템이 아니라, 수많은 Endpoint Event를 빠르고 정확하게 연결해 무슨 일이 일어났는지 설명할 수 있는 EDR을 구현했습니다.

## 2. 발표 구성 원칙

### 2.1 서로 다른 청중을 동시에 만족시키는 방법

- 기업 관계자·교수에게는 프로젝트의 문제와 가치가 먼저 보여야 한다.
- 주니어·학생 개발자에게는 `Event → Alert → Incident` 흐름이 직관적으로 보여야 한다.
- 시니어·수석 개발자에게는 기술 선택의 이유, trade-off, 검증 근거, 현재 한계를 숨기지 않아야 한다.
- 전문 용어를 많이 나열하는 대신, 하나의 공격 시나리오를 따라가며 필요한 기술을 설명한다.

### 2.2 설명과 시연의 배치

발표는 `짧은 설명 → 시연 → 깊은 기술 설명`의 혼합 구조를 사용한다.

1. 시연 전에 EDR 개념과 큰 데이터 흐름만 설명한다.
2. 시연 중에는 사용자와 분석가의 관점에 집중한다.
3. 시연 후에는 방금 본 결과가 내부에서 어떻게 만들어졌는지 Kafka와 저장소 구조를 중심으로 설명한다.

시연 중에 Kafka topic, offset, DB query 같은 내부 구현을 동시에 설명하지 않는다. 조작과 상세 설명이 겹치면 청중의 시선이 분산되고 발표자가 시간을 통제하기 어려워진다.

## 3. 8분 권장 타임라인

| 구간 | 시간 | 누적 | 목적 |
| --- | ---: | ---: | --- |
| 인트로 영상 | 25초 | 0:25 | 공격 상황에 대한 관심 유도 |
| EDR 개념 소개 | 25초 | 0:50 | 비전공·비보안 청중의 이해 확보 |
| EDR_C 소개와 큰 흐름 | 30초 | 1:20 | 프로젝트 범위와 차별점 제시 |
| 라이브 시연 | 1분 40초 | 3:00 | 실제 동작과 조사 경험 증명 |
| 전체 아키텍처 | 20초 | 3:20 | 구현 범위와 구성요소 조망 |
| Kafka 상세 | 50초 | 4:10 | 핵심 기술 선택과 처리 경계 설명 |
| ClickHouse·PostgreSQL 역할 | 25초 | 4:35 | 저장소 분리 이유 설명 |
| 트러블슈팅 1: 성능 | 1분 | 5:35 | 실측 성과와 병목 해결 과정 증명 |
| 트러블슈팅 2: 정확성 | 1분 | 6:35 | 보안 분석의 정확성 개선 증명 |
| 범위·한계·결과 | 40초 | 7:15 | 과장 없는 현재 완성도 제시 |
| 인트로 회수와 결론 | 30초 | 7:45 | 발표 메시지 회수 |
| 전환 여유 | 15초 | 8:00 | 영상·페이지 이동 지연 흡수 |

리허설에서는 7분 30초~7분 45초에 본문이 끝나도록 맞춘다. 실제 발표에서는 영상 재생, 브라우저 이동, 청중 반응으로 시간이 더 소요될 수 있다.

## 4. 인트로 영상

### 4.1 콘셉트

팀원의 초등학생 시절 컴퓨터로 돌아간다는 설정으로 시작한다. 게임을 무료로 받을 수 있다는 말에 출처를 알 수 없는 설치 파일을 실행하고, 겉으로는 아무 변화가 없지만 백그라운드에서 의심 행위가 발생하는 상황을 보여준다.

이 이야기는 실제 경험이라고 주장하지 않는다. 영상 또는 슬라이드 한쪽에 다음 문구를 표시한다.

> 시연을 위해 재구성한 가상 시나리오

실제 게임, 실제 불법 사이트, 실제 악성코드 브랜드는 사용하지 않는다. 가상의 게임과 다운로드 페이지를 사용한다.

### 4.2 20~25초 스토리보드

| 시간 | 화면 | 의도 |
| ---: | --- | --- |
| 0~4초 | 어린 시절 느낌의 컴퓨터와 게임 검색 | 개인적이고 이해하기 쉬운 진입점 |
| 4~8초 | 출처가 불분명한 설치 파일 다운로드 | 위험한 행동 제시 |
| 8~12초 | 파일 실행, 화면에는 별다른 변화 없음 | 보이지 않는 공격 강조 |
| 12~18초 | Encoded PowerShell 실행과 외부 암호화 통신을 시각화 | 실제 데모 시나리오 연결 |
| 18~23초 | 화면 정지와 질문 표시 | 발표자에게 전환 |

영상 마지막 질문:

> 이 컴퓨터에서는 무슨 일이 일어난 걸까요?

영상에는 Dashboard를 미리 노출하지 않는다. 공격 상황은 영상이 담당하고, 분석 결과는 이후 라이브 시연에서 처음 공개한다.

### 4.3 영상 운영 방식

- 영상은 효과음과 화면 연출 중심으로 제작한다.
- 마지막 질문 이후부터 발표자가 직접 말한다.
- 영상 파일은 발표 PC에 로컬로 저장하고, 동일 파일을 USB 또는 별도 저장소에도 백업한다.
- 자동 재생, 음량, 화면 비율, 발표 프로그램 전환 시간을 리허설에서 확인한다.

## 5. EDR과 EDR_C 소개

### 5.1 EDR 개념 설명

인트로 영상 직후 EDR을 먼저 설명한다. 청중 전체가 EDR이라는 용어를 알고 있다고 가정하지 않는다.

권장 설명:

> EDR은 Endpoint Detection and Response의 약자로, PC와 같은 단말에서 발생하는 행위를 지속해서 관찰하고 위협을 탐지·조사·대응하는 보안 시스템입니다. 전통적인 백신이 악성 파일의 차단에 집중했다면, EDR은 공격 전후의 행위를 연결해 무슨 일이 일어났는지 파악하는 데 초점을 둡니다.

현대 백신과 EDR의 기능은 일부 겹칠 수 있으므로 “백신은 파일만 보고 EDR은 행위만 본다”처럼 절대적으로 구분하지 않는다.

### 5.2 EDR_C 한 문장 소개

> EDR_C는 Windows와 macOS Endpoint에서 발생하는 행위를 수집하고, 탐지된 위협을 Alert와 Incident로 연결하여 공격 흐름과 대응 근거를 제공하는 EDR 시스템입니다.

### 5.3 프로젝트 범위

```text
Windows·macOS Endpoint
프로세스·네트워크·파일·DNS·L7 Event 수집
              ↓
RuleV1 탐지 + MITRE ATT&CK 매핑
              ↓
Alert 생성·Incident 연결
              ↓
Dashboard에서 공격 흐름과 대응 근거 조사
```

프로젝트 소개 단계에서는 Kafka, ClickHouse, PostgreSQL의 상세 선정 이유를 설명하지 않는다. 먼저 사용자가 보는 입력과 결과를 이해시킨다.

## 6. 대표 공격 시나리오와 구현 경계

인트로 영상의 공격 상황은 다음으로 유지한다.

> Endpoint에서 출처를 알 수 없는 파일을 실행한 뒤 인코딩된 PowerShell 명령과 암호화된 외부 통신이 관찰된다.

관련 탐지 규칙:

- `PROC_POWERSHELL_ENCODED`: Encoded PowerShell command detected
- `NET_SUSPICIOUS_EGRESS`: Suspicious encrypted egress detected

### 6.1 현재 Detection Worker의 실제 correlation 방식

현재 Detection Worker는 RuleV1이 만든 `(endpoint_id, correlation_key, window_start_at)`을 기준으로 Incident를 UPSERT하고 해당 Rule의 Alert를 연결한다.

- `PROC_POWERSHELL_ENCODED`
  - `correlation_key: suspicious-powershell`
  - `window_seconds: 1800`
- `NET_SUSPICIOUS_EGRESS`
  - `correlation_key: suspicious-egress`
  - `window_seconds: 1800`

두 Rule은 correlation key가 다르다. 따라서 현재 구현은 PowerShell Alert와 encrypted egress Alert를 자동으로 하나의 Incident에 합치지 않는다. 두 신호를 같은 공격으로 자동 연결하는 cross-rule correlation은 현재 구현 범위가 아니다.

### 6.2 코드 기준 권장 시연

한 Incident에 여러 Alert가 연결되는 모습을 보여주려면 다음 시나리오를 사용한다.

```text
동일 Endpoint
→ 30분 window 안에서 Encoded PowerShell Event가 두 번 발생
→ PROC_POWERSHELL_ENCODED Alert 두 개 생성
→ 동일 suspicious-powershell Incident에 연결
```

암호화된 외부 통신은 같은 Endpoint에서 관찰된 별도의 탐지 결과로 보여줄 수 있지만, PowerShell Incident에 자동 연결됐다고 말하지 않는다.

### 6.3 현재 QA 시드 주의사항

`tests/seed_frontend_qa.py`는 발표 화면을 만들기 위해 다음 두 Alert를 `incident_alerts`에 직접 삽입한다.

- Alert 1: `PROC_POWERSHELL_ENCODED`
- Alert 2: `NET_SUSPICIOUS_EGRESS`

그러나 실제 Detection Worker는 두 Rule의 서로 다른 correlation key 때문에 이 연결을 자동 생성하지 않는다. 현재 QA fixture의 화면을 그대로 사용해 “Detection Worker가 두 신호를 자동으로 하나의 Incident로 묶었다”고 설명하면 구현과 다른 발표가 된다.

최종 시연 전 다음 중 하나를 수행해야 한다.

1. 실제 Worker 동작과 일치하도록 같은 Rule의 반복 탐지 fixture를 준비한다.
2. 현재 fixture를 사용한다면 수동으로 구성한 QA 관계라고 명시하고 자동 correlation 성과로 설명하지 않는다.

이 발표는 구현 코드를 기준으로 하므로 1번을 권장한다.

## 7. 라이브 시연 계획

### 7.1 기본 원칙

- 인트로 영상이 공격 발생을 보여주고, 라이브 시연은 분석 결과를 보여준다.
- 목데이터는 발표 전에 미리 생성한다.
- 발표 중 Event가 들어오기를 기다리거나 Kafka 처리 완료 시간을 기다리지 않는다.
- 라이브 조작과 동일한 흐름을 녹화한 백업 영상을 준비한다.
- 시연 화면은 새로고침, 로그인, 긴 검색 입력을 최소화한다.

### 7.2 권장 클릭 동선

#### 1) Overview — 약 10초

확인할 내용:

- 수집된 Event와 Alert
- Endpoint 상태
- 전체 보안 상태

권장 멘트:

> 영상에서 발생한 행위는 Endpoint Agent를 통해 Event로 수집됐고, 현재 Dashboard에 보안 신호로 반영됐습니다.

#### 2) Incident 목록 — 약 10초

`Encoded PowerShell command detected` Incident를 선택한다.

권장 멘트:

> 분석가는 수많은 Event를 하나씩 보는 대신, 관련 위협이 묶인 Incident부터 조사합니다.

#### 3) Incident 상세 — 약 25초

확인할 내용:

- 같은 Endpoint에서 발생한 Encoded PowerShell Alert들
- 같은 `suspicious-powershell` correlation key와 30분 window
- 동일 Incident에 연결된 여러 Alert

권장 멘트:

> 같은 Endpoint에서 30분 안에 반복된 Encoded PowerShell 탐지는 각각 Alert로 기록되지만, 같은 correlation key를 사용해 하나의 Incident에서 조사할 수 있습니다.

암호화된 외부 통신 Alert를 함께 보여줄 때는 별도 correlation key로 생성된 별도 Incident라고 설명한다. 최종 리허설에서는 실제 Detection Worker의 결과, 시연 fixture, 발표 멘트가 정확히 일치하는지 확인한다.

#### 4) Investigation Graph — 약 30초

확인할 내용:

- Incident → Alert → Event → Process → Destination 관계
- Process와 외부 Destination 선택
- Inspector 또는 Evidence 영역

권장 멘트:

> 그래프의 관계는 화면을 꾸미기 위해 추측해서 만든 것이 아니라, 실제로 관찰된 Event와 연결 정보를 근거로 구성했습니다.

#### 5) Alert 상세·Response Guidance — 약 20초

확인할 내용:

- 원본 Event 연결
- MITRE ATT&CK tactic·technique
- RuleV1에 정의된 Response Guidance

권장 멘트:

> 탐지 결과에는 MITRE ATT&CK 정보와 함께 분석가가 다음으로 확인해야 할 대응 절차도 제공됩니다.

#### 6) 기술 설명으로 전환 — 약 5초

> 지금까지가 사용자가 보는 공격 조사 과정입니다. 이제 이 결과가 내부에서 어떻게 만들어졌는지 설명드리겠습니다.

### 7.3 시연 데이터 준비

로컬 QA 시드 명령은 기존 PostgreSQL과 ClickHouse QA 데이터를 초기화한다. 발표 전용 로컬 환경에서만 실행하고 운영 환경에는 실행하지 않는다.

```powershell
uv run --env-file .env python .\tests\seed_frontend_qa.py
```

장기 Dashboard 데이터가 필요하면 먼저 `--dry-run`으로 규모를 확인한다.

```powershell
uv run --env-file .env python -m tools.seed_dashboard_long_range `
  --days 7 `
  --endpoints 20 `
  --events-per-endpoint-day 100 `
  --seed 20260715 `
  --dry-run
```

실제 시드에는 DB 초기화를 승인하는 `--confirm-reset`이 필요하다. 발표 직전에는 데이터 재생성보다 검증된 snapshot을 유지하는 편이 안정적이다.

## 8. 전체 아키텍처 설명

전체 아키텍처 슬라이드는 약 20초만 사용한다. 목적은 모든 세부 기술을 설명하는 것이 아니라, Endpoint부터 Dashboard까지 구현 범위를 보여주는 것이다.

권장 멘트:

> 저희는 Endpoint 수집부터 비동기 처리, 탐지, 저장, 조사 Dashboard까지 전체 EDR 흐름을 구현했습니다.

### 8.1 발표용 아키텍처 이미지 수정 사항

현재 공유된 PNG는 발표 자료의 기반으로 사용하되, 최종본 제작 전에 다음 내용을 현재 구현과 일치하도록 수정한다.

- Endpoint의 Python 아이콘을 Windows C++20 Agent와 macOS Swift Agent로 교체
- `Kafka Table Engine` 제거
- Kafka와 ClickHouse 사이에 Event Storage Worker 추가
- `telemetry.raw`와 `telemetry.validated` 흐름 분리
- ClickHouse와 S3 사이에 Storage Lifecycle Worker 추가
- Dashboard API와 Collector를 별도 microservice처럼 보이기보다 하나의 FastAPI Backend 내부 논리 모듈로 표현
- Endpoint → Nginx 구간에 `HTTPS + mTLS` 표시
- 운영 Frontend는 Vercel, 로컬에서만 Docker 컨테이너라는 경계 표시
- Grafana, Slack, GitHub Actions는 핵심 데이터 흐름과 분리하여 점선으로 표시

정확한 핵심 흐름:

```text
Windows/macOS Agent
→ Nginx(mTLS)
→ FastAPI Collector
→ Kafka telemetry.raw
→ Event Storage Worker
→ ClickHouse
→ Kafka telemetry.validated
→ Detection Worker
→ PostgreSQL Alert/Incident
→ FastAPI Dashboard API
→ React Dashboard
```

Archive 흐름:

```text
ClickHouse
→ Storage Lifecycle Worker
→ Parquet/ZSTD
→ Amazon S3
```

## 9. Kafka 핵심 기술 설명

전체 아키텍처와 Kafka 상세 슬라이드는 분리한다. Kafka 상세는 약 50초를 사용하며, 기술 설명에서 가장 큰 비중을 둔다.

### 9.1 해결하려던 문제

저장과 탐지를 Collector 요청 안에서 모두 동기 처리하면 ClickHouse나 탐지 엔진의 지연이 Agent 수집 요청까지 전파된다.

```text
Agent 요청
→ Event 저장
→ 탐지
→ Alert 생성
→ 응답
```

Kafka를 수집과 후속 처리의 경계로 사용해 다음 구조로 분리했다.

```text
Collector
   │
   ▼
Kafka telemetry.raw
   │
   ▼
Event Storage Worker ──→ ClickHouse
   │
   ▼
Kafka telemetry.validated
   │
   ▼
Detection Worker ──→ PostgreSQL
```

### 9.2 설명할 설계 판단

#### Broker ACK 경계

Collector는 Kafka broker ACK를 받은 Event만 `acceptedEventIds`에 포함한다. 이 ACK는 ClickHouse 저장이나 탐지 완료를 의미하지 않는다. Agent는 broker가 수락한 Event를 로컬 SQLite ACK buffer에서 제거할 수 있고, 후속 저장·탐지는 Worker가 비동기로 처리한다.

#### 두 Topic을 분리한 이유

- `telemetry.raw`: Collector가 받은 Event의 비동기 처리 시작점
- Event Storage Worker: identity·payload 검증, 중복 판단, ClickHouse 저장
- `telemetry.validated`: 저장·검증 단계를 통과한 Event를 Detection Worker에 전달

따라서 Detection Worker는 Collector 요청 본문을 바로 탐지하지 않고, 저장·검증 경계를 통과한 Event를 처리한다.

#### Endpoint 단위 순서

Collector와 Event Storage Worker는 `endpointId`를 Kafka key로 사용한다. 같은 Endpoint의 Event는 같은 partition으로 라우팅되어 해당 partition 안의 순서를 유지한다.

#### at-least-once와 멱등성

Kafka consumer는 auto commit을 사용하지 않고 처리 결과에 따라 offset을 수동 commit한다. 재처리 과정에서 같은 메시지가 다시 전달될 수 있으므로 exactly-once라고 주장하지 않는다.

- Event는 동일 `eventId`와 동일 identity·payload이면 논리적 중복을 만들지 않는다.
- 동일 `eventId`인데 identity 또는 payload가 다르면 conflict failure로 처리한다.
- Alert는 `(event_id, rule_code, rule_version)`으로 멱등 생성한다.
- Kafka producer는 idempotence를 활성화한다.
- Failure Sink가 실패하면 offset을 commit하지 않고 해당 메시지 위치로 rewind한다.

권장 한 문장:

> Kafka는 at-least-once 방식이기 때문에 메시지가 다시 전달될 수 있습니다. 따라서 Event와 Alert에 멱등성을 적용해 재처리되더라도 논리적 중복이 생기지 않도록 설계했습니다.

#### 확장성 표현

다음처럼 표현한다.

> Kafka partition 수 범위에서 Event Storage Worker와 Detection Worker를 독립적으로 확장할 수 있도록 구성했습니다.

자동 scaling이나 무제한 확장을 구현했다고 말하지 않는다. 현재 로컬 Compose는 각 Worker를 1개씩 실행한다.

### 9.3 Kafka partition 문서 불일치

발표 전 해결해야 할 정합성 문제다.

- 현재 `backend/kafka.py` 기본값: topic당 2 partitions
- 현재 `compose.yaml` 기본값: topic당 2 partitions
- `docs/architecture/TECH_STACK.md`: 최소 3 partitions라고 기록

코드와 문서 중 어느 값을 최종 기준으로 할지 팀이 결정하고 문서를 맞춰야 한다. 정리 전까지 발표에서는 특정 partition 개수를 말하지 않고 “설정된 partition 수 범위에서 확장”이라고 표현한다.

로컬 replication factor는 1이므로 로컬 구성을 고가용성 Kafka cluster라고 설명하지 않는다.

## 10. ClickHouse·PostgreSQL 역할 분리

Kafka 설명 이후 약 25초 동안 저장소 선택 이유를 설명한다.

| 저장소 | 담당 데이터 | 선정 이유 |
| --- | --- | --- |
| ClickHouse | 대량 Event, Event Failure index, 기간 검색과 집계 | append 중심의 대량 Event 분석과 집계 |
| PostgreSQL | 사용자, Endpoint, 인증 키, Alert, Incident, 감사 로그, Archive metadata | 트랜잭션과 상태 변경, 관계 데이터의 정합성 |
| S3 | Archive와 실패 원문 | 장기 보관과 복원 |

권장 멘트:

> 대량 Event의 기간 검색과 집계는 ClickHouse에, 트랜잭션과 상태 변경이 중요한 Alert와 Incident는 PostgreSQL에 저장했습니다.

트러블슈팅 전환 문장:

> 하지만 ClickHouse를 사용한다고 자동으로 빠른 것은 아니었습니다.

## 11. 트러블슈팅 1 — Dashboard 집계 성능

### 11.1 슬라이드 제목

> ClickHouse를 사용했는데 왜 16초가 걸렸을까?

### 11.2 Before

```text
ClickHouse
→ Event를 500건씩 반복 조회
→ raw_payload를 포함한 전체 Row 전송
→ Python에서 total·시간대·Top dimension 집계
```

표시할 수치:

- LATEST_24H: 16.31초
- 24시간 응답 크기: 약 135KB

### 11.3 원인

병목은 ClickHouse 자체가 아니라 다음 구조에 있었다.

- 원본 Event를 애플리케이션으로 반복 전송
- Dashboard에 필요하지 않은 `raw_payload`까지 projection
- Python object 생성과 반복 집계
- Event 수 증가에 따라 DB 왕복, 전송량, 애플리케이션 연산이 함께 증가

### 11.4 After

```text
ClickHouse에서 GROUP BY·ORDER BY·LIMIT
→ Dashboard에 필요한 Column만 조회
→ 집계 결과만 Python으로 전달
```

표시할 수치:

- LATEST_24H: 0.584초
- 24시간 응답 크기: 약 7KB
- 지연 감소: 96.42%
- 속도 향상: 27.93배

가운데 핵심 문구:

> 연산 위치를 Application에서 Database로 이동

### 11.5 발표 멘트 초안

> 처음에는 ClickHouse를 사용하면서도 Event와 raw payload를 애플리케이션으로 가져와 Python에서 집계했습니다. 병목은 데이터베이스 선택이 아니라 불필요한 데이터 이동과 집계 위치에 있었습니다. 집계를 ClickHouse로 옮긴 결과 24시간 조회가 16.31초에서 0.584초로 줄었고, 응답 크기도 약 135KB에서 7KB로 감소했습니다.

결론:

> 빠른 Database를 선택하는 것보다, 데이터를 어디에서 계산할지 결정하는 것이 중요했습니다.

### 11.6 수치 사용 규칙

- 측정 환경은 31일, 100 Endpoint, 248,000 Event 목데이터다.
- production traffic의 P95/P99 결과라고 표현하지 않는다.
- 이후 HOT ClickHouse query가 9개에서 2개로 줄어든 것은 DB round trip 감소다.
- `9 → 2`를 wall-clock 4.5배 개선이라고 말하지 않는다.
- `FINAL`, `ARRAY JOIN`, RESTORED archive scan 비용은 남아 있다.

## 12. 트러블슈팅 2 — IP·Domain 상관분석 정확성

### 12.1 슬라이드 제목

> 검색 결과가 많으면 좋은 상관분석일까?

### 12.2 Before

일반 Event 검색의 부분 문자열 조건을 보안 상관분석에도 사용하면 다음 오탐이 발생할 수 있다.

입력:

```text
yahoo.com
```

결과 예시:

```text
정상  yahoo.com
정상  mail.yahoo.com
오탐  notyahoo.com
오탐  yahoo.com.evil.example
```

DNS Answer를 구조화된 배열이 아니라 문자열처럼 비교하면 IP 관계도 정확하지 않을 수 있다.

### 12.3 원인

- 일반 검색과 상관분석이 같은 부분 일치 semantics를 사용
- Domain label 경계를 고려하지 않음
- `dns_answers_json`의 배열 원소가 아니라 문자열을 비교
- 사용자 편의를 위한 검색 조건과 공격 근거를 만드는 조건을 분리하지 않음

### 12.4 After

- 입력 Domain의 앞뒤 공백 제거
- 소문자 정규화
- 마지막 `.` 제거
- 정확히 같은 Domain 허용
- `.` 경계를 가진 실제 Subdomain만 허용
- DNS Answer는 `JSONExtract(..., 'Array(String)')`와 `has()`로 정확한 배열 원소 비교
- `endpointIds`는 ClickHouse `IN` 조건으로 pushdown
- 외부 DNS가 실패해도 이미 관찰된 Endpoint Event 근거는 유지

### 12.5 발표 멘트 초안

> 초기에는 일반 검색에 사용하던 부분 문자열 조건을 상관분석에도 적용했습니다. 이 경우 yahoo.com을 조회했을 때 notyahoo.com처럼 관계없는 Domain까지 결과에 포함될 수 있었습니다. 보안 분석에서는 이런 오탐이 잘못된 공격 관계로 이어질 수 있습니다. 그래서 일반 검색과 상관분석의 조건을 분리하고, 정확히 같은 Domain 또는 점 경계를 가진 실제 Subdomain만 연결하도록 수정했습니다.

결론:

> 보안 시스템에서는 많이 찾는 것보다, 왜 연결됐는지 설명할 수 있는 정확성이 중요했습니다.

### 12.6 검증 근거

- Domain normalization 단위 테스트
- Domain exact·subdomain boundary query 테스트
- DNS Answer JSON 배열 exact membership 테스트
- Endpoint filter SQL pushdown 테스트
- 실제 ClickHouse integration test에서 `notyahoo.com`, `yahoo.com.evil.example` 제외 확인

이 사례에는 wall-clock 개선 수치가 없다. 성능 개선처럼 표현하지 않고 correctness 개선이라고 명확히 말한다.

## 13. 결론과 인트로 회수

두 번째 트러블슈팅 이후 처음의 게임 다운로드 화면을 다시 보여준다.

권장 멘트:

> 처음 영상 속 컴퓨터에서는 단순히 수상한 파일이 실행된 것이 아니었습니다. 인코딩된 PowerShell 명령이 실행됐고, 이어서 외부 서버와 암호화 통신이 발생했습니다.

화면에 다음 흐름을 겹쳐 표시한다.

```text
Event 관찰
→ Rule에 따른 Alert 탐지
→ Endpoint·correlation key·window 기준 Incident 연결
→ 공격 관계와 대응 근거 제공
```

현재 범위를 솔직하게 밝힌다.

> 현재 버전은 자동 격리나 프로세스 종료 대신 분석가를 위한 대응 가이드까지 제공하며, 실제 원격 대응 자동화는 다음 확장 범위로 남겨두었습니다.

최종 문장:

> 저희는 단순히 위험을 경고하는 시스템이 아니라, 수많은 Endpoint Event를 빠르고 정확하게 연결해 무슨 일이 일어났는지 설명할 수 있는 EDR을 구현했습니다.

## 14. 슬라이드 구성 제안

| 번호 | 슬라이드 | 핵심 요소 |
| ---: | --- | --- |
| 1 | 인트로 영상 | 가상 게임 다운로드와 보이지 않는 공격 |
| 2 | EDR이란? | 경고와 공격 과정 설명의 차이 |
| 3 | EDR_C | 입력 → 탐지 → Incident → 조사 |
| 4 | 라이브 시연 | 별도 슬라이드보다 실제 Dashboard 전환 |
| 5 | 전체 아키텍처 | 전체 구현 범위, 세부 설명 최소화 |
| 6 | Kafka Pipeline | raw → storage → validated → detection |
| 7 | 저장소 역할 | ClickHouse·PostgreSQL·S3 역할 |
| 8 | 성능 트러블슈팅 | Before/After와 실측 수치 |
| 9 | 정확성 트러블슈팅 | Domain 오탐 Before/After |
| 10 | 결론 | 인트로 회수, 빠르고 정확한 EDR |

슬라이드 수는 전환용 화면을 포함해 약 9~10장으로 유지한다. 아키텍처 슬라이드와 Kafka 슬라이드를 합치지 않는다. 별도의 기술 스택 나열 표는 만들지 않는다.

## 15. 표현 규칙

### 15.1 사용해도 되는 표현

- Kafka를 이용해 수집과 저장·탐지 처리를 분리했다.
- partition 수 범위에서 Worker를 독립적으로 확장할 수 있다.
- Kafka의 at-least-once 전달을 고려해 Event와 Alert를 멱등 처리했다.
- ClickHouse는 대량 Event 검색·집계, PostgreSQL은 상태와 트랜잭션 데이터에 사용했다.
- 31일·100 Endpoint·248,000 Event 목데이터에서 Dashboard 24시간 조회가 16.31초에서 0.584초로 감소했다.
- IP·Domain 상관분석에서 Domain boundary와 DNS Answer exact membership을 검증했다.
- 같은 Endpoint·correlation key·window의 Alert를 하나의 Incident에 연결한다.

### 15.2 피해야 하는 표현

- Kafka로 exactly-once를 보장했다.
- Worker가 트래픽에 따라 자동으로 무한 확장된다.
- 로컬 replication factor 1 구성을 고가용성 cluster라고 설명한다.
- Dashboard가 production에서 항상 0.584초다.
- query 수 9→2 감소로 wall-clock이 4.5배 빨라졌다.
- DNS 정확성 개선을 성능 개선 수치처럼 설명한다.
- 가상 인트로를 실제 팀원의 과거 경험이라고 주장한다.
- Response Guidance를 자동 격리·프로세스 종료 기능이라고 설명한다.
- PowerShell과 encrypted egress Alert가 현재 Detection Worker에서 자동으로 하나의 Incident에 합쳐진다고 설명한다.

## 16. 예상 질문과 답변 방향

### 왜 Kafka가 필요한가?

Collector 요청과 저장·탐지 처리를 분리하고, downstream 지연이 Agent 요청에 직접 전파되지 않게 하기 위해 사용했다. `telemetry.raw`와 `telemetry.validated`를 분리해 저장·검증 이후 탐지하는 경계도 만들었다.

### Kafka가 중복 메시지를 전달하면 어떻게 하는가?

at-least-once를 전제로 Event, Alert, Failure 저장 경로에 멱등성을 적용했다. consumer auto commit은 비활성화하고 처리 결과에 따라 수동 commit한다.

### 왜 ClickHouse와 PostgreSQL을 모두 사용했는가?

대량 append Event의 기간 검색·집계와 Alert·Incident의 상태 변경·트랜잭션 요구가 다르기 때문이다.

### 성능 수치는 실제 운영 수치인가?

아니다. 31일·100 Endpoint·248,000 Event 목데이터 환경의 동일 API 전후 측정이다. production P95/P99로 과장하지 않는다.

### EDR과 백신은 완전히 다른가?

현대 제품은 기능이 겹칠 수 있다. 발표에서는 백신의 예방·차단 중심 관점과 EDR의 지속 관찰·조사·대응 중심 관점의 차이를 설명한다.

### 원본 패킷을 저장하는가?

저장하지 않는다. Npcap과 tcpdump를 packet input provider로 사용하되 DNS, HTTP plaintext, TLS metadata 등을 추출한 뒤 원 packet을 폐기한다.

### 자동 대응이 가능한가?

현재는 RuleV1의 Response Guidance를 분석가에게 제공하는 범위다. 원격 격리, 프로세스 종료, 파일 삭제는 현재 구현 범위가 아니다.

### PowerShell과 encrypted egress를 하나의 Incident로 자동 연결하는가?

현재는 아니다. 두 Rule은 서로 다른 correlation key를 사용한다. 현재 Incident UPSERT 기준은 `(endpoint_id, correlation_key, window_start_at)`이며, 같은 key와 window의 반복 탐지만 같은 Incident에 연결된다. cross-rule correlation은 후속 확장 범위다.

### 인트로 사례는 실제인가?

시연을 위해 재구성한 가상 시나리오다. 실제 악성코드 실행이 아니라 검증된 목데이터를 이용해 조사 흐름을 보여준다.

## 17. 역할 분담 제안

| 역할 | 담당 작업 | 완료 기준 |
| --- | --- | --- |
| 발표 총괄 | 시간표와 전체 메시지 관리 | 8분 이내, 중복 설명 없음 |
| 영상 담당 | 20~25초 인트로 제작 | 가상 시나리오 표시, 로컬 재생 검증 |
| 슬라이드 담당 | 약 9~10장 제작 | 한 장 한 메시지, 숫자 출처 표시 |
| 아키텍처 담당 | 공유 PNG 수정·재작성 | 현재 코드 흐름과 일치 |
| Kafka 담당 | 상세 흐름과 Q&A 준비 | ACK·topic·partition·멱등성 설명 가능 |
| 데모 담당 | 목데이터·계정·클릭 동선 준비 | 1분 40초 안에 동일 결과 재현 |
| 검증 담당 | 발표 수치와 기술 주장 교차 확인 | 금지 표현과 문서 불일치 제거 |
| 백업 담당 | 영상·PDF·녹화 데모 준비 | 인터넷 없이 발표 가능 |

발표자가 여러 명이면 화면 전환 시점보다 의미 단위로 역할을 나눈다. 예를 들어 `문제·EDR 소개`, `시연`, `Kafka·DB·트러블슈팅`, `결론` 단위가 자연스럽다.

## 18. 발표 전 체크리스트

### 콘텐츠

- [ ] 인트로 영상에 가상 시나리오 표기
- [ ] EDR 설명이 25초 이내인지 확인
- [ ] EDR_C 한 문장 소개 통일
- [ ] 성능 수치에 목데이터 환경 표시
- [ ] DNS 개선을 correctness로 표현
- [ ] 현재 한계와 확장 범위 한 문장 포함

### 아키텍처

- [ ] Python Endpoint 아이콘을 C++·Swift로 교체
- [ ] Kafka Table Engine 제거
- [ ] Event Storage Worker와 Detection Worker 표시
- [ ] `telemetry.raw`와 `telemetry.validated` 표시
- [ ] Storage Lifecycle Worker와 S3 Archive 표시
- [ ] Vercel·Docker·AWS 경계 수정
- [ ] Kafka partition 수의 코드·문서 불일치 해결

### 데모

- [ ] 발표 전 목데이터 생성 완료
- [ ] 같은 Rule·correlation key·window의 Alert 두 개가 동일 Incident에 연결되는지 확인
- [ ] Incident 안의 여러 Alert가 같은 Rule·correlation key·window에서 실제 Worker 동작으로 생성됐는지 확인
- [ ] 현재 QA seed의 PowerShell·egress 수동 연결을 자동 correlation으로 설명하지 않는지 확인
- [ ] Investigation Graph와 Evidence 확인
- [ ] Response Guidance 확인
- [ ] 로그인 상태와 브라우저 확대 비율 확인
- [ ] 알림·메신저·자동 업데이트 차단
- [ ] 동일 흐름 녹화 영상 준비
- [ ] 인터넷 없이 사용할 screenshot 준비

### 리허설

- [ ] 전체 본문 7분 45초 이내
- [ ] Kafka 설명 50초 이내
- [ ] 라이브 시연 1분 40초 이내
- [ ] 두 트러블슈팅 각각 1분 이내
- [ ] 발표자 교대 시간 측정
- [ ] 영상 실패 시 즉시 넘어가는 문장 준비
- [ ] Q&A 담당자와 답변 범위 합의

## 19. 근거 자료

- 프로젝트 소개와 실행: `README.md`
- 전체 기술 구조: `docs/architecture/TECH_STACK.md`
- API와 Kafka ACK·멱등성 계약: `docs/contracts/API_SPEC.md`
- 성능 측정과 주의사항: `docs/operations/PERFORMANCE_IMPROVEMENTS_HISTORY.md`
- 시연용 탐지 규칙: `rules/process/proc_powershell_encoded.v1.yaml`, `rules/network/net_suspicious_egress.v1.yaml`
- 시연 데이터: `tests/seed_frontend_qa.py`, `tools/seed_dashboard_long_range.py`
- DNS 정확성 테스트: `tests/test_dns_lookup.py`, `tests/test_storage_integration.py`
- 화면 참고: `docs/frontend/screenshot-gallery/`

## 20. 아직 남은 작업

다음 작업은 기획이 아니라 제작 단계다.

1. 발표자 수와 구간별 담당자 확정
2. 인트로 영상 스토리보드 확정 및 제작
3. 아키텍처 이미지 수정 또는 재작성
4. Kafka 상세 슬라이드 제작
5. 두 Before/After 트러블슈팅 슬라이드 제작
6. 데모용 목데이터 snapshot과 클릭 동선 고정
7. 8분 발표 대본 작성 — `docs/presentation/PRESENTATION_SCRIPT.md`
8. 백업 영상과 PDF 제작
9. 최소 3회 전체 리허설 및 시간 조정
10. Kafka partition 문서 불일치 정리
11. QA seed의 cross-rule 수동 Incident 연결과 실제 Detection Worker correlation 동작 정리
