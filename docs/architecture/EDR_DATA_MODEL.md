# EDR ERD 테이블 정의서

## 1. 문서 목적

이 문서는 single-tenant 포트폴리오 EDR PoC의 최종 논리 데이터 모델을 정의한다. `ERD_FINAL.sql`은 ERDCloud 업로드를 위해 MySQL 호환 타입으로 통일한 최종 논리 ERD다. 파일의 한글 테이블 설명에 실제 저장소를 표시한다. 실행 DDL은 SQLite, PostgreSQL, ClickHouse migration으로 분리한다.

## 2. 서비스 정의

Windows C++ Agent와 macOS Swift Agent가 Process, Network, File, DNS, L7 5종 telemetry를 수집한다. Npcap과 tcpdump는 패킷 입력 수단으로만 사용하며 원본 PCAP 파일을 만들거나 장기 저장하지 않는다. 패킷은 실시간 분석 후 DNS, HTTP plaintext, TLS metadata와 네트워크 metadata만 JSON telemetry로 전송한다.

Python Backend/Worker는 telemetry를 Kafka로 수신하고 ClickHouse에 저장한 뒤 RuleV1 YAML을 평가한다. 탐지 결과는 MITRE ATT&CK에 매핑해 PostgreSQL Alert와 자동 correlation Incident로 제공한다.

## 3. 전체 데이터 흐름

```text
Windows C++ / macOS Swift Agent
-> OS API + Npcap/tcpdump live packet stream
-> Process/Network/File/DNS/L7 metadata 생성
-> SQLite local_event_buffer
-> HTTPS REST + mTLS / Nginx / FastAPI Collector
-> Kafka telemetry.raw
-> Event Storage Worker
   -> ClickHouse edr_events
   -> Kafka telemetry.validated
-> Detection Worker
   -> RuleV1 + MITRE ATT&CK
   -> PostgreSQL alerts / incidents / incident_alerts

처리 실패
-> 원문 S3 Standard
-> ClickHouse event_failures에 검색 index와 S3 pointer
-> 관리자가 CLI로 필요할 때만 telemetry.raw에 수동 재발행

장기 보관
-> Endpoint + UTC timestamp bucket
-> Parquet/ZSTD + checksum
-> S3 Glacier Flexible Retrieval
-> PostgreSQL ingest_metadata에 위치·상태 기록
```

원본 PCAP rolling 저장, segment 정책, S3 PCAP upload, PCAP heartbeat command, artifact API는 사용하지 않는다.

## 4. 저장소 분리 기준

| 저장소 | 테이블/데이터 | 역할 |
| --- | --- | --- |
| Agent SQLite | `local_event_buffer` | Collector ACK 전 metadata event 임시 저장 |
| ClickHouse | `edr_events`, `event_failures` | 정상 telemetry와 대량 failure 검색 index |
| PostgreSQL | `endpoints`, `agent_auth_keys`, `audit_logs`, `ingest_metadata`, `users`, `user_dashboard_layouts`, `alerts`, `incidents`, `incident_alerts` | 운영 상태, 인증, 감사, 저장 카탈로그, 사용자 Dashboard 설정, 탐지 결과 |
| S3 Standard | 최초 실패부터 7일까지 failure 원문 | Failure 단기 object |
| S3 Glacier Instant Retrieval | 7일 이후 failure 원문 | 최초 실패 기준 총 90일 보존 |
| S3 Glacier Flexible Retrieval | raw event archive | Parquet/ZSTD 장기 보관과 7일 임시 RestoreObject |

PostgreSQL에는 event failure row와 원문을 저장하지 않는다. ClickHouse `event_failures`에는 원문 대신 S3 object key, checksum, 크기만 저장한다.

## 5. 테이블 구성

최종 논리 ERD는 12개 테이블이다.

| 저장소 | 테이블 | 속성 수 | 역할 |
| --- | --- | ---: | --- |
| SQLite | `local_event_buffer` | 13 | ACK 전 telemetry buffer |
| ClickHouse | `event_failures` | 24 | failure 검색·수동 재처리 결과 |
| ClickHouse | `edr_events` | 44 | 5종 raw metadata event |
| PostgreSQL | `endpoints` | 17 | Endpoint와 Agent 상태 |
| PostgreSQL | `agent_auth_keys` | 11 | mTLS 인증서 이력 |
| PostgreSQL | `audit_logs` | 10 | append-only control-plane audit |
| PostgreSQL | `ingest_metadata` | 19 | Endpoint/UTC DAY bucket 저장 위치 |
| PostgreSQL | `incidents` | 15 | 자동 correlation projection |
| PostgreSQL | `users` | 11 | Dashboard 로그인/RBAC/UI 언어 설정 |
| PostgreSQL | `user_dashboard_layouts` | 8 | JWT 사용자별 Dashboard 위젯 layout |
| PostgreSQL | `incident_alerts` | 7 | Incident-Alert N:M 연결 |
| PostgreSQL | `alerts` | 22 | Rule/MITRE 탐지 결과 |
| **합계** | **12개** | **201** |  |

## 6. 관계 요약

```text
endpoints -> agent_auth_keys
endpoints -> ingest_metadata
endpoints -> alerts
endpoints -> incidents
incidents -> incident_alerts <- alerts
users -> user_dashboard_layouts
```

