# EDR Dashboard MVP API 및 Collector REST 명세

## 1. 문서 목적

이 문서는 single-tenant 포트폴리오 EDR PoC의 Dashboard REST API와 Windows/macOS Agent Collector REST 계약을 정의한다.

Endpoint Risk와 전역 EDR 상태의 계산 공식은 `RISK_POLICY.md`, 프론트 route·polling·화면 mapping·시각 token·component state는 `../frontend/FRONTEND_SPEC.md`를 따른다. 외부 API 응답 shape가 충돌하면 이 문서의 FastAPI/Pydantic 계약이 우선한다.

Agent는 Process, Network, File, DNS, L7 5종 metadata를 전송한다. Npcap/tcpdump에서 읽은 원본 packet은 실시간 분석 후 폐기하며 PCAP 파일, PCAP upload API, Agent command API는 제공하지 않는다.

## 2. 최종 API 개수

| 구분 | 개수 |
| --- | ---: |
| Dashboard Backend REST API | 30 |
| Collector REST API | 3 |
| **제품 REST API 합계** | **33** |

`/health/live`, `/health/ready`, `/metrics`, Swagger/OpenAPI 경로는 운영 endpoint이므로 제품 API 개수에서 제외한다. Failure 재처리는 공개 REST API가 아니라 관리자용 Python CLI로 수행한다.

## 3. 설계 기준

### 3.1 테넌시와 지원 OS

- single tenant이며 `tenantId`를 사용하지 않는다.
- Windows Agent는 C++20 Service/CLI다.
- macOS Agent는 Swift CLI + system LaunchDaemon이다. 현재 packet capture 때문에 전체 프로세스가 root로 실행되며, root-owned config/private key/state와 `umask 077`을 강제하지만 별도 privileged helper 분리는 구현하지 않았다.
- Linux와 iOS는 지원하지 않는다.

### 3.2 저장소 구분

| 저장소 | 데이터 |
| --- | --- |
| Agent SQLite | ACK 전 `local_event_buffer` |
| PostgreSQL | `users`, `endpoints`, `agent_auth_keys`, `alerts`, `incidents`, `incident_alerts`, `audit_logs`, `ingest_metadata` |
| ClickHouse | `edr_events`, `event_failures` |
| S3 Standard | 최초 실패부터 7일까지 failure 원문 |
| Glacier Instant Retrieval | 7일 이후 failure 원문, 총 90일 |
| Glacier Flexible Retrieval | raw event archive와 RestoreObject 7일 임시 복원 |

PostgreSQL에는 event failure row나 원문을 저장하지 않는다. Failure payload의 Standard/Instant lifecycle은 `ingest_metadata`가 아니라 S3 lifecycle과 `event_failures` pointer로 관리한다. 원본 PCAP은 어떤 저장소에도 저장하지 않는다.

### 3.3 패킷 metadata 정책

- Windows Npcap, macOS tcpdump는 live packet input provider다.
- packet에서 Network/DNS/HTTP plaintext/TLS metadata를 생성한 뒤 원 packet을 폐기한다.
- TLS payload는 복호화하지 않는다.
- TLS 필드는 SNI, version, certificate subject/issuer/SHA-256로 제한한다. Passive capture에서 실제로 관측된 값만 채우며, TLS 1.3 암호화 handshake 등으로 보이지 않는 SNI·certificate 필드는 `null`로 두고 event를 거절하지 않는다.
- `PCAP_CAPTURE` event type을 사용하지 않는다.

### 3.4 수집·저장 정책

| 항목 | 정책 |
| --- | --- |
| micro-batch | 5초, 100 events, 5MiB 중 먼저 도달 |
| heartbeat | 30초 ±10% jitter |
| OFFLINE | 2분 미수신 |
| stale | 7일 미수신, 별도 boolean 파생값 |
| SQLite ACK | `acceptedEventIds` row 즉시 물리 삭제 |
| raw archive | Endpoint별 object checksum 검증 + 7일 safety window 후 동일 UTC 날짜의 ClickHouse partition 전체 삭제 |
| failure payload | S3 Standard 7일 → Glacier Instant Retrieval, 최초 실패부터 90일 |
| Rollup | 현재 제외, 추후 확장 |

`batchId`는 전송 추적용이며 서버에 ingest batch table을 만들지 않는다.

`RETIRED`가 아닌 Endpoint는 Heartbeat 수신 시 `ONLINE`이 된다. 기존 Detection Worker process의 30초 periodic task가 `last_seen_at`을 검사해 2분 미수신 Endpoint를 `OFFLINE`으로 바꾼다. `RETIRED`는 ONLINE/OFFLINE보다 우선하며 자동 변경하지 않는다.

### 3.5 Latest 조회 규칙

```text
LATEST_15M
LATEST_1H
LATEST_24H
LATEST_7D
CUSTOM
```

- 기본값은 `LATEST_24H`다.
- `CUSTOM`만 `from`, `to`를 요구한다.
- 모든 범위는 UTC `[from, to)`다.
- 단일 요청 최대 범위는 31일이다.

## 4. 공통 규약

### 4.1 Base URL

```text
Dashboard: https://api.example.com/api/v1
Collector: https://collector.example.com/api/v1
```

### 4.2 인증과 신원

| 호출자 | 인증 |
| --- | --- |
| Dashboard | JWT Bearer |
| Agent | mTLS |

최초 등록은 CA-valid Agent certificate SAN의 `agentId`와 request `agentId`가 일치해야 하며, 이 값으로 Endpoint identity를 생성한다. 등록 API를 제외한 heartbeat·telemetry 요청은 SAN `agentId`, request `agentId`, 등록된 Endpoint identity가 모두 일치하고, 전달된 SHA-256 fingerprint가 해당 Endpoint의 활성 `agent_auth_keys` row와 일치해야 한다. 활성 인증서는 `is_delete=false`, fingerprint 일치, `revoked_at IS NULL`, `issued_at <= now()`, `expires_at > now()`이며 Endpoint가 `RETIRED`가 아닌 row다. Nginx는 외부 certificate forwarding header를 제거하고 TLS 검증을 통과한 escaped PEM certificate만 Backend에 전달한다. Backend는 certificate의 단일 URI SAN, subject, SHA-256 fingerprint, notBefore, notAfter를 직접 읽고 시각을 UTC timestamp로 변환해 각각 `issued_at`, `expires_at`으로 저장한다. REST request/response DTO에는 인증서 필드를 추가하지 않는다.

관리자는 먼저 다음 CLI로 개발용 CA certificate와 Agent certificate/private key를 발급한다.

```text
python -m tools.provision_agent_cert --agent-id <AGENT_ID>
```

`agentId`는 `[a-z0-9][a-z0-9._-]{0,63}`이며 certificate의 단일 URI SAN은 `urn:edr:agent:<agentId>`다. 개발환경별 CA는 하나만 사용하고 최초 CLI 실행 시 없으면 생성하며, CA certificate는 Nginx client-CA trust bundle과 Agent에 설치하고 CA private key는 관리자 로컬 보안 경로에만 둔다. Agent에 certificate/key/CA를 설치한 뒤 mTLS로 기존 등록 API를 호출하고 서버는 fingerprint와 SAN agent ID를 저장한다. Rotation도 같은 CA로 새 certificate를 발급한 뒤 기존 등록 API를 다시 호출한다. 새 `agent_auth_keys` row 저장이 성공하면 같은 transaction에서 기존 활성 row의 `revoked_at`을 기록하며 인증서 중첩 유예기간은 두지 않는다. 인증서 발급 REST API는 만들지 않는다.

### 4.3 Dashboard 권한

```text
ADMIN
ANALYST
VIEWER
```

- 조회 API: 세 role 모두 허용
- 본인 Dashboard layout 조회·저장·삭제: 세 role 모두 허용. JWT `sub` 사용자만 대상으로 하며 body/query user ID는 받지 않는다.
- Alert 상태 변경: `ADMIN`, `ANALYST`
- Archive restore 시작: `ADMIN`, `ANALYST`; `VIEWER`는 `403 FORBIDDEN`
- 담당자 지정 기능 없음
- `AGENT`, `SYSTEM`은 user role이 아닌 service principal이다.

### 4.4 공통 응답

성공:

```json
{
  "data": {},
  "meta": {
    "requestId": "req_01HZX..."
  }
}
```

