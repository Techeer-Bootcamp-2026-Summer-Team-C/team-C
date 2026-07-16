# Frontend UI 개편 실행 계획

- 문서 상태: Complete
- 작성일: 2026-07-15
- 완료일: 2026-07-16
- 적용 대상: `frontend/`, `backend/`, 관련 계약·migration·test
- 수명: 이번 Frontend·Backend UI 개편 완료 시까지
- 목적: 작업 순서, 진행 상태, blocker, 변경 범위와 검증 증거 관리
- 장기 디자인 기준: [DESIGN.md](./DESIGN.md)
- 현재 디자인 baseline: `DESIGN.md Approved v3.0`
- Master Work Order: [FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md](./FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md)

## 1. 문서 책임

| 문서 | 책임 | 변경 시점 |
| --- | --- | --- |
| `DESIGN.md` | 장기 시각·레이아웃·상호작용 기준과 확정된 디자인 결정 | 디자인 원칙이나 제품 UI 기준이 바뀔 때 |
| `FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md` | 승인된 전체 Frontend·Backend 범위, 실행 순서와 release gate | 전체 범위 또는 계약 경계가 바뀔 때 |
| 이 문서 | 이번 개편의 순서, 범위, 상태, blocker, 구현 파일, 완료 증거 | Work Package 시작·완료 또는 blocker 변경 시 |
| `FRONTEND_UI_REDESIGN_WORKSHOP.md` | 팀 토의 원본, 선택지, 회의 결과 | 회의 전후 |
| `FRONTEND_SPEC.md` | Route, query, polling, auth, 권한과 화면 동작 계약 | 제품 동작 계약이 바뀔 때 |
| `API_SPEC.md`, `RISK_POLICY.md` | API와 데이터 의미 | Backend 계약이 바뀔 때 |

실행 계획은 `DESIGN.md`의 `확정` 항목을 변경할 수 없다. 계획 수행 중 새 디자인 결정이 필요하면 먼저 Workshop에서 합의하고 `DESIGN.md` 결정 기록을 갱신한 뒤 blocker를 해제한다.

## 2. 상태와 갱신 규칙

| 상태 | 의미 |
| --- | --- |
| `대기` | 시작할 수 있으나 아직 착수하지 않음 |
| `진행 중` | 담당자가 현재 구현·검증 중 |
| `차단` | 선행 작업 또는 팀 결정 없이는 본 구현 금지 |
| `완료` | 범위와 검증 조건을 충족하고 증거가 기록됨 |
| `제외` | 이번 개편에서 제거됨. 근거 필수 |

작업자는 다음 규칙을 따른다.

1. 한 번의 작업지시는 Work Package 하나만 대상으로 한다.
2. 시작 전에 해당 Work Package를 `진행 중`으로 변경하고 담당·시작일을 적는다.
3. 범위를 넓혀야 하면 임의로 진행하지 않고 blocker 또는 후속 Work Package로 기록한다.
4. 완료 전 `DESIGN.md` 14.7 Hard Pre-flight와 이 문서의 검증 명령을 실행한다.
5. 결과에는 변경 파일, 실행 명령, 성공·실패 결과와 남은 위험을 기록한다.
6. commit, push, PR은 사용자가 별도로 요청한 경우에만 수행한다.

## 3. 현재 확정사항

| ID | 확정 내용 | 구현 영향 |
| --- | --- | --- |
| P-DEC-001 | `DESIGN.md`를 지속적인 Frontend 디자인 source of truth로 사용 | 모든 UI 작업이 `확정` 항목을 우선 확인 |
| P-DEC-002 | 목적이 명확한 gradient 사용 허용 | chart fill, selected context, 주요 조사 시작점에 제한 적용 |
| P-DEC-003 | Sidebar를 Overview, Triage, Evidence, Analysis, Platform group으로 확정 | `AppShell` Navigation과 mobile drawer에 적용 |
| P-DEC-004 | 팀 이미지 4장은 pattern 참고로만 사용 | 브랜드·데이터·화면을 그대로 복제하지 않음 |
| P-DEC-005 | 단발성 구현 계획은 `DESIGN.md`와 분리 | 진행률과 완료 증거는 이 문서에서만 관리 |
| P-DEC-006 | 외부 reference의 채택·비채택 pattern을 `DESIGN.md` 2.2에서 추적 | 구현 전 적용 절과 복제 금지 범위를 확인 |
| P-DEC-007 | KPI, Tooltip·Popover, DataTable, compact toolbar의 공통 계약을 `DESIGN.md`에 고정 | Work Package에서 임의 interaction을 만들지 않음 |
| P-DEC-008 | Workshop 권장안 전체 확정 | `제안`과 `결정 필요` 상태를 Approved v3.0 기준으로 구현 |
| P-DEC-009 | Login 포함, dark-only, compact density | Foundation과 responsive 완료 조건에 적용 |
| P-DEC-010 | Overview 10 block, 8 widget 제거와 layout v2 1회 migration | WP-04와 BWP-04에서 구현 |
| P-DEC-011 | ECharts, React Flow + Dagre를 PoC·fallback·feature flag 조건으로 채택 | WP-06과 WP-08에서 단계 적용 |
| P-DEC-012 | UI 필수 Backend contract를 이번 개편에 포함 | BWP-01~04 선행 후 관련 Frontend 연결 |
| P-DEC-013 | 첫 배포는 Foundation+공통 pattern+AppShell+Overview | WP-09 release gate에서 검증 |

## 4. 해제된 결정 Blocker

| ID | 확정 결과 | 상태 |
| --- | --- | --- |
| B-001 | Login 포함 | 해제 |
| B-002 | dark-only 배포, future light-ready semantic token | 해제 |
| B-003 | Approved v3.0의 Sidebar group과 순서 | 해제 |
| B-004 | 10 block, 8 widget 제거, layout v2 자동 migration+1회 안내 | 해제 |
| B-005 | compact 기본, density 전환은 후속 | 해제 |
| B-006 | ECharts와 React Flow + Dagre PoC 후 feature flag 적용 | 해제 |
| B-007 | Foundation+공통 pattern+AppShell+Overview 첫 배포 | 해제 |

## 5. Baseline 문제 목록

| ID | 현상 | 현재 근거 | 처리 Work Package |
| --- | --- | --- | --- |
| PR-001 | Overview 편집 중 완료하지 않고 새로고침하면 버벅임 | layout 저장은 650ms debounce이며 grid key에 `layoutLoadedAt`이 포함됨. 정확한 원인은 재현 후 확정 | WP-01 |
| PR-002 | Time range 영역과 dashboard card의 가로 폭이 맞지 않음 | `.dashboard-grid`에 `margin: -12px`가 있어 공통 page inset과 차이가 발생 | WP-01 |
| PR-003 | 목록 table의 계층과 조작 방식이 화면마다 일관되지 않음 | 현재 공통 CSS와 페이지별 column 구성이 분산됨 | WP-03 |
| PR-004 | Overview에 상세 분포 widget이 과도하게 집중됨 | 기본 layout에 OS, Sensor, Rule, MITRE, signal, failure, storage widget이 포함됨 | WP-04 |
| PR-005 | Endpoint 선택과 상세 조사 화면의 시각 정보가 부족함 | 목록은 comma-separated Endpoint ID filter 중심이며 상세 전환용 switcher가 없음 | WP-07 |
| PR-006 | Response guidance summary가 실제 조사 지원에 부족함 | 기존 DTO를 표시할 수 있지만 compact UI가 설명과 후속 단계를 제한 | WP-05 |

PR-001의 원인은 아직 진단 가설이다. debounce, in-flight save, revision conflict, grid remount 중 실제 원인을 재현 증거 없이 단정하지 않는다.

## 6. 범위와 비범위

### 이번 개편 범위

- dark EDR console의 semantic token과 공통 surface 정리
- 제한적인 functional gradient
- Overview 편집 안정성과 공통 layout gutter
- table, tooltip, popover, filter, pagination pattern
- Overview, Alerts, Incidents, Endpoints, Events, Intelligence, Operations, Archives의 정보 계층
- Loading, Empty, Error, Stale, Partial failure와 responsive/accessibility 검증
- Endpoint paged search와 승인된 server sorting
- Incident investigation read model
- Overview layout v2 migration 호환성
- API 문서, Pydantic, OpenAPI와 generated TypeScript schema 동기화

### 비범위

- Tailwind 또는 shadcn/ui 전체 migration
- API에 없는 공격 인과관계, network flow, 처리량 생성
- Response guidance를 원격 명령 실행 UI로 변경
- light theme 본 구현
- Service·Worker 장기 이력, 저장된 view와 전역 검색 확장
- `bytesOut`, PCAP, agent telemetry protocol과 multi-tenant 변경

## 7. Work Package

| ID | 우선순위 | 상태 | 범위 | 선행 조건 |
| --- | --- | --- | --- | --- |
| MWO-00 | P0 | `완료` | Baseline, 회귀 기준과 계약 audit | 없음 |
| BWP-01 | P0 | `완료` | API contract, Pydantic, OpenAPI, generated schema | MWO-00 |
| BWP-02 | P0 | `완료` | Endpoint search와 server sorting | BWP-01 |
| BWP-03 | P1 | `완료` | Incident investigation read model | BWP-01 |
| BWP-04 | P0 | `완료` | Dashboard layout v2 호환성 | BWP-01 |
| WP-01 | P0 | `완료` | Overview 편집 안정성과 가로 폭 정렬 | 없음 |
| WP-02 | P0 | `완료` | Foundation, Login과 AppShell | WP-01 권장 |
| WP-03 | P1 | `완료` | 공통 Data Interaction | WP-02, BWP-02 |
| WP-04 | P0 | `완료` | Overview 10 block, toolbar와 migration | WP-01, WP-02, BWP-04 |
| WP-05 | P1 | `완료` | Alerts와 Response Guidance | WP-03, BWP-02 |
| WP-06 | P1 | `완료` | Incidents와 Investigation | WP-03, BWP-03 |
| WP-07 | P1 | `완료` | Endpoints와 Events | WP-03, BWP-02 |
| WP-08 | P1 | `완료` | Intelligence, Operations와 Archives | WP-03, BWP-03 |
| WP-09 | P0 | `완료` | 통합 QA와 release gate | 전체 대상 Package 완료 |

### MWO-00과 BWP-01~04

Backend 선행 package의 상세 범위와 완료 조건은 Master Work Order 5절을 따른다.

- `MWO-00`: current behavior, API, visual, performance와 test baseline
- `BWP-01`: contract-first API 문서, Pydantic, manifest, OpenAPI와 generated schema
- `BWP-02`: paged Endpoint search, Alerts priority sort와 필요한 server sorting
- `BWP-03`: observed evidence만 사용하는 Incident investigation read model
- `BWP-04`: Overview layout version 1 load, version 2 save, conflict와 reset 호환성

#### MWO-00 완료 증거

```text
Package: MWO-00 Baseline과 회귀 기준
상태: 완료
담당: Codex
완료일: 2026-07-15
변경 파일:
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약 변경: 없음. 현재 계약과 결함을 후속 Package의 회귀 기준으로 고정했다.
Migration: 없음.
```

보존할 현재 계약:

- Route: 공개 `/login`과 인증이 필요한 Overview, Alerts, Incidents, Endpoints, Events, Intelligence, Operations, Archives의 기존 12개 App route를 유지한다. Event Detail의 `endpointId`, `occurredAt` deep-link query를 유지한다.
- Auth/session: JWT, `UserDto`, `expiresAt`만 탭 `sessionStorage`에 보존하고, 복원 후 `GET /users/me`로 재검증한다. `401`만 session을 제거하며 `403`은 logout하지 않는다.
- Permission: 조회는 `ADMIN/ANALYST/VIEWER`, Alert 상태 변경과 Archive restore는 `ADMIN/ANALYST`, 사용자 Overview layout 조회·저장·reset은 세 role 모두 허용한다.
- Query/URL: 기본 `page=1`, `size=50`, `sortOrder=desc`, filter 변경 시 page reset, filter/sort/page/time range URL 직렬화, CUSTOM UTC range 검증을 유지한다.
- Polling: Overview 30초, Operations ingest 15초, health/failure 30초, Archive 10/30초이며 hidden document에서는 중단한다. 목록·상세에는 자동 polling을 추가하지 않는다. `503`만 5/15/30초로 최대 3회 재시도한다.
- Data meaning: Endpoint Risk, EDR State, chart bucket과 count는 Backend 값을 사용하고 Frontend에서 재계산하지 않는다. Dashboard summary, Process Tree, Attack Timeline, Egress Topology와 Response Guidance DTO를 재사용한다.
- Envelope/nullability: camelCase success/error envelope와 `meta.requestId`, 명시적 `null`, 빈 collection `[]` 규칙을 유지한다.

후속 변경 범위가 필요한 계약 gap:

- `EndpointListQuery`에는 `q`가 없고 `riskScore|lastSeenAt|registeredAt` sort만 있다.
- `AlertListQuery`에는 `sortBy`가 없고 `sortOrder`만 있다.
- `/incidents/{incidentId}/investigation` route, manifest entry와 graph DTO가 없다. 현재 `investigations.py`는 Failure, Timeline, Topology DTO만 제공한다.
- Backend layout contract는 `layoutVersion >= 1`을 허용하지만 Frontend `OVERVIEW_LAYOUT_VERSION`은 1이며 v1→v2 migration과 1회 안내가 없다.
- OpenAPI artifact와 generated TypeScript schema는 현재 구현과 일치한다. BWP-01에서 위 네 gap을 contract-first로 추가한다.

재현된 기존 결함과 설계 판단:

- Layout save: 1.5초 지연한 `PUT /dashboard/layouts/overview`에서 widget을 숨긴 직후 `Done`을 누르면 100ms 시점에 `Edit dashboard`가 다시 표시되어 edit mode는 종료됐지만 상태는 `Saving dashboard layout.`이었다. 약 2초 후 `Dashboard layout saved.`로 전환됐다. 코드도 `finishEditing()`이 `void saveNow()` 직후 `setIsEditing(false)`를 호출하므로 pending/in-flight 완료를 기다리지 않는다. 재현 후 layout은 default로 reset했다. WP-01에서 완료 대기와 실패·conflict 복구를 구현한다.
- Horizontal alignment: 1440px에서 `.filter-bar`와 `.dashboard-grid-shell`은 `left=74/right=1420`으로 일치하지만 `.dashboard-grid`는 `margin:-12px` 때문에 `left=62/right=1432`로 frame 밖에 12px씩 확장된다. WP-01에서 공통 frame과 12px gutter로 수정한다.
- Responsive: 1440/1024/768px에서 document width와 viewport가 일치했다. 360px에서는 EN/KO와 모든 주요 route가 `documentWidth=768`로 고정되어 horizontal overflow가 재현됐다. WP-02에서 root `min-width:768px` 제거 전후를 비교한다.
- Bundle: production JS 507.06 kB, gzip 151.07 kB로 Vite 500 kB chunk warning이 있다. CSS는 47.22 kB, gzip 8.45 kB다. 신규 chart/graph dependency gate에서 이 값을 기준으로 증분을 기록한다.