- `users`는 Dashboard 로그인/RBAC와 사용자별 Dashboard layout 소유권에만 연결된다.
- 담당자 지정 기능이 없으므로 `users`와 Alert/Incident 사이 FK가 없다.
- `edr_events.event_id`와 `event_failures.event_id`는 PostgreSQL FK가 아닌 논리 참조다.
- `audit_logs`의 actor/resource ID는 삭제 이후에도 이력을 보존하는 문자열 snapshot이다.

## 7. 공통 정책

### 7.1 ID와 시간

- 단일 tenant이므로 `tenant_id`를 사용하지 않는다.
- PostgreSQL 업무 PK는 `BIGINT`, event/failure ID는 `UUID`를 사용한다.
- 시간은 UTC `TIMESTAMPTZ` 또는 `DateTime64(3, 'UTC')`로 저장한다.
- 시간 범위는 `[start, end)` 규칙을 사용한다.
- `ingest_metadata`의 routing key는 `(endpoint_id, bucket_start_at, storage_backend, storage_class)`다.

### 7.2 삭제와 중복

- `local_event_buffer`는 `acceptedEventIds` ACK를 받으면 transaction에서 물리 삭제한다.
- `is_delete` 컬럼이 있는 PostgreSQL·ClickHouse row는 조회, 인증, 집계와 상태 변경에서 `is_delete=false`만 사용한다.
- `audit_logs`는 append-only이며 application role에 UPDATE/DELETE 권한을 주지 않는다.
- Event 중복은 논리 ERD의 `event_id` unique와 실제 Event Storage Worker의 identity/payload 검증으로 차단하고, Alert 중복은 `(event_id, rule_code, rule_version)`으로 차단한다.
- 복잡한 CAS 경쟁, orphan reconciliation, 다단계 상태 versioning은 추후 확장이다.

### 7.3 패킷 수집

- Windows는 별도 설치한 Npcap에서 packet callback을 받아 실시간 분석한다.
- macOS는 기본 tcpdump의 stdout stream을 읽어 실시간 분석한다.
- 원본 packet payload는 분석이 끝나면 폐기하고 파일로 남기지 않는다.
- HTTP는 plaintext metadata 중 method, host, query/fragment를 제거한 URL path, status code, user agent만 수집한다. Request/response body, cookie, authorization 및 그 밖의 임의 header는 수집하지 않는다. TLS payload는 복호화하지 않는다.
- TLS는 수동 복호화 없이 관측 가능한 SNI, version, certificate subject/issuer/SHA-256만 저장한다. 보이지 않는 SNI·certificate 값은 nullable이며 누락 자체를 수집 실패로 처리하지 않는다.
- PCAP 파일, segment, local quota, S3 upload, command, artifact 개념은 ERD에 없다.

### 7.4 Failure와 수동 재처리

- Worker의 짧은 in-process retry 후에도 실패한 원문은 S3에 저장한다.
- `event_failures`는 `FAILED`, `REPROCESSED`, `REPROCESS_FAILED`만 사용한다.
- 자동 scheduler와 replay state machine을 사용하지 않는다.
- 관리자는 내부 CLI로 failure ID를 지정해 checksum 검증 후 `telemetry.raw`에 재발행한다.
- 동일 failure의 최신 결과는 `updated_at` 기준으로 조회한다.
- `failure_id`는 `uuid.NAMESPACE_URL`과 `urn:edr:failure:v1:` + `json.dumps([source_topic, source_partition, source_offset, consumer_name, failure_stage], ensure_ascii=False, separators=(",", ":"))` name으로 계산한 UUIDv5다.
- S3 key는 `failures/{failureId}/payload.json.gz`다. Failure envelope를 `sort_keys=True`, `ensure_ascii=False`, compact separator로 직렬화하고 gzip level 9, `mtime=0`으로 압축한 exact object bytes의 SHA-256을 사용한다.
- 동일 key/checksum은 멱등 성공이고 checksum이 다르면 overwrite와 offset commit을 중단한다. S3 PUT과 ClickHouse row 기록이 모두 성공한 뒤에만 source offset을 commit한다.
- Failure payload는 S3 Standard 7일 후 Glacier Instant Retrieval로 전환하고 최초 실패부터 90일에 삭제한다. `retention_expires_at`은 90일 payload 만료 시각이고 ClickHouse index TTL은 최초 실패부터 97일이다.
- Failure Standard/Instant lifecycle은 `ingest_metadata`가 아니라 S3 lifecycle과 `event_failures` pointer로 관리한다.

### 7.5 Archive

