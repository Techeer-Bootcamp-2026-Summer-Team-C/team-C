# Frontend·Backend UI 개편 Master Work Order

- 상태: Ready
- 승인일: 2026-07-15
- 승인 근거: 팀 Workshop 권장안 전체 확정, Backend 포함
- 적용 범위: `frontend/`, `backend/`, `docs/frontend/`, `docs/contracts/`, `docs/architecture/`, `openapi/`, `migrations/`, 관련 `tests/`
- 완료 기준: 아래 Work Package와 통합 Release Gate를 모두 통과

## 1. 작업 목표

현재 EDR 관제 콘솔을 `상태 → 원인 → 우선 대상 → 근거 → 다음 행동` 순으로 읽히는 dark investigation console로 개편한다. Login부터 AppShell, Overview, 목록·상세, Investigation, Intelligence, Operations와 Archives까지 하나의 design system과 interaction contract로 연결한다.

Backend는 화면이 필요로 하는 검색·정렬·investigation read model과 Overview layout migration을 제공한다. 이미 존재하는 Dashboard 집계, Process Tree, Attack Timeline, Egress Topology와 Response Guidance 계약은 복제하지 않고 재사용한다.

## 2. Source of Truth

충돌 시 다음 순서를 적용한다.

1. 데이터 의미·REST 계약: `docs/contracts/API_SPEC.md`, `docs/contracts/RISK_POLICY.md`
2. 장기 디자인 기준: `docs/frontend/DESIGN.md` Approved v3.0
3. 전체 실행 지시: 이 문서
4. Work Package 상태와 증거: `docs/frontend/FRONTEND_UI_REDESIGN_PLAN.md`
5. Route·query·polling·권한: `docs/frontend/FRONTEND_SPEC.md`
6. 현재 구현: `backend/`, `frontend/src/`

Backend 계약을 바꿀 때는 같은 Work Package에서 API 문서, Pydantic contract, API manifest, route/service/storage, OpenAPI artifact, generated TypeScript schema, API client와 contract test를 함께 갱신한다. Backend만 또는 Frontend만 먼저 임시 DTO를 만들지 않는다.

## 3. 확정 결정

- Login을 이번 개편에 포함한다.
- 배포 theme는 dark-only이며 semantic token은 future light theme 확장을 허용한다.
- 기본 density는 compact다. 사용자 density 전환은 후속이다.
- Sidebar는 `Overview / Triage / Evidence / Analysis / Platform` group을 사용한다.
- Overview는 10개 기본 block을 사용하고 8개 기존 widget을 제거한다.
- 기존 Overview layout은 version 2로 1회 자동 migration하고 사용자에게 한 번 안내한다.
- Alerts는 `상태 → Severity → Risk → 최신 시각` 우선순위를 사용한다.
- Alert 상태 변경에는 `저장`과 `저장 후 다음`을 제공한다.
- Incident는 읽기 전용 lifecycle을 유지하고 graph, timeline, inspector와 evidence를 연결한다.
- Endpoint Detail은 paged server search 기반 `EndpointSwitcher`를 제공한다.
- Event 상세는 유형별 field group, 접힌 Raw Payload, copy와 내부 검색을 제공한다.
- 정량 chart는 ECharts PoC를 통과한 범위부터 적용한다.
- 관계 graph는 React Flow + Dagre PoC를 통과한 범위부터 feature flag로 적용한다.
- motion은 CSS를 우선하며 복잡 전환이 입증된 경우에만 Motion for React를 추가한다.
- 모든 chart와 graph에 text 또는 table fallback을 제공한다.
- 첫 배포는 Foundation과 공통 pattern, AppShell, Overview를 포함한다. 고급 시각화는 feature flag로 순차 활성화한다.

세부 결정은 `FRONTEND_UI_REDESIGN_WORKSHOP.md`의 확정 열을 그대로 따른다.

## 4. 이번 Backend 범위

### 4.1 재사용할 현재 계약

- `GET /dashboard/summary`: Event time series, Top Rules, MITRE, KPI와 guidance summary
- `GET /dashboard/endpoints/summary`, `GET /dashboard/ingest/summary`
- `GET /endpoints/{endpointId}/process-tree`
- `GET /incidents/{incidentId}/timeline`
- `GET /dashboard/topology`
- `GET/PUT/DELETE /dashboard/layouts/{dashboardKey}`
- Alert Detail의 읽기 전용 `responseGuidance`
- `GET /operations/health`, Archive restore 계약

