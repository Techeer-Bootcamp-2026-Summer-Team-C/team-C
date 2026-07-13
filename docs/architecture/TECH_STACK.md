# EDR 기술 스택 정의

## 1. 문서 목적

이 문서는 Windows/macOS 실제 단말 수집부터 탐지, REST API, Dashboard까지 실행 가능한 single-tenant 포트폴리오 EDR PoC의 최종 기술 스택과 책임 경계를 정의한다.

## 2. 문서와 산출물의 책임

| 문서 | 책임 |
| --- | --- |
| `../contracts/API_SPEC.md` | Dashboard와 Agent가 사용하는 REST 계약 |
| `../contracts/RISK_POLICY.md` | Endpoint Risk, Threat Level, Collection Health와 전역 EDR 상태 계산 공식 |
| `../frontend/FRONTEND_SPEC.md` | Frontend route, 화면별 API, query, polling, 인증, 시각 token, component state, responsive와 접근성 |
| `EDR_DATA_MODEL.md` | 저장소별 논리 데이터 모델 |
| `ERD_FINAL.sql` | 한글 설명을 포함한 ERDCloud 업로드용 MySQL 호환 최종 논리 ERD |
| `TECH_STACK.md` | 컴포넌트, 실행환경, 데이터 흐름과 운영 정책 |

`EDR_ARCHITECTURE.excalidraw`는 전체 구조의 편집 가능한 시각 원본이다.

## 3. 전체 서비스 흐름

### 3.1 이벤트 수집·탐지·저장

```text
Windows C++ Agent / macOS Swift Agent
-> OS telemetry + Npcap/tcpdump live packet stream
-> Process/Network/File/DNS/L7 metadata
-> SQLite ACK buffer
-> HTTPS REST + mTLS
-> Nginx
-> Uvicorn / FastAPI Collector
-> Kafka telemetry.raw
-> Event Storage Worker
   -> ClickHouse edr_events
   -> Kafka telemetry.validated
-> Detection Worker
   -> RuleV1 YAML
   -> MITRE ATT&CK mapping
   -> PostgreSQL alerts / incidents

Dashboard
-> Nginx
-> Uvicorn / FastAPI
-> PostgreSQL / ClickHouse / restored archive 조회
-> React Dashboard
```

위험 여부와 관계없이 유효한 raw metadata event는 ClickHouse에 저장한다. Detection Worker가 생성한 Alert와 자동 correlation Incident만 PostgreSQL에 저장한다.

### 3.2 패킷 처리 원칙

Npcap과 tcpdump는 packet input provider다. 원본 PCAP 파일을 만들거나 로컬·S3에 저장하지 않는다.

```text
packet 수신
-> Ethernet/IP/TCP/UDP parsing
-> DNS / HTTP plaintext / TLS ClientHello·certificate metadata 추출
-> NETWORK_CONNECTION / DNS_QUERY / L7_EVENT 생성
-> 원 packet 폐기
```

- TLS payload를 복호화하지 않는다.
- HTTP는 plaintext metadata 중 method, host, query/fragment를 제거한 URL path, status code, user agent만 수집한다. Request/response body, cookie, authorization 및 그 밖의 임의 header는 수집하지 않는다.
- TLS는 수동 복호화 없이 관측 가능한 SNI, version, certificate subject/issuer/SHA-256만 저장한다. TLS 1.3 암호화 handshake 등으로 보이지 않는 SNI·certificate 필드는 nullable이며 누락 자체를 수집 실패로 처리하지 않는다.
- rolling segment, 로컬 2GiB quota, 탐지 전후 upload, S3 PCAP, heartbeat command, artifact API는 사용하지 않는다.

## 4. Agent 수집 범위

### 4.1 공통 event type

| Event type | 내용 |
| --- | --- |
| `PROCESS_EXECUTION` | 프로세스 실행/snapshot metadata |
| `NETWORK_CONNECTION` | 연결 tuple과 프로세스 연결 정보 |
| `FILE_EVENT` | 지정 폴더 파일 변경과 hash |
| `DNS_QUERY` | query, record type, response code, answer metadata |
| `L7_EVENT` | HTTP plaintext 또는 TLS metadata |

PCAP은 event type이 아니라 metadata를 만들기 위한 packet capture 방식이다.

### 4.2 Windows C++ Agent

| 영역 | 구현 |
| --- | --- |
| 언어/빌드 | C++20, CMake, x64 |
| 실행 | Windows Service/CLI, 포트폴리오 profile은 `LocalSystem` |
| Process | Toolhelp32 snapshot |
| Network | `GetExtendedTcpTable` |
| File | 지정 폴더 `ReadDirectoryChangesW` + SHA-256 |
| DNS | DNS Client ETW |
| Packet input | 사용자가 별도 설치한 Npcap live capture |
| L7 | DNS, HTTP plaintext, TLS ClientHello/certificate metadata parser |