실행한 검증:

- `uv run ruff check backend tests tools`: PASS.
- 최초 `uv run pytest`: 환경 기준선 FAIL 1건. Windows PATH에 `openssl`이 없어 certificate provisioning test만 실패했고 189 passed, 4 skipped였다.
- `$env:Path = 'C:\Program Files\Git\usr\bin;' + $env:Path; $env:UV_CACHE_DIR = '.uv-cache'; uv run pytest --basetemp '.tmp\mwo00-pytest' -p no:cacheprovider`: PASS, 190 passed, 4 skipped, 2 warnings, 31.46s.
- `docker compose config --quiet`: PASS. 샌드박스의 `.env`/Docker config 접근 거부는 실제 Docker 권한으로 재실행해 환경 오류와 분리했다.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run test`: PASS, 13 files, 51 tests, 10.66s. 샌드박스의 Vite config 상위 경로 접근 거부는 실제 권한 재실행으로 분리했다.
- `npm.cmd run build`: PASS, 10.79s. JS 507.06 kB/151.07 kB gzip, CSS 47.22 kB/8.45 kB gzip.
- `npm.cmd run openapi:check`: PASS. `openapi/openapi.json`과 `frontend/src/api/generated/schema.ts` drift 없음.
- `docker compose up -d --build --wait`: PASS. Backend, Frontend, workers, PostgreSQL, ClickHouse, Kafka, MinIO와 Nginx healthy.
- `uv run --env-file .env python .\tests\seed_frontend_qa.py`: PASS. ADMIN/VIEWER, normal/long/partial/archive-not-ready fixture 생성.

핵심 API latency baseline:

| API | min | median | p95/max (10회) |
| --- | ---: | ---: | ---: |
| Dashboard summary | 76.5ms | 92.2ms | 118.0ms |
| Endpoint summary | 31.5ms | 33.1ms | 46.3ms |
| Ingest summary | 40.6ms | 43.7ms | 60.0ms |
| Endpoints | 33.1ms | 39.5ms | 49.4ms |
| Alerts | 33.7ms | 37.1ms | 41.5ms |
| Incidents | 33.6ms | 36.6ms | 40.4ms |
| Egress topology | 45.9ms | 55.1ms | 62.9ms |
| Operations health | 161.5ms | 255.5ms | 292.4ms |
| Overview layout | 38.1ms | 49.5ms | 107.6ms |

Browser QA 증거:

- 경로: `output/playwright/mwo-00/` (gitignored local evidence).
- 총 54 PNG, 3,341,233 bytes: Login EN 1440 1장, Overview EN/KO 1440·1024·768·360 8장, Alerts/Alert Detail/Incidents/Incident Detail/Endpoints/Endpoint Detail/Events/Event Detail/Intelligence/Operations/Archives EN·KO 1440·360 44장, pending-save 재현 1장.
- seeded Event Detail은 목록이 생성한 `endpointId`와 `occurredAt` deep link로 캡처했다.
- 대표 이미지와 accessibility snapshot을 시각 검수했고 blank/error capture가 아님을 확인했다. browser console warning/error는 0건이었다.

성능·접근성 결과:

- 1440/1024/768px EN/KO 주요 화면은 viewport 폭을 넘지 않았다.
- 360px은 고정 768px document width 때문에 실패로 기록했다. 이 기존 실패를 신규 회귀와 구분한다.
- accessibility tree에서 skip link, navigation label, heading, form label, table/region name과 EN/KO 전환을 확인했다.
- keyboard로 Overview edit 진입, widget hide, Done과 reset을 수행했다.

남은 위험:

- Operations health median 255.5ms가 다른 read API보다 높다. MWO 범위에서는 회귀 기준으로만 유지하고 Operations 변경 시 비교한다.
- JS chunk가 500 kB 경고선보다 7.06 kB 크다. 시각화 dependency PoC에서 code splitting과 증분 budget을 검증한다.
- 360px overflow, layout grid frame 이탈과 pending-save 종료는 각각 WP-02, WP-01의 확인된 기존 결함이다.

다음 Package: BWP-01 Contract와 OpenAPI.
```

#### BWP-01 완료 증거

```text
Package: BWP-01 Contract와 OpenAPI
상태: 완료
담당: Codex
완료일: 2026-07-15
변경 파일:
- docs/contracts/API_SPEC.md
- docs/frontend/FRONTEND_SPEC.md
- backend/contracts/enums.py
- backend/contracts/requests.py
- backend/contracts/investigations.py
- backend/contracts/dashboard_layouts.py
- backend/contracts/api_manifest.py
- backend/main.py
- openapi/openapi.json
- frontend/src/api/generated/schema.ts
- frontend/src/contracts.ts
- frontend/src/api/endpoints.ts
- tests/test_api_manifest.py
- tests/test_enums.py
- tests/test_health.py
- tests/test_openapi.py
- tests/test_ui_redesign_contracts.py
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약 변경:
- Endpoint `q`: trim 후 1~128자. 숫자는 Endpoint ID exact, 문자열은 hostname/agent ID case-insensitive exact 또는 prefix다. wildcard는 literal로 처리하고 검색 ranking은 exact, active status, risk, hostname, Endpoint ID 순이다.
- Alert `sortBy`: priority/detectedAt/severity/riskScore/status enum, 기본 priority. priority는 status, Severity, Risk, 최신 시각, Alert ID의 고정 순서다.
- Incident Investigation: `/incidents/{incidentId}/investigation`, 5 node type, 4 relation, `OBSERVED` evidence, partial warning, fallback, node/edge count와 truncated 계약을 추가했다.
- Dashboard layout: `layoutVersion`을 1 또는 2로 제한하고 v1 read → Frontend v2 save → reload와 revision conflict 재적용 계약을 문서화했다.
- 제품 API manifest는 Dashboard 26 + Collector 3 = 29개다.
- generated schema 외 임시 Frontend interface를 만들지 않았고 API client도 `IncidentInvestigationDto`를 직접 사용한다.

Migration: 없음. BWP-01은 schema/contract Package이며 DB row 일괄 갱신을 만들지 않았다.

원인 또는 설계 판단:
- 검색 길이는 운영 console autocomplete에 충분하면서 무제한 prefix query를 막는 128자로 고정했다.
- graph는 시간 인접성으로 관계를 만들지 않고 `incident_alerts`, Alert `event_id`, Event PID/PPID·destination field로 추적 가능한 edge만 허용했다.
- HOT/RESTORED evidence가 없거나 Archive가 준비되지 않은 경우 성공 graph에 가짜 relation을 넣지 않고 `partial=true`와 typed warning을 반환하도록 계약했다.
- graph cap은 250 node/500 edge이며 Timeline과 Alert/Event table fallback availability를 항상 반환한다.
- Backend가 v1을 임의로 v2로 바꾸지 않고 Frontend migration PUT 성공 후에만 안내 완료로 간주한다.

실행한 검증:
- `uv run ruff check backend tests tools`: PASS.
- contract targeted pytest: PASS, 18 passed, 1 warning, 9.14s.
- 전체 pytest: 첫 실행은 기존 exact API count assertion 28 때문에 1 fail/194 pass. assertion을 새 manifest 29와 동기화한 뒤 PASS, 195 passed, 4 skipped, 2 warnings, 16.89s.
- `docker compose config --quiet`: PASS.
- `npm.cmd run openapi:export`: PASS.
- `npm.cmd run openapi:generate`: PASS.
- `npm.cmd run openapi:check`: PASS, artifact와 generated schema drift 없음.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run test`: PASS, 13 files, 51 tests, 10.67s.
- `npm.cmd run build`: PASS, 12.84s. JS 507.14 kB/151.09 kB gzip, CSS 47.22 kB/8.45 kB gzip.
- `git diff --check`: PASS. Windows CRLF normalization warning만 있으며 whitespace error 없음.

브라우저 QA 증거:
- 해당 없음. UI 렌더링 변경이 없는 contract-only Package다. MWO-00의 54개 capture를 보존한다.

성능·접근성 결과:
- DB query 변경 없음. generated type과 client method 추가 후 JS baseline 대비 +0.08 kB, gzip +0.02 kB다.
- nullable field는 모두 required key이고 empty nodes/edges/warnings는 `[]`로 serialization test를 통과했다.

남은 위험:
- Endpoint `q`와 Alert `sortBy` storage/service semantics는 BWP-02에서 구현한다.
- Investigation route는 BWP-03 구현 전 가짜 graph 대신 인증 후 retryable `503 SERVICE_UNAVAILABLE`를 반환한다.
- layout v2 service/storage 호환성은 BWP-04에서 구현한다.

다음 Package: BWP-02 Query, Search와 정렬.
```

#### BWP-02 완료 증거

```text
Package: BWP-02 Query, Search와 정렬
상태: 완료
담당: Codex
완료일: 2026-07-15
변경 파일:
- backend/api_services.py
- backend/storage/postgres.py
- migrations/postgresql/0005_query_search_sort_indexes.up.sql
- migrations/postgresql/0005_query_search_sort_indexes.down.sql
- tools/local_demo.py
- tools/prod_init.py
- docs/contracts/API_SPEC.md
- tests/test_query_search_sorting.py
- tests/test_storage_integration.py
- tests/test_dashboard_api_integration.py
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- Endpoint `q`를 repository/service/route 전체에 연결했다. 숫자는 Endpoint ID exact, 문자열은 escaped case-insensitive hostname/agent ID exact·prefix 후보만 조회하며 `%`, `_`, `\`는 wildcard가 아닌 literal이다.
- 검색 후보 전체에 대해 exact 우선, `ONLINE → OFFLINE → RETIRED`, Risk DESC, hostname ASC, Endpoint ID ASC를 적용한 뒤 page를 자른다. `q`가 있으면 요청 `sortBy/sortOrder`를 적용하지 않는다.
- `q`가 없을 때 기존 Endpoint sort를 유지하고 Endpoint ID ASC tie-break를 보존한다. `riskLevel`, status, OS, endpointIds filter는 검색과 AND로 결합된다.
- Alert `priority`는 `OPEN → IN_PROGRESS → RESOLVED`, `CRITICAL → HIGH → MEDIUM → LOW`, Risk DESC, detectedAt DESC, Alert ID ASC다. priority는 `sortOrder`를 무시한다.
- Alert detectedAt/severity/riskScore/status 정렬은 요청 방향을 적용하고 항상 Alert ID ASC로 tie-break한다. enum ordinal은 API_SPEC에 명시했다.
- 현재 UI header가 요구하지 않는 다른 목록 sort는 추가하지 않았다.

Migration:
- `0005_query_search_sort_indexes`: active Endpoint의 `LOWER(hostname)`/`LOWER(agent_id)`에 `text_pattern_ops` expression index를 추가하고 Alert의 `(detected_at DESC, alert_id ASC)` partial index를 추가했다.
- up migration은 `IF NOT EXISTS`, down migration은 역순 `DROP INDEX IF EXISTS`로 멱등 적용·rollback한다.
- 기존 DB에서도 누락되지 않도록 local demo와 production app-init이 0005를 실행한다. 최초 실스택 검증에서 기존 app-init이 신규 migration을 건너뛰는 blocker를 발견해 이 경로를 수정했다.

실행한 검증:
- BWP-02 unit/contract targeted pytest: PASS, 11 tests.
- init/compose targeted pytest: PASS, 27 tests, 1 warning.
- 실제 PostgreSQL storage integration: PASS. 전체 down/up, 0005 2회 멱등 적용, index 3개 확인, 숫자 exact, prefix, wildcard literal과 rollback 검증.
- 전체 pytest: PASS, 202 passed, 4 skipped, 2 warnings.
- `uv run ruff check .`: PASS.
- `npm.cmd run openapi:check`: PASS, artifact drift 없음.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd test -- --run`: PASS, 13 files, 51 tests, 10.69s.
- `npm.cmd run build`: PASS, 9.83s. JS 507.14 kB/151.09 kB gzip, CSS 47.22 kB/8.45 kB gzip. 기존 500 kB warning만 유지.
- `docker compose config --quiet`: PASS.
- `git diff --check`: PASS. CRLF normalization warning만 있고 whitespace error 없음.

DB·API 검증 증거:
- app-init 재빌드·실행 후 PostgreSQL에 `idx_endpoints_hostname_lower_prefix`, `idx_endpoints_agent_id_lower_prefix`, `idx_alerts_detected_at`가 생성됐다.
- `EXPLAIN (COSTS OFF)`에서 Endpoint prefix query가 `idx_endpoints_agent_id_lower_prefix` Index Scan을 선택했다.
- 인증 live API: `q=agent&size=1` page 1/2가 총 3건에서 Endpoint 1/2, `q=2`는 1건, `q=agent-%`는 0건, 129자 query는 400을 반환했다.
- 인증 live API: Alert priority는 `[1, 2]`, `riskScore DESC`는 `[2, 1]`을 반환했다. 무인증 401과 VIEWER read permission은 기존 auth integration 계약을 보존한다.
- destructive migration integration 후 app-init과 `tests/seed_frontend_qa.py`를 다시 실행해 QA fixture와 healthy stack을 복원했고 최종 smoke에서 Endpoint total 3, Alert priority `[1, 2]`를 재확인했다.

브라우저 QA 증거:
- 해당 없음. DOM·style·route UI를 변경하지 않은 Backend query Package이며 MWO-00 visual baseline을 보존한다.

성능·접근성 결과:
- QA seed 10회 요청: Endpoint search min 24.0ms, median 25.0ms, p95/max 51.8ms. Alert priority min 23.0ms, median 25.1ms, p95/max 32.8ms.
- Frontend bundle은 BWP-01 값과 동일하다. UI와 accessibility tree 변경은 없다.

남은 위험:
- Endpoint Risk는 Backend application 계산값이므로 검색 prefix가 매우 넓으면 모든 일치 후보를 계산한 뒤 page를 자른다. client prefetch는 없고 index로 후보를 제한하지만 대규모 운영 cardinality에서는 별도 부하 관찰이 필요하다.
- Alert priority는 최대 31일로 제한된 filter 결과를 PostgreSQL이 정렬한다. 현 QA latency는 기준 이내지만 대량 운영 데이터에서는 sort spill과 time-range 선택도를 관찰한다.
- Incident investigation route의 임시 503은 BWP-03에서 실제 observed read model로 교체한다.