기존 DTO로 제공되는 값을 새 endpoint나 client 계산으로 중복 구현하지 않는다.

### 4.2 추가·확장할 계약

1. Endpoint paged search
   - `GET /endpoints`에 `q`를 추가한다.
   - 숫자 query는 exact Endpoint ID, 문자열은 hostname과 agent ID의 case-insensitive exact 또는 prefix search다.
   - 검색 결과는 pagination을 유지하고 exact match, active status, risk, hostname 순으로 안정 정렬한다.
   - wildcard 전체 scan이나 client 전체 prefetch를 허용하지 않는다.

2. 승인된 server sorting
   - Alerts에 `sortBy=priority|detectedAt|severity|riskScore|status`를 제공한다.
   - 기본 `priority`는 미처리 상태, 높은 Severity, 높은 Risk, 최신 시각, ID 순의 결정적 정렬이다.
   - 다른 paged 목록은 현재 계약을 audit하고 디자인에서 실제로 노출하는 header에 필요한 sort만 추가한다.
   - 현재 page만 client-side sort해 전체 순서처럼 보이게 하지 않는다.

3. Incident investigation read model
   - `GET /incidents/{incidentId}/investigation`을 계약에 추가한다.
   - 응답은 Incident, Alert, Event, Process, Destination node와 관측된 relation edge, time range, node/edge count, `truncated`를 제공한다.
   - relation은 기존 FK와 Event field로 증명 가능한 `CONTAINS`, `TRIGGERED_BY`, `PARENT_OF`, `CONNECTED_TO`만 사용한다.
   - edge에는 `evidence=OBSERVED`를 명시한다. 시간상 인접하다는 이유로 인과관계를 만들지 않는다.
   - graph 크기는 서버에서 제한하고 잘린 경우 `truncated=true`와 table/timeline 탐색 경로를 제공한다.

4. Overview layout version 2 migration
   - 기존 version 1 layout을 읽을 수 있어야 한다.
   - Frontend가 제거 widget을 제외하고 신규 기본 block을 병합한 version 2 전체 layout을 같은 revision 계약으로 1회 저장한다.
   - 저장 성공 후에만 migration 안내를 완료 처리한다.
   - `409 DASHBOARD_LAYOUT_REVISION_CONFLICT`에서는 최신 layout을 다시 읽고 migration을 재적용할 수 있어야 한다.
   - 필요하지 않다면 기존 row를 일괄 갱신하는 DB migration은 만들지 않는다.

### 4.3 Backend 비범위

- Agent 원격 명령, 격리, 프로세스 종료, 파일 삭제와 실행형 playbook
- PCAP, packet payload, TLS 복호화 데이터
- 수집하지 않는 `bytesOut` 또는 bandwidth 추정
- Service·Worker 장기 상태 이력과 throughput snapshot 저장
- AI summary, report artifact 저장·공유 API
- multi-tenant, 신규 RBAC, Incident 수동 상태 변경
- Agent telemetry schema와 수집 protocol 변경

비범위 기능을 UI placeholder, disabled button 또는 가짜 데이터로 만들지 않는다.

## 5. Work Package 실행 순서

전체 범위는 승인되어 있지만 동시에 여러 package를 수정하지 않는다. 아래 순서로 하나를 `진행 중`으로 변경하고 완료 증거를 기록한 다음 다음 package로 이동한다. 이미 승인된 결정에 대해 다시 사용자 확인을 요구하지 않는다.

### MWO-00. Baseline과 회귀 기준

- 현재 Route, query, auth, polling, permission과 API response를 audit한다.
- Overview layout 저장 문제와 horizontal alignment를 재현한다.
- 주요 화면을 1440, 1024, 768, 360px과 KO/EN에서 baseline capture한다.
- bundle size, 핵심 API latency와 test baseline을 기록한다.
- 기존 실패는 신규 회귀와 구분해 기록한다.

완료 조건: 재현 절차, 보존할 계약, 변경 범위와 baseline 증거가 계획 문서에 기록됨.