Minifilter, WFP kernel driver는 구현하지 않는다. Npcap installer/driver/SDK/DLL은 repository, release, Agent package에 포함하지 않는다.

Npcap이 없으면 Process/Network/File/DNS collector는 계속 동작하고 packet 기반 L7 collector만 `DEGRADED`로 보고한다.

### 4.3 macOS Swift Agent

| 영역 | 구현 |
| --- | --- |
| 언어/빌드 | Swift, Swift Package Manager, Xcode |
| 실행 | Swift CLI + LaunchAgent |
| Process | `sysctl` 또는 `/bin/ps` snapshot |
| Network | `/usr/sbin/lsof` connection snapshot |
| File | FSEvents 지정 폴더 감시 |
| Packet input | `/usr/sbin/tcpdump` stdout stream |
| DNS/L7 | tcpdump stream에서 DNS, HTTP plaintext, TLS metadata parser |

tcpdump는 `-w -`로 stdout에 packet stream을 쓰고 Agent가 즉시 parsing한다. 디스크 spool이나 PCAP 파일을 만들지 않는다. 권한이 필요하므로 demo 시작 시 고정된 인자로 bootstrap하며, 검증된 console user로 privilege drop한다.

Endpoint Security, Network Extension, KEXT/System Extension은 사용하지 않는다. 무료 Apple Account와 Xcode만 사용하고 Developer ID, notarization, 유료 entitlement를 요구하지 않는다.

### 4.4 Agent 공통 정책

- 지원 OS는 Windows와 macOS다. Linux와 iOS는 지원하지 않는다.
- 외부 전송은 `TelemetryBatchV1` JSON과 HTTPS REST/mTLS다.
- micro-batch 기준은 5초, 100 events, 5MiB 중 먼저 도달한 조건이다.
- Collector가 `acceptedEventIds`를 ACK하면 SQLite row를 즉시 물리 삭제한다.
- Heartbeat는 30초 ±10% jitter, OFFLINE은 2분 미수신, stale은 7일 미수신이다.
- command inbox, PCAP segment manifest, artifact upload 상태는 존재하지 않는다.

## 5. 백엔드 컴포넌트

| 컴포넌트 | 스택 | 역할 |
| --- | --- | --- |
| Nginx | Reverse proxy/TLS | HTTPS/mTLS 종료, body/rate limit, 검증된 certificate header 전달 |
| Collector | Python, FastAPI, Uvicorn | Agent 등록, heartbeat, telemetry validation, Kafka publish |
| Kafka | `telemetry.raw`, `telemetry.validated` | 수집과 탐지 경계, at-least-once 전달 |
| Event Storage Worker | Python, ClickHouse native client | raw consume, identity/payload 검증, ClickHouse batch insert, validated publish |
| Detection Worker | Python | RuleV1/MITRE 평가, Alert/Incident 저장, Endpoint 30초·Incident 60초 상태 sweep |
| Failure Sink module | Python, S3, ClickHouse | 결정적 failure ID/S3 key로 원문과 failure index 기록 |
| Admin CLI | Python CLI | Dashboard ADMIN 생성, Agent 인증서 provision, failure 수동 재발행 |
| Storage Lifecycle Worker | Python, AWS SDK, PyArrow | timestamp bucket archive/checksum, RestoreObject, restore metadata 관리 |
| Dashboard API | Python, FastAPI, Uvicorn, PyArrow | 15개 Dashboard REST API, Endpoint Risk/전역 EDR 상태 계산, restored Parquet 직접 조회, Swagger |

Backend/API/Worker 패키지 관리는 `uv`를 사용한다. REST/FastAPI를 우선 구현하고 gRPC는 추후 확장으로 남긴다.

`telemetry.raw`, `telemetry.validated`는 각각 최소 3개 partition과 local replication factor 1을 사용한다. 기존
Topic이 1~2개 partition이면 startup에서 3개로 증가시키며 더 많은 partition은 축소하지 않는다. Collector와
Event Storage Worker는 `endpointId`를 Kafka key로 사용해 같은 Endpoint의 이벤트를 같은 partition에 유지한다.
Local demo는 Event Storage Worker와 Detection Worker를 각각 1개만 실행하며 각 consumer가 3개 partition을 모두
담당한다. Worker 수는 부하에 따라 partition 수 이하에서 확장한다.

### 5.1 인증·사용자 Bootstrap CLI

최초 Dashboard ADMIN은 다음 관리자 CLI로 생성한다.