오류:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "요청 값이 올바르지 않습니다.",
    "retryable": false,
    "details": []
  },
  "meta": {
    "requestId": "req_01HZX..."
  }
}
```

FastAPI/Pydantic response model을 최종 응답 계약으로 사용한다.

- 성공 응답은 항상 `data`와 `meta.requestId`를 반환한다.
- 이 문서의 DTO 필드는 모두 required key다. `T | null`만 값이 nullable이며 key를 생략하지 않는다.
- `T[]`는 non-null list이며 값이 없으면 `[]`다.
- 모든 timestamp는 UTC RFC3339 `Z` 형식이다.
- Pydantic v2 nullable field는 기본값 없는 `T | None`으로 선언하고 FastAPI는 `response_model_exclude_none=false`, `response_model_exclude_unset=false`, `response_model_by_alias=true`를 사용한다.
- 내부 Python/DB snake_case는 Pydantic camelCase alias로 직렬화한다.
- 오류의 `details`도 항상 배열이며 각 원소는 `field: string | null`, `message: string`, `context: object | null` required key를 가진다. Field validation은 `context: null`, resource 상태 오류는 정해진 context object를 사용한다.

공통 목록 `data`는 다음 필드를 사용한다.

| 필드 | 타입 |
| --- | --- |
| `items` | `T[]` |
| `page` | integer |
| `size` | integer |
| `total` | integer |

### 4.5 공통 HTTP 상태

| HTTP | 의미 |
| ---: | --- |
| 200 | 조회/멱등 성공 또는 telemetry event별 부분 성공 결과 |
| 201 | 생성 성공 |
| 202 | archive restore 접수 |
| 400 | validation 실패 |
| 401 | 인증 실패 |
| 403 | 권한, disabled 계정 또는 retired Endpoint |
| 404 | resource 없음 |
| 409 | 상태·identity 충돌 |
| 413 | body/event 수 제한 초과 |
| 429 | rate limit |
| 503 | Kafka/DB 등 일시 장애 |

### 4.6 목록 Query

| Query | 타입 | 기본 | 설명 |
| --- | --- | --- | --- |
| `page` | integer | 1 | 1 이상 |
| `size` | integer | 50 | 1~500 |
| `timePreset` | string | `LATEST_24H` | latest preset |
| `from`, `to` | RFC3339 | - | CUSTOM일 때 필수 |
| `sortOrder` | string | `desc` | `asc`, `desc` |

모든 목록 filter는 함께 전달되면 AND로 결합한다. 빈 string query는 validation 대상이므로 프론트는 전송하지 않는다. 동일 sort key에서 결과가 같으면 각 API가 정의한 ID tie-break를 적용해 pagination 순서를 결정적으로 유지한다.

## 5. 최종 API 목록

### 5.1 Dashboard Backend REST API

| No | Method | Path | 역할 | Pydantic `data` model |
| ---: | --- | --- | --- | --- |
| 1 | POST | `/auth/login` | 로그인 | `LoginData` |
| 2 | GET | `/users/me` | 현재 사용자 조회 | `UserDto` |
| 3 | PATCH | `/users/me/locale` | 현재 사용자 locale 변경 | `UserDto` |
| 4 | GET | `/endpoints` | Endpoint 목록 | `PagedData<EndpointDto>` |
| 5 | GET | `/endpoints/{endpointId}` | Endpoint 상세 | `EndpointDetailDto` |
| 6 | GET | `/endpoints/{endpointId}/process-tree` | 수집 Event 기반 Process Tree | `ProcessTreeDto` |
| 7 | GET | `/events` | Event 목록 | `PagedData<EventDto>` |
| 8 | GET | `/events/{eventId}` | Event 상세 | `EventDetailDto` |
| 9 | GET | `/failures` | 읽기 전용 Failure/DLQ 목록 | `PagedData<EventFailureDto>` |
| 10 | POST | `/archives/restores` | Archive 복원 시작 | `ArchiveRestoreStartDto` |
| 11 | GET | `/archives/restores` | Archive 복원 상태 | `PagedData<ArchiveBucketDto>` |
| 12 | GET | `/alerts` | Alert 목록 | `PagedData<AlertDto>` |
| 13 | GET | `/alerts/{alertId}` | Alert 상세 | `AlertDetailDto` |
| 14 | PATCH | `/alerts/{alertId}/status` | Alert 상태 변경 | `AlertDto` |
| 15 | GET | `/incidents` | Incident 목록 | `PagedData<IncidentDto>` |
| 16 | GET | `/incidents/{incidentId}` | Incident 상세 | `IncidentDetailDto` |
| 17 | GET | `/incidents/{incidentId}/timeline` | Event→Alert→Incident 타임라인 | `AttackTimelineDto` |
| 18 | GET | `/incidents/{incidentId}/investigation` | 관측 근거 기반 Incident graph read model | `IncidentInvestigationDto` |
| 19 | GET | `/dashboard/summary` | 전체 요약 | `DashboardSummaryDto` |
| 20 | GET | `/dashboard/endpoints/summary` | Endpoint 요약 | `EndpointSummaryDto` |
| 21 | GET | `/dashboard/ingest/summary` | 수집·저장·failure 요약 | `IngestSummaryDto` |
| 22 | GET | `/dashboard/topology` | Endpoint egress 관계 요약 | `EgressTopologyDto` |
| 23 | GET | `/dashboard/layouts/{dashboardKey}` | 본인 저장 layout 또는 기본 layout 조회 | `DashboardLayoutDto` |
| 24 | PUT | `/dashboard/layouts/{dashboardKey}` | 본인 전체 layout revision upsert | `DashboardLayoutDto` |
| 25 | DELETE | `/dashboard/layouts/{dashboardKey}` | 본인 저장 layout 삭제·기본값 복귀 | `DashboardLayoutDto` |
| 26 | GET | `/operations/health` | 실시간 의존 서비스·Kafka Worker 상태 | `OperationsHealthDto` |
| 27 | GET | `/intelligence/forward-dns` | Domain의 현재 A/AAAA 조회 | `ForwardDnsDto` |
| 28 | GET | `/intelligence/reverse-dns` | IP의 현재 PTR 후보 조회 | `ReverseDnsDto` |
| 29 | GET | `/intelligence/dns-lookup` | DNS record type별 조회 | `DnsLookupDto` |
| 30 | GET | `/intelligence/correlate` | Live DNS와 관찰 Event의 IP/Domain 관계 조회 | `CorrelationDto` |

### 5.2 Collector REST API

| No | Method | Path | 역할 |
| ---: | --- | --- | --- |
| 1 | POST | `/collector/agents/register` | 등록/재등록 |
| 2 | POST | `/collector/agents/heartbeat` | 상태와 sensor health 갱신 |
| 3 | POST | `/collector/telemetry/batches` | metadata telemetry ingest |

## 6. Auth와 Users API

### 6.1 로그인

```http
POST /api/v1/auth/login
```

```json
{
  "loginId": "analyst",
  "password": "password"
}
```

```json
{
  "data": {
    "accessToken": "jwt",
    "tokenType": "Bearer",
    "expiresIn": 43200,
    "user": {
      "userId": 1,
      "loginId": "analyst",
      "name": "Analyst",
      "role": "ANALYST",
      "status": "ACTIVE",
      "locale": "EN"
    }
  },
  "meta": {"requestId": "req_01HZX..."}
}
```

`LoginData`는 `accessToken: string`, `tokenType: "Bearer"`, `expiresIn: integer`, `user: UserDto`다. `UserDto`는 `userId: integer`, `loginId: string`, `name: string`, `role: ADMIN | ANALYST | VIEWER`, `status: ACTIVE | DISABLED`, `locale: EN | KO` required field를 반환한다.

Login ID는 사용자가 지정하며 trim/lowercase 정규화 후 PostgreSQL의 `LOWER(login_id)` partial unique index로 대소문자 구분 없이 중복을 막는다. DB column과 API 길이는 3~64자이고 영문 소문자 또는 숫자로 시작하며 영문, 숫자, `.`, `_`, `@`, `+`, `-`를 허용한다. `@`는 기존 이메일 계정 migration 호환을 위한 허용 문자일 뿐 이메일 형식을 요구하지 않는다. password 요청은 1~1,024자로 제한한다. `is_delete=false AND status=ACTIVE`만 로그인할 수 있고 `DISABLED`는 `403 ACCOUNT_DISABLED`다. Nginx는 로그인 요청을 IP별 분당 10회와 burst 10으로 제한하며 초과 시 `429 RATE_LIMITED`를 반환한다. JWT access token은 현재 브라우저 탭의 `sessionStorage`에 보관해 새로고침 후 복구하며 기본 만료는 12시간이다. `EDR_ACCESS_TOKEN_TTL_SECONDS`로 5분~7일 범위에서 조정한다.

최초 ADMIN은 다음 관리자 CLI로 생성한다.

```text
python -m tools.create_admin --login-id <LOGIN_ID> --name <DISPLAY_NAME>
```

개발 환경에서 같은 ID의 비밀번호를 다시 지정할 때는 `--reset-existing`을 추가한다. 비밀번호는 기본적으로 숨김 prompt에서 입력하며 `--password-stdin`도 사용할 수 있다.

CLI는 `ACTIVE` ADMIN을 생성한다. 비밀번호나 초기 계정을 migration에 하드코딩하지 않으며 사용자 생성·삭제·상태 변경 REST API는 만들지 않는다.

### 6.2 현재 사용자 조회

```http
GET /api/v1/users/me
Authorization: Bearer <token>
```

`operationId`는 `usersMeGet`이다. `ADMIN`, `ANALYST`, `VIEWER`가 자신의 활성 사용자 정보를 조회할 수 있으며 응답은 `SuccessEnvelope<UserDto>`다. 미인증 요청은 `401`이다.

```json
{
  "data": {
    "userId": 1,
    "loginId": "analyst",
    "name": "Analyst",
    "role": "ANALYST",
    "status": "ACTIVE",
    "locale": "EN"
  },
  "meta": {"requestId": "req_01HZX..."}
}
```

### 6.3 현재 사용자 locale 변경

```http
PATCH /api/v1/users/me/locale
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "locale": "KO"
}
```

`operationId`는 `usersLocaleUpdate`다. 세 Dashboard role 모두 자신의 locale만 변경할 수 있으며 응답은 변경된 `SuccessEnvelope<UserDto>`다. `EN`, `KO` 외의 값은 기존 `400 VALIDATION_ERROR` 계약을 따른다. 같은 locale 요청은 멱등이며 `updated_at`과 audit log를 다시 기록하지 않는다. 실제 변경은 사용자 row와 `USER_LOCALE_CHANGED` audit log를 같은 transaction에서 기록한다.

Backend의 `users.locale`이 최종 source of truth다. JWT claim은 기존 `sub`, `role`, `iat`, `exp` 구조를 유지하고 locale을 포함하지 않으므로 locale 변경에 token 재발급이 필요하지 않다. Backend 오류 메시지는 locale별로 바꾸지 않으며 Frontend는 안정적인 `error.code`를 번역하고 동적 `message`는 fallback으로만 사용한다.

## 7. Collector REST 계약

### 7.1 Agent 등록

```http
POST /api/v1/collector/agents/register
```

```json
{
  "agentId": "agent-win-001",
  "hostname": "WIN-ENDPOINT-01",
  "osType": "WINDOWS",
  "osVersion": "11",
  "agentVersion": "0.1.0",
  "agentBuildId": "win-x64-20260711.1",
  "agentArch": "X64",
  "capabilityCodes": [
    "PROCESS_EXECUTION",
    "NETWORK_CONNECTION",
    "FILE_EVENT",
    "DNS_QUERY",
    "L7_EVENT",
    "PACKET_METADATA_V1"
  ]
}
```

등록 시 `sensor_health_json`은 빈 배열 `[]`로 초기화하고 첫 heartbeat의 전체 snapshot으로 교체한다. Endpoint 사용자·등록자 개인정보는 수집하지 않는다.

```json
{
  "data": {
    "endpointId": 1001,
    "agentId": "agent-win-001",
    "status": "ONLINE",
    "heartbeatIntervalSeconds": 30,
    "registeredAt": "2026-07-11T00:00:01Z"
  },
  "meta": {"requestId": "req_01HZX..."}
}
```

- 신규 Agent/certificate는 `201`이다.
- 같은 `agentId`와 fingerprint 재등록은 멱등 `200`이다.
- 같은 SAN agent ID의 새 CA-valid certificate는 rotation `200`이며 새 `agent_auth_keys` row를 만들고 저장 성공 후 기존 활성 row를 즉시 revoke한다.
- 다른 Endpoint가 사용 중인 `agentId`/fingerprint는 `409`다.
- `RETIRED` Endpoint의 등록·rotation은 `403 ENDPOINT_RETIRED`이며 상태와 인증서 이력을 변경하지 않는다.

### 7.2 Agent Heartbeat

```http
POST /api/v1/collector/agents/heartbeat
```

```json
{
  "agentId": "agent-win-001",
  "agentVersion": "0.1.0",
  "agentBuildId": "win-x64-20260711.1",
  "agentArch": "X64",
  "capabilityCodes": [
    "PROCESS_EXECUTION",
    "NETWORK_CONNECTION",
    "FILE_EVENT",
    "DNS_QUERY",
    "L7_EVENT",
    "PACKET_METADATA_V1"
  ],
  "bufferDepth": 12,
  "sensorHealth": [
    {"sensor": "PROCESS", "status": "HEALTHY"},
    {"sensor": "PACKET_METADATA", "provider": "NPCAP", "status": "HEALTHY", "packetDropCount": 0},
    {"sensor": "L7", "status": "HEALTHY", "parseErrorCount": 0}
  ],
  "sentAt": "2026-07-11T00:00:30Z"
}
```

```json
{
  "data": {
    "serverTime": "2026-07-11T00:00:30Z",
    "nextHeartbeatSeconds": 30,
    "endpointStatus": "ONLINE"
  },
  "meta": {"requestId": "req_01HZX..."}
}
```

Heartbeat는 상태 보고 전용이다. `RETIRED`가 아니면 server receive time으로 `last_seen_at`을 갱신하고 `ONLINE`으로 바꾼다. `RETIRED` Endpoint에는 `403 ENDPOINT_RETIRED`를 반환하고 상태와 `last_seen_at`을 변경하지 않는다. 등록 API를 제외한 heartbeat·telemetry는 활성 인증서 fingerprint가 일치하지 않으면 `401 INVALID_AGENT_CERTIFICATE`를 반환한다. Command, command report, upload window, artifact 정보는 요청·응답에 포함하지 않는다.

`capabilityCodes`와 `sensorHealth`는 patch가 아니라 Agent의 현재 전체 snapshot이다. 서버는 heartbeat를 받을 때 `capability_codes_json`, `sensor_health_json`을 각각 이 배열로 교체한다.

### 7.3 Telemetry Batch 수집

```http
POST /api/v1/collector/telemetry/batches
```

```json
{
  "schemaVersion": 1,
  "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e000",
  "agentId": "agent-win-001",
  "sentAt": "2026-07-11T00:00:05Z",
  "events": [
    {
      "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e001",
      "eventType": "DNS_QUERY",
      "occurredAt": "2026-07-11T00:00:04.123Z",
      "payload": {
        "query": "example.com",
        "recordType": "A",
        "responseCode": "NOERROR",
        "answers": ["93.184.216.34"]
      }
    }
  ]
}
```

제한:

- event 수: 1~100
- uncompressed body: 최대 5MiB
- `Content-Type: application/json`
- 선택적 `Content-Encoding: gzip`
- `eventId`, `batchId`: UUID/UUIDv7 권장
- `occurredAt`: server time보다 5분 초과 미래이면 거절
- 같은 batch 안의 중복 `eventId`는 거절

Event별 필수 필드:

| Event type | 필수 payload | 선택 payload |
| --- | --- | --- |
| `PROCESS_EXECUTION` | `processName`, `pid` | processPath, ppid, commandLine, userName |
| `NETWORK_CONNECTION` | `protocol`, `remoteIp`, `remotePort` | remoteDomain, processName, pid |
| `FILE_EVENT` | `filePath`, `action` | sha256, processName, pid |
| `DNS_QUERY` | `query`, `recordType` | responseCode, answers, processName, pid |
| `L7_EVENT` | `l7Protocol` | HTTP/TLS metadata fields |

`L7_EVENT` HTTP 필드는 `httpMethod`, `httpHost`, `url`, `httpStatusCode`, `httpUserAgent`만 허용한다. `url`은 query와 fragment를 제거한 path만 저장한다. Request/response body, cookie, authorization 및 그 밖의 임의 header는 수집하지 않는다. TLS 필드는 `tlsSni`, `tlsVersion`, `tlsCertificateSubject`, `tlsCertificateIssuer`, `tlsCertificateSha256`만 허용한다. Packet payload와 PCAP bytes는 허용하지 않는다. `RETIRED` Endpoint의 telemetry는 event를 Kafka에 publish하지 않고 `403 ENDPOINT_RETIRED`를 반환한다.

성공/부분 성공:

```json
{
  "data": {
    "batchId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e000",
    "acceptedEventIds": ["018ff8f4-86de-7b25-9b8a-2d22f6a3e001"],
    "rejectedEvents": []
  },
  "meta": {"requestId": "req_01HZX..."}
}
```

`rejectedEvents` 원소 계약:

```json
{
  "eventId": "018ff8f4-86de-7b25-9b8a-2d22f6a3e002",
  "code": "EVENT_TIME_IN_FUTURE",
  "message": "occurredAt이 허용 범위를 벗어났습니다.",
  "retryable": false
}
```

- 정상 request envelope의 event별 성공·거절 결과는 부분 성공을 포함해 `200`으로 반환한다.
- request envelope 자체가 잘못되면 `400`, body/event 수 제한을 넘으면 `413`이며 event별 결과를 만들지 않는다.
- Kafka 장애로 broker ACK를 하나도 받지 못하면 `503`이며 Agent는 아직 ACK되지 않은 row를 재시도한다.

Collector는 Kafka broker ACK를 받은 event만 `acceptedEventIds`에 포함하며, 이 ACK는 downstream ClickHouse 저장이나 탐지 완료를 의미하지 않는다. 같은 batch 안의 중복·payload validation은 Collector가 거절하고, 이전 전송까지 포함한 전역 `eventId` 멱등성과 identity/payload 충돌은 Kafka 뒤 Event Storage Worker가 처리한다. Worker는 같은 `eventId`와 같은 identity/payload를 논리 중복으로 만들지 않고, identity 또는 payload가 다른 동일 `eventId`는 failure 처리한다.

Event Storage Worker는 `occurredAt`의 UTC 날짜별 HOT row를 확인한다. 해당 날짜의 `CLICKHOUSE/HOT` row가 partition 삭제 완료로 `is_delete=true`이면 ClickHouse partition을 다시 만들지 않고 `ARCHIVED_DAY_IMMUTABLE` failure로 기록한다. HOT row가 활성 상태에서 이미 검증된 S3 Archive object에 늦은 event가 추가되면 대응 S3 row의 `archive_verified_at`과 `checksum_sha256`을 `null`로 되돌리고 Archive Worker가 해당 Endpoint/UTC DAY object를 다시 export·검증한다.

Collector validation 실패는 Kafka offset이 없으므로 server `event_failures`에 저장하지 않는다. Agent는 `retryable=true`인 거절 row를 `PENDING`으로 유지해 재시도하고, `retryable=false`인 row는 SQLite `FAILED`로 남긴다. 두 경우 모두 운영 metric에 rejection count를 기록한다.

## 8. Endpoints API

### 8.1 목록

```http
GET /api/v1/endpoints?q=SOC-WIN&status=ONLINE&osType=WINDOWS&page=1&size=50
```

목록에는 Endpoint ID, agent ID, hostname, OS, IP, Agent version/build/arch, status, lastSeenAt, isStale, sensor health와 Backend가 계산한 Endpoint Risk를 반환한다.

목록 응답 model은 `PagedData<EndpointDto>`다.

목록 Query:

| Query | 타입 | 기본 | 설명 |
| --- | --- | --- | --- |
| `endpointIds` | repeated integer | - | Endpoint ID exact match, 여러 값은 OR |
| `q` | trimmed string, 1~128자 | - | 숫자는 Endpoint ID exact, 문자열은 hostname/agent ID의 case-insensitive exact 또는 prefix |
| `status` | EndpointStatus | - | exact match |
| `osType` | `WINDOWS / MACOS` | - | exact match |
| `riskLevel` | RiskLevel | - | 현재 Endpoint Risk level exact match |
| `page`, `size` | integer | 1, 50 | 공통 pagination |
| `sortBy` | `riskScore / lastSeenAt / registeredAt` | `riskScore` | Endpoint sort field |
| `sortOrder` | `asc / desc` | `desc` | sort direction |

`riskScore`는 `risk.score`를 의미한다. 동일 sort 값의 tie-break는 `endpointId ASC`다.

`q`와 다른 filter는 AND로 결합한다. 숫자만 있는 `q`는 양의 정수 Endpoint ID exact match이며 wildcard로 해석하지 않는다. 문자열 `q`는 `%`, `_`, `\\`를 wildcard로 해석하지 않고 literal prefix로 처리한다. 검색 결과는 case-insensitive exact match 우선, `ONLINE → OFFLINE → RETIRED`, `riskScore DESC`, `hostname ASC`, `endpointId ASC` 순으로 안정 정렬하며 이때 `sortBy`와 `sortOrder`는 적용하지 않는다. 전체 Endpoint를 client로 prefetch하거나 contains scan을 제공하지 않는다.

`SensorHealthDto`:

| 필드 | 타입 |
| --- | --- |
| `sensor` | string |
| `status` | `HEALTHY / DEGRADED / UNAVAILABLE` |
| `provider` | nullable string |
| `packetDropCount` | nullable integer |
| `parseErrorCount` | nullable integer |

`EndpointRiskFactorDto`:

| 필드 | 타입 |
| --- | --- |
| `code` | string |
| `title`, `description` | string |
| `contribution` | integer |
| `sourceType` | EndpointRiskFactorSourceType |
| `sourceId` | integer |

`EndpointRiskDto`:

| 필드 | 타입 |
| --- | --- |
| `score` | 0~100 integer |
| `level` | RiskLevel |
| `activeAlertCount` | integer |
| `openIncidentCount` | integer |
| `highestAlertRiskScore` | nullable number |
| `calculatedAt` | timestamp |
| `riskFactors` | `EndpointRiskFactorDto[]` |

Endpoint Risk의 주요 입력은 `is_delete=false`인 `OPEN/IN_PROGRESS` Alert의 `riskScore`와 `OPEN` Incident다. `score`는 0~100으로 clamp한 integer이며 등급은 `LOW=0~24`, `MEDIUM=25~49`, `HIGH=50~79`, `CRITICAL=80~100`으로 고정한다. 활성 Alert가 없으면 `highestAlertRiskScore`는 `null`이고 count는 `0`이다. `riskFactors`는 `RISK_POLICY.md` 계산 순서에 따라 최대 5개를 반환하고 contribution 합계는 최종 score와 같으며, 값이 없으면 `[]`다. Event raw payload나 packet metadata 원문은 factor에 포함하지 않는다.

Endpoint Risk는 Dashboard API가 요청 시점의 PostgreSQL Alert/Incident snapshot에서 `RISK_POLICY.md` V1 공식으로 계산한다. 현재 active Alert/OPEN Incident 상태를 나타내므로 목록의 `timePreset`/`from`/`to`와 무관하다. 프론트는 Alert/Event 목록에서 점수를 다시 계산하지 않는다.

`EndpointDto`:

| 필드 | 타입 |
| --- | --- |
| `endpointId` | integer |
| `agentId`, `hostname` | string |
| `osType` | `WINDOWS / MACOS` |
| `osVersion`, `ipAddress` | nullable string |
| `agentVersion`, `agentBuildId` | nullable string |
| `agentArch` | nullable `X64 / ARM64` |
| `capabilityCodes` | `string[]` |
| `status` | `ONLINE / OFFLINE / RETIRED` |
| `lastSeenAt` | nullable timestamp |
| `isStale` | boolean |
| `sensorHealth` | `SensorHealthDto[]` |
| `risk` | `EndpointRiskDto` |
| `registeredAt` | timestamp |

`capabilityCodes`와 `sensorHealth`는 각각 `capability_codes_json`, `sensor_health_json`을 역직렬화한다. 배열 값이 없으면 `[]`다.

### 8.2 상세

```http
GET /api/v1/endpoints/{endpointId}
```

상세 응답 model은 `EndpointDetailDto`이며 `risk`를 포함한 `EndpointDto` 전체 필드와 `certificates: CertificateDto[]`를 반환한다.

`CertificateDto`:

| 필드 | 타입 |
| --- | --- |
| `certFingerprint`, `certSubject`, `certSanAgentId` | string |
| `issuedAt`, `expiresAt` | timestamp |
| `revokedAt` | nullable timestamp |
| `isExpired`, `isRevoked` | boolean |

`certificates`는 `agent_auth_keys` 이력에서 조회하며 값이 없으면 `[]`다. Private key, 개발용 CA private key, 내부 secret은 반환하지 않는다.

### 8.3 Process Tree 조회

```http
GET /api/v1/endpoints/{endpointId}/process-tree?timePreset=CUSTOM&from=...&to=...&selectedPid=1234
```

기존 `PROCESS_EXECUTION` Event의 PID/PPID를 묶어 `ProcessTreeDto`를 반환한다. node에는 process metadata, 최초/최종 관측 시각, Event 수, 선택 PID와 parent 수집 여부가 포함된다. 프로세스 실시간 상태나 실행 제어를 만들지 않으며 ERD 변경 없이 ClickHouse Event를 조회한다.

## 9. Events API

### 9.1 목록

```http
GET /api/v1/events?endpointId=1001&eventType=DNS_QUERY&timePreset=LATEST_24H&page=1&size=50
```

목록 Query:

| Query | 타입 | 기본 | 설명 |
| --- | --- | --- | --- |
| `endpointId` | integer | - | Endpoint exact match |
| `eventType` | EventType | - | exact match |
| `processName` | string | - | case-insensitive contains |
| `filePath` | string | - | case-insensitive contains |
| `domain` | string | - | `remoteDomain` 또는 `httpHost` case-insensitive contains |
| `remoteIp` | string | - | canonical IP exact match |
| `dnsQuery` | string | - | case-insensitive contains |
| `l7Protocol` | string | - | case-insensitive exact match |
| `timePreset` | TimePreset | `LATEST_24H` | latest preset |
| `from`, `to` | timestamp | - | CUSTOM일 때 필수 |
| `page`, `size` | integer | 1, 50 | 공통 pagination |
| `sortOrder` | `asc / desc` | `desc` | `occurredAt` 정렬 |

기본 정렬은 `(occurredAt DESC, eventId DESC)`이고 `sortOrder=asc`이면 두 field를 모두 ASC로 바꾼다.

목록 응답 model은 `PagedData<EventDto>`다. `EventDto`는 flat camelCase이며 아래 필드를 required key로 반환한다.

| 그룹 | 필드와 타입 |
| --- | --- |
| 공통 | `eventId: string`, `batchId: string`, `endpointId: integer`, `agentId: string`, `hostname: string`, `osType: WINDOWS/MACOS`, `ipAddress: nullable string`, `eventType: EventType`, `occurredAt: timestamp`, `ingestedAt: timestamp` |
| Process | `processName: nullable string`, `processPath: nullable string`, `pid: nullable integer`, `ppid: nullable integer`, `commandLine: nullable string`, `userName: nullable string` |
| File | `filePath: nullable string`, `fileAction: nullable string`, `fileHashSha256: nullable string` |
| Network | `remoteIp: nullable string`, `remoteDomain: nullable string`, `remotePort: nullable integer`, `protocol: nullable string` |
| DNS | `dnsQuery: nullable string`, `dnsRecordType: nullable string`, `dnsResponseCode: nullable string`, `dnsAnswers: string[]` |
| HTTP | `l7Protocol: nullable string`, `httpMethod: nullable string`, `httpHost: nullable string`, `url: nullable string`, `httpStatusCode: nullable integer`, `httpUserAgent: nullable string` |
| TLS | `tlsSni: nullable string`, `tlsVersion: nullable string`, `tlsCertificateSubject: nullable string`, `tlsCertificateIssuer: nullable string`, `tlsCertificateSha256: nullable string` |

Event 종류와 무관한 scalar 필드도 생략하지 않고 `null`로 반환한다. `dnsAnswers`는 `dns_answers_json`을 역직렬화하며 DB null 또는 빈 배열이면 항상 `[]`다. Collector request의 `payload.action` → `file_action`, `payload.sha256` → `file_hash_sha256`, `payload.query` → `dns_query`, `payload.recordType` → `dns_record_type`으로 정규화한다.

### 9.2 상세

```http
GET /api/v1/events/{eventId}?endpointId=1001&occurredAt=2026-07-11T00:00:04.123Z
```

상세 응답 model은 `EventDetailDto`다. `EventDto` 전체 필드에 `rawPayload: object`, `payloadSha256: string`, `schemaVersion: integer`를 추가한다. `rawPayload`는 정규화된 metadata event JSON이며 packet/PCAP bytes가 아니다.

`endpointId`, `occurredAt`은 ClickHouse partition pruning과 archive routing을 위해 요구한다. 원본 PCAP download URL은 제공하지 않는다.

API는 `is_delete=false` row에서 `event_id`별 최신 row를 조회하고 정확한 count는 `uniqExact(event_id)`로 계산한다. Rollup은 사용하지 않는다.

Event 목록·상세는 bucket 상태에 따라 다음과 같이 조회한다.

- `HOT`: ClickHouse에서 조회한다.
- `RESTORED`: PyArrow S3 filesystem으로 같은 Glacier Flexible Retrieval Parquet object를 직접 조회한다.
- HOT과 RESTORED 결과는 `(occurredAt, eventId)`로 병합 정렬한 뒤 pagination한다.
- 요청 `[from, to)`와 겹치는 UTC DAY bucket은 `bucketStartAt < to AND bucketEndAt > from`으로 선택하고, HOT ClickHouse query와 RESTORED PyArrow scan 모두 event의 `occurredAt`을 원래 `[from, to)`로 다시 필터링한다.
- archive 검증 후 ClickHouse 삭제 전 7일 safety window처럼 동일 논리 bucket에 HOT과 S3 row가 함께 있으면 HOT이 우선하며, 해당 S3 row의 상태는 조회를 차단하지 않는다.
- HOT 또는 RESTORED로 충족되지 않은 논리 bucket에 `ARCHIVED`, `RESTORE_REQUESTED`, `RESTORE_FAILED`, `EXPIRED` 상태가 있으면 부분 결과를 반환하지 않고 `409 ARCHIVE_NOT_READY`를 반환한다. 각 `error.details[].context`는 `endpointId`, `bucketStartAt`, `storageStatus` required field를 가진다.
- Event 조회가 archive 복원을 자동 시작하거나 restored data를 ClickHouse에 재적재하지 않는다.

### 9.3 Failure 목록

```http
GET /api/v1/failures?timePreset=LATEST_24H&status=FAILED&page=1&size=50
```

`PagedData<EventFailureDto>`를 반환하는 읽기 전용 DLQ Monitor API다. `status`, `failureStage`, `retryable`, 시간 범위, pagination과 sort를 지원한다. replay·삭제·상태 변경은 제공하지 않고 기존 관리자 CLI 경계를 유지한다.

## 10. Archive API

### 10.1 복원 시작

```http
POST /api/v1/archives/restores
```

```json
{
  "endpointIds": [1001],
  "from": "2026-01-01T00:00:00Z",
  "to": "2026-01-02T00:00:00Z"
}
```

`from`은 `to`보다 앞서야 하며 단일 요청 범위는 최대 31일이다.

`ADMIN`, `ANALYST`만 이 API를 호출할 수 있고 `VIEWER`는 `403 FORBIDDEN`이다. 서버는 고정 정책 `AWS RestoreObject(Days=7, Tier=Standard)`로 `S3/GLACIER_FLEXIBLE_RETRIEVAL` bucket을 임시 복원하고 `ingest_metadata`를 `RESTORE_REQUESTED`로 갱신한다. 원 object key, `storageBackend=S3`, `storageClass=GLACIER_FLEXIBLE_RETRIEVAL`은 바꾸지 않으며 영구 S3 Standard copy와 ClickHouse 재적재를 만들지 않는다.

응답 model `ArchiveRestoreStartDto`:

| 필드 | 타입 |
| --- | --- |
| `endpointIds` | `integer[]` |
| `from`, `to` | timestamp |
| `restoreDays` | integer, 고정 `7` |
| `retrievalTier` | string, 고정 `Standard` |
| `buckets` | `ArchiveBucketDto[]` |

HOT으로 충족되지 않은 `ARCHIVED`, `RESTORE_FAILED`, `EXPIRED` bucket이 하나라도 새 RestoreObject 호출로 전이하거나 기존 `RESTORE_REQUESTED`가 하나라도 진행 중이면 `202`다. 대상 S3 bucket이 모두 아직 유효한 `RESTORED`이거나 복원 대상 S3 bucket 없이 HOT bucket만 있으면 멱등 `200`이다. 동일 논리 bucket에 HOT row가 있으면 대응하는 S3 row에도 RestoreObject를 호출하지 않으며 HOT bucket은 `buckets` 목록에서 제외한다. 별도 restore job/request table은 만들지 않는다.

### 10.2 복원 상태

```http
GET /api/v1/archives/restores?endpointIds=1001&from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z&page=1&size=50
```

`endpointIds`는 FastAPI repeated query로 전달한다. 예를 들어 두 Endpoint는 `endpointIds=1001&endpointIds=1002`다. 기본 정렬은 `(bucketStartAt DESC, endpointId ASC)`다.
`from`은 `to`보다 앞서야 하며 단일 조회 범위는 최대 31일이다.

상태 응답 model은 `PagedData<ArchiveBucketDto>`다.

`ArchiveBucketDto`:

Archive 논리 bucket은 Endpoint별 UTC DAY이며 Endpoint 한 대의 하루치 event를 Parquet object 하나로 저장한다. ClickHouse 물리 partition은 `toDate(occurred_at)` UTC 날짜 단위로 모든 Endpoint가 공유한다. Lifecycle Worker는 export 직전에 Endpoint/UTC DAY별 `uniqExact(event_id)`를 계산해 HOT `event_count`를 갱신하고, Parquet row count가 같은지 확인한 뒤 S3 `event_count`, checksum, `archive_verified_at`을 기록한다. 같은 날짜에 활성 HOT row가 있는 모든 Endpoint의 S3 object가 검증되고 `MAX(archive_verified_at) + 7일`이 지나면 날짜 배타 lock 안에서 모든 HOT row를 먼저 `is_delete=true`로 닫은 뒤 해당 날짜 partition 전체를 삭제한다. ClickHouse 삭제가 실패하면 HOT row는 닫힌 상태로 유지하고 검증된 S3 object를 보존한 채 Lifecycle Worker가 partition 삭제를 재시도한다.

| 필드 | 타입 |
| --- | --- |
| `endpointId` | integer |
| `bucketStartAt`, `bucketEndAt` | timestamp |
| `storageBackend` | `CLICKHOUSE / S3` |
| `storageClass` | `HOT / GLACIER_FLEXIBLE_RETRIEVAL` |
| `storageStatus` | StorageStatus |
| `storagePath` | string |
| `eventCount` | integer |
| `sizeBytes` | nullable integer |
| `checksumSha256` | nullable string |
| `archivedAt`, `archiveVerifiedAt` | nullable timestamp |
| `restoreRequestedAt`, `restoredAt`, `restoreExpiresAt` | nullable timestamp |
| `lastError` | nullable string |

유효 조합은 `CLICKHOUSE/HOT`, `S3/GLACIER_FLEXIBLE_RETRIEVAL`뿐이다. Archive row는 `ARCHIVED -> RESTORE_REQUESTED -> RESTORED -> EXPIRED`로 전이하고 실패하면 `RESTORE_FAILED`다. Storage Lifecycle Worker는 AWS가 보고한 임시 copy 만료 시각을 `restoreExpiresAt`에 기록하고 만료 후 `EXPIRED`로 바꾼다. `EXPIRED`는 원 archive 삭제가 아니라 다시 RestoreObject가 필요한 상태다.

## 11. Alerts API

### 11.1 목록

```http
GET /api/v1/alerts?status=OPEN&severity=HIGH&sortBy=priority&timePreset=LATEST_24H&page=1&size=50
```

목록 응답 model은 `PagedData<AlertDto>`다.

목록 Query:

| Query | 타입 | 기본 | 설명 |
| --- | --- | --- | --- |
| `endpointId` | integer | - | Endpoint exact match |
| `status` | AlertStatus | - | exact match |
| `severity` | Severity | - | exact match |
| `ruleCode` | string | - | exact match |
| `timePreset` | TimePreset | `LATEST_24H` | `detectedAt` 기준 |
| `from`, `to` | timestamp | - | CUSTOM일 때 필수 |
| `page`, `size` | integer | 1, 50 | 공통 pagination |
| `sortBy` | `priority / detectedAt / severity / riskScore / status` | `priority` | server sort field |
| `sortOrder` | `asc / desc` | `desc` | `priority` 이외 field의 방향 |

기본 `priority`는 `OPEN → IN_PROGRESS → RESOLVED`, `CRITICAL → HIGH → MEDIUM → LOW`, `riskScore DESC`, `detectedAt DESC`, `alertId ASC`의 고정 순서다. `priority`에서는 `sortOrder`를 적용하지 않는다. 다른 `sortBy`는 요청 방향을 적용한 뒤 `alertId ASC`를 최종 tie-break로 사용한다. 현재 page만 client-side sort해 전체 dataset 순서처럼 표시하지 않는다.

개별 enum field 정렬의 ordinal은 `severity: LOW < MEDIUM < HIGH < CRITICAL`, `status: RESOLVED < IN_PROGRESS < OPEN`이다. 따라서 `sortOrder=desc`는 더 높은 Severity와 더 긴급한 status를 먼저 반환한다.

`AlertDto`:

| 필드 | 타입 |
| --- | --- |
| `alertId`, `endpointId` | integer |
| `eventId` | string |
| `eventOccurredAt` | timestamp |
| `batchId` | nullable string |
| `agentId`, `ruleCode`, `ruleName` | string |
| `ruleVersion` | integer |
| `mitreTacticCode`, `mitreTacticName` | string |
| `mitreTechniqueCode`, `mitreTechniqueName` | string |
| `title`, `summary` | string |
| `severity` | `LOW / MEDIUM / HIGH / CRITICAL` |
| `riskScore` | 0~100 number |
| `status` | `OPEN / IN_PROGRESS / RESOLVED` |
| `detectedAt`, `createdAt`, `updatedAt` | timestamp |

`ruleName`, `title`, `summary`는 Alert 생성 당시 RuleV1의 required `rule_name`, `alert_title`, `alert_summary` 문자열을 템플릿 처리 없이 그대로 snapshot한다. MITRE 네 필드는 모든 활성 RuleV1에서 required/non-null이며 Backend의 고정 ATT&CK mapping 파일에서 code를 name으로 변환한다.

### 11.2 상세

```http
GET /api/v1/alerts/{alertId}
```

상세 응답 model은 `AlertDetailDto`다. `AlertDto` 전체 필드와 `sourceEvent: EventDto | null`, `incidents: IncidentReferenceDto[]`, `responseGuidance: ResponseGuidanceStepDto[]`를 반환한다.

`ResponseGuidanceStepDto`:

| 필드 | 타입 |
| --- | --- |
| `order` | integer |
| `title`, `description` | string |
| `requiresManualAction` | boolean |

`responseGuidance`는 Alert의 `(ruleCode, ruleVersion)`과 일치하는 versioned RuleV1 YAML에서 읽어 `order` 오름차순으로 반환한다. Guidance가 없으면 `[]`다. 이 배열은 읽기 전용 분석·대응 가이드이며 실행 상태, Agent command ID, 원격 격리, 프로세스 종료, 파일 삭제 기능을 포함하지 않는다.

`IncidentReferenceDto`는 `incidentId: integer`, `title: string`, `severity: Severity`, `status: OPEN | CLOSED`, `windowStartAt: timestamp`, `windowEndAt: timestamp` required field를 가진다. Source event가 HOT/RESTORED에서 조회되지 않으면 `sourceEvent` key는 유지하고 `null`로 반환하며, 연결 Incident가 없으면 `incidents: []`다. 담당자 필드는 없다.

Incident 최초 생성 시 원인이 된 Alert RuleV1의 `alert_title`, `alert_summary`를 각각 Incident `title`, `description`에 그대로 snapshot한다. 같은 Incident key에 후속 Alert가 연결되어도 기존 문자열을 덮어쓰지 않는다. 서로 다른 Rule은 같은 Endpoint에서 동일한 `correlation_key`와 고정 window를 명시한 경우에만 Incident를 공유하며, 이 관계는 시간 기반 묶음이지 프로세스와 통신의 인과관계 증명이 아니다.

### 11.3 상태 변경

```http
PATCH /api/v1/alerts/{alertId}/status
```

```json
{
  "status": "IN_PROGRESS"
}
```

허용 상태는 `OPEN`, `IN_PROGRESS`, `RESOLVED`다. Alert update와 `ALERT_STATUS_CHANGED` audit insert는 같은 PostgreSQL transaction에서 처리하고 갱신된 `AlertDto`를 반환한다.

## 12. Incidents API

Incident는 RuleV1 correlation key/window로 자동 생성하는 read-only projection이다. 활성 Rule condition은 해당 event type에서 정규화되는 payload field만 참조할 수 있고, 공유 correlation key는 모든 참여 Rule에서 동일한 window 크기를 사용해야 readiness를 통과한다. 생성 시 `OPEN`이며 기존 Detection Worker의 60초 periodic task가 `window_end_at`이 지난 OPEN Incident를 `CLOSED`로 바꾸고 `closed_at=window_end_at`을 기록한다. 담당자·사용자 상태 변경 API는 없다.

### 12.1 목록

```http
GET /api/v1/incidents?status=OPEN&timePreset=LATEST_7D&page=1&size=50
```

목록 응답 model은 `PagedData<IncidentDto>`다.

목록 Query:

| Query | 타입 | 기본 | 설명 |
| --- | --- | --- | --- |
| `endpointId` | integer | - | Endpoint exact match |
| `status` | IncidentStatus | - | exact match |
| `severity` | Severity | - | exact match |
| `timePreset` | TimePreset | `LATEST_24H` | `lastDetectedAt` 기준 |
| `from`, `to` | timestamp | - | CUSTOM일 때 필수 |
| `page`, `size` | integer | 1, 50 | 공통 pagination |
| `sortOrder` | `asc / desc` | `desc` | `lastDetectedAt` 정렬 |

기본 정렬은 `(lastDetectedAt DESC, incidentId DESC)`이고 `sortOrder=asc`이면 두 field를 모두 ASC로 바꾼다.

`IncidentDto`:

| 필드 | 타입 |
| --- | --- |
| `incidentId`, `endpointId` | integer |
| `correlationKey` | string |
| `windowStartAt`, `windowEndAt` | timestamp |
| `title` | string |
| `description` | nullable string |
| `severity` | `LOW / MEDIUM / HIGH / CRITICAL` |
| `status` | `OPEN / CLOSED` |
| `firstDetectedAt`, `lastDetectedAt` | timestamp |
| `closedAt` | nullable timestamp |
| `createdAt`, `updatedAt` | timestamp |
| `alertCount` | integer |

`OPEN`은 `closedAt: null`, 자동 종료된 `CLOSED`는 `closedAt=windowEndAt`이다. `alertCount`는 `incident_alerts`에서 계산한다.

### 12.2 상세

```http
GET /api/v1/incidents/{incidentId}
```

상세 응답 model은 `IncidentDetailDto`다. `IncidentDto` 전체 필드와 `alerts: AlertDto[]`를 반환하며 연결 Alert가 없으면 `[]`다.

### 12.3 Attack Timeline

```http
GET /api/v1/incidents/{incidentId}/timeline
```

기존 `incidents`, `incident_alerts`, `alerts`와 Event detail을 결합해 `AttackTimelineDto`를 반환한다. 항목 타입은 `INCIDENT`, `EVENT`, `ALERT`이며 발생 시각 순으로 정렬한다. 별도 timeline table이나 ERD 변경은 없다.

### 12.4 Incident Investigation

```http
GET /api/v1/incidents/{incidentId}/investigation
```

응답 model은 `IncidentInvestigationDto`다. Incident correlation window를 `timeRange`로 사용하고 최대 250 node, 500 edge를 반환한다. `nodeCount`와 `edgeCount`는 실제 반환 배열 길이이며 제한으로 일부를 제외하면 `truncated=true`다. 동일 입력은 `nodeType`, 관측 시각, 원본 ID 순의 결정적 순서를 사용한다.

`InvestigationNodeDto`는 `nodeId`, `nodeType`, `label`과 아래 nullable context key를 모두 required로 반환한다.

| 필드 | 타입 |
| --- | --- |
| `nodeType` | `INCIDENT / ALERT / EVENT / PROCESS / DESTINATION` |
| `endpointId`, `incidentId`, `alertId`, `pid` | nullable integer |
| `eventId`, `processName`, `destination`, `protocol` | nullable string |
| `occurredAt` | nullable timestamp |
| `severity` | nullable Severity |
| `eventType` | nullable EventType |
| `riskScore` | nullable 0~100 number |

`InvestigationEdgeDto`는 `edgeId`, `sourceNodeId`, `targetNodeId`, `relation`, `evidence`와 원본 추적용 nullable `incidentId`, `alertId`, `eventId`, `observedAt`을 required key로 반환한다. `evidence`는 현재 `OBSERVED`만 허용한다.

| relation | 방향 | 허용 근거 |
| --- | --- | --- |
| `CONTAINS` | Incident → Alert | `incident_alerts` FK |
| `TRIGGERED_BY` | Alert → Event, Event → Process | Alert `event_id` 또는 Event의 수집된 process field |
| `PARENT_OF` | parent Process → child Process | 같은 Endpoint Event의 PID/PPID field |
| `CONNECTED_TO` | Process → Destination | Network/DNS/L7 Event의 process·destination field |

시간상 인접하다는 이유만으로 edge를 만들지 않는다. Event가 HOT/RESTORED에서 조회되지 않으면 해당 Event/Process/Destination relation을 만들지 않고 `partial=true`와 `warnings[]`의 `EVENT_NOT_FOUND` 또는 `ARCHIVE_NOT_READY`를 반환한다. `warnings`가 없으면 `[]`다. `fallback`은 기존 Timeline, Incident Alert table과 Event table 사용 가능 여부를 required boolean으로 제공하며 graph flag off, error 또는 truncation에서도 기존 API로 동일 근거를 탐색할 수 있게 한다. Incident가 없으면 `404 NOT_FOUND`다.

## 13. Dashboard와 Intelligence API

### 13.1 전체 요약

```http
GET /api/v1/dashboard/summary?timePreset=LATEST_24H&interval=5m
```

선택 query `endpointId: positive integer`를 전달하면 Endpoint snapshot, Alert, Incident, Event, failure, storage, EDR state를 모두 해당 Endpoint 범위로 제한한다. 생략하면 전체 Endpoint 집계를 반환한다.

응답 model은 `DashboardSummaryDto`다. `TimeRangeDto`는 `from: timestamp`, `to: timestamp` required field를 가진다.

Dashboard metric item model은 다음 required field를 사용한다.

| Model | 필드와 타입 |
| --- | --- |
| `SeverityCountDto` | `severity: Severity`, `count: integer` |
| `AlertStatusCountDto` | `status: AlertStatus`, `count: integer` |
| `EventTypeCountDto` | `eventType: EventType`, `count: integer` |
| `FailureStatusCountDto` | `status: EventFailureStatus`, `count: integer` |
| `StorageBackendCountDto` | `storageBackend: StorageBackend`, `count: integer` |
| `StorageClassCountDto` | `storageClass: StorageClass`, `count: integer` |
| `StorageStatusCountDto` | `storageStatus: StorageStatus`, `count: integer` |
| `OsTypeCountDto` | `osType: WINDOWS/MACOS`, `count: integer` |
| `SensorHealthCountDto` | `sensor: string`, `status: SensorHealth`, `count: integer` |
| `TimeSeriesPointDto` | `bucketStartAt: timestamp`, `count: integer` |
| `IncidentTimeSeriesPointDto` | `bucketStartAt: timestamp`, `openCount: integer`, `closedCount: integer` |
| `TopRuleDto` | `ruleCode: string`, `ruleName: string`, `count: integer` |
| `MitreTacticCountDto` | `mitreTacticCode: string`, `mitreTacticName: string`, `count: integer` |
| `MitreTechniqueCountDto` | `mitreTechniqueCode: string`, `mitreTechniqueName: string`, `count: integer` |
| `TopProcessDto` | `processName: string`, `count: integer` |
| `TopRemoteIpDto` | `remoteIp: string`, `count: integer` |
| `TopDomainDto` | `domain: string`, `count: integer` |
| `TopFileHashDto` | `fileHashSha256: string`, `count: integer` |
| `TopDnsQueryDto` | `dnsQuery: string`, `count: integer` |
| `TopL7ProtocolDto` | `l7Protocol: string`, `count: integer` |
| `FailureStageCountDto` | `failureStage: string`, `count: integer` |
| `FailureCodeCountDto` | `failureCode: nullable string`, `count: integer` |
| `RiskLevelCountDto` | `level: RiskLevel`, `count: integer` |

`EndpointRiskSummaryDto`:

| 필드 | 타입 |
| --- | --- |
| `highestScore` | nullable integer |
| `highRiskEndpointCount` | integer |
| `criticalRiskEndpointCount` | integer |
| `byLevel` | `RiskLevelCountDto[]` |
| `calculatedAt` | timestamp |

`EdrStateAxisDto`:

| 필드 | 타입 |
| --- | --- |
| `status` | EdrStateStatus |
| `score` | 0~100 integer |
| `reasonCodes` | `EdrStateReasonCode[]` |

`EdrStateDto`:

| 필드 | 타입 |
| --- | --- |
| `status` | EdrStateStatus |
| `score` | 0~100 integer |
| `threatLevel` | `EdrStateAxisDto` |
| `collectionHealth` | `EdrStateAxisDto` |
| `highestEndpointRiskScore` | nullable integer |
| `highRiskEndpointCount` | integer |
| `criticalRiskEndpointCount` | integer |
| `reasonCodes` | `EdrStateReasonCode[]` |
| `calculatedAt` | timestamp |

`threatLevel`은 Endpoint Risk, HIGH/CRITICAL Endpoint 수, OPEN Incident, CRITICAL Alert를 입력으로 사용한다. `collectionHealth`는 OFFLINE/STALE Endpoint, DEGRADED/UNAVAILABLE sensor, ingest failure, `latestIngestedAt` 지연, storage failure를 입력으로 사용한다. 두 축과 최종 `status`, `score`, `reasonCodes`는 `RISK_POLICY.md` V1 공식으로 Backend가 계산하며 프론트는 이를 다시 계산하지 않는다. `highRiskEndpointCount`는 `HIGH`, `criticalRiskEndpointCount`는 `CRITICAL`만 각각 세며 서로 중복하지 않는다. Endpoint가 없으면 `highestEndpointRiskScore`는 `null`이고 두 count는 `0`이다. `edrState`는 현재 운영 상태 snapshot이므로 Dashboard의 `timePreset`/`from`/`to`와 무관하다. 원인이 없으면 각 `reasonCodes`는 `[]`다.

| `DashboardSummaryDto` 필드 | 타입/하위 필드 |
| --- | --- |
| `timeRange` | `TimeRangeDto` |
| `interval` | `1m / 5m / 1h / 1d` |
| `edrState` | `EdrStateDto` |
| `alerts` | `totalCount: integer`, `bySeverity: SeverityCountDto[]`, `byStatus: AlertStatusCountDto[]`, `topRules: TopRuleDto[]`, `mitreTactics: MitreTacticCountDto[]`, `mitreTechniques: MitreTechniqueCountDto[]`, `timeSeries: TimeSeriesPointDto[]` |
| `incidents` | `openCount: integer`, `closedCount: integer`, `bySeverity: SeverityCountDto[]`, `timeSeries: IncidentTimeSeriesPointDto[]` |
| `endpoints` | `totalCount: integer`, `onlineCount: integer`, `offlineCount: integer`, `retiredCount: integer`, `staleCount: integer` |
| `events` | `totalCount: integer`, `byEventType: EventTypeCountDto[]`, `topProcesses: TopProcessDto[]`, `topRemoteIps: TopRemoteIpDto[]`, `topDomains: TopDomainDto[]`, `topFileHashes: TopFileHashDto[]`, `topDnsQueries: TopDnsQueryDto[]`, `topL7Protocols: TopL7ProtocolDto[]`, `timeSeries: TimeSeriesPointDto[]` |
| `eventFailures` | `totalCount: integer`, `byStage: FailureStageCountDto[]`, `byCode: FailureCodeCountDto[]`, `byStatus: FailureStatusCountDto[]` |
| `storage` | `totalBucketCount: integer`, `byBackend: StorageBackendCountDto[]`, `byClass: StorageClassCountDto[]`, `byStatus: StorageStatusCountDto[]` |
| `responseGuidance` | `affectedAlertCount`, `ruleCount`, `manualActionStepCount`, `highestSeverity`, `steps: ResponseGuidanceStepDto[]` |

모든 하위 object와 list field는 required다. 집계 결과가 없으면 count는 `0`, list는 `[]`다. `topDomains.domain`은 `COALESCE(remote_domain, http_host)`로 계산하고 DNS query는 `topDnsQueries`에서 별도 집계한다. `top*` list는 count 내림차순, 값 오름차순으로 정렬한 상위 10개까지 반환한다.

`interval`은 `1m`, `5m`, `1h`, `1d`, 최대 point 수는 2,000이다.

### 13.2 Endpoint 상태 요약

```http
GET /api/v1/dashboard/endpoints/summary?timePreset=LATEST_24H
```

선택 query `endpointId: positive integer`를 전달하면 현재 Endpoint snapshot과 지정 시간 범위의 Alert·Incident 집계를 해당 Endpoint로 제한한다. 생략하면 전체 Endpoint 집계를 반환한다.

응답 model `EndpointSummaryDto`:

| 필드 | 타입/하위 필드 |
| --- | --- |
| `timeRange` | `TimeRangeDto` |
| `totalCount`, `onlineCount`, `offlineCount`, `retiredCount`, `staleCount` | integer |
| `byOsType` | `OsTypeCountDto[]` |
| `sensorHealth` | `SensorHealthCountDto[]` |
| `risk` | `EndpointRiskSummaryDto` |
| `alerts` | `totalCount: integer`, `bySeverity: SeverityCountDto[]` |
| `incidents` | `totalCount: integer`, `openCount: integer`, `closedCount: integer`, `bySeverity: SeverityCountDto[]` |

Endpoint 상태·OS·sensor와 `risk`는 요청 시점의 현재 snapshot이다. 공통 `timePreset`/`from`/`to`는 기존 `alerts`, `incidents` 집계에만 적용하고 `risk`에는 적용하지 않는다. `risk.highRiskEndpointCount`는 `HIGH`, `risk.criticalRiskEndpointCount`는 `CRITICAL`만 각각 세며 서로 중복하지 않는다. Endpoint가 없으면 `risk.highestScore`는 `null`, count는 `0`, 빈 분포는 `[]`다.

### 13.3 수집·저장·failure 요약

```http
GET /api/v1/dashboard/ingest/summary?timePreset=LATEST_24H
```

선택 query `endpointId: positive integer`를 전달하면 Event ingest, failure, storage 집계를 해당 Endpoint로 제한한다. 생략하면 전체 Endpoint 집계를 반환한다.

```json
{
  "data": {
    "timeRange": {
      "from": "2026-07-10T00:00:00Z",
      "to": "2026-07-11T00:00:00Z"
    },
    "events": {
      "ingestedCount": 1000000,
      "ratePerMinute": 694.44,
      "latestIngestedAt": "2026-07-11T00:00:01Z"
    },
    "eventFailures": {
      "failedCount": 12,
      "ratePerMinute": 0.01,
      "reprocessedCount": 5,
      "reprocessFailedCount": 1,
      "oldestFailedAt": "2026-07-10T22:00:00Z"
    },
    "storage": {
      "clickhouseHotBucketCount": 240,
      "restoredBucketCount": 20,
      "glacierArchivedBucketCount": 90,
      "restoringBucketCount": 1,
      "failedBucketCount": 0,
      "expiredBucketCount": 3
    }
  },
  "meta": {"requestId": "req_01HZX..."}
}
```

응답 model `IngestSummaryDto`는 예시와 같은 required object를 사용한다. `latestIngestedAt`, `oldestFailedAt`만 `timestamp | null`이고 count와 `ratePerMinute`는 required다. rate는 선택 범위의 분당 평균이며 Event/failure가 없으면 timestamp는 `null`, count와 rate는 `0`이다.

Failure는 ClickHouse에서 `failure_id`별 최신 `updated_at` row를 선택하고 storage는 PostgreSQL `ingest_metadata`에서 집계한다. `restoredBucketCount`는 `storage_backend=S3`, `storage_class=GLACIER_FLEXIBLE_RETRIEVAL`, `storage_status=RESTORED`인 bucket 수다. API 응답에서만 DB snake_case를 camelCase로 변환한다.

### 13.4 Endpoint Egress Topology

```http
GET /api/v1/dashboard/topology?timePreset=LATEST_24H&endpointIds=1001&endpointIds=1002
```

기존 network/DNS/L7 Event와 Alert를 Endpoint→target 관계로 집계해 `EgressTopologyDto`를 반환한다. node는 현재 Endpoint 상태·Risk, edge는 protocol·Event 수·Alert 수·마지막 관측 시각을 포함한다. `bytesOut`은 현재 수집 데이터에 없으므로 추정하지 않는다.

### 13.5 사용자 Dashboard layout

현재 `dashboardKey`는 `overview`만 허용한다. 세 API 모두 Bearer JWT가 필요하고 사용자는 token의 `sub`로만 식별한다. request body나 query로 `userId`를 받지 않는다.

```http
GET /api/v1/dashboard/layouts/overview
```

`layoutVersion`은 1 또는 2다. 저장 row가 없으면 version 2 registry 기본 layout을 `isDefault=true`, `revision=0`으로 반환한다. 저장 row가 있으면 저장된 version 1 또는 2를 그대로 반환하며 Backend가 version을 임의 변경하지 않는다. 삭제된 widget ID와 중복 ID를 제거하고, 신규 widget을 기본 위치에 추가하며, 변경된 min/max와 12열 bounds에 맞게 보정한다. JSON이 손상되었으면 해당 version의 기본 layout으로 복구하되 기존 row revision은 유지한다. 지원하지 않는 version은 `400 VALIDATION_ERROR`다.

```json
{
  "data": {
    "dashboardKey": "overview",
    "layoutVersion": 2,
    "revision": 3,
    "isDefault": false,
    "widgets": [
      {"id": "detection-activity", "x": 0, "y": 4, "w": 8, "h": 5, "hidden": false}
    ]
  },
  "meta": {"requestId": "req_01HZX..."}
}
```

```http
PUT /api/v1/dashboard/layouts/overview
```

```json
{
  "layoutVersion": 2,
  "revision": 3,
  "widgets": [
    {"id": "detection-activity", "x": 0, "y": 4, "w": 8, "h": 5, "hidden": false}
  ]
}
```

PUT은 version 1과 2 전체 layout을 upsert하고 성공할 때 revision을 1 증가시킨다. Frontend의 v1→v2 migration도 같은 revision 계약으로 version 2 전체 layout을 저장한다. 알려지지 않은 widget ID, 중복 ID, widget별 min/max 위반, `x + w > 12`, 겹치는 visible widget, 숨김 불가 widget은 `400 INVALID_DASHBOARD_LAYOUT`이다. 현재 저장 revision과 request revision이 다르면 변경하지 않고 `409 DASHBOARD_LAYOUT_REVISION_CONFLICT`를 반환한다.

위 JSON은 item 모양을 보여주기 위해 한 개만 줄여 적었다. current client는 version 2 registry의 10개 widget 전체를 `widgets`에 전송한다. version 1 호환 registry는 기존 23개 widget을 유지하며, GET 정규화는 저장 row의 version registry를 사용한다. version 2 registry ID는 `edr-state`, `kpi-alerts`, `kpi-open-incidents`, `kpi-high-risk-endpoints`, `kpi-event-failures`, `detection-activity`, `alert-severity`, `endpoint-risk`, `highest-risk-endpoints`, `incident-queue`다. 서버는 해당 version에서 누락한 신규 widget만 registry 기본값으로 병합한다. `y + h`는 최대 256 row를 넘을 수 없다.

```http
DELETE /api/v1/dashboard/layouts/overview
```

DELETE는 본인 row를 물리 삭제하고 기본 layout 응답을 반환한다. row가 없어도 멱등 `200`이다. 저장소는 `user_dashboard_layouts`이며 `(user_id, dashboard_key)` unique, `layout_json JSONB`, `layout_version`, `revision`을 사용한다.

### 13.6 실시간 운영 상태

```http
GET /api/v1/operations/health
```

이 API는 요청 시점에 Backend API, PostgreSQL, ClickHouse, Kafka, S3를 직접 probe하고 `edr-event-storage-v1`, `edr-detection-v1` Consumer Group의 member 수와 committed-offset lag를 조회한다. 결과를 저장하지 않으므로 ERD 변경과 과거 이력은 없다. 일부 probe가 실패해도 HTTP 200으로 성공한 결과와 실패한 결과를 함께 반환하며, 인증 실패만 401이다.

`OperationsHealthDto`:

| 필드 | 타입/하위 필드 |
| --- | --- |
| `checkedAt` | timestamp |
| `status` | `HEALTHY / DEGRADED / UNAVAILABLE` |
| `services` | `service`, `status`, `latencyMs`, `detail` |
| `workers` | `worker`, `groupId`, `topic`, `status`, `memberCount`, `lag`, `detail` |

Worker `status`는 `RUNNING / IDLE / OFFLINE / UNKNOWN`이다. Group member 조회가 실패하면 `memberCount`, `lag`는 각각 확인 가능한 범위만 반환하며 확인할 수 없는 값은 `null`이다. UI는 이 API와 `dashboard/ingest/summary`의 `latestIngestedAt`을 함께 표시하되 과거 availability 그래프를 만들지 않는다.

### 13.7 DTO와 ERD Mapping 예외

기본 규칙은 camelCase field를 같은 단어의 snake_case 컬럼에 대응하는 것이다. 예외는 다음으로 고정한다.

| API field | ERD/source |
| --- | --- |
| `capabilityCodes` | `endpoints.capability_codes_json` 역직렬화 |
| `sensorHealth` | `endpoints.sensor_health_json` 역직렬화 |
| `dnsAnswers` | `edr_events.dns_answers_json`, DB null은 `[]` |
| `certificates` | `agent_auth_keys` join |
| `sourceEvent` | `edr_events` HOT/RESTORED 조회 |
| `responseGuidance` | `(rule_code, rule_version)`에 해당하는 versioned RuleV1 YAML |
| `incidents`, `alerts` | `incident_alerts` join |
| `alertCount` | `incident_alerts` count |
| `risk`, Endpoint Risk count/distribution | PostgreSQL active Alert/OPEN Incident aggregate 파생값 |
| `edrState` | Endpoint Risk와 PostgreSQL/ClickHouse 수집·저장 상태 집계 파생값 |
| `DashboardLayoutDto.widgets` | `user_dashboard_layouts.layout_json`, row가 없거나 손상되면 registry 기본 layout |
| Dashboard count/top/timeSeries | PostgreSQL/ClickHouse/PyArrow 집계 파생값 |
| `restoredBucketCount` | `ingest_metadata`의 `S3/GLACIER_FLEXIBLE_RETRIEVAL/RESTORED` count |

### 13.8 IP와 Domain Intelligence

네 API는 모두 Bearer JWT가 필요하며 read-only다. DNS 명령이나 shell을 실행하지 않고 Backend resolver를 통해 조회한다.

```http
GET /api/v1/intelligence/forward-dns?domain=example.com
GET /api/v1/intelligence/reverse-dns?ip=8.8.8.8
GET /api/v1/intelligence/dns-lookup?query=example.com&recordType=MX
GET /api/v1/intelligence/correlate?value=yahoo.com&timePreset=LATEST_24H&endpointIds=1001
```

`correlate`는 현재 Backend DNS 결과와 선택 기간의 ClickHouse Event 근거를 합친다. DNS 조회가 실패해도 관찰 Event 결과는 반환한다. `endpointIds`는 반복 query이며 Event 근거에만 적용한다. PTR 이름은 후보일 뿐 입력 IP를 대체하지 않는다.

`CorrelationDto`는 `inputValue`, `inputType`, `from`, `to`, `related[]`, `relationships[]`를 required field로 반환한다. `related[]`는 값, `IP / DOMAIN` 유형과 `LIVE_DNS / OBSERVED_EVENTS` source를 제공한다. `relationships[]`는 `sourceValue`, `sourceType`, `targetValue`, `targetType`, `relation`, `sources`를 제공한다.

| relation | 방향 | 의미 |
| --- | --- | --- |
| `RESOLVES_TO` | Domain → IP | Live forward DNS 또는 Event에서 함께 관찰된 Domain/IP 근거 |
| `PTR_CANDIDATE` | IP → Domain | 현재 PTR 응답이며 확정 소유 관계나 IP 대체값이 아님 |
| `SUBDOMAIN_OF` | subdomain → 요청 Domain | exact domain-boundary로 확인한 관찰 Event 값 |

`OBSERVED_EVENTS`가 붙은 `RESOLVES_TO`는 선택 기간에 함께 관찰된 관계이며 현재 authoritative DNS 상태를 보장하지 않는다. 부모/자식 판정은 요청 Domain의 exact 또는 `.<domain>` suffix까지만 지원하고 Public Suffix List 기반 조직 경계 추론은 하지 않는다. 별도 관계 table이나 graph DB에 파생 edge를 저장하지 않는다.

## 14. Enum 정의

### 14.1 Endpoint Status

```text
ONLINE
OFFLINE
RETIRED
```

### 14.2 지원 OS

```text
WINDOWS
MACOS
```

### 14.3 Event Type

```text
PROCESS_EXECUTION
NETWORK_CONNECTION
FILE_EVENT
DNS_QUERY
L7_EVENT
```

### 14.4 Severity

```text
LOW
MEDIUM
HIGH
CRITICAL
```

### 14.5 Alert Status

```text
OPEN
IN_PROGRESS
RESOLVED
```

### 14.6 Incident Status

```text
OPEN
CLOSED
```

### 14.7 Event Failure Status

```text
FAILED
REPROCESSED
REPROCESS_FAILED
```

### 14.8 Storage Status

```text
HOT
ARCHIVED
RESTORE_REQUESTED
RESTORED
RESTORE_FAILED
EXPIRED
```

### 14.9 Storage Backend

```text
CLICKHOUSE
S3
```

### 14.10 Storage Class

```text
HOT
GLACIER_FLEXIBLE_RETRIEVAL
```

Failure payload의 S3 `STANDARD`, `GLACIER_IR` lifecycle literal은 `ingest_metadata.storageClass`가 아니다.

### 14.11 Dashboard User Status

```text
ACTIVE
DISABLED
```

### 14.12 Sensor Health

```text
HEALTHY
DEGRADED
UNAVAILABLE
```

### 14.13 Agent Architecture

```text
X64
ARM64
```

### 14.14 Risk Level

```text
LOW
MEDIUM
HIGH
CRITICAL
```

`RiskLevel`은 Alert `Severity`와 literal이 같아도 Endpoint의 계산된 위험도 등급이므로 별도 enum이다.

### 14.15 Endpoint Risk Factor Source Type

```text
ALERT
INCIDENT
```

### 14.16 EDR State Status

```text
GREEN
YELLOW
RED
```

### 14.17 EDR State Reason Code

```text
MEDIUM_ENDPOINT_RISK
HIGH_ENDPOINT_RISK
CRITICAL_ENDPOINT_RISK
OPEN_INCIDENT
CRITICAL_ALERT
OFFLINE_ENDPOINT
STALE_ENDPOINT
DEGRADED_SENSOR
UNAVAILABLE_SENSOR
INGEST_FAILURE
INGEST_DELAYED
STORAGE_FAILURE
```

### 14.18 Time Preset

```text
LATEST_15M
LATEST_1H
LATEST_24H
LATEST_7D
CUSTOM
```

## 15. 관리자 Failure 재처리 계약

공개 REST API를 만들지 않는다.

Failure 저장 identity와 object 계약:

- `failureId`는 `uuid.NAMESPACE_URL`과 `urn:edr:failure:v1:` + `json.dumps([sourceTopic, sourcePartition, sourceOffset, consumerName, failureStage], ensure_ascii=False, separators=(",", ":"))` name으로 계산한 UUIDv5다.
- S3 key는 `failures/{failureId}/payload.json.gz`다.
- Failure envelope를 `sort_keys=True`, `ensure_ascii=False`, compact separator로 직렬화하고 gzip level 9, `mtime=0`으로 압축한 exact object bytes의 SHA-256을 checksum으로 사용한다.
- 동일 key/checksum은 멱등 성공이고 동일 key의 checksum이 다르면 overwrite와 source offset commit을 중단한다.
- S3 PUT과 ClickHouse `event_failures` 기록이 모두 성공한 뒤 source offset을 commit한다.
- Failure payload는 최초 실패부터 90일, ClickHouse failure index는 97일 보존한다.

```text
python -m tools.replay_failure --failure-id <UUID>
```

CLI는 S3 원문의 보존 만료, 크기, checksum을 검증한 뒤 `replay_failure_id` header와 함께 `telemetry.raw`에 publish한다. broker ACK까지 성공하면 `REPROCESSED`, 실패하면 `REPROCESS_FAILED`를 기록한다. 이후 Event Storage Worker는 동일 `eventId`의 raw event를 논리 중복으로 만들지 않으면서 `telemetry.validated`까지 다시 전달하고, Alert unique key가 중복 Alert 생성을 막는다.

자동 scheduler, `telemetry.replay` topic, replay pointer, `REPLAY_REQUESTED`/`REPLAY_PUBLISHED`, occurrence ID와 다단계 versioning은 사용하지 않는다.

## 16. 확정된 설계 결정

| 항목 | 결정 |
| --- | --- |
| Agent | Windows C++20, macOS Swift |
| Backend | Python/FastAPI/Uvicorn, REST 우선 |
| Event | Process/Network/File/DNS/L7 5종 metadata |
| Packet | Npcap/tcpdump live 분석 후 원 packet 폐기 |
| PCAP file | 생성·rolling·S3 upload·download 모두 사용하지 않음 |
| Agent command | 사용하지 않음 |
| Response Playbook | versioned RuleV1의 읽기 전용 `responseGuidance`, 원격 실행 기능 없음 |
| Endpoint Risk | Dashboard API가 `RISK_POLICY.md` V1로 계산, 프론트 집계 없음 |
| 전역 EDR 상태 | Dashboard API가 `RISK_POLICY.md` V1의 Threat Level과 Collection Health를 결합 |
| Report | Report Center/Modal, HTML/Markdown path, 저장·공유 API 사용하지 않음 |
| DB | PostgreSQL 운영 데이터, ClickHouse event/failure |
| Failure | 결정적 UUIDv5/S3 key, payload 90일, index 97일, 관리자 CLI 수동 재처리 |
| 웹 Failure 관리 | 읽기 전용 DLQ Monitor 제공, 웹 replay API는 사용하지 않음 |
| Archive | RestoreObject 7일 Standard tier, 동일 Glacier key/class, PyArrow 직접 조회 |
| Endpoint 상태 | Heartbeat ONLINE, 30초 Worker sweep, 2분 미수신 OFFLINE, RETIRED 우선 |
| Incident 상태 | 생성 OPEN, 60초 Detection Worker sweep, window 만료 CLOSED |
| Dashboard 사용자 | ACTIVE/DISABLED, 최초 ADMIN은 `tools.create_admin` CLI |
| Agent 인증서 | `tools.provision_agent_cert` CLI와 URI SAN, 발급 REST 없음 |
| MITRE | 모든 활성 RuleV1 code 필수, 고정 mapping 파일에서 name 변환 |
| Audit | append-only `audit_logs`, 조회 API 없음 |
| 담당자 | 완전 제거 |
| Rollup | 추후 확장 |
| gRPC | 추후 확장 |

## 17. 개발·검증 전제

### 17.1 Windows

- 실제 Windows Endpoint 1대
- 사용자가 Npcap 공식 배포본을 별도 설치
- Npcap installer/driver/SDK/DLL을 repository나 Agent package에 포함하지 않음
- Npcap packet callback을 실시간 parsing하며 PCAP writer를 사용하지 않음
- packet provider가 준비되지 않으면 L7 sensor만 `DEGRADED`

### 17.2 macOS

- 실제 macOS Endpoint 1대
- 무료 Apple Account와 Xcode 사용
- tcpdump stdout stream을 parsing하고 disk spool을 만들지 않음
- Swift 기능 단위로 실제 Mac에서 build/test

### 17.3 포트폴리오 검증

- 실제 Windows/macOS에서 5종 telemetry end-to-end 검증
- Kafka consumer 중단 후 lag 회복 확인
- ClickHouse insert와 Detection 처리 확인
- packet이 로컬 파일이나 S3에 남지 않는지 확인
- failure 1건을 관리자 CLI로 수동 재처리
- Endpoint Risk가 active Alert/OPEN Incident 입력과 등급 구간을 일관되게 반영하는지 확인
- 전역 EDR 상태가 Threat Level과 Collection Health reason code를 Backend 계산 결과로 반환하는지 확인
- Alert 상세의 versioned `responseGuidance`가 읽기 전용으로 표시되고 Agent command를 만들지 않는지 확인
- Rollup과 PCAP artifact 시나리오는 검증 범위에 없음