- `ingest_metadata`는 ingest batch/job/Alert 단위가 아니라 Endpoint + UTC timestamp bucket 저장 카탈로그다.
- 논리 bucket은 Endpoint별 UTC DAY이며 Endpoint 한 대의 하루치 event를 Parquet object 하나로 저장한다.
- ClickHouse 물리 partition은 `toDate(occurred_at)` UTC 날짜 단위이며 같은 날짜의 모든 Endpoint가 공유한다.
- `storage_backend`는 `CLICKHOUSE`, `S3`, `storage_class`는 `HOT`, `GLACIER_FLEXIBLE_RETRIEVAL`만 사용한다. 유효 조합은 `CLICKHOUSE/HOT`, `S3/GLACIER_FLEXIBLE_RETRIEVAL`이다.
- Lifecycle Worker는 export 직전에 `is_delete=false` ClickHouse row의 Endpoint/UTC DAY별 `uniqExact(event_id)`를 HOT `event_count`에 기록한다. Parquet/ZSTD export 후 row count 일치와 checksum을 검증하고 같은 값을 S3 `event_count`에 기록한 뒤 `ARCHIVED`로 전이한다.
- 해당 날짜의 모든 활성 HOT row에 대응하는 S3 row가 존재하고 `archive_verified_at`, `checksum_sha256`, 동일한 `event_count`가 확인된 뒤 `MAX(archive_verified_at) + 7일`에 날짜 배타 lock 안에서 같은 날짜 HOT row를 먼저 `is_delete=true`로 닫고 partition 전체를 삭제한다. 이벤트가 없어 HOT row가 없는 Endpoint는 대상이 아니다. ClickHouse 삭제가 실패하면 HOT row는 닫힌 상태로 유지하고 검증된 S3 object를 보존한 채 삭제를 재시도한다.
- partition 삭제 전 늦은 event가 들어오면 대응 S3 row의 `archive_verified_at`, `checksum_sha256`을 `null`로 되돌리고 해당 Endpoint/UTC DAY object를 다시 export·검증한다. 삭제 후 같은 날짜 event는 `ARCHIVED_DAY_IMMUTABLE` failure로 기록하고 partition을 다시 만들지 않는다.
- 기존 Storage Lifecycle Worker가 AWS `RestoreObject(Days=7, Tier=Standard)`로 임시 복원한다. 원 object key와 storage class는 유지하고 영구 Standard copy를 만들지 않는다.
- 상태는 `ARCHIVED -> RESTORE_REQUESTED -> RESTORED -> EXPIRED`이며 실패하면 `RESTORE_FAILED`다. 복원 완료 후 PyArrow가 같은 S3 Parquet object를 직접 조회하고 ClickHouse에는 재적재하지 않는다.
- archive 검증 후 ClickHouse 삭제 전 7일 safety window처럼 동일 논리 bucket에 HOT과 S3 row가 함께 있으면 HOT을 우선한다. 이 경우 S3 row 상태는 조회를 차단하거나 RestoreObject를 시작하지 않으며, HOT 또는 RESTORED로 충족되지 않은 논리 bucket만 archive 미준비 상태로 판단한다.
- 별도 restore job/request table을 만들지 않는다.
- Rollup은 구현하지 않고 추후 확장으로 둔다.

### 7.6 Latest 조회

- `LATEST_15M`, `LATEST_1H`, `LATEST_24H`, `LATEST_7D`, `CUSTOM`을 지원한다.
- 기본값은 `LATEST_24H`다.
- Endpoint/Alert/Incident는 PostgreSQL, event와 failure는 ClickHouse, archive 위치는 `ingest_metadata`에서 조회한다.

## 8. 테이블 상세 정의

### 8.1 `local_event_buffer`

목적: Collector가 개별 event를 ACK할 때까지 metadata JSON을 보관한다.

| 컬럼 | 타입 | NULL | 설명 |
| --- | --- | --- | --- |
| `local_event_buffer_id` | `INTEGER` | NOT NULL | SQLite 자동 증가 row ID |
| `endpoint_id` | `INTEGER` | NULL | 등록 전이면 null 가능한 로컬 Endpoint ID |
| `event_id` | `TEXT` | NOT NULL | 전역 event ID. unique |
| `batch_id` | `TEXT` | NULL | 전송 묶음 추적 ID |
| `event_type` | `TEXT` | NOT NULL | 5종 event type |
| `payload_json` | `TEXT` | NOT NULL | `json_valid` 검증을 통과한 metadata event JSON |
| `collected_at` | `TEXT` | NOT NULL | ISO-8601 Agent 수집 시각 |
| `status` | `TEXT` | NOT NULL | `PENDING`, `FAILED` |
| `retry_count` | `INTEGER` | NOT NULL | 전송 재시도 수 |
| `last_error` | `TEXT` | NULL | 마지막 오류 |
| `next_retry_at` | `TEXT` | NULL | ISO-8601 다음 전송 시각 |
| `created_at` | `TEXT` | NOT NULL | ISO-8601 생성 시각 |
| `updated_at` | `TEXT` | NOT NULL | ISO-8601 갱신 시각 |

### 8.2 `event_failures`

목적: 대량 failure를 OLAP에서 검색하고 S3 원문을 수동 재처리한다.