```text
python -m tools.create_admin
```

CLI는 email, name, password를 대화형 또는 안전한 stdin으로 받아 `ACTIVE` ADMIN을 생성한다. 초기 계정이나 비밀번호를 migration, seed, repository에 하드코딩하지 않으며 사용자 생성·삭제·상태 변경 REST API는 만들지 않는다.

Agent mTLS 인증서는 다음 CLI로 발급한다.

```text
python -m tools.provision_agent_cert --agent-id <AGENT_ID>
```

- 개발환경별 CA는 하나만 사용하며 최초 실행 시 없으면 생성한다. CLI는 이 CA로 Agent certificate/private key와 배포용 CA certificate를 생성한다.
- `agentId`는 `[a-z0-9][a-z0-9._-]{0,63}`이고 certificate에는 단일 URI SAN `urn:edr:agent:<agentId>`를 넣는다.
- CA certificate는 Nginx client-CA trust bundle과 Agent에 설치하고, Agent certificate/key로 기존 등록 API를 mTLS 호출한다.
- 서버는 URI SAN prefix를 제거한 `agentId`를 request와 exact match하고 fingerprint와 SAN agent ID를 `agent_auth_keys`에 저장한다.
- 등록 API를 제외한 heartbeat·telemetry는 전달된 fingerprint가 해당 Endpoint의 `is_delete=false`, `revoked_at IS NULL`, `issued_at <= now()`, `expires_at > now()`인 활성 `agent_auth_keys` row와 일치하고 Endpoint가 `RETIRED`가 아니어야 한다. Nginx는 외부 신원 헤더를 제거하고 TLS 검증 결과의 subject, SAN agent ID, SHA-256 fingerprint, notBefore, notAfter로 덮어쓰며 Backend는 인증서 시각을 UTC로 변환한다.
- Rotation은 같은 개발용 CA로 새 certificate를 발급한 뒤 기존 등록 API를 다시 호출한다. 새 row 저장이 성공하면 같은 transaction에서 기존 활성 row를 즉시 revoke하며 인증서 중첩 유예기간은 두지 않는다.
- `RETIRED` Endpoint의 등록·rotation·heartbeat·telemetry는 모두 `403 ENDPOINT_RETIRED`이며 상태, `last_seen_at`, 인증서 이력을 변경하거나 event를 publish하지 않는다.
- 인증서 발급 REST API는 만들지 않으며 개발용 CA private key와 Agent private key를 repository나 migration에 넣지 않는다.

## 6. Failure와 수동 재처리

### 6.1 저장 경계

- PostgreSQL에 event failure row나 원문을 저장하지 않는다.
- 실패 원문은 S3 Standard에 저장한다.
- ClickHouse `event_failures`에는 stage/code/error, retryable, S3 path/checksum/size와 단순 결과만 저장한다.
- Kafka를 장기 원문 DLQ로 사용하지 않는다.

`failure_id`는 Python `uuid.NAMESPACE_URL`을 namespace로 사용하는 UUIDv5다. name은 `urn:edr:failure:v1:` 뒤에 `[source_topic, source_partition, source_offset, consumer_name, failure_stage]`를 `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`로 직렬화한 문자열이다. 배열 순서를 고정하고 partition/offset은 JSON 10진 integer로 기록한다.

S3 object key는 `failures/{failureId}/payload.json.gz`다. Failure envelope를 `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))`로 직렬화하고 `gzip.compress(..., compresslevel=9, mtime=0)`으로 압축한다. 이 exact object bytes의 SHA-256과 byte length를 `payload_sha256`, `payload_size_bytes`에 기록한다. 동일 key와 동일 checksum이면 PUT을 반복하지 않고 멱등 성공으로 처리하며, 동일 key의 checksum이 다르면 overwrite와 offset commit을 모두 중단한다.

네트워크·DB 일시 장애는 Worker 내부에서 1초/5초/30초로 최대 3회 재시도한다. 이후 실패는 위 결정적 key에 대한 S3 원문 PUT과 ClickHouse `event_failures` 기록이 모두 durable ACK된 뒤에만 source offset을 commit한다. Failure Sink 자체가 장애이거나 checksum 충돌이면 offset을 commit하지 않고 consumer를 pause/retry한다. 자동 replay scheduler와 replay topic은 없다.

### 6.2 관리자 CLI

```text
python -m tools.replay_failure --failure-id <UUID>
```

CLI는 다음 순서로 실행한다.

1. `event_failures`에서 failure와 S3 pointer 조회
2. `retryable`, 보존 만료 시각 확인
3. S3 원문을 읽고 크기와 SHA-256 검증
4. canonical `TelemetryEventV1`로 변환
5. `replay_failure_id` header와 함께 `telemetry.raw` publish
6. broker ACK 확인 후 `REPROCESSED`, 실패하면 `REPROCESS_FAILED` 기록