다음 Package: BWP-03 Incident Investigation Read Model.
```

#### BWP-03 완료 증거

```text
Package: BWP-03 Incident Investigation Read Model
상태: 완료
담당: Codex
완료일: 2026-07-15
변경 파일:
- backend/investigation_service.py
- backend/main.py
- tests/test_incident_investigation.py
- tests/test_dashboard_api_integration.py
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- BWP-01의 `GET /incidents/{incidentId}/investigation` 임시 503을 인증된 실제 `InvestigationService.investigation()` read model로 교체했다.
- Incident node와 Incident→Alert `CONTAINS` edge는 `incidents`, `incident_alerts`, `alerts`의 FK 근거로 만든다.
- 각 연결 Alert의 원본 `eventId`, `endpointId`, `eventOccurredAt`로 HOT 또는 RESTORED Event detail을 조회해 실제 Event가 있을 때만 Alert→Event와 Event→Process `TRIGGERED_BY` edge를 만든다.
- 수집된 PID/PPID가 있을 때만 parent Process→child Process `PARENT_OF`, process와 destination field가 모두 있을 때만 Process→Destination `CONNECTED_TO`를 만든다. 시간 인접성으로 relation을 추론하지 않는다.
- Event 누락은 `EVENT_NOT_FOUND`, 준비되지 않은 archive는 `ARCHIVE_NOT_READY` warning과 `partial=true`로 반환하고 해당 Event/Process/Destination node·edge를 만들지 않는다. archive warning이면 `fallback.eventTableAvailable=false`다.
- node ID는 원본 Incident/Alert/Event/Endpoint/PID를 사용하고 Destination만 endpoint·protocol·destination의 deterministic SHA-256 prefix를 사용한다. edge ID에는 관계 원본 ID가 포함되며 모든 edge는 `OBSERVED`와 nullable incident/alert/event/observedAt trace context를 가진다.
- 반환 순서는 Incident, Alert, Event, Process, Destination와 관측 시각·원본 ID 순으로 결정적이다. 최대 250 nodes/500 edges를 적용한 뒤 dangling edge를 제거하고 실제 배열 길이를 count로 반환한다.
- 원본 Alert endpoint가 Incident endpoint와 비정상적으로 다르더라도 Alert/Event/Process context와 Event lookup은 실제 Alert row endpoint를 보존한다.

Migration: 없음. 기존 PostgreSQL Incident/Alert 관계와 ClickHouse/S3 Event field만 조합하며 schema 변경이 없다.

설계 판단:
- Incident 연결 Alert의 원본 Event만 graph 확장점으로 사용한다. Incident window의 관계 없는 Event를 시간상 가깝다는 이유로 연결하지 않으며 추가 탐색은 fallback Event table이 담당한다.
- PID가 없고 processName만 있는 Event는 Event ID 기반 Process node를 사용해 서로 다른 관측을 임의로 합치지 않는다.
- PPID는 child Event의 수집 field 자체가 근거이므로 parent process detail이 별도로 없어도 nullable processName의 PID node와 추적 가능한 `PARENT_OF` edge를 허용한다.

실행한 검증:
- Investigation unit/service targeted pytest: PASS, 8 tests. 같은 입력 동일 graph, 4 relation, edge trace, missing/archive partial, 404, 250-node cap, dangling edge 부재를 검증했다.
- 실제 PostgreSQL·ClickHouse·S3 dashboard integration: PASS, 1 test, 2 warnings. ADMIN/VIEWER read 200, 무인증 401, 없는 Incident 404, HOT Event graph와 `OBSERVED` edge를 검증했다.
- 전체 pytest: PASS, 206 passed, 4 skipped, 2 warnings.
- `uv run ruff check .`: PASS.
- `npm.cmd run openapi:check`: PASS, BWP-01 artifact와 구현 drift 없음.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd test -- --run`: PASS, 13 files, 51 tests, 13.88s.
- `npm.cmd run build`: PASS, 11.43s. JS 507.14 kB/151.09 kB gzip, CSS 47.22 kB/8.45 kB gzip. 기존 500 kB warning만 유지.
- `docker compose config --quiet`: PASS.
- `git diff --check`: PASS. CRLF normalization warning만 있고 whitespace error 없음.

실스택 검증 증거:
- schema 통합 테스트 동안 Backend/worker/frontend/nginx만 정지하고 PostgreSQL·ClickHouse·Kafka·MinIO를 유지했다. 테스트 후 `docker compose up -d --build --wait`와 QA seed를 재실행해 전체 healthy 상태를 복원했다.
- 최종 인증 live graph는 8 nodes/8 edges이며 node type은 Incident 1, Alert 2, Event 2, Process 2, Destination 1이다.
- relation은 CONTAINS 2, TRIGGERED_BY 4, PARENT_OF 1, CONNECTED_TO 1이고 evidence는 전부 `OBSERVED`, warnings 0, partial/truncated false다.
- live VIEWER read 200, 무인증 401, Incident 999는 404를 반환했다.

브라우저 QA 증거:
- 해당 없음. Frontend DOM·style·route 렌더링을 변경하지 않은 Backend read-model Package이며 MWO-00 visual baseline을 보존한다.

성능·접근성 결과:
- 최종 QA seed Incident 1의 10회 요청은 min 39.7ms, median 42.5ms, p95/max 93.6ms다.
- Frontend bundle은 BWP-01/BWP-02와 동일하고 accessibility tree 변경은 없다.

남은 위험:
- 현재 read model은 연결 Alert마다 Event detail을 조회한다. node cap으로 응답은 제한되지만 연결 Alert가 매우 많은 Incident는 dependency round trip이 늘 수 있어 운영 cardinality에서 bulk fetch 또는 lookup budget을 후속 최적화 대상으로 관찰한다.
- missing Event warning 수는 연결 Alert 수를 따른다. oversized graph는 node/edge를 안전하게 cap하지만 극단적인 Alert 수의 warning payload도 운영 부하 관찰 대상이다.
- Frontend graph 렌더링과 partial/truncated fallback 전환은 WP-06에서 구현·시각 검증한다.

다음 Package: BWP-04 Dashboard Layout v2 호환성.
```

#### BWP-04 완료 증거

```text
Package: BWP-04 Dashboard Layout v2 호환성
상태: 완료
담당: Codex
완료일: 2026-07-15
변경 파일:
- backend/dashboard_layouts.py
- tests/test_dashboard_layouts.py
- tests/test_dashboard_api_integration.py
- frontend/tests/dashboard-layout-v1.fixture.ts
- frontend/tests/dashboard-layout.test.ts
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- 신규 또는 reset된 Overview layout의 기본 `layoutVersion`을 2로 전환했다.
- Backend는 BWP-01의 `Literal[1, 2]` 계약대로 v1과 v2 전체 layout을 모두 검증·저장하고, 저장된 버전과 revision을 임의 변경하지 않고 그대로 조회한다.
- v1 저장 layout을 조회한 뒤 같은 revision으로 v2 전체 layout을 저장하면 revision이 1 증가하고, 재조회와 PostgreSQL 행 모두 v2를 반환한다.
- 손상된 v1 layout은 저장 버전과 revision을 유지한 채 현재 기본 widget 배열과 `isDefault=true`를 반환한다. 지원하지 않는 저장 버전은 `400 VALIDATION_ERROR`로 거부한다.
- optimistic revision conflict, idempotent reset, 사용자별 layout 격리를 보존했다.
- WP-04가 구현 상태에 종속되지 않고 migration을 검증할 수 있도록 23개 v1 widget, revision 7, 사용자 hidden·size 선택을 포함한 정적 TypeScript fixture를 추가했다.

Migration: DB migration 없음. 기존 `user_dashboard_layouts.layout_version`과 optimistic revision 저장 계약을 그대로 사용하며 v1 row를 Backend가 자동으로 갱신하지 않는다. 실제 v1→v2 1회 migration과 안내는 WP-04 Frontend가 수행한다.

설계 판단:
- Backend의 v2 기본값과 v1/v2 저장 호환성만 이번 Package에 적용했다. 현재 Frontend의 `OVERVIEW_LAYOUT_VERSION=1`과 23-widget registry는 WP-04 전환 전까지 유지해 승인된 Package 경계를 지켰다.
- 손상된 지원 버전은 복구 가능한 기본 layout으로 반환하지만, 알 수 없는 미래 버전을 현재 registry로 조용히 덮어쓰지 않고 명시적 validation error로 중단한다.
- fixture는 현재 registry 함수로 생성하지 않고 정적으로 고정해 이후 widget 제거·추가 자체를 migration test가 감지하도록 했다.

실행한 검증:
- `uv run pytest -p no:cacheprovider --basetemp .tmp\\bwp04-unit tests/test_dashboard_layouts.py tests/test_ui_redesign_contracts.py tests/test_contract_serialization.py -q`: PASS, 25 tests, 2 warnings.
- `uv run ruff check backend/dashboard_layouts.py tests/test_dashboard_layouts.py tests/test_dashboard_api_integration.py`: PASS.
- `npm.cmd run test -- --run tests/dashboard-layout.test.ts`: PASS, 1 file, 9 tests.
- `npm.cmd run typecheck`: PASS.
- 실제 PostgreSQL·ClickHouse·MinIO dashboard integration: PASS, 1 test, 2 warnings. v2 default, v1 save/load, v2 save/reload, DB `(layout_version, revision)=(2,2)`, conflict, corruption fallback, reset과 user isolation을 검증했다.
- 전체 pytest: PASS, 209 passed, 4 skipped, 2 warnings. 첫 환경 실행은 `openssl` 미탐색으로 인증서 test 1개가 실패했고, `C:\\Program Files\\Git\\usr\\bin`을 PATH에 추가하고 `UV_CACHE_DIR=.uv-cache`를 사용한 동일 전체 suite가 통과했다.
- `uv run ruff check .`: PASS.
- `npm.cmd run openapi:check`: PASS, OpenAPI와 generated TypeScript schema drift 없음.
- `npm.cmd run lint`: PASS.
- `npm.cmd run test`: PASS, 13 files, 52 tests, 8.14s.
- `npm.cmd run build`: PASS, 4.70s. JS 507.14 kB/151.09 kB gzip, CSS 47.22 kB/8.45 kB gzip. 기존 500 kB warning만 유지.
- `docker compose config --quiet`: PASS.
- `git diff --check`: PASS. CRLF normalization warning만 있고 whitespace error 없음.

실스택 검증 증거:
- 재빌드된 live API에서 ADMIN은 `2/0/default → 1/1 → v1 reload → 2/2 → v2 reload` 순서가 통과했고 사용자 hidden 선택이 각 reload에서 유지됐다.
- stale revision 0의 v2 PUT은 `409 DASHBOARD_LAYOUT_REVISION_CONFLICT`, VIEWER는 별도 `2/0/default`, ADMIN reset과 reset 후 재조회는 모두 `2/0/default`였다.
- 첫 integration 시도는 코드 진입 전 ClickHouse host port connection refused로 실패했다. `docker compose ps -a`에서 데이터 컨테이너 전체 종료를 확인하고 PostgreSQL·ClickHouse·MinIO·Kafka만 healthy로 복구한 뒤 동일 테스트가 통과했다.
- 테스트 후 `docker compose up -d --build --wait`와 `uv run --env-file .env python tests/seed_frontend_qa.py`를 실행했다. Backend, Frontend, workers, PostgreSQL, ClickHouse, Kafka, MinIO와 Nginx가 최종 healthy이며 ADMIN layout은 default로 reset했다.

브라우저 QA 증거:
- 해당 없음. DOM·style·route 렌더링을 변경하지 않은 Backend 호환성 및 test fixture Package다. 실제 editor interaction과 viewport 검증은 WP-01, layout v2 UI migration은 WP-04에서 수행한다.

성능·접근성 결과:
- Frontend production bundle은 BWP-01~03과 동일하다. DOM과 accessibility tree 변경이 없다.
- layout API의 live 계약 흐름은 모두 로컬 Nginx 경유 요청으로 완료됐으며 새 polling, animation 또는 keyboard interaction을 추가하지 않았다.

남은 위험:
- Frontend는 WP-04 전까지 v1을 계속 저장하므로 Backend v2 기본값과의 과도기 상태다. Backend가 두 버전을 명시적으로 보존해 데이터 손실은 없지만 실제 1회 migration·conflict 재적용·안내 완료 처리는 WP-04에서 검증한다.
- Backend widget registry는 현재 23개다. 승인된 10-block registry와 제거 widget 병합 정책은 WP-04에서 Backend/Frontend를 함께 전환해야 한다.
- 기존 production bundle의 500 kB 초과 warning은 그대로이며 이번 Package로 증가하지 않았다.

다음 Package: WP-01 Overview 편집 안정성과 가로 폭 정렬.
```

### WP-01. Overview 편집 안정성과 가로 폭 정렬

범위:

- 편집 중 browser refresh, layout reload, Done 동작을 각각 재현한다.
- debounce save, in-flight request, revision update와 grid remount의 실제 관계를 진단한다.
- unsaved 또는 saving 상태에서 refresh가 발생할 때 동작을 명시적으로 처리한다.
- page header, filter/toolbar와 dashboard grid가 같은 horizontal inset을 사용하게 한다.
- 이 Package에서는 Sidebar, widget 구성, API 계약과 새로운 시각 스타일을 변경하지 않는다.

완료 조건:

- refresh 시 버벅임과 반복 remount가 재현되지 않는다.
- pending save는 flush, cancel 또는 사용자 경고 중 구현된 정책에 따라 결정적으로 처리된다.
- `PUT /dashboard/layouts/overview`의 전체 layout과 revision 계약을 유지한다.
- 1024px과 1440px에서 toolbar와 grid의 좌우 경계가 일치한다.
- 관련 component test와 전체 Frontend 검증 명령이 통과한다.

#### WP-01 완료 증거