| 컬럼 | 타입 | NULL | 설명 |
| --- | --- | --- | --- |
| `failure_id` | `UUID` | NOT NULL | source topic/partition/offset, consumer, stage 기반 UUIDv5 |
| `event_id` | `Nullable(UUID)` | NULL | 원 event ID |
| `endpoint_id` | `Nullable(UInt64)` | NULL | Endpoint ID |
| `source_topic` | `LowCardinality(String)` | NOT NULL | 원 Kafka topic |
| `source_partition` | `UInt32` | NOT NULL | 원 partition |
| `source_offset` | `UInt64` | NOT NULL | 원 offset |
| `consumer_name` | `LowCardinality(String)` | NOT NULL | 실패 consumer |
| `failure_stage` | `LowCardinality(String)` | NOT NULL | 실패 단계 |
| `failure_code` | `Nullable(String)` | NULL | 안정된 오류 코드 |
| `error_message` | `String` | NOT NULL | 오류 설명 |
| `retryable` | `UInt8` | NOT NULL | 수동 재처리 가능 여부 |
| `retry_count` | `UInt16` | NOT NULL | in-process retry 수 |
| `payload_object_key` | `String` | NOT NULL | `failures/{failureId}/payload.json.gz` |
| `payload_sha256` | `FixedString(64)` | NOT NULL | 저장된 deterministic gzip object SHA-256 |
| `payload_size_bytes` | `UInt64` | NOT NULL | 저장된 deterministic gzip object byte length |
| `status` | `LowCardinality(String)` | NOT NULL | Failure 상태 |
| `failed_at` | `DateTime64(3, 'UTC')` | NOT NULL | 최초 실패 시각 |
| `replay_count` | `UInt16` | NOT NULL | 수동 재처리 횟수 |
| `last_replayed_at` | `Nullable(DateTime64(3, 'UTC'))` | NULL | 마지막 CLI 실행 시각 |
| `reprocess_outcome` | `Nullable(String)` | NULL | 재처리 결과 요약 |
| `resolved_at` | `Nullable(DateTime64(3, 'UTC'))` | NULL | 성공 시각 |
| `retention_expires_at` | `DateTime64(3, 'UTC')` | NOT NULL | 최초 실패 + 90일 S3 원문 삭제 시각 |
| `created_at` | `DateTime64(3, 'UTC')` | NOT NULL | 생성 시각 |
| `updated_at` | `DateTime64(3, 'UTC')` | NOT NULL | 최신 결과 시각 |

### 8.3 `endpoints`

목적: Agent 식별정보, 단말 상태와 sensor 상태를 관리한다. Endpoint 사용자·등록자 개인정보는 수집하지 않는다. 등록 시 `sensor_health_json`은 빈 배열로 초기화하고 heartbeat 전체 snapshot으로 교체한다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `endpoint_id` | `BIGSERIAL` | Endpoint PK |
| `agent_id` | `VARCHAR(64)` | Agent가 설치 시 생성하고 유지하는 불변 식별자 |
| `hostname` | `VARCHAR(255)` | 마지막 등록/갱신 시 보고된 호스트 이름 |
| `os_type` | `VARCHAR(30)` | `WINDOWS` 또는 `MACOS` |
| `os_version` | `VARCHAR(100) NULL` | Agent가 보고한 운영체제 버전 |
| `ip_address` | `INET NULL` | Collector가 마지막으로 확인한 Agent IP |
| `agent_version` | `VARCHAR(50) NULL` | 설치된 Agent 애플리케이션 버전 |
| `agent_build_id` | `VARCHAR(200) NULL` | 배포 빌드 추적 식별자 |
| `agent_arch` | `VARCHAR(20) NULL` | `X64` 또는 `ARM64` |
| `capability_codes_json` | `JSONB` | Agent가 현재 제공할 수 있는 수집 기능 코드 배열 |
| `sensor_health_json` | `JSONB` | Heartbeat가 보고한 sensor별 상태 snapshot 배열 |
| `registered_at` | `TIMESTAMPTZ` | Endpoint가 최초 등록된 UTC 시각 |
| `status` | `VARCHAR(30)` | `ONLINE`, `OFFLINE`, `RETIRED` |
| `last_seen_at` | `TIMESTAMPTZ NULL` | 마지막 정상 Heartbeat 수신 시각 |
| `created_at` | `TIMESTAMPTZ` | 행 생성 시각 |
| `updated_at` | `TIMESTAMPTZ` | Endpoint 상태나 snapshot 마지막 갱신 시각 |
| `is_delete` | `BOOLEAN` | 소프트 삭제 표시. 현재 조회·인증은 `FALSE`만 사용 |

`RETIRED`가 아니면 Heartbeat 수신 시 `ONLINE`이다. 기존 Detection Worker process의 30초 periodic task가 `last_seen_at`을 검사해 2분 미수신 Endpoint를 `OFFLINE`으로 바꾼다. `RETIRED`는 ONLINE/OFFLINE보다 우선하며 자동 변경하지 않는다. `RETIRED` Endpoint의 등록·rotation·heartbeat·telemetry는 모두 `403 ENDPOINT_RETIRED`이며 상태, `last_seen_at`, 인증서 이력을 변경하거나 event를 publish하지 않는다. stale은 7일 미수신 파생값이다.

### 8.4 `agent_auth_keys`