재발행 이후 처리는 비동기다. Event Storage Worker는 동일 raw event를 논리 중복으로 만들지 않으면서 `telemetry.validated`까지 다시 전달하고, Alert unique key가 중복 Alert 생성을 막는다.

상태는 `FAILED`, `REPROCESSED`, `REPROCESS_FAILED`만 사용한다. 동일 failure 최신 결과는 `updated_at`으로 선택한다. 복잡한 occurrence ID, tie-break priority/fingerprint, 자동 attempt state machine, CAS 경쟁 처리는 구현하지 않는다.

Failure payload는 최초 실패부터 7일까지 S3 Standard, 이후 Glacier Instant Retrieval로 전환하고 최초 실패 시각부터 90일에 삭제한다. `retention_expires_at`은 이 90일 payload 만료 시각이며 ClickHouse `event_failures` 실행 DDL의 TTL은 `failed_at + 97일`로 고정한다. 이 lifecycle은 `ingest_metadata`가 아니라 S3 lifecycle과 `event_failures` pointer로 관리한다.

## 7. Detection과 Incident

RuleV1은 versioned YAML + JSON Schema로 관리한다.

```yaml
schema_version: 1
rule_code: PROC_POWERSHELL_ENCODED
rule_name: PowerShell Encoded Command
alert_title: Encoded PowerShell command detected
alert_summary: PowerShell was executed with an encoded command argument.
version: 1
enabled: true
event_type: PROCESS_EXECUTION
conditions:
  all:
    - field: command_line
      operator: contains
      value: "-EncodedCommand"
severity: HIGH
risk_score: 85
mitre:
  tactic_code: TA0002
  technique_code: T1059.001
incident:
  enabled: true
  correlation_key: suspicious-powershell
  window_seconds: 1800
response_guidance:
  - order: 1
    title: Review source event
    description: 원본 이벤트와 관련 프로세스를 확인합니다.
    requires_manual_action: false
```

MVP operator는 `eq`, `neq`, `contains`, `regex`, `in`, `cidr_contains`, `gt`, `gte`, `lt`, `lte`다. RuleV1 `rule_name`, `alert_title`, `alert_summary`는 required non-empty string이며 Detection Worker가 템플릿 처리 없이 Alert의 `rule_name`, `title`, `summary`에 그대로 snapshot한다. RuleV1 `risk_score`는 0~100 number다. 모든 `enabled=true` RuleV1은 `mitre.tactic_code`, `mitre.technique_code`를 가져야 하며 두 code가 `mappings/mitre_attack.yaml`에 없거나 누락되면 Worker readiness를 실패시킨다. `enabled=false` Rule은 `mitre`를 생략하고 `incident.enabled=false`이면 `correlation_key`, `window_seconds`를 생략한다. YAML에는 MITRE code만 저장하고 Backend가 고정 mapping 파일에서 tactic/technique name을 변환해 Alert의 MITRE code/name 4개 NOT NULL 컬럼을 채운다. 새 MITRE 테이블은 만들지 않는다.

`response_guidance`는 선택 필드이며 없으면 Alert 상세 API가 `responseGuidance: []`를 반환한다. 각 원소는 `order`, `title`, `description`, `requires_manual_action`을 가지며 order 중복, 1 미만 order, 빈 title/description은 Rule schema validation 실패다. Alert 상세는 최신 Rule이 아니라 Alert의 `(rule_code, rule_version)`과 정확히 일치하는 versioned YAML에서 guidance를 읽는다. Rule version 파일은 해당 version을 참조하는 Alert가 존재하는 동안 보존한다.

Alert는 `(event_id, rule_code, rule_version)`으로 멱등 생성한다. Incident는 `(endpoint_id, correlation_key, window_start_at)`으로 UPSERT하며 생성 시 `OPEN`이다. 같은 Detection Worker process의 60초 periodic task가 `status=OPEN AND window_end_at <= now()`를 확인해 `CLOSED`로 바꾸고 `closed_at=window_end_at`을 기록한다. 같은 process의 별도 30초 task는 `RETIRED`가 아닌 Endpoint의 `last_seen_at`을 검사해 2분 미수신이면 `OFFLINE`으로 바꾼다. Heartbeat는 `RETIRED`가 아닌 Endpoint를 `ONLINE`으로 만들며 `RETIRED`는 두 상태보다 우선하고 자동 변경하지 않는다. 새 서비스나 상태 변경 REST API는 만들지 않는다.