### BWP-01. Contract와 OpenAPI

- `API_SPEC.md`, `FRONTEND_SPEC.md`에 Endpoint search, Alert sort, Incident investigation, layout v2 migration을 먼저 정의한다.
- Pydantic DTO/query, enum, nullable/empty 규칙과 error code를 정의한다.
- `backend/contracts/api_manifest.py`와 contract serialization test를 갱신한다.
- OpenAPI를 export하고 generated TypeScript schema를 갱신한다.

완료 조건: 문서, Pydantic, OpenAPI, generated schema가 동일하며 임시 frontend interface가 없음.

### BWP-02. Query, Search와 정렬

- Endpoint repository/service/route에 paged `q` search를 구현한다.
- Alerts priority sort와 허용 sort field를 구현한다.
- 다른 목록은 실제 UI header에서 필요한 sort만 구현한다.
- query plan을 확인하고 필요한 경우 새 PostgreSQL migration에 expression/prefix index를 추가한다.
- wildcard escaping, maximum query length, stable tiebreaker와 pagination 경계를 테스트한다.

완료 조건: 검색·정렬이 전체 dataset 기준으로 결정적이며 contract, permission, pagination test 통과.

### BWP-03. Incident Investigation Read Model

- 기존 Incident, `incident_alerts`, Alert `event_id`, ClickHouse Event와 process/network field를 조합한다.
- observed node/edge만 생성하고 node cap과 deterministic order를 적용한다.
- Event가 HOT/RESTORED에서 조회되지 않는 경우 부분 evidence를 반환하되 relation을 만들지 않는다.
- 권한, 404, archive-not-ready, partial data와 oversized graph를 테스트한다.

완료 조건: 같은 입력이 같은 graph를 만들고 각 edge를 원본 record로 추적할 수 있으며 `truncated`와 fallback 정보가 정확함.

### BWP-04. Dashboard Layout v2 호환성

- Backend가 version 1과 2 layout을 안전하게 조회·저장하도록 contract test를 추가한다.
- revision conflict, reset과 user isolation을 보존한다.
- Frontend migration을 위한 fixture를 제공한다.

완료 조건: v1 load → v2 save → reload, conflict, reset과 사용자 분리 시나리오 통과.

### WP-01. Overview Editor 안정화

- debounce, in-flight save, revision, grid remount의 실제 원인을 재현해 수정한다.
- `Done`은 pending save 성공 후 종료하고 실패·conflict에서 edit mode와 복구 경로를 유지한다.
- `DashboardFrame` inset과 12px gutter를 맞추고 negative margin을 제거한다.

완료 조건: refresh, save, cancel, reset, conflict와 reload에서 layout 유실·수평 흔들림 없음.

### WP-02. Foundation, Login과 AppShell

- semantic token, dark surface, typography, spacing, elevation과 functional gradient를 구현한다.
- Button, Field, Select, Badge, Dialog, Drawer, Tooltip, Popover와 상태 contract를 정리한다.
- CSS를 token, primitive, shell, pattern, visualization, page 계층으로 점진 분리한다.
- Login을 제품 설명과 인증 form으로 분리하고 오류·session·keyboard 동작을 보존한다.
- Sidebar group, compact mode, breadcrumb와 mobile modal drawer를 확정 순서로 구현한다.
- 고정 `min-width: 768px`를 제거하고 360px부터 지원한다.

완료 조건: dark-only token, KO/EN, focus, 200% zoom, reduced motion와 360px layout 통과.

### WP-03. 공통 Data Interaction

- 공통 `PageHeader`, `FilterBar`, applied filter, `DataTable`, Pagination, MasterDetail, Inspector와 `ChartFrame`을 구현한다.
- 기본 filter는 3개 이내로 노출하고 나머지는 Drawer/Popover에 둔다.
- filter, sort, page, selection과 time range를 URL로 보존한다.
- loading, refetching, stale, partial failure, empty, invalid filter, forbidden과 archive-not-ready를 구분한다.

완료 조건: Alerts, Incidents, Endpoints, Events와 Archives가 동일 contract를 사용하며 semantic table과 keyboard test 통과.

### WP-04. Overview 10 Block과 Migration