```text
Package: WP-01 Overview Editor 안정화
상태: 완료
담당: Codex
완료일: 2026-07-15
변경 파일:
- frontend/src/pages/OverviewPage.tsx
- frontend/src/styles.css
- frontend/tests/dashboard-layout-editor.test.tsx
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

원인·구현:
- 기존 `finishEditing()`은 `void saveNow()` 직후 edit mode를 닫아 pending PUT의 성공·실패를 기다리지 않았다. 저장 실패에서 committed default로 rollback되면 사용자는 편집 종료 뒤 layout이 사라진 것처럼 보였다.
- 기존 in-flight 분기는 최신 draft를 queue한 뒤 현재 호출에는 즉시 반환하고 후속 PUT을 별도 `void` chain으로 실행해 `Done`이 전체 revision 연쇄를 기다릴 수 없었다.
- save를 현재 요청과 최신 queued draft를 소진하는 단일 drain Promise로 직렬화했다. 각 PUT은 직전 응답 revision을 사용하고, `Done`은 drain 성공 후에만 edit mode를 닫으며 일반 실패와 409에서는 edit mode·rollback·복구 UI를 유지한다.
- cancel이 in-flight 저장과 겹치면 edit baseline을 최신 queue로 넣어 중간 자동 저장값이 최종 상태가 되지 않게 했다. reset의 pending debounce 취소와 idempotent 서버 reset 동작은 보존했다.
- `unsaved` 또는 `saving` 동안 native `beforeunload` 경고를 등록하고 성공·실패 상태 전환 시 제거한다. hard reload를 dismiss하면 edit mode와 draft를 유지한다.
- grid key에서 `layoutLoadedAt`을 제거해 layout refetch만으로 remount하지 않게 했다. 실제 visible widget set 또는 responsive breakpoint가 바뀔 때만 key가 바뀐다.
- Responsive grid의 outer `containerPadding`을 0으로 지정하고 12px widget gutter는 유지했다. `.dashboard-grid`의 `margin:-12px`을 제거해 PageHeader, filter, editor bar, grid shell과 첫·마지막 panel이 같은 frame edge를 사용한다.

계약·제외:
- `PUT /dashboard/layouts/overview`의 v1 전체 layout, optimistic revision, 650ms debounce와 BWP-04 v1/v2 Backend 호환 계약을 변경하지 않았다.
- Sidebar, 23-widget 구성, layout v2 migration, token 재구성과 새 시각 스타일은 각각 WP-02/WP-04 범위로 남겼다. Backend·OpenAPI 변경은 없다.

실행한 검증:
- WP-01 editor targeted Vitest: PASS, 1 file, 10 tests. pending Done, already in-flight + latest queue, revision 4→5 serialization, 일반 실패, Done conflict, cancel, reset, unload warning을 검증했다.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run test`: PASS, 13 files, 56 tests, 10.25s.
- `npm.cmd run build`: PASS, 8.90s. JS 507.58 kB/151.25 kB gzip, CSS 47.22 kB/8.45 kB gzip. 기존 500 kB warning만 유지.
- Backend layout contract pytest: PASS, 15 tests, 2 warnings.
- `npm.cmd run openapi:check`: PASS, artifact/generated schema drift 없음.
- `docker compose config --quiet`: PASS.
- `git diff --check`: PASS. CRLF normalization warning만 있고 whitespace error 없음.

브라우저 QA 증거:
- 최신 Frontend image를 재빌드하고 Playwright headless Chromium으로 live Nginx/API를 검증했다. PUT을 900ms 지연한 상태에서 keyboard `Delete`로 widget을 숨기고 `Done`을 눌렀을 때 edit control과 `Saving dashboard layout.`이 유지됐으며, 성공 뒤에만 edit mode가 종료됐다.
- 저장 뒤 grid DOM node가 동일했고 widget은 화면에서 숨겨졌다. hard reload 후에도 저장 상태가 유지됐으며 reset과 cancel 뒤 기본 widget이 복원됐다.
- unsaved hard reload는 실제 `beforeunload` dialog를 만들었고 dismiss 후 `Done`, Unsaved 상태와 draft가 유지됐다.
- 외부 저장으로 stale revision을 만든 뒤 UI `Done`은 `409 DASHBOARD_LAYOUT_REVISION_CONFLICT`에서 edit mode와 conflict 안내를 유지했다. `Reload latest` 후 외부 서버 layout을 적용했고, 다른 unsaved change는 rollback됐다. 마지막 reset으로 ADMIN layout을 default로 복구했다.
- 1440px에서 frame x=74, width=1346, 1024px에서 x=74, width=930이었다. PageHeader, filter, editor, grid shell, full-width 첫 panel의 left/right delta는 두 viewport 모두 0px이고 document `scrollWidth == clientWidth`였다.
- 캡처: `wp01-overview-1440.png`, `wp01-overview-1024.png`. 시각 점검에서 clipping, horizontal jump와 panel edge 불일치 없음.
- page error 0. 일반 시나리오 console error 0이며 conflict 시나리오에서 의도적으로 발생시킨 HTTP 409 resource log 1개만 확인했다.

Hard Pre-flight 결과:
- Route, URL time filter, API enum·권한, v1 layout contract, status semantic color와 기존 dark surface를 보존했다.
- keyboard hide, aria-live save status, native refresh warning, reduced-motion 기존 규칙과 1024/1440 horizontal frame을 확인했다. 새 hover-only 정보, gradient, animation, KPI 계산 또는 dependency를 추가하지 않았다.
- 360px fixed min-width, mobile drawer, KO/EN AppShell과 200% zoom은 이번 editor-only Package의 변경 대상이 아니며 바로 다음 WP-02의 명시적 완료 조건이다.

남은 위험:
- native beforeunload 문구는 browser가 결정하므로 제품 문구를 표시할 수 없다. 이번 범위의 hard refresh는 경고하지만 SPA route blocker는 새로 추가하지 않았다.
- Frontend는 WP-04 전까지 layout v1과 23-widget registry를 유지한다.
- 360px에서의 기존 `min-width:768px` horizontal overflow와 200% zoom AppShell은 WP-02에서 해결·검증한다.
- production JS의 기존 500 kB warning은 유지되며 BWP-04 대비 raw 약 0.44 kB, gzip 약 0.16 kB 증가했다.

다음 Package: WP-02 Foundation, Login과 AppShell.
```

### WP-02. Foundation, Login과 AppShell

범위:

- semantic surface, border, text, action, status token을 역할 중심으로 정리한다.
- `--gradient-accent-surface`, `--gradient-chart-fill`을 prototype으로 구현한다.
- Button, Field, Select, Badge, Dialog, Drawer와 공통 상태 표현을 정리한다.
- `min-width: 768px` 의존을 제거하고 360px부터 사용할 수 있는 기반을 만든다.
- Login의 제품 설명과 인증 form을 분리하고 오류·session·keyboard 동작을 보존한다.
- 확정된 Sidebar group, compact mode, breadcrumb와 mobile modal drawer를 구현한다.

완료 조건:

- gradient가 `DESIGN.md` 6.2의 허용 범위에만 사용된다.
- status color와 gradient 의미가 분리된다.
- keyboard focus, reduced motion, 200% zoom과 contrast를 검증한다.
- 360, 768, 1024, 1440px과 KO/EN에서 Login과 AppShell이 동작한다.

#### WP-02 완료 증거

```text
Package: WP-02 Foundation, Login과 AppShell
상태: 완료
담당: Codex
완료일: 2026-07-15
변경 파일:
- frontend/src/components/AppShell.tsx
- frontend/src/components/primitives.tsx
- frontend/src/components/ui.tsx
- frontend/src/i18n/translations.ts
- frontend/src/main.tsx
- frontend/src/pages/LoginPage.tsx
- frontend/src/styles/tokens.css
- frontend/src/styles/reset.css
- frontend/src/styles/primitives.css
- frontend/src/styles/shell.css
- frontend/src/styles/patterns.css
- frontend/src/styles/visualizations.css
- frontend/src/styles/pages/login.css
- frontend/tests/primitives.test.tsx
- frontend/tests/app-shell-foundation.test.tsx
- frontend/tests/auth-routing.test.tsx
- frontend/tests/locale.test.tsx
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

Foundation·구현:
- dark-only role token으로 canvas/shell/panel/raised/inset surface, border, 3단계 text, primary accent, 4개 status, spacing, radius, typography와 elevation을 정의했다. legacy selector가 사용하는 color/type alias는 token을 참조하게 해 페이지 migration 전에도 동일 의미를 사용한다.
- `--gradient-accent-surface`는 active navigation과 Login 제품 context에만 낮은 대비로 적용했다. status는 solid semantic color와 text/icon을 유지하며 gradient로 상태를 표현하지 않는다. `--gradient-chart-fill`은 향후 chart area consumer를 위한 기능 token으로 정의했으며 장식 배경으로 오용하지 않았다.
- 공통 Button/IconButton, Field/TextField/SelectField, Badge, Tooltip, Popover, Dialog와 Drawer를 추가했다. disabled/loading, helper/error association, Escape, outside close, body scroll lock, modal Tab wrap와 focus 반환 계약을 구현했다.
- 기존 `styles.css`는 페이지 호환 레이어로 먼저 읽고, `token → reset → primitive → shell → pattern → visualization → page` 순으로 새 CSS를 적용한다. Login 전용 override와 chart/status override를 소유 계층으로 분리했다.
- root의 고정 `min-width: 768px`를 후행 reset에서 제거해 `html`, `body`, `#root`가 360px까지 줄어들게 했다.
- Sidebar는 Overview / Triage / Evidence / Analysis / Platform group 순서로 재구성하고 Operations 아래 Archives child hierarchy를 표시한다. desktop compact state의 기존 localStorage 계약을 유지하고 icon-only 상태에도 동작명과 keyboard Tooltip을 제공한다.
- top bar에 route 기반 breadcrumb, 기존 Event evidence search, Backend locale selector와 Account Popover를 배치했다. 기존 print/report 동작은 focus-trapped Dialog로 옮겼다.
- 900px 이하에서는 desktop navigation을 숨기고 동일 route source를 쓰는 modal Drawer를 제공한다. Drawer는 close button으로 focus 이동, 앞/뒤 Tab wrap, Escape close와 menu trigger focus 반환을 지원한다.
- Login의 제품 context와 인증 form 분리를 유지하면서 새 Field/Button primitive를 적용했다. login error, 탭 session 복원, intended route, KO 사용자 로그인 후 locale 적용과 logout 초기화 계약을 보존했다.
- 신규 npm dependency는 추가하지 않았다.

계약·보존:
- Backend, API, OpenAPI, generated schema와 DB migration 변경은 없다. 기존 route, JWT/sessionStorage, `GET /users/me` 재검증, role permission, URL query, polling과 Backend 계산값 의미를 보존했다.
- locale은 기존 `PATCH /users/me/locale`과 session `UserDto.locale`만 사용한다. Login은 locale 선택 흐름에 포함하지 않는다.
- global search는 숫자를 `endpointId`, 문자열을 `processName`으로 직렬화하는 기존 `/events` query 계약을 유지한다.
- Report는 현재 pathname, 생성 시각, 사용자 role과 browser print를 유지하며 새 data 또는 계산값을 만들지 않는다.

실행한 검증:
- `npm.cmd test -- --run tests/primitives.test.tsx tests/app-shell-foundation.test.tsx tests/auth-routing.test.tsx tests/locale.test.tsx`: PASS, 4 files, 16 tests.
- compact accessible-name 실브라우저 결함 수정 후 `npm.cmd test -- --run tests/app-shell-foundation.test.tsx`: PASS, 2 tests.
- 최종 `npm.cmd run typecheck`: PASS.
- 최종 `npm.cmd run lint`: PASS.
- 최종 `npm.cmd test -- --run`: PASS, 15 files, 61 tests, 11.70s.
- 최종 `npm.cmd run build`: PASS, 9.74s. JS 514.81 kB/153.29 kB gzip, CSS 66.14 kB/11.77 kB gzip. 기존 500 kB chunk warning만 유지.
- `npm.cmd run openapi:check`: PASS. OpenAPI artifact와 generated schema drift 없음.
- `docker compose config --quiet`: PASS.
- `docker compose up -d --build --no-deps --wait frontend`: PASS. 최신 Frontend image healthy, Nginx와 Backend 포함 기존 stack healthy.
- `git diff --check`: PASS. 기존 CRLF normalization warning만 있고 whitespace error 없음.

브라우저 QA 증거:
- Playwright headless Chromium으로 live Nginx/API의 `/operations/archives`와 `/login`을 검증했다. 실제 ADMIN login/session과 Backend locale PATCH를 사용했고 마지막에 locale을 EN으로 복원했다.
- 1440px과 1024px은 216px grouped desktop navigation, 768px과 360px은 modal navigation trigger가 활성화됐다. 네 viewport 모두 `document.scrollWidth == clientWidth`이고 top bar와 main right edge가 viewport와 일치했다.
- 768px Drawer focus는 `Close navigation → Shift+Tab Archives → Tab Close navigation`으로 wrap했고 Escape 뒤 menu trigger로 반환됐다.
- 360px KO에서 account label `계정 메뉴 열기`, drawer label `탐색 메뉴 열기/닫기`, translated Archive form과 no-overflow를 확인했다. EN으로 복원 후 session도 유지됐다.
- compact mode 실검증에서 숨긴 text 때문에 toggle accessible name이 사라지는 문제를 발견해 `aria-label`을 추가했다. keyboard focus에서 Tooltip이 보이고 compact/expand가 양방향 동작했다.
- Account Popover의 ADMIN/name/login ID, Report Dialog의 initial focus, Escape close를 확인했다. console error와 page error는 0건이다.
- `prefers-reduced-motion: reduce`에서 transition duration은 `0.00001s`였다. 1440px browser 200% zoom의 layout reflow 등가인 720 CSS px에서 mobile shell로 전환되고 overflow는 0이었다.
- Login은 360px과 1440px 모두 overflow 0, Login ID/Password keyboard focus, 빈 submit의 accessible validation error와 기존 session 문구를 확인했다.
- 캡처: `wp02-shell-1440.png`, `wp02-shell-1024.png`, `wp02-shell-768.png`, `wp02-shell-360.png`, `wp02-shell-360-ko.png`, `wp02-login-1440.png`, `wp02-login-360.png`. 대표 이미지를 시각 검수했고 clipping, overlap, blank/error capture가 없었다.

접근성·Hard Pre-flight:
- text-primary/panel 15.24:1, text-secondary/panel 7.09:1, accent/shell 10.57:1, critical/panel 4.80:1이다. baseline text-tertiary는 4.39:1이어서 `DESIGN.md` 6.3 규칙대로 `#768498`로 최소 조정해 panel 위 4.51:1을 확보했다.
- focus-visible accent, modal focus management, skip link, form label/description, breadcrumb/navigation 이름, text+icon status와 reduced-motion을 확인했다.
- Route, auth/session, locale, URL search, permission과 data meaning은 변경하지 않았다. generic gradient, glass, 장식 pill, hover-only 핵심 정보와 새 animation을 추가하지 않았다.
- DataTable 공통 interaction과 page별 loading/stale/partial 표준화는 이번 Foundation 범위에서 변경하지 않았고 바로 다음 WP-03 gate로 남겼다.

남은 위험:
- legacy `styles.css`와 새 계층을 함께 제공하는 과도기라 CSS가 WP-01 47.22 kB에서 66.14 kB로 증가했다. WP-03~08에서 공통 pattern과 page selector를 새 소유 파일로 옮긴 뒤 legacy 중복을 제거한다.
- JS는 WP-01 대비 raw +7.23 kB, gzip +2.04 kB이며 500 kB warning을 유지한다. 신규 dependency 때문은 아니며 WP-09에서 route code splitting을 release gate로 검토한다.
- `--gradient-chart-fill`은 token/계층만 준비됐고 실제 정량 area chart 적용은 chart 구성이 확정되는 WP-04/WP-08에서 접근성 table fallback과 함께 검증한다.
- 200% 검증은 Chromium의 1440px→720 CSS px reflow 등가로 자동화했다. 최종 WP-09에서는 실제 지원 browser의 UI zoom 수동 smoke test도 함께 기록한다.