Incident 최초 생성 시 해당 Alert RuleV1의 `alert_title`, `alert_summary`를 Incident `title`, `description`에 그대로 snapshot한다. 동일 Incident에 후속 Alert가 연결되어도 UPSERT는 기존 문자열을 변경하지 않는다.

### 7.1 Endpoint Risk

Endpoint Risk는 새 저장 테이블이나 Worker를 만들지 않고 Dashboard API가 PostgreSQL에서 요청 시점에 계산한다.

```text
is_delete=false Endpoint
-> OPEN/IN_PROGRESS Alert와 risk_score aggregate
-> OPEN Incident aggregate
-> EndpointRiskDto
-> Endpoint 목록/상세/summary
```

- score는 0~100 integer다.
- 등급은 `LOW=0~24`, `MEDIUM=25~49`, `HIGH=50~79`, `CRITICAL=80~100`이다.
- 주요 입력은 active Alert의 기존 `risk_score`와 OPEN Incident다.
- 목록 조회는 Endpoint마다 별도 query를 실행하지 않고 aggregate CTE/subquery로 한 번에 계산한다.
- RETIRED Endpoint도 과거부터 이어진 active Alert/OPEN Incident가 있으면 risk를 계산하되 Collection Health의 OFFLINE/STALE 대상에서는 제외한다.
- Endpoint Risk는 현재 active 상태 snapshot이므로 Dashboard `timePreset`/`from`/`to`의 영향을 받지 않는다.
- 프론트는 Alert/Event 목록에서 Endpoint Risk를 계산하지 않는다.
- 점수 공식, 가중치, 동일 Rule 중복 제거, ROUND_HALF_UP, factor와 등급 경계는 `../contracts/RISK_POLICY.md` V1을 그대로 구현한다.

### 7.2 전역 EDR 상태

전역 EDR 상태는 Dashboard API가 Threat Level과 Collection Health 두 축을 같은 요청 snapshot에서 계산한 뒤 결합한다.

```text
Threat Level
<- Endpoint Risk
<- HIGH/CRITICAL Endpoint count
<- OPEN Incident
<- CRITICAL Alert

Collection Health
<- OFFLINE/STALE Endpoint
<- DEGRADED/UNAVAILABLE sensor
<- ingest failure와 latestIngestedAt 지연
<- storage failure

Threat Level + Collection Health
-> EdrStateDto
```

각 축은 `status`, 0~100 `score`, 고정 enum `reasonCodes`를 반환한다. 최종 `status`, `score`, `reasonCodes`도 Backend가 계산하며 프론트는 색상 mapping 외의 판정을 하지 않는다. Endpoint Risk aggregate와 전역 상태는 하나의 기준 `calculatedAt`을 사용하고, ClickHouse/PostgreSQL 값은 해당 요청에서 조회한 최신 snapshot을 사용한다. 전역 상태도 현재 운영 snapshot이므로 Dashboard `timePreset`/`from`/`to`의 영향을 받지 않는다. Threat/Collection contribution, 상태 임계값, 최근 15분 failure window와 두 축 결합은 `../contracts/RISK_POLICY.md` V1을 그대로 구현한다.

### 7.3 읽기 전용 Response Playbook

Response Playbook은 RuleV1의 `response_guidance`를 Alert 상세에서 보여주는 분석·대응 가이드다. Agent command가 아니며 실행 결과, 완료 상태, 원격 격리, 프로세스 종료, 파일 삭제를 저장하거나 수행하지 않는다. `requires_manual_action=true`는 사용자가 외부에서 수동 조치를 검토해야 한다는 표시일 뿐 실행 버튼이나 자동화 계약이 아니다.

## 8. Audit

`audit_logs`는 PostgreSQL append-only table이며 application role에 UPDATE/DELETE 권한을 주지 않는다.

최소 action:

- `ALERT_STATUS_CHANGED`
- `ARCHIVE_RESTORE_REQUESTED`
- `ARCHIVE_RESTORE_COMPLETED`
- `ARCHIVE_RESTORE_FAILED`
- `AGENT_CERT_ROTATED`

Telemetry, heartbeat, packet metadata 자체는 대량이므로 audit 대상이 아니라 metric/log 대상이다. Audit 조회 REST API는 만들지 않는다.

## 9. 저장소 역할

| 저장소 | 역할 |
| --- | --- |
| SQLite | Agent ACK 전 metadata event buffer |
| ClickHouse | `edr_events`, `event_failures` 검색·집계 |
| PostgreSQL | users, endpoints, auth keys, audit, alerts, incidents, timestamp bucket catalog |
| S3 Standard | 최초 실패부터 7일까지 failure 원문 |
| Glacier Instant Retrieval | 7일 이후 failure 원문, 총 90일 |
| Glacier Flexible Retrieval | raw event archive와 RestoreObject 7일 임시 복원 |