목적: mTLS certificate fingerprint, subject, SAN agent ID와 발급·만료·폐기 이력을 관리한다. 속성 수는 11개다. 관리자는 `python -m tools.provision_agent_cert --agent-id <AGENT_ID>`로 개발용 CA certificate와 Agent certificate/private key를 발급한다. Agent certificate의 단일 URI SAN은 `urn:edr:agent:<agentId>`이며 서버는 기존 등록 API에서 request `agentId`와 exact match한 뒤 fingerprint와 SAN agent ID를 저장한다. Nginx는 TLS 검증을 통과한 escaped PEM certificate를 전달하고 Backend가 여기서 읽은 notBefore/notAfter를 UTC로 변환해 `issued_at`, `expires_at`에 저장한다. 등록 API를 제외한 heartbeat·telemetry는 해당 Endpoint의 `is_delete=false`, fingerprint 일치, `revoked_at IS NULL`, `issued_at <= now()`, `expires_at > now()`이며 Endpoint가 `RETIRED`가 아닌 활성 인증서만 허용한다. Rotation도 CLI 재발급 후 같은 등록 API를 사용하며 새 row 저장 성공 후 같은 transaction에서 기존 활성 row를 즉시 revoke하고 인증서 중첩 유예기간은 두지 않는다. 인증서 발급 REST API는 만들지 않는다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `agent_auth_key_id` | `BIGSERIAL` | 인증서 이력 PK |
| `endpoint_id` | `BIGINT` | 인증서를 소유한 Endpoint FK |
| `cert_fingerprint` | `VARCHAR(128)` | 인증서 SHA-256 fingerprint. 인증 요청 비교에 사용 |
| `cert_subject` | `VARCHAR(500)` | 발급 당시 certificate subject snapshot |
| `cert_san_agent_id` | `VARCHAR(64)` | URI SAN에서 추출한 Agent ID |
| `issued_at` | `TIMESTAMPTZ` | 인증서 유효기간 시작 시각 |
| `expires_at` | `TIMESTAMPTZ` | 인증서 만료 시각 |
| `revoked_at` | `TIMESTAMPTZ NULL` | rotation 등으로 폐기한 시각. 활성 인증서는 `NULL` |
| `created_at` | `TIMESTAMPTZ` | 인증서 이력 행 생성 시각 |
| `updated_at` | `TIMESTAMPTZ` | 폐기 등 마지막 변경 시각 |
| `is_delete` | `BOOLEAN` | 소프트 삭제 표시. 인증은 `FALSE`인 행만 허용 |

### 8.5 `audit_logs`

목적: Alert 상태 변경, archive restore, 인증서 rotation을 append-only로 기록한다.

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `audit_log_id` | `BIGINT` | PK |
| `actor_type` | `VARCHAR(30)` | `USER`, `AGENT`, `SYSTEM` |
| `actor_identifier` | `VARCHAR(255)` | actor snapshot |
| `action` | `VARCHAR(100)` | action code |
| `resource_type` | `VARCHAR(50)` | resource 종류 |
| `resource_id` | `VARCHAR(255)` | resource ID snapshot |
| `before_json` | `JSONB` | 변경 전 |
| `after_json` | `JSONB` | 변경 후 |
| `request_id` | `VARCHAR(100)` | 요청 추적 ID |
| `created_at` | `TIMESTAMPTZ` | 생성 시각 |

### 8.6 `ingest_metadata`

목적: Endpoint/UTC DAY bucket별 data 위치와 단순 archive/restore 상태를 관리한다. 속성 수는 19개다. Endpoint 한 대의 하루치 event를 Parquet object 하나로 저장하고 ClickHouse 물리 partition은 같은 UTC 날짜의 모든 Endpoint가 공유한다. Archive row는 복원 중에도 `storage_backend=S3`, `storage_class=GLACIER_FLEXIBLE_RETRIEVAL`, 동일 `storage_path`를 유지하며 `restore_expires_at` 이후 `EXPIRED`가 된다.

HOT `storage_path`는 Endpoint별 ClickHouse 논리 조회 locator이고 S3 `storage_path`는 실제 object key다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `endpoint_id` | `BIGINT` | bucket이 속한 Endpoint FK |
| `bucket_start_at` | `TIMESTAMPTZ` | Endpoint별 UTC DAY 시작 시각 |
| `bucket_end_at` | `TIMESTAMPTZ` | UTC DAY 종료 시각. 조회 구간은 `[start, end)` |
| `storage_backend` | `VARCHAR(30)` | `CLICKHOUSE` 또는 `S3` |
| `storage_class` | `VARCHAR(50)` | `HOT` 또는 `GLACIER_FLEXIBLE_RETRIEVAL` |
| `storage_status` | `VARCHAR(30)` | HOT/archive/restore lifecycle 상태 |
| `storage_path` | `VARCHAR(1000)` | ClickHouse locator 또는 S3 object key |
| `event_count` | `BIGINT` | bucket에 포함된 unique event 수 |
| `size_bytes` | `BIGINT NULL` | archive object 또는 bucket의 byte 크기 |
| `checksum_sha256` | `CHAR(64) NULL` | export된 archive object의 SHA-256 |
| `archived_at` | `TIMESTAMPTZ NULL` | archive object 생성 완료 시각 |
| `archive_verified_at` | `TIMESTAMPTZ NULL` | row count와 checksum 검증 완료 시각 |
| `restore_requested_at` | `TIMESTAMPTZ NULL` | S3 RestoreObject 요청 시각 |
| `restored_at` | `TIMESTAMPTZ NULL` | 임시 복원 완료 시각 |
| `restore_expires_at` | `TIMESTAMPTZ NULL` | 7일 임시 복원 만료 시각 |
| `last_error` | `TEXT NULL` | 마지막 archive 또는 restore 오류 |
| `created_at` | `TIMESTAMPTZ` | catalog row 생성 시각 |
| `updated_at` | `TIMESTAMPTZ` | lifecycle 상태 마지막 갱신 시각 |
| `is_delete` | `BOOLEAN` | HOT bucket 폐기 또는 catalog 소프트 삭제 표시 |

### 8.7 `incidents`