- EDR state, 4개 KPI, Detection Activity, Alert Severity, Endpoint Risk Distribution, Highest-risk Endpoints와 Incident Queue의 10개 block으로 재구성한다.
- compact toolbar에 Endpoint scope, time range, refresh, last updated와 layout edit를 통합한다.
- 제거 8개 widget을 소유 화면으로 이동하고 layout v2 migration과 1회 안내를 구현한다.
- API에 없는 previous value와 delta를 만들지 않는다.

완료 조건: 세 핵심 질문에 15초 안에 답할 수 있고 v1/v2 layout과 conflict test 통과.

### WP-05. Alerts와 Response Guidance

- Desktop queue+detail, mobile drawer, priority sort와 사용자 sort를 구현한다.
- `저장`, `저장 후 다음`을 분리하고 권한·mutation error를 표시한다.
- Response Guidance는 Rule version, order, title, description과 Manual badge를 유지한 읽기 전용 UI로 구현한다.

완료 조건: 상태 변경, 다음 항목 이동, deep link, keyboard, 빈 guidance와 권한 시나리오 통과.

### WP-06. Incidents와 Investigation

- queue, Incident graph, Selected context, swimlane timeline, evidence list와 Process Tree를 연결한다.
- graph selection을 Inspector, timeline과 evidence row에 동기화한다.
- lifecycle은 읽기 전용이며 observed/inferred를 혼동하지 않는다.
- graph feature flag off 또는 error 시 timeline과 table fallback을 기본 동작으로 유지한다.

완료 조건: 각 graph edge의 evidence 도달, partial/archive 상태, keyboard와 250-node cap 검증 통과.

### WP-07. Endpoints와 Events

- Endpoint inventory를 유지하고 searchable `EndpointSwitcher`를 server pagination과 연결한다.
- 상세에서 risk, collection health, related Alert·Incident, recent Event, profile, certificate와 Process Tree를 위계화한다.
- Events 목록은 공통 식별 field와 Event Type별 field를 조합한다.
- Event 상세는 유형별 group, Process Tree, 접힌 Raw Payload, copy와 검색을 제공한다.

완료 조건: 전체 prefetch 없이 switcher 동작, 목록 복귀 context 보존, certificate 이상 강조와 Event 유형 fixture 통과.

### WP-08. Intelligence, Operations와 Archives

- MITRE Matrix와 table fallback, Rules/Signal Top-N tabs를 구현한다.
- Egress Topology는 graph+Inspector+evidence table을 제공하고 protocol, Event/Alert count, last observed만 표시한다.
- Operations pipeline은 현재 snapshot으로 표시하며 움직이는 과거 flow처럼 표현하지 않는다.
- Collection, Detection, Storage 문제를 우선 표시하고 Archives에 lifecycle board, table과 restore action을 제공한다.

완료 조건: graph flag on/off, zero/empty/partial 상태, restore lifecycle과 role permission 검증 통과.

### WP-09. 통합 QA와 Release

- MWO-00 baseline과 최종 결과를 비교한다.
- Foundation, AppShell와 Overview를 첫 release scope로 검증한다.
- Incident, Topology와 고급 chart는 package별 gate 통과 후 feature flag를 활성화한다.
- 문서, API, OpenAPI, generated schema와 실제 화면을 최종 동기화한다.

완료 조건: 아래 Release Gate를 전부 통과하고 rollback 및 feature flag 상태가 기록됨.

## 6. 의존성 정책

- ECharts는 PoC가 접근성 fallback, resize, print와 bundle 기준을 통과한 뒤 추가한다.
- 관계 graph는 `@xyflow/react`와 `@dagrejs/dagre`를 우선 검토한다.
- Motion for React는 CSS로 해결할 수 없는 승인된 전환이 생길 때만 추가한다.
- 각 신규 package는 선택 이유, 대안, bundle 변화, license와 production audit 결과를 기록한다.
- Tailwind 또는 shadcn/ui 전체 migration은 하지 않는다.

## 7. 검증 명령

Repository root:

```powershell
uv run ruff check backend tests tools
uv run pytest
docker compose config
```

OpenAPI와 Frontend:

```powershell
Set-Location frontend
npm.cmd run openapi:export
npm.cmd run openapi:generate
npm.cmd run openapi:check
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run test
npm.cmd run build
```

로컬 서비스가 준비된 경우 integration marker와 실제 API smoke test를 추가로 수행한다. 환경 문제로 실행할 수 없는 검증은 성공으로 처리하지 않고 명령, 원인과 재실행 조건을 기록한다.

## 8. 수동·브라우저 QA Matrix

| 범위 | 필수 조합 |
| --- | --- |
| Viewport | 360, 768, 1024, 1440px |
| Locale | KO, EN |
| Input | keyboard-only, pointer, touch equivalent |
| Accessibility | visible focus, 200% zoom, reduced motion, contrast, screen-reader name |
| Data | normal, zero, empty, long text, partial failure, stale, permission denied, archive not ready |
| Graph | feature flag on/off, 1 node, 250 nodes, truncated, missing evidence |
| Layout | v1 migration, v2 load, save, refresh, cancel, reset, conflict |
| Print | Raw Payload와 사용자 정보 기본 제외, chart/table fallback 확인 |

## 9. Release Gate

- 모든 `DESIGN.md` Hard Pre-flight 항목을 충족한다.
- API 문서, Pydantic, OpenAPI와 generated TypeScript schema에 drift가 없다.
- Backend와 Frontend test, lint, typecheck와 build가 통과한다.
- 360px에서 핵심 흐름이 가로 고정 layout 때문에 차단되지 않는다.
- Alert → Event/Incident, Incident → evidence, Endpoint → Event/Process Tree 흐름이 보존된다.
- polling/refetch가 focus, scroll, selection과 열린 Popover를 불필요하게 초기화하지 않는다.
- chart와 graph를 끄거나 실패시켜도 text/table fallback으로 동일 핵심 정보에 접근할 수 있다.
- API에 없는 데이터, 실행할 수 없는 action과 확인되지 않은 인과관계를 표시하지 않는다.
- migration rollback, feature flag 기본값과 배포 순서가 문서화된다.

## 10. 완료 보고 형식

각 Work Package 완료 시 실행 계획에 다음을 기록한다.

```text
Package:
상태:
변경 파일:
계약 변경:
Migration:
원인 또는 설계 판단:
실행한 검증:
브라우저 QA 증거:
성능·접근성 결과:
남은 위험:
다음 Package:
```

검증되지 않은 항목을 `완료`로 표시하지 않는다. commit, push와 PR은 사용자가 별도로 요청한 경우에만 수행한다.

## 11. Coding Agent 시작 지시문

```text
docs/frontend/FRONTEND_BACKEND_UI_REDESIGN_WORK_ORDER.md를 전체 작업의 실행 기준으로 사용해줘.

먼저 DESIGN.md, FRONTEND_UI_REDESIGN_PLAN.md, FRONTEND_SPEC.md,
API_SPEC.md, RISK_POLICY.md와 대상 코드를 읽고 MWO-00부터 시작한다.

이 문서의 전체 Frontend·Backend 범위와 Workshop 권장안은 승인되었다.
이미 확정된 디자인 결정을 다시 질문하지 말고 Work Package 순서대로 계속 진행한다.
단, 한 번에 하나의 Package만 진행 중으로 두고 package마다 계약, 구현, test와 증거를 완결한다.

Backend 계약 변경은 API 문서 → Pydantic/manifest → service/storage → OpenAPI
→ generated TypeScript schema → API client/UI → contract/integration test 순서를 지킨다.
기존 Dashboard 집계, Process Tree, Timeline, Topology와 Guidance 계약을 중복 구현하지 않는다.

원격 명령, bytesOut 추정, PCAP, multi-tenant, 상태 이력 저장과 가짜 데이터는 추가하지 않는다.
새로운 blocker가 실제 코드·계약 근거로 확인된 경우에만 중단하고 재현 증거와 최소 선택지를 보고한다.

각 Package가 끝나면 FRONTEND_UI_REDESIGN_PLAN.md에 상태, 변경 파일,
실행 명령, 결과, 남은 위험과 다음 Package를 기록한다.
모든 Package와 Release Gate가 완료될 때까지 같은 절차로 이어서 수행한다.
```