다음 Package: WP-03 공통 Data Interaction.
```

### WP-03. 공통 Data Interaction

범위:

- semantic `<table>`을 유지한 공통 header, row, selected, hover, empty, loading pattern을 만든다.
- 숫자 정렬, truncated identifier, row action, horizontal overflow 우선순위를 정한다.
- KPI 정의, chart point, truncated text 같은 보조 정보에 Tooltip 또는 Popover를 제공한다.
- 핵심 정보와 action을 hover에만 숨기지 않는다.
- 기본 filter는 3개 이내로 노출하고 나머지는 Popover 또는 Drawer로 이동한다.
- filter, sort, page, selection과 time range를 URL로 보존한다.

완료 조건:

- mouse hover, keyboard focus, touch/click에서 동등한 정보를 확인할 수 있다.
- 대표 목록 한 화면에서 검증한 뒤 다른 화면으로 확장한다.
- sort, filter, pagination과 URL 상태를 보존한다.

#### WP-03 완료 증거

```text
Package: WP-03 공통 Data Interaction
상태: 완료
담당: Codex
완료일: 2026-07-15

변경 파일:
- frontend/src/components/primitives.tsx
- frontend/src/components/ui.tsx
- frontend/src/components/filters.tsx
- frontend/src/features/listInteractions.ts
- frontend/src/i18n/translations.ts
- frontend/src/pages/AlertsPage.tsx
- frontend/src/pages/IncidentsPage.tsx
- frontend/src/pages/EndpointsPage.tsx
- frontend/src/pages/EventsPage.tsx
- frontend/src/pages/ArchivesPage.tsx
- frontend/src/pages/IncidentDetailPage.tsx
- frontend/src/pages/EndpointDetailPage.tsx
- frontend/src/pages/EventDetailPage.tsx
- frontend/src/styles/primitives.css
- frontend/src/styles/patterns.css
- frontend/tests/data-interaction.test.tsx
- frontend/tests/data-interaction-source.test.ts
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- `FilterBar`는 기본 field를 최대 3개로 제한하고 추가 field를 제목과 focus trap이 있는 right-side Drawer에 둔다. 적용 filter chip은 개별 제거, 전체 초기화와 page reset을 지원한다.
- Alerts, Incidents, Endpoints, Events와 Archives가 같은 FilterBar, QueryFeedback, semantic DataTable과 Pagination 계약을 사용한다. Archives는 필수 3개 기준만 노출하며 incomplete와 invalid를 구분한다.
- filter, sort, order, page, size, selected와 time range는 URLSearchParams에 보존된다. Alerts/Incidents/Endpoints 상세의 back link는 list query를 유지하고 Event detail은 allowlist된 `returnTo`만 사용한다.
- BWP-02의 Endpoint `q`와 Alert server sort를 실제 UI에 연결했다. enum, positive integer, text 길이, page/size와 custom time range를 API 요청 전에 검증한다.
- DataTable은 숨김 caption, 명명된 keyboard scroll region, `scope`, `aria-sort`, selected row와 `aria-busy`를 제공한다. Panel과 table scroll region의 accessible name 충돌을 피하도록 table region은 `… table`로 구분한다.
- loading, background refetching, stale/refetch error, partial failure, empty, invalid filter, forbidden과 archive-not-ready를 서로 다른 시각·ARIA 상태로 제공한다.
- `MasterDetail`, `Inspector`와 chart의 설명·meta·접근 가능한 data fallback을 소유하는 `ChartFrame`을 추가했다. 실제 chart/graph dependency와 domain-specific consumer는 WP-04/WP-06/WP-08 범위로 남겼다.
- Backend, OpenAPI, generated schema, DB와 permission 의미는 변경하지 않았다. 신규 npm dependency도 없다.

실행한 검증:
- `npm.cmd test -- --run tests/data-interaction.test.tsx tests/data-interaction-source.test.ts --reporter=dot`: PASS, 2 files, 13 tests. filter 3개, Drawer focus/Escape, applied filter, table caption/sort, URL pagination/size/selection, loading·stale·partial·forbidden·archive, 5개 page 공유 계약을 검증했다.
- `npm.cmd test -- --run --reporter=dot`: PASS, 17 files, 74 tests, 10.97s.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run build`: PASS, 5.43s. JS 525.46 kB/156.40 kB gzip, CSS 71.47 kB/12.49 kB gzip. 기존 500 kB chunk warning만 유지된다.
- `$env:UV_CACHE_DIR='.uv-cache'; npm.cmd run openapi:check`: PASS. OpenAPI artifact와 generated schema drift 없음.
- `docker compose config --quiet`: PASS.
- `docker compose up -d --build --no-deps --wait frontend`: PASS. 최신 Frontend image healthy.
- `docker compose ps --format json`: PASS. Frontend, Backend, Nginx, PostgreSQL, ClickHouse, Kafka와 MinIO가 running/healthy이고 두 worker가 running이다.
- `git diff --check`: PASS. 기존 CRLF normalization warning만 있고 whitespace error 없음.

브라우저 QA 증거:
- Playwright headless Chromium과 실제 ADMIN session으로 Alerts, Incidents, Endpoints, Events, Archives를 1440px/360px에서 검증했다. 10개 조합 모두 root horizontal overflow 0이고 기본 filter field는 정확히 3개다.
- 추가 filter가 있는 4개 화면에서 right Drawer initial focus, Escape close와 trigger focus 반환을 확인했다. Archives에는 추가 filter trigger가 없다.
- keyboard Enter로 Alerts Risk sort를 실행해 `sortBy=riskScore&sortOrder=desc`, Endpoint 검색으로 `q=win`, Event detail link에서 selected를 포함한 allowlist `returnTo`를 확인했다.
- invalid Alert enum은 list API 요청 전에 차단됐고 Archive의 미입력 empty와 역전/invalid range 상태가 구분됐다. console error와 page error는 각각 0건이다.
- semantic table은 실제 데이터가 있는 Alerts, Incidents와 Endpoints에서 caption, keyboard region과 horizontal inner scroll을 유지하면서 360px root overflow를 만들지 않았다.
- 캡처: `wp03-alerts-1440.png`, `wp03-alerts-360.png`, `wp03-incidents-360.png`, `wp03-endpoints-360-stable.png`, `wp03-events-360.png`, `wp03-archives-360.png`. 대표 캡처를 시각 검수해 clipping, overlap과 빈 오류 화면이 없음을 확인했다.

남은 위험:
- live Alerts fixture는 총 1건이어서 실제 Nginx/API에서 next-page 전환은 만들 수 없었다. 120건 fixture component test로 previous/next URL, page reset과 25/50/100 page-size를 검증했으며 운영 cardinality smoke는 WP-09에서 반복한다.
- legacy `styles.css`와 새 pattern layer의 과도기 중복으로 WP-02 대비 JS raw/gzip은 +10.65/+3.11 kB, CSS raw/gzip은 +5.33/+0.72 kB다. 신규 dependency는 없지만 route code splitting과 legacy selector 제거는 WP-09 bundle gate까지 추적한다.
- `PartialFailureWarning`, `Inspector`와 `ChartFrame`의 공통 계약은 검증했지만 실제 Incident/Intelligence partial consumer와 graph/table fallback은 WP-06/WP-08에서 domain fixture로 검증한다.

다음 Package: WP-04 Overview 10 Block과 Migration.
```

### WP-04. Overview 축소와 Toolbar

확정 범위:

- 확정된 기본 block만 남기고 제거 widget과 저장 layout migration을 적용한다.
- Time range, Endpoint scope, refresh, last updated, layout edit를 compact toolbar/popover로 통합한다.
- KPI, Detection Activity, Alert Severity, Endpoint Risk Distribution과 priority queue가 중복 없이 상태→원인→우선 대상 순으로 읽히게 한다.
- layout v2 migration 성공 후 1회 안내를 표시하고 conflict에서 재시도 경로를 제공한다.

#### WP-04 완료 증거

```text
Package: WP-04 Overview 축소와 Toolbar
상태: 완료
담당: Codex
완료일: 2026-07-15

변경 파일:
- backend/dashboard_layouts.py
- tests/test_dashboard_layouts.py
- tests/test_dashboard_api_integration.py
- frontend/src/components/charts.tsx
- frontend/src/features/dashboardLayout.ts
- frontend/src/features/overviewWidgetRegistry.tsx
- frontend/src/pages/OverviewPage.tsx
- frontend/src/i18n/translations.ts
- frontend/src/styles/pages/overview.css
- frontend/src/main.tsx
- frontend/tests/dashboard-layout.test.ts
- frontend/tests/dashboard-layout-editor.test.tsx
- frontend/tests/overview-redesign.test.tsx
- docs/contracts/API_SPEC.md
- docs/frontend/FRONTEND_SPEC.md
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- Backend layout registry를 version별로 분리했다. v1은 기존 23개 widget 호환성을 보존하고 v2는 승인된 `edr-state`, Alert/Open Incident/High-risk Endpoint/Event Failure KPI, Detection Activity, Alert Severity, Endpoint Risk, Highest-risk Endpoints, Incident Queue의 10개만 소유한다.
- Frontend v2 registry도 동일한 10개 ID와 제약으로 고정했다. 제거된 OS, sensor, Top Rule, MITRE, signal, failure/storage distribution, Response Guidance와 개별 Event/Alert/Incident chart renderer를 Overview에서 제거했다.
- `event-volume`의 geometry와 hidden 선택을 `detection-activity`로 옮기는 pure v1→v2 migration을 구현했다. PUT 성공 뒤에만 현재 tab 안내를 표시하고, conflict reload와 non-conflict retry를 제공한다.
- React StrictMode 실제 remount가 같은 v1 응답을 두 번 migration하여 두 번째 PUT이 409가 되는 결함을 browser QA에서 발견했다. in-flight Promise와 동일 응답 객체 1회 guard를 함께 적용해 최종 PUT 1회로 고정했다.
- Detection Activity는 Dashboard API가 반환한 Event, Alert, Incident time bucket을 재집계하지 않고 3개 small series와 semantic table fallback으로 표시한다.
- toolbar는 현재 계약이 지원하는 정직한 `All endpoints` scope Popover, URL time range Popover, manual refresh, 30초 auto-refresh 설명, last updated와 layout editor action을 통합한다. Endpoint별 Summary filter는 Backend 계약에 없으므로 client-side 가상 필터를 만들지 않았다.
- 768px 미만에는 저장된 desktop 순서를 보존하는 read-only 1-column 안전 layout을 제공한다. 2026-07-15 사용자 지시에 따라 모바일 size는 이후 Package의 추가 완료 기준과 시각 QA에서 제외한다.

실행 명령·결과:
- `$env:Path='C:\Program Files\Git\usr\bin;' + $env:Path; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest -p no:cacheprovider --basetemp .tmp\wp04-full`: PASS, 209 passed, 4 skipped, 2 warnings, 16.74s.
- `$env:UV_CACHE_DIR='.uv-cache'; uv run ruff check backend tests tools`: PASS.
- `npm.cmd test -- --run tests/dashboard-layout.test.ts tests/dashboard-layout-editor.test.tsx tests/overview-redesign.test.tsx`: PASS, 3 files, 24 tests.
- `npm.cmd test -- --run`: PASS, 18 files, 79 tests.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run build`: PASS, 1711 modules, 8.82s. JS 527.49 kB/157.06 kB gzip, CSS 76.14 kB/13.10 kB gzip. 기존 500 kB chunk warning만 유지됐다.
- `$env:UV_CACHE_DIR='.uv-cache'; npm.cmd run openapi:check`: PASS, OpenAPI artifact와 generated schema drift 없음.
- `docker compose config --quiet`: PASS.
- `docker compose up -d --build backend frontend`: PASS. 변경 Backend/Frontend image가 healthy 상태로 기동됐다.

Browser·live 증거:
- Playwright headless Chromium과 실제 ADMIN session으로 v2 row의 현재 revision을 조회한 뒤 v1 `event-volume` 12x6 fixture를 저장하고 Overview를 열었다. Frontend는 revision 9를 사용한 v2 PUT을 정확히 1회 실행했고 최종 revision 10, layoutVersion 2, widget 10개를 반환했다.
- `detection-activity`는 v1의 12x6 geometry를 보존했다. 1440px에서 승인된 10개 widget이 모두 렌더링됐고 root overflow 0, Detection Activity series 3개, toolbar 1328px를 확인했다.
- Endpoint scope Popover는 Escape 뒤 trigger focus를 복원했다. Time range는 `?timePreset=LATEST_1H`로 URL에 보존됐고 manual refresh가 새 Dashboard request를 발생시켰다.
- 최종 run은 layout PUT 1회, HTTP 4xx/5xx 0, console error 0, page error 0이다. capture는 `wp04-overview-1440.png`다.

남은 위험:
- Dashboard Summary API에는 endpoint scope query가 없으므로 toolbar scope는 `All endpoints`만 제공한다. 실제 endpoint filter 확장은 별도 Backend 계약 Package가 필요하다.
- production JS 527.49 kB의 기존 chunk warning이 남아 있으며 WP-09 release gate에서 route code splitting을 검토한다.
- legacy `styles.css`와 page CSS의 과도기 중복은 WP-05~08 consumer 이동 뒤 WP-09에서 정리한다.

다음 Package: WP-05 Alerts와 Response Guidance.
```

### WP-05. Alerts와 Response Guidance

범위:

- desktop queue+detail, mobile drawer와 priority sort를 구현한다.
- `저장`과 `저장 후 다음`을 분리한다.
- Rule version, order, title, description과 Manual badge를 유지한 읽기 전용 guidance를 구현한다.
- 실행, 격리, 프로세스 종료와 파일 삭제 control은 추가하지 않는다.

#### WP-05 완료 증거

```text
Package: WP-05 Alerts와 Response Guidance
상태: 완료
담당: Codex
완료일: 2026-07-15