목적: RuleV1 correlation key/window로 관련 Alert를 자동 묶는 read-only projection이다. 속성 수는 15개다. 최초 생성 Alert RuleV1의 `alert_title`, `alert_summary`를 `title`, `description`에 그대로 snapshot하며 후속 Alert UPSERT는 이를 덮어쓰지 않는다. 생성 시 `OPEN`이며 Detection Worker의 60초 periodic task가 `window_end_at`이 지난 row를 `CLOSED`로 바꾸고 `closed_at=window_end_at`을 기록한다. 담당자·상태 변경 API를 두지 않는다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `incident_id` | `BIGSERIAL` | Incident PK |
| `endpoint_id` | `BIGINT` | Incident가 속한 Endpoint FK |
| `correlation_key` | `VARCHAR(255)` | RuleV1이 정의한 Alert 묶음 기준 |
| `window_start_at` | `TIMESTAMPTZ` | correlation window 시작 시각 |
| `window_end_at` | `TIMESTAMPTZ` | correlation window 종료 시각 |
| `title` | `VARCHAR(200)` | 최초 Alert rule의 제목 snapshot |
| `description` | `TEXT NULL` | 최초 Alert rule의 요약 snapshot |
| `severity` | `VARCHAR(20)` | 연결 Alert 중 최고 심각도 |
| `status` | `VARCHAR(30)` | `OPEN` 또는 자동 종료된 `CLOSED` |
| `first_detected_at` | `TIMESTAMPTZ` | 첫 Alert 탐지 시각 |
| `last_detected_at` | `TIMESTAMPTZ` | 같은 window에서 가장 최근 Alert 탐지 시각 |
| `closed_at` | `TIMESTAMPTZ NULL` | 자동 종료 시 `window_end_at`과 같은 값 |
| `created_at` | `TIMESTAMPTZ` | Incident 최초 생성 시각 |
| `updated_at` | `TIMESTAMPTZ` | severity/window/status 마지막 갱신 시각 |
| `is_delete` | `BOOLEAN` | 소프트 삭제 표시 |

### 8.8 `users`

목적: Dashboard 로그인, RBAC와 계정별 UI 언어 설정을 관리한다. 속성 수는 11개다. 내부 관계와 감사 로그에는 자동 생성 `user_id`를 사용하고 사용자는 별도의 `login_id`와 password로 로그인한다. `status`는 `ACTIVE`, `DISABLED`만 사용하고 `is_delete=false AND status=ACTIVE`만 로그인할 수 있으며 `DISABLED`는 `403 ACCOUNT_DISABLED`다. `locale`은 `EN`, `KO`만 허용하고 기본값은 `EN`이며 인증된 사용자의 Frontend 언어 source of truth다. 최초 ADMIN은 `python -m tools.create_admin --login-id <LOGIN_ID> --name <DISPLAY_NAME>`으로 생성하고 migration에 계정이나 비밀번호를 하드코딩하지 않는다. 사용자 생성·삭제·상태 변경 REST API를 만들지 않으며 Alert·Incident와 연결하지 않는다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `user_id` | `BIGSERIAL` | Dashboard 사용자 PK |
| `login_id` | `VARCHAR(64)` | 3~64자이며 사용자가 지정하고 소문자로 정규화하는 로그인 ID |
| `password_hash` | `VARCHAR(255)` | Argon2 password hash |
| `name` | `VARCHAR(100)` | 화면에 표시할 사용자 이름 |
| `role` | `VARCHAR(30)` | `ADMIN`, `ANALYST`, `VIEWER` 권한 역할 |
| `status` | `VARCHAR(30)` | `ACTIVE` 또는 `DISABLED` |
| `locale` | `VARCHAR(2)` | UI 언어 설정. `EN`, `KO`만 허용하며 기본값은 `EN` |
| `last_login_at` | `TIMESTAMPTZ NULL` | 마지막 로그인 성공 시각 |
| `created_at` | `TIMESTAMPTZ` | 계정 생성 시각 |
| `updated_at` | `TIMESTAMPTZ` | 로그인 또는 계정 상태 마지막 갱신 시각 |
| `is_delete` | `BOOLEAN` | 소프트 삭제 표시. 로그인은 `FALSE`만 허용 |

`ck_users_login_id_format`은 허용 문자와 소문자 정규화를 강제한다. `ck_users_locale`은 `locale IN ('EN', 'KO')`를 강제한다. `uq_users_login_id_active`는 `LOWER(login_id)`에 `WHERE is_delete=FALSE`를 적용하는 partial unique index다.

### 8.9 `user_dashboard_layouts`

목적: Overview의 데스크톱 12열 위젯 layout을 JWT 사용자별로 저장한다. `(user_id, dashboard_key)`는 unique이며 API는 body/query 사용자 ID를 받지 않는다. `revision`은 오래된 PUT을 거부하는 낙관적 동시성 값이다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `layout_id` | `BIGSERIAL` | Dashboard layout PK |
| `user_id` | `BIGINT` | `users.user_id` FK, 사용자 삭제 시 cascade |
| `dashboard_key` | `VARCHAR(64)` | 현재 `overview` |
| `layout_version` | `INTEGER` | 위젯 registry/layout schema 버전 |
| `revision` | `BIGINT` | 저장마다 증가하는 revision |
| `layout_json` | `JSONB` | `{id,x,y,w,h,hidden}` 배열 |
| `created_at` | `TIMESTAMPTZ` | 최초 저장 시각 |
| `updated_at` | `TIMESTAMPTZ` | 마지막 저장 시각 |