PCAP object용 S3 prefix/bucket과 PCAP retention 정책은 없다.

## 10. Timestamp bucket과 Archive

`ingest_metadata`는 ingest job/batch/Alert 단위가 아니라 Endpoint + UTC timestamp bucket 저장 위치 카탈로그다.

| 항목 | 정책 |
| --- | --- |
| routing key | `(endpoint_id, bucket_start_at, storage_backend, storage_class)` |
| logical bucket | Endpoint별 UTC DAY, 하루치 Parquet object 하나 |
| ClickHouse partition | `toDate(occurred_at)` UTC DAY, 같은 날짜의 모든 Endpoint가 공유 |
| hot | `storage_backend=CLICKHOUSE`, `storage_class=HOT` |
| archive | `storage_backend=S3`, `storage_class=GLACIER_FLEXIBLE_RETRIEVAL`, Parquet + ZSTD + SHA-256 |

실행 ClickHouse DDL은 `PARTITION BY toDate(occurred_at)`, `ORDER BY (endpoint_id, occurred_at, event_type, event_id)`를 사용한다. Lifecycle Worker는 export 직전에 `is_delete=false` ClickHouse row의 Endpoint/UTC DAY별 `uniqExact(event_id)`를 계산해 HOT `event_count`를 갱신한다. Endpoint별 하루치 object를 export한 뒤 Parquet row count가 HOT `event_count`와 같은지 확인하고 S3 `event_count`, checksum, `archive_verified_at`을 기록한다.

날짜 partition 삭제 조건은 해당 날짜의 `is_delete=false` HOT row마다 대응하는 `is_delete=false` S3 row가 존재하고, 모든 S3 row의 `archive_verified_at`과 `checksum_sha256`이 존재하며, HOT/S3 `event_count`가 일치하고, 현재 시각이 `MAX(archive_verified_at) + 7일` 이상인 경우다. 이벤트가 없어서 HOT row가 없는 Endpoint는 검사 대상이 아니다. Lifecycle Worker는 PostgreSQL 날짜 advisory lock을 배타 모드로 획득하고 조건을 다시 확인한 뒤 모든 HOT row를 먼저 `is_delete=true`로 닫고 해당 날짜 partition 전체를 삭제한다. ClickHouse 삭제가 실패하면 HOT row는 닫힌 상태로 유지하고 검증된 S3 object를 보존한 채 다음 sweep에서 삭제를 재시도한다. `ingest_metadata`의 backend/class literal은 `CLICKHOUSE`, `S3`와 `HOT`, `GLACIER_FLEXIBLE_RETRIEVAL`만 허용하며 failure payload의 Standard/Instant lifecycle은 이 catalog에 넣지 않는다.

Event Storage Worker는 ClickHouse batch insert와 metadata 갱신 동안 같은 PostgreSQL 날짜 advisory lock을 공유 모드로 사용하고 HOT row를 확인한다. 같은 날짜의 HOT row가 이미 `is_delete=true`이면 partition을 재생성하지 않고 `ARCHIVED_DAY_IMMUTABLE` failure로 기록한다. partition 삭제 전 늦은 event가 들어와 검증된 Archive object가 오래된 상태가 되면 대응 S3 row의 `archive_verified_at`과 `checksum_sha256`을 `null`로 되돌린 뒤 해당 Endpoint/UTC DAY object를 다시 export·검증하고 7일 safety window를 새 검증 시각부터 다시 계산한다.

Archive 복원은 기존 Storage Lifecycle Worker가 AWS `RestoreObject(Days=7, Tier=Standard)`로 수행한다. 원 S3 object key와 `GLACIER_FLEXIBLE_RETRIEVAL` class는 바꾸지 않고 영구 Standard copy를 만들지 않는다. 상태는 `ARCHIVED -> RESTORE_REQUESTED -> RESTORED -> EXPIRED`이며 실패하면 `RESTORE_FAILED`다. `restore_expires_at`은 완료 시각이 아니라 AWS가 반환한 임시 copy 만료 시각을 기록한다.