변경 파일:
- frontend/src/components/ui.tsx
- frontend/src/features/alertTriage.ts
- frontend/src/i18n/translations.ts
- frontend/src/main.tsx
- frontend/src/pages/AlertDetailPage.tsx
- frontend/src/pages/AlertsPage.tsx
- frontend/src/styles/pages/alerts.css
- frontend/tests/alert-triage.test.ts
- frontend/tests/alert-workbench.test.tsx
- frontend/tests/cache-boundary.test.ts
- frontend/tests/components.test.tsx
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- Alert 목록의 Backend `priority` 정렬 계약을 그대로 사용하고 우선순위 기준을 화면에 명시했다. `priority` 선택 중에는 Backend가 방향을 무시한다는 사실에 맞춰 order control을 비활성화하고 동률 정렬 기준을 설명한다.
- detail queue query가 목록의 time, status, severity, endpoint, rule, sort field와 sort order를 보존하도록 통합했다. 선택 이동 URL은 stale `selected`를 복사하지 않고 다음 Alert ID로 교체한다.
- queue와 detail을 340px/가변 폭 desktop monitor workbench로 구성하고 severity, status, risk를 동시에 노출했다. 2026-07-15 사용자 지시에 따라 mobile drawer 구현과 mobile viewport QA는 완료 기준에서 제외했다.
- `저장`은 현재 Alert에 머물고 `저장 후 다음`은 mutation 성공 뒤 다음 unresolved Alert로 이동하도록 분리했다. Alert mutation은 목록뿐 아니라 triage queue cache도 무효화해 처리 완료 행이 재등장하지 않게 했다.
- Response Guidance는 ruleCode와 version 출처, order, title, description을 읽기 전용 ordered list로 표시한다. Manual action은 warning badge로 표시하며 checkbox, 실행, 격리, 프로세스 종료, 파일 삭제 control은 제공하지 않는다.
- VIEWER에서는 상태 변경 control을 숨기고 read-only 안내와 guidance만 유지한다. Backend·OpenAPI 계약 변경은 없다.

실행 명령·결과:
- `npm.cmd test -- --run tests/alert-triage.test.ts tests/cache-boundary.test.ts tests/components.test.tsx tests/alert-workbench.test.tsx tests/data-interaction.test.tsx`: PASS, 5 files, 23 tests.
- `npm.cmd test -- --run`: PASS, 19 files, 85 tests, 12.66s.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run build`: PASS, 1712 modules, 6.66s. JS 528.71 kB/157.33 kB gzip, CSS 77.21 kB/13.28 kB gzip. 기존 500 kB chunk warning만 유지됐다.
- `docker compose build frontend`: PASS.
- `docker compose up -d --no-deps frontend`: PASS. 변경 Frontend image로 실제 browser QA를 수행했다.
- `git diff --check`: PASS. 기존 line-ending 변환 warning만 있고 whitespace error는 없다.

Browser·live 증거:
- Playwright headless Chromium과 실제 ADMIN/VIEWER session을 사용해 1440x900 monitor viewport에서 검증했다. mobile viewport는 사용자 지시에 따라 실행하지 않았다.
- Alert 목록은 priority 기준과 설명을 표시하고 order select를 비활성화했다. detail URL은 `/alerts/1?status=OPEN&sortBy=priority&selected=1`로 목록 상태와 선택을 함께 보존했다.
- ADMIN workbench는 queue x=88, width=340, detail x=444, width=972, root overflow 0이며 `저장`과 `저장 후 다음`을 별도 action으로 표시했다. VIEWER에서는 두 action이 모두 숨겨지고 read-only 안내가 표시됐다.
- 실제 guidance 출처는 `PROC_POWERSHELL_ENCODED v1`로 표시됐고 checkbox·run control은 없었다. ADMIN/VIEWER 모두 HTTP 4xx/5xx 0, console error 0, page error 0이다.
- capture는 `wp05-alert-workbench-1440.png`다.

남은 위험:
- live fixture에는 unresolved Alert가 1개뿐이어서 실제 환경의 `저장 후 다음` 다중 행 이동은 mutation 없는 browser run에서 재현할 수 없었다. 3행 fixture component test가 저장 후 다음 ID 이동과 query 보존을 검증한다.
- queue는 현재 API 최대 page size인 500개를 사용한다. 운영 queue가 이를 넘으면 cursor 또는 queue 전용 pagination 계약이 별도 Backend Package로 필요하다.
- production JS 528.71 kB의 기존 chunk warning과 legacy CSS 중복은 WP-09 release gate에서 정리한다.

다음 Package: WP-06 Incidents와 Investigation.
```

### WP-06. Incidents와 Investigation

범위:

- Incident queue, graph, Selected context, swimlane timeline과 evidence list를 연결한다.
- Process Tree는 Endpoint와 time range가 확보된 경우 제공한다.
- graph selection을 Inspector, timeline과 evidence row에 동기화한다.
- lifecycle은 읽기 전용이며 graph error 또는 flag off에서 timeline/table fallback을 유지한다.

#### WP-06 완료 증거

```text
Package: WP-06 Incidents와 Investigation
상태: 완료
담당: Codex
완료일: 2026-07-15

변경 파일:
- .env.example
- .env.production.example
- compose.yaml
- frontend/package.json
- frontend/package-lock.json
- frontend/src/components/IncidentGraph.tsx
- frontend/src/components/IncidentInvestigation.tsx
- frontend/src/features/incidentInvestigation.ts
- frontend/src/i18n/translations.ts
- frontend/src/main.tsx
- frontend/src/pages/IncidentDetailPage.tsx
- frontend/src/styles/pages/incidents.css
- frontend/src/vite-env.d.ts
- frontend/tests/incident-investigation.test.tsx
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- BWP-03의 `GET /incidents/{incidentId}/investigation` 계약을 변경 없이 소비한다. Backend/OpenAPI/generated schema 변경과 DB migration은 없다.
- 목록의 time, status, severity, Endpoint와 sort context를 유지하는 최대 500개 Incident queue를 detail에 연결했다. status가 없으면 OPEN을 기본 queue로 사용하고 선택 URL의 stale `selected`를 현재 Incident ID로 교체한다.
- 상단은 340px OPEN queue와 Incident detail, 하단은 모니터 전체 폭 Investigation workspace로 구성했다. 2026-07-15 사용자 지시에 따라 mobile layout과 mobile viewport QA는 이번 Package 완료 기준에서 제외했다.
- `@xyflow/react 12.11.2`와 `@dagrejs/dagre 3.0.0`을 exact pin으로 추가했다. 두 package는 MIT이며 승인된 관계 graph 선택을 따르고, native SVG 대안보다 keyboard selection·pan/zoom과 deterministic layout을 재사용할 수 있어 채택했다.
- React Flow/Dagre는 dynamic import의 별도 chunk로 분리했다. `VITE_INCIDENT_GRAPH_ENABLED=false` 또는 `0`, partial, truncated, empty, request error에서는 graph chunk를 주 UI로 사용하지 않고 기존 Timeline, 연결 Alert와 observed evidence table을 기본 fallback으로 유지한다.
- graph node/edge, Inspector, Timeline selection과 evidence row를 동일 selection context로 동기화했다. 모든 edge는 `OBSERVED` label과 source Incident/Alert/Event link를 가지며 추론 인과관계로 표현하지 않는다.
- Process node 또는 그 edge를 선택한 경우에만 Incident endpoint와 investigation timeRange로 기존 Process Tree API를 호출한다. Incident lifecycle control은 추가하지 않았다.
- partial/truncated warning, `EVENT_NOT_FOUND`/`ARCHIVE_NOT_READY` message와 Archive operations link를 표시한다. feature flag 기본값은 true이며 production Vite build 시 환경값으로 끌 수 있다.

실행 명령·결과:
- `npm.cmd install --save-exact @xyflow/react@12.11.2 @dagrejs/dagre@3.0.0`: PASS, 327 packages audited, 0 vulnerabilities.
- `npm.cmd test -- --run tests/incident-investigation.test.tsx tests/data-interaction.test.tsx`: PASS, 2 files, 17 tests.
- `npm.cmd test -- --run`: PASS, 20 files, 90 tests, 15.24s. 샌드박스의 상위 디렉터리 read 제한 때문에 승인된 외부 실행으로 검증했다.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run build`: PASS, 1878 modules, 6.18s. initial JS 547.05 kB/162.20 kB gzip, CSS 83.05 kB/14.15 kB gzip, lazy IncidentGraph JS 220.92 kB/72.89 kB gzip, lazy graph CSS 15.87 kB/2.67 kB gzip이다.
- `npm.cmd audit --omit=dev`: PASS, production vulnerabilities 0.
- `docker compose config --quiet`: PASS.
- `docker compose build frontend`; `docker compose up -d --no-deps frontend`: PASS. 최종 Frontend container가 healthy다.
- `git diff --check`: PASS. 기존 line-ending 변환 warning만 있고 whitespace error는 없다.

자동화·Browser 증거:
- feature helper test가 flag true/false/0, OPEN queue default, filter/deep-link 보존, partial/truncated와 archive fallback, edge→Timeline context, Process PID와 250개 node Dagre position 생성을 검증했다.
- Playwright headless Chromium과 실제 ADMIN session을 1440x1000 monitor viewport에서 실행했다. 실제 Incident 1은 8 node, 8 edge이며 Investigation API 요청 2회와 graph edge별 evidence button 8개가 정확히 대응했다.
- 첫 Evidence button을 focus 후 Enter로 선택해 `aria-pressed=true`와 Inspector 동기화를 확인했다. Timeline Evidence도 keyboard로 선택했고 Process node 선택은 실제 Process Tree request를 발생시켰다.
- workbench는 전체 1328px, queue x=88/width=340/right=428, detail x=440/width=976이며 root overflow 0이다. 최종 Investigation graph는 전체 monitor content 폭을 사용한다.
- HTTP 4xx/5xx 0, console error 0, page error 0이다. capture는 `wp06-incident-investigation-1440.png`다.

성능·접근성:
- graph가 없는 route와 flag/fallback 경로는 72.89 kB gzip graph JS를 초기 실행에 포함하지 않는다. node는 keyboard focusable하며 graph를 사용하지 않아도 모든 edge의 핵심 정보와 원본 link를 semantic table에서 사용할 수 있다.
- 250-node cap은 deterministic layout test로 node 손실 없이 검증했다. 실제 browser fixture는 8 node이므로 250-node browser pan/zoom 밀도는 남은 운영 위험으로 기록한다.

남은 위험:
- initial production JS 547.05 kB가 기존 500 kB warning을 유지한다. graph는 분리됐지만 App route가 모두 eager import이므로 WP-09에서 route-level code splitting을 적용한다.
- 250-node layout 계산과 누락 없음은 자동화했지만 실제 고밀도 graph의 analyst 가독성과 저사양 monitor interaction은 production-like fixture로 추가 관찰이 필요하다.
- production에서 graph를 끄려면 Vite build 전에 `VITE_INCIDENT_GRAPH_ENABLED=false`를 주입해야 한다. runtime-only 환경 변경으로 이미 생성된 정적 bundle을 바꾸지는 못한다.

다음 Package: WP-07 Endpoints와 Events.
```

### WP-07. Endpoints와 Events

범위:

- Endpoint inventory를 유지하고 paged server search 기반 `EndpointSwitcher`를 제공한다.
- risk, collection health, related Alert·Incident, recent Event, profile, certificate와 Process Tree를 위계화한다.
- Event 목록은 공통 식별 field와 Event Type별 field를 조합한다.
- Event 상세는 유형별 group, Process Tree, 접힌 Raw Payload, copy와 검색을 제공한다.

#### WP-07 완료 증거

```text
Package: WP-07 Endpoints와 Events
상태: 완료
담당: Codex
완료일: 2026-07-15

변경 파일:
- frontend/src/components/EndpointSwitcher.tsx
- frontend/src/components/RawPayloadViewer.tsx
- frontend/src/features/eventPresentation.ts
- frontend/src/i18n/translations.ts
- frontend/src/main.tsx
- frontend/src/pages/EndpointDetailPage.tsx
- frontend/src/pages/EventDetailPage.tsx
- frontend/src/pages/EventsPage.tsx
- frontend/src/styles/pages/endpoints-events.css
- frontend/tests/endpoint-event-workbench.test.tsx
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- BWP-02의 paged Endpoint `q` search 계약을 변경 없이 사용한다. Backend/OpenAPI/generated schema 변경과 DB migration은 없다.
- Endpoint Detail header에 입력 전 request를 보내지 않는 server-paged `EndpointSwitcher` combobox를 추가했다. hostname, agent ID와 exact Endpoint ID를 `q`, page 1, size 20으로 검색하며 hostname을 primary, ID·agent ID·status·risk를 secondary 정보로 표시한다.
- ArrowDown/ArrowUp, Enter, Escape와 pointer 선택을 지원한다. Endpoint 전환 URL은 기존 list filter, sort, page와 `selected` context를 보존하며 전체 fleet prefetch를 하지 않는다.
- Endpoint Detail을 Risk와 related evidence → sensor health → profile → certificate 순으로 재배치했다. API에 related row가 없으므로 count를 재계산하지 않고 Alert/Incident/Event 소유 목록으로 endpoint filter link를 제공한다.
- Endpoint-level Process Tree는 time range가 없으면 생성하지 않는다. Event 목록으로 이동해 Event 시각으로 기존 Process Tree window를 확정하도록 안내한다.
- certificate는 Backend의 `isRevoked`/`isExpired`만 사용해 이상 항목을 먼저 정렬하고 red rail, status와 검토 문구를 함께 표시한다. 만료 임박을 client에서 추정하지 않는다.
- Event 목록의 공통 식별 column은 유지하고 단일 Process/Network column 대신 Event Type별 요약을 표시한다. 상세는 Identity/Time, Process/User, File, Network, DNS, HTTP/TLS 중 실제 type과 non-null field가 있는 group만 표시한다.
- Process Tree는 Raw Payload보다 먼저 유지한다. Raw Payload는 기본 접힘 details로 바꾸고 내부 검색·match count·highlight와 정확한 JSON clipboard copy를 제공하며 print에서는 제외한다.