### 8.10 `incident_alerts`

목적: Incident와 Alert의 N:M 관계를 저장한다. `(incident_id, alert_id)`는 unique이며 속성 수는 7개다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `incident_alert_id` | `BIGSERIAL` | 연결 행 PK |
| `incident_id` | `BIGINT` | Incident FK |
| `alert_id` | `BIGINT` | Alert FK |
| `linked_at` | `TIMESTAMPTZ` | Detection Worker가 자동 연결한 시각 |
| `created_at` | `TIMESTAMPTZ` | 연결 행 생성 시각 |
| `updated_at` | `TIMESTAMPTZ` | 연결 행 마지막 갱신 시각 |
| `is_delete` | `BOOLEAN` | 연결 소프트 삭제 표시 |

### 8.11 `edr_events`

목적: Process, Network, File, DNS, L7 metadata를 검색·집계한다. 속성 수는 44개다.

| 컬럼 | 실제 ClickHouse 타입 | 설명 |
| --- | --- | --- |
| `event_id` | `UUID` | Agent가 생성한 전역 event 식별자 |
| `batch_id` | `UUID` | Collector 전송 묶음 식별자 |
| `endpoint_id` | `UInt64` | PostgreSQL Endpoint에 대한 논리 참조 |
| `agent_id` | `String` | 수집 당시 Agent ID snapshot |
| `hostname` | `String` | 수집 당시 hostname snapshot |
| `os_type` | `LowCardinality(String)` | 수집 당시 `WINDOWS` 또는 `MACOS` |
| `ip_address` | `Nullable(String)` | 수집 당시 Agent IP snapshot |
| `event_type` | `LowCardinality(String)` | 5종 telemetry 구분값 |
| `occurred_at` | `DateTime64(3, 'UTC')` | 단말에서 실제 event가 발생한 시각 |
| `ingested_at` | `DateTime64(3, 'UTC')` | Event Storage Worker가 처리한 시각 |
| `process_name` | `Nullable(String)` | 관련 프로세스 이름 |
| `process_path` | `Nullable(String)` | 프로세스 실행 경로 |
| `pid` | `Nullable(UInt64)` | 프로세스 ID |
| `ppid` | `Nullable(UInt64)` | 부모 프로세스 ID |
| `command_line` | `Nullable(String)` | 프로세스 실행 명령행 |
| `user_name` | `Nullable(String)` | 프로세스 실행 사용자 |
| `file_path` | `Nullable(String)` | 변경 또는 관찰한 파일 경로 |
| `file_action` | `Nullable(String)` | 파일 생성·변경 등 동작 |
| `file_hash_sha256` | `Nullable(String)` | 파일 콘텐츠 SHA-256 |
| `remote_ip` | `Nullable(String)` | 원격 통신 대상 IP |
| `remote_domain` | `Nullable(String)` | 원격 대상 도메인 |
| `remote_port` | `Nullable(UInt16)` | 원격 대상 포트 |
| `protocol` | `Nullable(String)` | TCP/UDP 등 전송 프로토콜 |
| `dns_query` | `Nullable(String)` | DNS 질의 이름 |
| `dns_record_type` | `Nullable(String)` | A, AAAA 등 DNS record type |
| `dns_response_code` | `Nullable(String)` | NOERROR 등 DNS 응답 코드 |
| `dns_answers_json` | `Nullable(String)` | DNS answer 문자열 배열 JSON |
| `l7_protocol` | `Nullable(String)` | HTTP 또는 TLS 등 애플리케이션 프로토콜 |
| `http_method` | `Nullable(String)` | HTTP request method |
| `http_host` | `Nullable(String)` | HTTP Host header |
| `url` | `Nullable(String)` | query/fragment를 제거한 URL path |
| `http_status_code` | `Nullable(UInt16)` | 관측된 HTTP response status |
| `http_user_agent` | `Nullable(String)` | HTTP User-Agent |
| `tls_sni` | `Nullable(String)` | TLS ClientHello의 SNI |
| `tls_version` | `Nullable(String)` | 관측된 TLS 버전 |
| `tls_certificate_subject` | `Nullable(String)` | 서버 인증서 subject |
| `tls_certificate_issuer` | `Nullable(String)` | 서버 인증서 issuer |
| `tls_certificate_sha256` | `Nullable(String)` | 서버 인증서 SHA-256 |
| `raw_payload` | `String` | PCAP이 아닌 정규화 telemetry event JSON |
| `payload_sha256` | `FixedString(64)` | 정규화 payload 충돌·중복 검사용 SHA-256 |
| `schema_version` | `UInt16` | Collector telemetry schema 버전 |
| `created_at` | `DateTime64(3, 'UTC')` | ClickHouse row 최초 생성 시각 |
| `updated_at` | `DateTime64(3, 'UTC')` | ReplacingMergeTree 최신 버전 선택 시각 |
| `is_delete` | `UInt8` | 논리 삭제 표시. 조회는 `0`만 사용 |

`raw_payload`는 PCAP packet이 아니라 정규화된 metadata event JSON이다.