`RESTORED` bucket은 Dashboard API가 PyArrow S3 filesystem으로 같은 Parquet object를 직접 조회한다. ClickHouse에 재적재하거나 로컬 파일로 복사하지 않는다. HOT과 RESTORED 결과를 함께 조회할 때는 `(occurred_at, event_id)`로 병합 정렬한 뒤 pagination한다. archive 검증 후 ClickHouse 삭제 전 7일 safety window처럼 동일 논리 bucket에 HOT과 S3 row가 함께 있으면 HOT을 우선하고 S3 상태는 조회와 RestoreObject를 차단하거나 시작하지 않는다. HOT 또는 RESTORED로 충족되지 않은 논리 bucket에 `ARCHIVED`, `RESTORE_REQUESTED`, `RESTORE_FAILED`, `EXPIRED` 상태가 있으면 부분 결과 대신 `409 ARCHIVE_NOT_READY`와 해당 bucket status를 반환한다. 별도 restore job/request table은 만들지 않으며 Orphan reconciliation과 다단계 restore state machine은 추후 확장이다.

요청 `[from, to)`와 겹치는 UTC DAY bucket은 `bucket_start_at < to AND bucket_end_at > from`으로 선택하고, HOT ClickHouse query와 RESTORED PyArrow scan 모두 `occurred_at`을 원래 `[from, to)`로 다시 필터링한다.

HOT `storage_path`는 물리 partition명이 아니라 `clickhouse://edr_events/date=<UTC_DATE>/endpoint_id=<ENDPOINT_ID>` 형식의 Endpoint별 논리 조회 locator다. S3 row의 `storage_path`는 복원 전후 동일한 실제 object key다.

## 11. API와 Dashboard

- 제품 REST API는 Dashboard 15개 + Collector 3개 = 18개다.
- Collector API는 Agent 등록, heartbeat, telemetry batch만 제공한다.
- PCAP artifact upload/download API와 Agent command API는 없다.
- Endpoint Risk는 기존 Endpoint 목록·상세·summary DTO를 확장하며 새 REST API를 만들지 않는다.
- 전역 EDR 상태는 `/dashboard/summary`의 Backend 계산 DTO이며 프론트에서 재계산하지 않는다.
- Response Playbook은 Alert 상세의 읽기 전용 `responseGuidance`이며 Agent response action API를 만들지 않는다.
- Report Center/Modal, HTML/Markdown report path, report 저장·공유 API는 만들지 않는다. 브라우저 print/CSV는 추후 별도 범위다.
- DLQ Monitor와 웹 failure replay는 만들지 않고 개별 failure 재처리는 관리자 Python CLI만 사용한다.
- Dashboard는 React, TypeScript, Vite로 구현하고 REST polling을 사용한다.
- Frontend route, 화면별 API 조합, query 직렬화, polling 주기, retry와 browser visibility 처리는 `../frontend/FRONTEND_SPEC.md`를 따른다.
- Frontend color, spacing, panel/chart/list primitive, responsive와 접근성은 `../frontend/FRONTEND_SPEC.md`의 Design System 부분을 따른다.
- Dashboard JWT access token은 메모리에 두고 layout만 `localStorage`에 저장한다.
- `lastRefreshedAt`은 프론트가 마지막 성공 응답 수신 시각으로 관리하며 API field가 아니다. Backend 계산 시각은 `edrState.calculatedAt`, `risk.calculatedAt`을 사용하고 legacy `generatedAt`, `decision`, `source`는 사용하지 않는다.
- CORS는 배포 origin allowlist를 사용한다.
- FastAPI/Pydantic response model이 최종 응답 계약이며 required key, explicit null, empty list, UTC RFC3339 규칙을 강제한다.
- `is_delete` 컬럼이 있는 PostgreSQL·ClickHouse row는 조회, 인증, 집계와 상태 변경에서 `is_delete=false`만 사용한다.
- `users.status`는 `ACTIVE`, `DISABLED`만 허용하고 `is_delete=false AND status=ACTIVE`만 로그인한다. `DISABLED`는 `403 ACCOUNT_DISABLED`다.
- Archive restore 시작은 `ADMIN`, `ANALYST`만 허용하고 `VIEWER`는 `403 FORBIDDEN`이다.
- 수집·저장 요약은 영구 Standard copy를 세지 않고 복원 완료 bucket을 `restoredBucketCount`로 반환한다.

Latest preset은 `LATEST_15M`, `LATEST_1H`, `LATEST_24H`, `LATEST_7D`, `CUSTOM`이며 기본은 `LATEST_24H`다. Rollup은 현재 구현하지 않고 ClickHouse raw table을 조회한다.

## 12. 운영과 관측성

필수 지표:

- Endpoint/Collector별 event count와 byte rate
- Agent SQLite buffer depth와 retry count
- Kafka consumer lag와 oldest pending age
- ClickHouse insert latency/error
- failure count by stage/code와 수동 replay 결과
- Npcap/tcpdump readiness와 packet drop count
- packet parse error와 metadata event 생성률
- archive/checksum/restore 오류
- Endpoint Risk 계산 latency와 level 분포
- EDR state status/score와 reason code 분포
- Dashboard polling success/error와 마지막 성공 응답 age