실행 명령·결과:
- `npm.cmd test -- --run tests/endpoint-event-workbench.test.tsx tests/data-interaction.test.tsx tests/process-tree.test.ts`: PASS, 3 files, 19 tests.
- `npm.cmd test -- --run`: PASS, 21 files, 94 tests, 14.81s.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run build`: PASS, 1882 modules, 7.28s. initial JS 558.69 kB/165.44 kB gzip, CSS 87.93 kB/14.80 kB gzip, lazy IncidentGraph JS 220.92 kB/72.89 kB gzip이다. 기존 500 kB warning만 유지됐다.
- `docker compose build frontend`; `docker compose up -d --no-deps frontend`: PASS. 최종 Frontend container가 healthy다.
- `git diff --check`: PASS. 기존 line-ending 변환 warning만 있고 whitespace error는 없다.

자동화·Browser 증거:
- switcher test는 입력 전 fetch 0회, `q=WIN-02&page=1&size=20`, keyboard 선택과 `/endpoints/1002?status=OFFLINE&page=3&selected=1002` 이동을 검증했다.
- Event Type fixture는 Process, File, Network, DNS와 L7의 group 및 list summary를 검증했다. expired certificate가 `anomalous` class, EXPIRED status와 명시적 review 문구를 갖는지 검증했다.
- Raw Payload test는 기본 접힘, 내부 검색 2건과 highlight 2개, exact formatted JSON clipboard copy와 Copied feedback을 검증했다.
- live API에서 Endpoint 3개를 확인했고 ID `1`, hostname `SOC-WIN-01` exact search가 각각 1건을 반환했다.
- Playwright headless Chromium과 실제 ADMIN session을 1440x1000에서 실행했다. EndpointSwitcher는 입력 전 search request 0회, exact ID 입력 뒤 `q=1&page=1&size=20` request 1회, ArrowDown selection과 Escape close를 통과했다.
- 실제 Event detail은 Identity와 Process group, Process Tree, 접힌 Raw Payload 순서를 유지했다. Raw Payload를 열어 `{` 검색 2건과 highlight, clipboard copy, `/events?page=1&selected=...` 복귀 context를 확인했다.
- Endpoint/Event root overflow는 모두 0이고 HTTP 4xx/5xx 0, console error 0, page error 0이다. capture는 `wp07-endpoint-detail-1440.png`, `wp07-event-detail-1440.png`다.

남은 위험:
- Endpoint Detail DTO는 related Alert/Incident/Event row를 포함하지 않는다. 현재는 Backend count와 각 소유 목록 link를 사용하며 inline recent table이 필요하면 별도 read-model 계약이 필요하다.
- switcher는 입력마다 취소 가능한 server query를 교체한다. 현재 exact/prefix index와 page size 20으로 검증했지만 고지연 환경에서는 debounce를 추가 검토할 수 있다.
- clipboard API가 차단된 browser에서는 copy 성공 feedback이 표시되지 않는다. 보안 context 정책과 실패 안내를 WP-09 접근성 점검에서 재확인한다.
- production initial JS 558.69 kB의 기존 warning과 print 시 사용자 식별 field 제외 범위는 WP-09 route splitting·print gate에서 정리한다.

다음 Package: WP-08 Intelligence, Operations와 Archives.
```

### WP-08. Intelligence, Operations와 Archives

범위:

- MITRE Matrix와 table fallback, Rules/Signal Top-N tabs를 구현한다.
- Egress Topology는 graph, Selected context와 evidence table을 연결한다.
- Operations pipeline은 현재 snapshot으로 표시한다.
- Archives에 lifecycle board, table과 restore action을 제공한다.
- Service·Worker 장기 이력과 `bytesOut`은 표시하지 않는다.

#### WP-08 완료 증거

```text
Package: WP-08 Intelligence, Operations와 Archives
상태: 완료
담당: Codex
완료일: 2026-07-16

변경 파일:
- .env.example
- .env.production.example
- frontend/src/components/TopologyGraph.tsx
- frontend/src/features/intelligenceOperations.ts
- frontend/src/i18n/translations.ts
- frontend/src/main.tsx
- frontend/src/pages/ArchivesPage.tsx
- frontend/src/pages/IntelligencePage.tsx
- frontend/src/pages/OperationsPage.tsx
- frontend/src/styles/pages/intelligence-operations.css
- frontend/src/vite-env.d.ts
- frontend/tests/intelligence-operations-archives.test.tsx
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

계약·구현:
- Intelligence는 summary와 topology를 독립적으로 렌더링해 한 source가 실패해도 다른 source와 partial 안내를 유지한다.
- MITRE tactic·technique matrix와 semantic table fallback, 선택 Inspector, Rules/Signals Top-N tabs를 같은 Alert snapshot에 연결했다.
- Egress Topology는 build-time `VITE_TOPOLOGY_GRAPH_ENABLED` flag, lazy graph, legend, 검색·Top-N, graph/Inspector/evidence table 선택 동기화를 제공한다. 표시 field는 protocol, Event/Alert count, last observed뿐이며 `bytesOut`은 추정하지 않는다.
- Operations pipeline은 실제 service·worker·failure·storage 응답에서 Collection/Detection/Storage 현재 상태를 구성하고 문제 stage를 먼저 배치한다. 애니메이션이나 저장된 historical flow로 표현하지 않는다.
- Archives는 HOT → ARCHIVED → RESTORE_REQUESTED → RESTORED → RESTORE_FAILED → EXPIRED 순서의 lifecycle board를 zero까지 명시한다. ADMIN/ANALYST만 restore action을 보고 VIEWER는 같은 상태를 읽기 전용으로 본다.
- restore 요청 성공 뒤 Backend 완료 전까지 `RESTORE_REQUESTED`로 남는 계약을 성공 안내와 test에 고정했다. Backend/OpenAPI/generated schema와 DB migration 변경은 없다.

실행 명령·결과:
- `npm.cmd test -- --run tests/intelligence-operations-archives.test.tsx`: PASS, 1 file, 6 tests.
- `npm.cmd test -- --run`: PASS, 22 files, 100 tests.
- `npm.cmd run typecheck`: PASS.
- `npm.cmd run lint`: PASS.
- `npm.cmd run build`: PASS, 1885 modules, 4.17s. initial JS 578.96 kB/172.38 kB gzip, CSS 95.33 kB/15.78 kB gzip, lazy TopologyGraph 1.78 kB/0.95 kB gzip, shared graph chunk 219.29 kB/72.26 kB gzip이다. 기존 500 kB warning만 유지됐다.
- `docker compose config --quiet`: PASS.
- `docker compose build frontend`; `docker compose up -d --no-deps frontend`: PASS. 실제 QA에서 발견한 React Flow 기본 흰 node 대비를 높은 specificity의 dark surface selector로 수정한 최종 image다.

자동화·Browser 증거:
- feature test가 graph flag on/off/`0`, deterministic Top-N 정렬, MITRE 선택·tabs·table fallback, edge/table Inspector sync와 `bytesOut` 부재를 검증했다.
- pipeline test가 현재 failure를 먼저 표시하고 historical moving flow를 만들지 않는지 검증했다. source partial과 lifecycle zero/전체 상태, ADMIN/ANALYST/VIEWER 권한도 함께 통과했다.
- Playwright headed Chromium과 실제 ADMIN/VIEWER session을 1440x1000에서 실행했다. 사용자 지시에 따라 mobile viewport는 실행하지 않았다.
- Intelligence에서 MITRE 선택, Signals tab, graph/table edge 선택과 Inspector를 확인했다. 초기 실제 캡처에서 graph node 대비 결함을 발견해 수정했고 재캡처에서 Endpoint/Target 라벨 가독성을 확인했다.
- Operations는 Detection degraded를 먼저 두고 Collection/Storage healthy를 이어서 표시했다. Archives는 QA seed에서 ARCHIVED 1, RESTORED 1과 나머지 zero를 lifecycle 순서로 표시했다.
- ADMIN에는 `Start archive restore`, VIEWER에는 `VIEWER access is read-only` 안내만 노출됐다. 실제 restore mutation은 실행하지 않았고 lifecycle 전이는 component test로 검증했다.
- 세 화면과 두 role session 모두 root horizontal overflow 0, console error 0이다. 주요 capture는 `output/playwright/wp08/.playwright-cli/element-2026-07-15T23-37-46-855Z.png`, `element-2026-07-15T23-38-41-637Z.png`, `element-2026-07-15T23-41-14-577Z.png`, `element-2026-07-15T23-43-01-834Z.png`다.

남은 위험:
- 같은 Endpoint/Target의 protocol별 parallel edge label은 graph에서 겹칠 수 있으므로 semantic evidence table을 전체 관계의 기준 fallback으로 유지한다.
- graph flag는 Vite build-time flag다. 배포 뒤 runtime-only 환경 변경으로 이미 생성된 정적 bundle을 바꾸지는 못한다.
- initial production JS의 기존 500 kB warning과 eager route import는 WP-09 route-level code splitting release gate에서 정리한다.

다음 Package: WP-09 QA와 Release.
```

### WP-09. QA와 Release

- EN/KO layout
- 360, 768, 1024, 1440px viewport
- keyboard, screen reader label, 200% zoom
- reduced motion, polling과 layout save 안정성
- Loading, Empty, Error, Stale, Partial failure
- 주요 task scenario와 visual regression

#### WP-09 완료 증거

```text
Package: WP-09 QA와 Release
상태: 완료
담당: Codex
완료일: 2026-07-16

변경 파일:
- frontend/src/App.tsx
- frontend/src/components/AppShell.tsx
- frontend/src/styles/patterns.css
- frontend/src/styles/shell.css
- frontend/tests/release-gates.test.ts
- docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md

통합·최적화:
- Login과 인증 AppShell은 critical path에 유지하고 Overview, 목록·상세, Intelligence, Operations와 Archives 12개 인증 page를 route-level `lazy()` chunk로 분리했다.
- AppShell 내부 Outlet에 접근 가능한 `role=status` Suspense boundary를 두어 page chunk가 로드되는 동안 navigation과 session context가 사라지지 않게 했다. spinner는 `prefers-reduced-motion: reduce`에서 정지한다.
- print에서 top bar의 사용자 context와 Raw Payload를 숨기고, 닫힌 chart/table `<details>` fallback의 실제 표 content를 강제로 노출한다.
- `@xyflow/react` 12.11.2와 `@dagrejs/dagre` 3.0.0은 둘 다 MIT다. DOM-only 대안보다 pan/zoom, keyboard focus와 deterministic Dagre layout을 재사용하면서 graph 본체와 route를 별도 chunk로 분리했다. production audit는 취약점 0이다.

MWO-00 baseline 비교:
- Backend: 190 passed/4 skipped → 209 passed/4 skipped.
- Frontend: 13 files/51 tests → 23 files/104 tests.
- initial production JS: 507.06 kB/151.07 kB gzip → 360.43 kB/113.11 kB gzip. raw -146.63 kB, gzip -37.96 kB이며 500 kB warning이 제거됐다.
- production CSS: 47.22 kB/8.45 kB gzip → 93.73 kB/15.55 kB gzip. semantic foundation과 전체 page layer를 포함한 최종 값이다.
- Overview `Done` 조기 종료와 grid 좌우 12px 이탈은 WP-01에서 save drain 완료 후 종료와 edge delta 0px로 수정됐다.
- 360px document width 768px baseline 결함은 WP-02/WP-03에서 overflow 0으로 수정·검증됐다. 이후 사용자의 속도 지시에 따라 WP-05~WP-09 최종 browser 반복은 1440px monitor만 실행했고 mobile을 재실행하지 않았다.

최종 local read API latency median, 각 10회:
- Dashboard summary 92.2ms → 49.3ms.
- Endpoint summary 33.1ms → 21.5ms.
- Ingest summary 43.7ms → 24.4ms.
- Endpoints 39.5ms → 20.0ms.
- Alerts 37.1ms → 19.4ms.
- Incidents 36.6ms → 20.9ms.
- Egress topology 55.1ms → 36.6ms.
- Operations health 255.5ms → 250.4ms.
- Overview layout 49.5ms → 21.3ms.
- 최종 측정은 같은 local QA seed와 ADMIN session에서 수행했고 모든 유효 요청 status는 200이다. 이는 회귀 비교이며 운영 SLA가 아니다.

실행 명령·결과:
- `$env:UV_CACHE_DIR='.uv-cache'; uv run ruff check backend tests tools`: PASS.
- OpenSSL PATH와 isolated basetemp를 사용한 `uv run pytest -p no:cacheprovider --basetemp .tmp\wp09-pytest`: PASS, 209 passed, 4 skipped, 2 warnings, 7.89s.
- `npm.cmd run openapi:check`: PASS. API 문서·Pydantic·manifest·OpenAPI artifact·generated TypeScript schema drift가 없다.
- `npm.cmd run typecheck`; `npm.cmd run lint`: PASS.
- `npm.cmd test -- --run`: PASS, 23 files, 104 tests, 9.38s.
- `npm.cmd run build`: PASS, 1885 modules, 2.62s. initial JS 360.43 kB/113.11 kB gzip이며 route page는 4.42~97.50 kB, graph shared chunk는 219.32 kB/72.27 kB gzip이다.
- `npm.cmd audit --omit=dev`: PASS, 0 vulnerabilities.
- `docker compose config --quiet`; final `docker compose build frontend`; `docker compose up -d --no-deps frontend`: PASS. Frontend와 전체 dependency stack이 running이고 healthcheck 대상은 healthy다.
- `git diff --check`: PASS. 기존 line-ending 변환 warning만 있고 whitespace error는 없다.

Browser·접근성·print 증거:
- Playwright headed Chromium의 실제 ADMIN session을 1440x1000에서 실행했다. `/`, `/alerts`, `/incidents`, `/endpoints`, `/events`, `/intelligence`, `/operations` 7개 route가 각 heading과 lazy chunk를 정상 표시했고 HTTP 4xx/5xx 0, root overflow 0이었다.
- 별도 깨끗한 final session에서 Login → Overview, overflow 0, console error/warning 0을 재확인했다.
- Operations를 KO로 전환해 layout overflow 0을 확인하고 Backend locale을 EN으로 복원했다. screen reader snapshot에서 navigation, heading, label, table/region name을 확인했다.
- print media에서 `.top-bar=none`, `.raw-payload-panel=none`, 닫힌 `.chart-frame-fallback` content=`block`을 실제 Overview/Event Detail에서 확인했다.
- graph flag on browser와 graph flag off component test, partial·truncated·archive·zero·empty·permission 상태는 WP-03~08 package gate 결과를 최종 release 근거로 재사용했다.

Feature flag·배포 순서:
- `VITE_INCIDENT_GRAPH_ENABLED=true`, `VITE_TOPOLOGY_GRAPH_ENABLED=true`가 example과 production example의 현재 build-time 기본값이다. WP-06/WP-08 gate를 통과했으므로 최종 release 상태는 enabled다.
- 1단계: DB backup과 현재 migration 상태를 확인하고 app-init/prod-init으로 additive `0005_query_search_sort_indexes.up.sql`을 멱등 적용한다.
- 2단계: v1/v2 layout과 기존 query를 함께 수용하는 Backend를 먼저 배포하고 health, OpenAPI와 read smoke를 확인한다.
- 3단계: 두 graph flag 값을 확정해 Frontend 정적 bundle을 build·배포하고 Login, AppShell, Overview를 먼저 smoke한 뒤 Incident/Intelligence graph를 확인한다.
- 4단계: Backend·worker·storage health와 browser error를 확인한 뒤 release를 완료한다.

Rollback:
- graph 결함만 있으면 해당 `VITE_*_GRAPH_ENABLED=false`로 Frontend를 재빌드·재배포한다. Timeline/evidence/table fallback은 유지되며 Backend나 DB rollback은 필요 없다.
- Frontend release 전체 rollback은 직전 Frontend image를 먼저 재배포한다. 새 Backend는 이전 Frontend 계약과 호환되므로 즉시 Backend를 내리지 않는다.
- `0005`는 search/sort index만 추가한다. 반드시 필요할 때만 `0005_query_search_sort_indexes.down.sql`로 세 index를 역순 제거하며 기능 정합성은 유지되고 query 성능만 baseline으로 돌아간다. BWP-02 integration에서 down/up 멱등성과 rollback을 검증했다.
- Backend rollback이 필요한 경우 Frontend를 먼저 이전 artifact 또는 graph-off build로 고정한 뒤 Backend를 되돌린다. 사용자별 layout row는 v1/v2 원본을 보존하므로 삭제하지 않는다.

남은 운영 위험:
- Operations health median은 250.4ms로 baseline 255.5ms와 유사하며 다른 read API보다 느리다. 현재 regression은 아니지만 운영 관찰 대상이다.
- protocol별 parallel topology edge label은 겹칠 수 있어 evidence table을 canonical fallback으로 유지한다.
- graph flag는 build-time이므로 runtime environment만 바꿔 이미 생성된 bundle을 전환할 수 없다.

Release 결정: 사용자 지시로 최종 viewport 반복을 1440px monitor로 제한한 조건에서 모든 Release Gate 통과. MWO-FB-001 완료.
```

#### WP-09 후속 레이아웃 교정 (2026-07-16)

상태: 완료

사용자 실화면 검수에서 확인된 가로 폭 불일치, 행의 빈 열, FilterBar와 요약 카드 내부 정렬을 후속 교정했다. Backend 계약과 데이터 의미는 변경하지 않았다.

원인과 변경:
- 1440px 창에서 확장 navigation을 사용하면 dashboard container는 1176px인데 desktop breakpoint가 1200px여서 Overview가 6열 tablet layout으로 잘못 전환됐다. desktop 기준을 1080px로 조정했다.
- tablet layout이 desktop widget 폭을 개별 반올림해 같은 행의 합이 6열보다 작아졌다. desktop 행 단위로 다시 묶고 각 행의 합이 항상 6열이 되도록 분배하며, KPI 4개 행은 2개씩 같은 폭으로 배치한다.
- 공통 FilterBar가 natural-width flex field를 사용해 입력 영역과 action 사이에 불규칙한 빈 공간이 남았다. auto-fit grid와 full-width control로 변경했다.
- Operations와 Intelligence의 KPI 4개가 공통 6열 grid의 4칸만 사용했다. 두 summary row를 명시적 4등분 grid로 변경했다.
- QA 중 저장됐던 ADMIN Overview layout revision 12가 widget 사이에 빈 열을 포함했다. live `DELETE /api/v1/dashboard/layouts/overview` reset을 실행해 revision 0, `isDefault=true`의 승인된 12열 기본 배치로 복구했다.

검증:
- `npm.cmd test -- --run tests/dashboard-layout.test.ts`: PASS, 11 tests.
- `npm.cmd run lint`; `npm.cmd run typecheck`: PASS.
- `npm.cmd test`: PASS, 23 files, 105 tests.
- `npm.cmd run build`: PASS, 1885 modules, initial JS 360.43 kB/113.12 kB gzip.
- `docker compose build frontend`; `docker compose up -d frontend`; `docker compose ps frontend`: PASS, Frontend healthy.
- Playwright Chromium ADMIN session, expanded navigation, 1440x1000: Overview grid 1176px, KPI 285px × 4; Alerts·Incidents·Endpoints·Events filter field 296px × 3; Intelligence field 514px × 2와 KPI 285px × 4; Operations field 252px × 4와 KPI 285px × 4; Archives field 339px × 3. 8개 route 모두 root horizontal overflow 0, console error 0.
- 캡처: `output/playwright/layout-fix/{overview,alerts,incidents,endpoints,events,intelligence,operations,archives}-1440.png`.

남은 위험:
- Alerts, Incidents, Endpoints, Archives처럼 현재 결과가 적은 화면의 세로 여백은 데이터 개수에 따른 정상 상태다. 가짜 row나 장식 panel로 채우지 않으며, filter와 결과 panel의 가로 정렬·폭은 전체 content edge에 맞췄다.

## 8. 기본 검증 명령

Repository root에서 Backend 기본 검증을 실행한다.

```powershell
uv run ruff check backend tests tools
uv run pytest
docker compose config
```

`frontend/`에서 Frontend 기본 검증을 실행한다.

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test
npm.cmd run build
```

API 또는 generated schema가 바뀌는 BWP에서는 다음 전체 순서를 실행한다.

```powershell
npm.cmd run openapi:export
npm.cmd run openapi:generate
npm.cmd run openapi:check
```

## 9. 완료 증거 형식

각 Work Package 아래 또는 진행 기록에 다음 형식으로 남긴다.

```text
상태: 완료
담당:
완료일:
변경 파일:
- path

검증:
- command: PASS/FAIL
- viewport 또는 browser scenario: PASS/FAIL

남은 위험:
- 없음 또는 후속 ID
```

## 10. Coding Agent 작업지시 템플릿

```text
전체 범위는 docs/frontend/FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md에서 승인되었다.
현재 작업 대상은 docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md의 [PACKAGE-ID] 하나다.

먼저 다음 문서를 읽어라.
1. docs/frontend/DESIGN.md
2. docs/frontend/FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md
3. docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md
4. docs/frontend/FRONTEND_SPEC.md
5. docs/contracts/API_SPEC.md와 관련 대상 코드

범위:
- [이번 작업에서 구현할 항목]

제외:
- 다른 Work Package
- 현재 Package 밖의 변경
- Master Work Order 비범위
- 계약 선행 없이 추가하는 Route, API, DTO 또는 dependency
- commit, push, PR

구현 전:
1. 현재 동작과 원인을 코드 근거로 보고한다.
2. 보존, 변경, 제외할 범위를 적는다.
3. Work Package를 진행 중으로 변경한다.

구현 후:
1. DESIGN.md 14.7 Hard Pre-flight를 수행한다.
2. Plan의 검증 명령과 필요한 browser scenario를 실행한다.
3. 변경 파일, 명령 결과, 남은 위험을 Work Package에 기록한다.
4. 조건을 모두 충족했을 때만 완료로 변경한다.
```

## 11. Master Work Order — Ready

- Work order: `MWO-FB-001`
- 대상: `MWO-00`, `BWP-01~04`, `WP-01~09`
- 상태: Ready
- 결정 blocker: 없음
- 실행 문서: [Frontend·Backend UI 개편 Master Work Order](./FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md)
- 첫 Package: `MWO-00 Baseline과 회귀 기준`
- 진행 규칙: 전체 범위는 승인됐지만 한 번에 한 Package만 `진행 중`으로 두고 완료 후 다음으로 이동

Coding Agent에는 Master Work Order 11절의 시작 지시문을 그대로 전달한다.

## 12. 진행 기록

| 날짜 | Work Package | 상태 변화 | 요약 | 증거 |
| --- | --- | --- | --- | --- |
| 2026-07-15 | Plan | 생성 | 장기 `DESIGN.md`와 단발성 실행 계획 분리 | 문서 구조 검토 |
| 2026-07-15 | Decisions | 전체 확정 | Workshop 권장안, Backend 포함, blocker B-001~007 해제 | `DESIGN.md` Approved v3.0, Workshop 확정 열 |
| 2026-07-15 | MWO-FB-001 | Ready | Frontend·Backend 통합 실행 순서와 Release Gate 작성 | `FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md` |
| 2026-07-15 | MWO-00 | 진행 중 | Route, query, auth, polling, permission, API, visual, 성능과 test baseline audit 착수 | 담당: Codex; 실제 코드와 실행 결과 수집 중 |
| 2026-07-15 | MWO-00 | 완료 | 계약 audit, 전체 test baseline, API latency, EN/KO·viewport capture와 layout 결함 재현 완료 | 190 backend tests, 51 frontend tests, OpenAPI drift 0, 54 browser captures |
| 2026-07-15 | BWP-01 | 진행 중 | Endpoint search, Alert sort, Incident investigation과 layout v2 contract-first 동기화 착수 | 문서 → Pydantic/manifest → OpenAPI/generated schema 순서 |
| 2026-07-15 | BWP-01 | 완료 | Endpoint search, Alert sort, Investigation graph와 layout v2 계약을 문서/Pydantic/OpenAPI/generated client에 동기화 | 195 backend tests, 51 frontend tests, OpenAPI drift 0 |
| 2026-07-15 | BWP-02 | 진행 중 | Endpoint paged search와 Alert server sorting 구현 착수 | repository query plan과 pagination 경계 검증 예정 |
| 2026-07-15 | BWP-02 | 완료 | Endpoint exact·prefix search, wildcard literal, stable paging과 Alert priority/field sort 구현 | 202 backend tests, PostgreSQL integration, live API·query plan, 51 frontend tests |
| 2026-07-15 | BWP-03 | 진행 중 | Incident·Alert·Event observed evidence 기반 Investigation read model 구현 착수 | 404/partial/archive/node cap과 deterministic graph 검증 예정 |
| 2026-07-15 | BWP-03 | 완료 | Incident·Alert FK와 HOT/RESTORED Event field로 deterministic OBSERVED graph 구현 | 206 backend tests, full-stack integration, live 8-node/8-edge graph |
| 2026-07-15 | BWP-04 | 진행 중 | Dashboard layout v1 read·v2 save·reload 호환성 구현 착수 | conflict/reset/user isolation과 migration fixture 검증 예정 |
| 2026-07-15 | BWP-04 | 완료 | v1/v2 조회·저장, revision conflict, reset·user isolation과 정적 migration fixture 구현 | 209 backend tests, 실제 저장소·live API, 52 frontend tests, OpenAPI drift 0 |
| 2026-07-15 | WP-01 | 진행 중 | Overview editor save lifecycle과 toolbar/grid inset 결함 진단 착수 | debounce·in-flight·revision·refresh·grid remount 재현 예정 |
| 2026-07-15 | WP-01 | 완료 | save drain과 Done 성공 후 종료, failure/conflict 복구, beforeunload와 DashboardFrame edge 정렬 구현 | 56 frontend tests, live delayed PUT·conflict/reload, 1024/1440 edge delta 0px |
| 2026-07-15 | WP-02 | 진행 중 | semantic foundation, Login, grouped AppShell과 360px responsive 기반 audit 착수 | token·primitive·drawer·breadcrumb·KO/EN·zoom 검증 예정 |
| 2026-07-15 | WP-02 | 완료 | semantic token·primitive·CSS 계층, grouped AppShell, accessible modal Drawer와 360px Login/KO 기반 구현 | 61 frontend tests, 4 viewport overflow 0, Drawer focus trap, OpenAPI drift 0 |
| 2026-07-15 | WP-03 | 진행 중 | 공통 Data Interaction audit 착수 | PageHeader·FilterBar·DataTable·URL state와 상태 표현 inventory 예정 |
| 2026-07-15 | WP-03 | 완료 | 5개 목록의 FilterBar·URL state·semantic DataTable·Pagination과 전체 query 상태 계약 통합 | 74 frontend tests, 10 viewport overflow 0, 4 Drawer focus/Escape, OpenAPI drift 0 |
| 2026-07-15 | WP-04 | 진행 중 | Overview 10 block, compact toolbar와 layout v2 1회 migration audit 착수 | BWP-04 compatibility와 기존 23-widget registry/layout v1 consumer inventory 예정 |
| 2026-07-15 | WP-04 | 완료 | 승인된 10 block, compact toolbar, version별 Backend registry와 v1→v2 1회 migration 구현 | 209 backend tests, 79 frontend tests, live PUT 1회, HTTP/console/page error 0 |
| 2026-07-15 | WP-05 | 진행 중 | Alerts queue/detail, priority sort와 read-only Response Guidance audit 착수 | 저장과 저장 후 다음 이동 분리, desktop 계약과 guidance field 검증 예정 |
| 2026-07-15 | WP-05 | 완료 | desktop queue/detail, priority sort 설명, 분리된 저장 흐름과 read-only Response Guidance 구현 | 85 frontend tests, ADMIN/VIEWER 1440px browser QA, HTTP/console/page error 0 |
| 2026-07-15 | WP-06 | 진행 중 | Incident queue, Investigation graph·timeline·evidence 동기화 audit 착수 | BWP-03 observed graph와 desktop monitor fallback 계약 검증 예정 |
| 2026-07-15 | WP-06 | 완료 | OPEN queue, observed graph·Inspector·Timeline·Evidence·Process Tree와 flag/partial fallback 구현 | 90 frontend tests, live 8-node/8-edge keyboard QA, production audit 0 |
| 2026-07-15 | WP-07 | 진행 중 | Endpoint inventory·switcher와 Event 유형별 detail audit 착수 | server pagination, 목록 복귀 context, certificate와 Process Tree 계약 검증 예정 |
| 2026-07-15 | WP-07 | 완료 | paged EndpointSwitcher, Risk/Evidence hierarchy, certificate anomaly와 Event 유형 group·Raw Payload tools 구현 | 94 frontend tests, exact search·clipboard·return context 1440px QA, error 0 |
| 2026-07-15 | WP-08 | 진행 중 | Intelligence, Operations, Archives information hierarchy와 fallback audit 착수 | MITRE/topology graph, snapshot pipeline, restore lifecycle·role permission 검증 예정 |
| 2026-07-16 | WP-08 | 완료 | MITRE·Top-N, Egress graph/Inspector/table, current pipeline snapshot과 Archive lifecycle·role UI 구현 | 100 frontend tests, ADMIN/VIEWER 1440px QA, overflow/console error 0 |
| 2026-07-16 | WP-09 | 진행 중 | 전체 route code splitting, release gate, baseline/final 회귀와 문서 동기화 착수 | Backend/OpenAPI/Frontend/Compose와 1440px 주요 task 최종 검증 예정 |
| 2026-07-16 | WP-09 | 완료 | 인증 page route splitting, print fallback, MWO baseline 비교와 전체 release/rollback gate 완료 | 209 backend tests, 104 frontend tests, OpenAPI drift/audit/browser error 0 |
| 2026-07-16 | MWO-FB-001 | 완료 | Frontend·Backend UI 개편 전체 Work Order 완료 | 모든 Package 완료, final initial JS 360.43 kB, 1440px release QA 통과 |
| 2026-07-16 | WP-09 후속 교정 | 완료 | 1440px breakpoint, tablet 행 채움, 공통 FilterBar와 4개 KPI summary 폭을 교정하고 ADMIN Overview 기본 layout을 복구 | 105 frontend tests, build PASS, 8 route overflow/console error 0, `output/playwright/layout-fix` |
| 2026-07-16 | WP-09 후속 Endpoint scope 교정 | 완료 | Overview Endpoint 범위를 전체/개별 선택으로 확장하고 Dashboard layout 안내 문구를 제거 | 211 backend tests, 107 frontend tests, OpenAPI drift 0, build PASS, 1440px overflow/console error 0, `output/playwright/overview-endpoint-scope` |