Event 조회, latest-row 선택과 `uniqExact(event_id)` 집계는 `is_delete=false` row만 사용한다. 요청 `[from, to)`와 겹치는 UTC DAY bucket은 `bucket_start_at < to AND bucket_end_at > from`으로 선택하고 실제 event는 원래 `[from, to)`로 다시 필터링한다.

### 8.12 `alerts`

목적: Detection Worker가 생성한 탐지 결과와 MITRE ATT&CK mapping을 저장한다. 속성 수는 22개다. Alert의 `rule_name`, `title`, `summary`는 탐지 당시 RuleV1의 `rule_name`, `alert_title`, `alert_summary` 문자열을 그대로 snapshot한다. 모든 `enabled=true` RuleV1은 tactic/technique code가 필수이고 누락되거나 `mappings/mitre_attack.yaml`에 없으면 readiness를 실패시킨다. YAML에는 code만 저장하고 Backend가 고정 mapping에서 name을 변환하므로 MITRE code/name 4개 컬럼은 모두 NOT NULL이다. `(event_id, rule_code, rule_version)`은 unique이며 담당자 컬럼은 없다.

| 컬럼 | 실제 PostgreSQL 타입 | 설명 |
| --- | --- | --- |
| `alert_id` | `BIGSERIAL` | Alert PK |
| `endpoint_id` | `BIGINT` | 탐지 대상 Endpoint FK |
| `event_id` | `UUID` | 근거 ClickHouse event의 논리 참조 |
| `event_occurred_at` | `TIMESTAMPTZ` | 근거 event 발생 시각. ClickHouse 상세 조회 routing에 사용 |
| `batch_id` | `UUID NULL` | 근거 event가 포함된 Collector batch ID |
| `agent_id` | `VARCHAR(64)` | 탐지 당시 Agent ID snapshot |
| `rule_code` | `VARCHAR(100)` | RuleV1의 안정된 식별 코드 |
| `rule_name` | `VARCHAR(200)` | 탐지 당시 rule 이름 snapshot |
| `rule_version` | `INTEGER` | 탐지에 사용한 rule 버전 |
| `mitre_tactic_code` | `VARCHAR(20)` | MITRE ATT&CK tactic 코드 |
| `mitre_tactic_name` | `VARCHAR(100)` | 탐지 당시 tactic 이름 snapshot |
| `mitre_technique_code` | `VARCHAR(30)` | MITRE ATT&CK technique 코드 |
| `mitre_technique_name` | `VARCHAR(200)` | 탐지 당시 technique 이름 snapshot |
| `title` | `VARCHAR(200)` | 사용자에게 표시할 Alert 제목 snapshot |
| `summary` | `TEXT` | Alert 설명 및 탐지 근거 요약 snapshot |
| `severity` | `VARCHAR(20)` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `risk_score` | `NUMERIC(5,2)` | 0~100 위험 점수 |
| `status` | `VARCHAR(30)` | `OPEN`, `IN_PROGRESS`, `RESOLVED` |
| `detected_at` | `TIMESTAMPTZ` | Detection Worker 탐지 시각 |
| `created_at` | `TIMESTAMPTZ` | Alert 생성 시각 |
| `updated_at` | `TIMESTAMPTZ` | 상태 등 마지막 변경 시각 |
| `is_delete` | `BOOLEAN` | 소프트 삭제 표시 |

## 9. 주요 상태값

| 테이블 | 컬럼 | 값 |
| --- | --- | --- |
| `local_event_buffer` | `status` | `PENDING`, `FAILED` |
| `event_failures` | `status` | `FAILED`, `REPROCESSED`, `REPROCESS_FAILED` |
| `endpoints` | `status` | `ONLINE`, `OFFLINE`, `RETIRED` |
| `users` | `status` | `ACTIVE`, `DISABLED` |
| `users` | `locale` | `EN`, `KO` |
| `ingest_metadata` | `storage_backend` | `CLICKHOUSE`, `S3` |
| `ingest_metadata` | `storage_class` | `HOT`, `GLACIER_FLEXIBLE_RETRIEVAL` |
| `ingest_metadata` | `storage_status` | `HOT`, `ARCHIVED`, `RESTORE_REQUESTED`, `RESTORED`, `RESTORE_FAILED`, `EXPIRED` |
| `alerts` | `status` | `OPEN`, `IN_PROGRESS`, `RESOLVED` |
| `incidents` | `status` | `OPEN`, `CLOSED` |
| `edr_events` | `event_type` | `PROCESS_EXECUTION`, `NETWORK_CONNECTION`, `FILE_EVENT`, `DNS_QUERY`, `L7_EVENT` |

## 10. ERD 외부 항목과 향후 확장

- Nginx, Uvicorn, FastAPI, Kafka, S3, Glacier는 인프라이므로 ERD 테이블이 아니다.
- Npcap/tcpdump는 live capture input이며 PCAP file storage가 아니다.
- Agent command, PCAP artifact, PCAP segment, automatic replay scheduler/topic, occurrence/attempt table은 없다.
- Archive restore job/request table과 영구 restored Standard object는 없다.
- Rollup, orphan reconciliation, CAS 경쟁 처리, 다단계 failure versioning은 규모 검증 후 확장한다.
- Windows Minifilter/WFP와 macOS Endpoint Security/System Extension은 포트폴리오 범위에서 제외한다.