민감정보를 log label로 사용하지 않고 `agent_id`, `endpoint_id`, request ID 중심으로 추적한다.

## 13. 실행 DDL과 코드 구조

```text
migrations/
  postgresql/
  clickhouse/
  sqlite/

schemas/
  telemetry-batch-v1.schema.json
  telemetry-event-v1.schema.json
  event-type/
  rule-v1.schema.json
  failure-payload-envelope-v1.schema.json

rules/
  process/
  network/
  file/
  dns/
  l7/

mappings/
  mitre_attack.yaml

tools/
  create_admin.py
  provision_agent_cert.py
  replay_failure.py
```

`ERD_FINAL.sql`은 ERDCloud 업로드용 논리 모델이며 실행 migration이 아니다. 파일 안의 `[SQLite]`, `[PostgreSQL]`, `[ClickHouse]` 한글 테이블 설명으로 실제 저장소를 구분한다. 논리 ERD의 `edr_events.event_id` unique는 전역 Event identity 계약을 표현하며, 실제 ClickHouse에서는 Event Storage Worker의 identity/payload 검증과 latest-row 조회 규칙으로 멱등성을 보장한다. PostgreSQL FK/unique/index, ClickHouse engine/partition/order/TTL, SQLite pragma/index는 저장소별 migration에서 구현한다.

## 14. 제외 및 추후 확장

| 항목 | 결정 |
| --- | --- |
| Linux/iOS Agent | 제외 |
| Windows kernel driver | 제외 |
| macOS System/Network Extension | 제외 |
| 원본 PCAP 저장·업로드 | 제외 |
| PCAP rolling/segment/quota | 제외 |
| PCAP heartbeat command/artifact API | 제외 |
| `agent_commands`와 PCAP 관련 테이블 | 제외 |
| Agent 원격 response action | 제외 |
| Endpoint 격리·프로세스 종료·파일 삭제 API | 제외 |
| Report Center/Modal과 저장형 HTML/Markdown report | 제외 |
| 웹 DLQ Monitor와 웹 failure replay API | 제외 |
| Response Playbook 실행·완료 상태 저장 | 제외 |
| 프론트 Endpoint Risk/EDR 상태 계산 | 제외 |
| 자동 failure replay state machine | 제외 |
| Orphan reconciliation/CAS 경쟁 | 추후 확장 |
| Rollup table/materialized view | 추후 확장 |
| gRPC | 추후 확장 |
| 담당자 지정 | 제거 |

## 15. 포트폴리오 검증 profile

### 15.1 규모

- 실제 Windows Endpoint 1대
- 실제 macOS Endpoint 1대
- Kafka consumer 중단 후 lag 회복 확인

원본 PCAP binary 부하 시나리오는 없다. Network/DNS/L7 metadata는 일반 telemetry 부하에 포함한다.

### 15.2 실제 단말 검증

- Windows에서 Process/Network/File/DNS/L7 5종 수집
- macOS에서 Process/Network/File/DNS/L7 5종 수집
- packet이 디스크에 남지 않는지 확인
- HTTP plaintext와 관측 가능한 TLS SNI/version/certificate metadata 확인
- Rule 탐지, MITRE mapping, Alert/Incident 확인
- active Alert/OPEN Incident 기반 Endpoint Risk score·등급·factor 확인
- Threat Level과 Collection Health를 구분한 EDR 상태와 reason code 확인
- Alert의 Rule version에 맞는 읽기 전용 response guidance 확인
- 목록 query가 `../contracts/API_SPEC.md`의 filter, deterministic sort와 pagination을 지키는지 확인
- Overview/Operations polling이 `../frontend/FRONTEND_SPEC.md` 주기와 visibility/retry 규칙을 지키는지 확인
- 375px, 768px, 1280px에서 `../frontend/FRONTEND_SPEC.md`의 navigation, table, focus와 상태 표시 확인
- Report, 웹 replay, Agent 원격 조치 endpoint가 존재하지 않는지 확인
- Agent SQLite ACK row 물리 삭제 확인
- failure 1건을 S3에 저장하고 관리자 CLI로 수동 재처리
- archive checksum과 `ingest_metadata` 상태 확인

### 15.3 macOS 개발 흐름

```text
Windows/Codex에서 Swift 코드 작성
-> GitHub 반영
-> Mac에서 pull
-> swift build/test
-> tcpdump stdout/FSEvents/LaunchAgent 실제 검증
-> Collector로 telemetry 전송
```

macOS 전용 코드는 기능 단위로 실제 Mac에서 지속적으로 빌드·테스트한다.
