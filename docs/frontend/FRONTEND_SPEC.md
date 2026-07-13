# EDR Dashboard Frontend 구현 명세

## 1. 문서 목적

이 문서는 React/TypeScript/Vite EDR Dashboard의 route, 화면 구성, API mapping, query, polling, 인증, 상태 처리와 기존 UI reference 사용 범위를 정의한다.

문서 책임 우선순위:

1. `../contracts/API_SPEC.md`: REST path, request/response DTO, enum, required/nullable/null/`[]` 규칙
2. `../contracts/RISK_POLICY.md`: Endpoint Risk와 전역 EDR 상태 계산 정책
3. `../architecture/TECH_STACK.md`: 실행환경, 컴포넌트 책임과 제외 범위
4. `FRONTEND_SPEC.md`: route, 화면별 API 조합, frontend behavior, 시각 token, component state, responsive와 접근성

기존 프론트는 API·DTO·state model의 기준이 아니다. 기존 프론트에서는 이 문서가 지정한 시각·상호작용 패턴만 참고한다.

## 2. 최종 Frontend 정보 구조

### 2.1 Route

| Route | 화면 | 인증 |
| --- | --- | --- |
| `/login` | Login | 불필요 |
| `/` | Overview | 필요 |
| `/alerts` | Alert 목록 | 필요 |
| `/alerts/:alertId` | Alert 상세 | 필요 |
| `/incidents` | Incident 목록 | 필요 |
| `/incidents/:incidentId` | Incident 상세 | 필요 |
| `/endpoints` | Endpoint 목록 | 필요 |
| `/endpoints/:endpointId` | Endpoint 상세 | 필요 |
| `/events` | Event 목록 | 필요 |
| `/events/:eventId` | Event 상세 | 필요 |
| `/operations` | Ingest Health | 필요 |
| `/operations/archives` | Archive Restore/상태 | 필요 |

Event 상세 API에 필요한 `endpointId`, `occurredAt`은 URL query로 유지한다.

```text
/events/{eventId}?endpointId=1001&occurredAt=2026-07-11T00%3A00%3A04.123Z
```

필수 query가 없으면 Event 상세 API를 호출하지 않고 Event 목록으로 돌아갈 수 있는 validation error 화면을 표시한다.

### 2.2 Primary navigation

```text
Overview
Alerts
Incidents
Endpoints
Events
Operations
```

Operations는 Ingest Health와 Archive 두 하위 route를 가진다.

삭제 대상:

- Intelligence 독립 메뉴
- Report Center/Modal
- DLQ Monitor와 웹 replay
- Topology
- Process Tree
- Timeline 전용 화면
- Agent response action
- 실행형 Response Playbook

MITRE, Top Rule, process/IP/domain 정보는 Overview와 Alert 상세에서 표시한다.

## 3. Frontend 기술 경계

- React, TypeScript, Vite를 사용한다.
- icon은 `lucide-react`를 사용하고 emoji를 icon으로 사용하지 않는다.
- URL route는 browser history를 사용하는 React routing layer로 구현한다. route와 filter 상태는 URL로 복원 가능해야 한다.
- JWT access token은 React memory state에만 저장한다.
- API response와 domain data를 `localStorage`나 `sessionStorage`에 저장하지 않는다.
- `localStorage`에는 마지막 primary route와 navigation compact 상태만 저장한다.
- FastAPI/Pydantic camelCase response가 최종 계약이다. Legacy adapter, normalizer, mock DTO fallback을 만들지 않는다.
- Endpoint Risk, EDR 상태, chart bucket, severity/status count를 프론트에서 다시 계산하지 않는다.
- Presentation을 위한 bar width, SVG coordinate, label sampling은 허용한다.
- 서버 response type에는 optional key를 임의로 추가하지 않는다. `T | null`과 `T[]` 규칙을 그대로 유지한다.

## 4. 인증과 권한

### 4.1 Login

- `POST /auth/login` 성공 시 JWT와 `UserDto`를 memory에 저장하고 `/`로 이동한다.
- 새로고침하면 token이 없으므로 `/login`으로 이동한다.
- 로그인 전에 접근한 내부 route는 memory에만 보관하고 로그인 성공 후 한 번 복귀할 수 있다.
- password, token, user object를 browser storage와 log에 기록하지 않는다.

### 4.2 HTTP 상태 처리

| 상태 | Frontend behavior |
| ---: | --- |
| 400 | field validation을 form/control 근처에 표시 |
| 401 | memory session 제거 후 `/login` 이동 |
| 403 | logout하지 않고 권한/계정 상태 오류 표시 |
| 404 | resource not found 화면과 목록 복귀 link |
| 409 | resource 상태 오류 표시, `ARCHIVE_NOT_READY`는 Archive route 안내 |
| 413 | body/범위 제한 메시지 표시 |
| 429 | `Retry-After`가 있으면 해당 시간 후 retry |
| 503 | 마지막 성공 데이터 유지, retry 가능한 service warning 표시 |

모든 오류 화면은 Backend message와 `meta.requestId`를 표시한다. 내부 stack과 raw response body는 표시하지 않는다.

### 4.3 Role

| 기능 | ADMIN | ANALYST | VIEWER |
| --- | --- | --- | --- |
| 조회 | 허용 | 허용 | 허용 |
| Alert status 변경 | 허용 | 허용 | control 숨김 |
| Archive restore 시작 | 허용 | 허용 | control 숨김 |
| Response Guidance 조회 | 허용 | 허용 | 허용 |

Control을 숨겨도 Backend 403 처리는 유지한다.

## 5. 공통 Query와 URL 상태

- 기본 `page=1`, `size=50`, `sortOrder=desc`다.
- filter가 바뀌면 `page=1`로 돌아간다.
- filter, page, size, sort는 URL query에 직렬화한다.
- 기본값은 URL에서 생략할 수 있지만 parsing 후에는 계약의 기본값으로 복원한다.
- CUSTOM은 `from`, `to`를 모두 요구한다.
- 모든 시간은 API로 UTC RFC3339 `Z`를 전송하고 화면은 사용자 local timezone으로 표시한다.
- 여러 filter는 AND로 결합한다.
- 빈 string filter는 전송하지 않는다.
- 전역 통합 검색 API는 만들지 않는다.

### 5.1 Time preset과 Dashboard interval

| TimePreset | interval |
| --- | --- |
| `LATEST_15M` | `1m` |
| `LATEST_1H` | `5m` |
| `LATEST_24H` | `1h` |
| `LATEST_7D` | `1d` |

CUSTOM:

| 범위 | interval |
| --- | --- |
| 6시간 이하 | `5m` |
| 48시간 이하 | `1h` |
| 48시간 초과 | `1d` |

Dashboard API의 최대 2,000 point 제한을 넘는 조합은 form validation에서 막고 Backend validation도 그대로 처리한다.

## 6. 목록 API query

정확한 외부 query 계약은 `../contracts/API_SPEC.md`를 따른다.

### 6.1 Endpoints

```text
status
osType
riskLevel
page
size
sortBy = riskScore / lastSeenAt / registeredAt
sortOrder
```

기본 정렬은 `sortBy=riskScore&sortOrder=desc`다.

### 6.2 Alerts

```text
endpointId
status
severity
ruleCode
timePreset
from
to
page
size
sortOrder
```

### 6.3 Incidents

```text
endpointId
status
severity
timePreset
from
to
page
size
sortOrder
```

### 6.4 Events

```text
endpointId
eventType
processName
filePath
domain
remoteIp
dnsQuery
l7Protocol
timePreset
from
to
page
size
sortOrder
```

### 6.5 Archive

```text
endpointIds
from
to
page
size
```

## 7. Polling과 request lifecycle

| 화면/API | 주기 |
| --- | ---: |
| Overview의 Dashboard API 3개 | 30초 |
| Operations Ingest summary | 15초 |
| Archive에 `RESTORE_REQUESTED` 존재 | 10초 |
| Archive 진행 항목 없음 | 30초 |
| Alert/Incident/Endpoint/Event 목록·상세 | 자동 polling 없음 |

규칙:

- 화면 진입 시 즉시 조회한다.
- browser document가 hidden이면 polling을 중지한다.
- visible 복귀 시 마지막 성공 조회가 해당 화면 polling 주기보다 오래됐으면 즉시 조회한다.
- route 이탈과 filter 변경 시 이전 request를 `AbortController`로 취소한다.
- Alert status mutation 성공 후 해당 Alert 상세와 현재 Alert 목록을 즉시 재조회한다.
- Archive restore 시작 성공 후 Archive 목록을 즉시 재조회한다.
- 429는 `Retry-After`를 우선한다.
- 503은 5초, 15초, 30초 간격으로 최대 3회 retry한다.
- 400, 401, 403, 404, 409, 413은 자동 retry하지 않는다.
- refresh 실패 시 마지막 성공 데이터를 유지하고 warning banner와 retry action을 표시한다.
- polling 결과가 갱신돼도 focus, scroll, 현재 선택 row를 초기화하지 않는다.

`lastRefreshedAt`은 해당 화면의 마지막 성공 응답을 받은 frontend 시각이다. API field가 아니며 `edrState.calculatedAt`, `risk.calculatedAt`과 구분한다.

## 8. 화면별 구성

### 8.1 Login

- email, password
- submit loading, field validation, account disabled, invalid credential 상태
- password 표시 toggle은 선택 사항이지만 token 저장 option은 제공하지 않는다.

### 8.2 Overview

동시에 호출:

- `GET /dashboard/summary`
- `GET /dashboard/endpoints/summary`
- `GET /dashboard/ingest/summary`

표시:

- `EdrStatePill`: status, score, reason codes, calculatedAt
- KPI: Event, Alert, OPEN Incident, ONLINE Endpoint, failure, storage bucket
- Alert severity donut
- Alert/Event/Incident time series
- Endpoint Risk distribution과 highest score
- Endpoint OS와 sensor health
- Top Rule, MITRE tactic/technique
- Top process, remote IP, domain, file hash, DNS, L7 protocol
- Failure stage/code/status와 storage distribution
- `lastRefreshedAt`

KPI와 chart 선택은 관련 목록 route로 이동하며 가능한 경우 URL filter를 설정한다.

### 8.3 Alerts

목록:

- rule name/code, severity, riskScore, status, agentId, detectedAt
- server pagination과 filter
- desktop master-detail 또는 detail route 이동

상세:

- Alert 기본 필드와 MITRE
- nullable `sourceEvent`
- 연결 Incident 목록
- 읽기 전용 `responseGuidance`
- ADMIN/ANALYST status 변경

Response Guidance에는 checkbox, run button, command status와 완료 저장 기능을 만들지 않는다.

### 8.4 Incidents

목록:

- title, endpointId, severity, status, alertCount, window, lastDetectedAt
- server pagination과 filter

상세:

- correlationKey, description, window와 closedAt
- 연결 Alert 목록
- Alert 선택 시 `/alerts/:alertId`
- Incident status 변경 control은 없음

### 8.5 Endpoints

목록:

- hostname, agentId, OS, status, lastSeenAt, stale
- Risk score/level, active Alert count, OPEN Incident count
- riskLevel filter와 riskScore 정렬

상세:

- Agent version/build/arch와 capability
- sensor health
- certificate history
- Endpoint Risk와 factor
- factor sourceType에 따라 Alert 또는 Incident 상세로 이동

프론트는 Risk factor 합계로 score를 교체하거나 재계산하지 않는다.

### 8.6 Events

목록 column:

- occurredAt
- hostname/endpointId
- eventType
- processName
- remoteDomain/remoteIp/DNS/L7 핵심 값
- ingestedAt

상세:

- EventDto 전체 required/nullable field
- `rawPayload`, `payloadSha256`, `schemaVersion`
- packet/PCAP download UI 없음

`409 ARCHIVE_NOT_READY`이면 error context의 bucket 상태를 표시하고 `/operations/archives` 이동 action을 제공한다. 자동 restore를 시작하지 않는다.

### 8.7 Operations

Ingest Health:

- ingestedCount, latestIngestedAt
- failed/reprocessed/reprocessFailed count
- oldestFailedAt
- HOT/RESTORED/ARCHIVED/RESTORING/FAILED/EXPIRED bucket count

Archive:

- endpointIds, UTC from/to restore form
- ArchiveBucketDto 목록과 server pagination
- ADMIN/ANALYST만 restore 시작
- `RESTORE_REQUESTED` 진행 중 polling
- failure payload DLQ 목록과 웹 replay control 없음

## 9. Loading, empty, error와 stale data

### Loading

- 최초 화면은 실제 layout footprint와 같은 skeleton을 표시한다.
- 상세 fetch 중 목록을 지우지 않는다.

### Empty

- resource 자체가 없음과 현재 filter 결과 없음 문구를 구분한다.
- API의 `[]`와 count 0은 정상 empty state다.

### Error

- 사용자 메시지, retry 가능 여부, `requestId`, 다음 action을 표시한다.
- nullable 값과 fetch error를 같은 `-`로 숨기지 않는다.

### Stale data

- refresh 실패 시 마지막 성공 데이터는 유지한다.
- banner에 실패 시각과 retry action을 제공한다.
- stale 데이터임을 chart/KPI마다 반복 표시하지 않고 화면 단위로 한 번 명확히 표시한다.

## 10. Responsive와 접근성

- 기준 viewport는 375px, 768px, 1280px다.
- 1280px 이상은 icon rail과 3-column Overview를 사용한다.
- 768~1279px는 1~2-column이다.
- 767px 이하는 single-column이며 table은 horizontal scroll을 허용한다.
- `body min-width:1024px`를 사용하지 않는다.
- 모든 interactive element는 visible focus와 accessible name을 가진다.
- status/severity는 color와 text를 함께 사용한다.
- chart는 text summary 또는 table fallback을 제공한다.
- polling이 screen reader live region을 반복 발생시키지 않도록 자동 refresh 결과는 silent update한다. 오류와 사용자 mutation 결과만 적절한 status message로 알린다.
- `prefers-reduced-motion`을 존중한다.
- WCAG 2.2 AA를 목표로 하며 구체 token과 primitive 규칙은 이 문서의 Design System 부분을 따른다.

## 11. 기존 UI reference 범위

다음 파일과 구간은 시각·상호작용 참고만 허용한다.

- `<LOCAL_FRONTEND_REFERENCE_REPOSITORY>/package.json`: 사용 기술과 UI dependency
- `web/src/App.tsx` 1~415, 705~858: shell, navigation, filter, Overview layout, skeleton
- `web/src/dashboardPanelCore.tsx` 전체: KPI, panel heading, empty, signal 표시 구조
- `web/src/dashboardCharts.tsx` 전체: chart 외형만 참고
- `web/src/dashboardQueues.tsx` 1~64, 116~211: Incident/Endpoint/Alert/Event 표시 구조
- `web/src/styles.css` 사용자 지정 구간: token, panel, chart, list, shell, skeleton, responsive

재사용 가능한 것은 color, spacing, surface, panel, chart shape, navigation, filter UX다. DTO, enum, adapter, fetch, mock, 상태 계산과 원시 데이터 집계는 재사용하지 않는다.

### 명시적 제외

- `src/**/*.py`
- `tests/**`
- `migrations/**`
- `scripts/**`
- `samples/**`
- `resultAdapter.ts`
- `resultNormalizer.ts`
- `resultRows.ts`
- `resultPrimitives.ts`
- `dashboardTypes.ts`
- `dashboardTopology.tsx`
- `dashboardReport.tsx`
- `OverviewWireframe.tsx`
- `overviewWireframe.css`
- 기존 `UI_HANDOFF.md`와 기존 Frontend의 `DESIGN.md`
- Dockerfile, docker-compose
- 기존 backend API route/model

## 12. Frontend state 목록

- Auth: token, user, intended route
- Router: route params와 URL query
- Overview: timePreset, CUSTOM range, interval, 3개 Dashboard response와 last success
- Lists: filter, page, size, sort
- Selection: 현재 detail ID
- Mutation: Alert status, Archive restore
- Request: loading, error, requestId, retryable, lastRefreshedAt
- Layout storage: compact navigation only

Legacy `DashboardResult`, `EndpointRisk`, `EDR state`, `decision`, `source`, `generatedAt`, `responseActions`, DLQ, topology와 report state를 만들지 않는다.

## 13. 개발 순서

1. 이 문서의 Design System primitive showcase와 shell
2. API enum/DTO/query/error type
3. memory auth와 Login
4. typed API client와 request lifecycle
5. common panel/filter/table/chart/empty/error/skeleton primitive
6. Dashboard API 3개와 Overview
7. Endpoint 목록·상세
8. Event 목록·상세와 archive-not-ready 처리
9. Alert 목록·상세·status mutation·Response Guidance
10. Incident 목록·상세
11. Operations Ingest/Archive
12. responsive, keyboard, accessibility, polling 안정화
13. 실제 Backend 연동과 browser visual QA

## 14. 완료 조건

- 모든 화면이 `../contracts/API_SPEC.md` DTO만 사용한다.
- 제품 REST API 수는 Dashboard 15개 + Collector 3개다.
- 프론트 집계로 Endpoint Risk/EDR 상태/chart bucket을 만들지 않는다.
- JWT가 storage에 남지 않는다.
- Report, DLQ Monitor, 웹 replay, Agent command가 없다.
- loading/empty/error/stale/forbidden/archive-not-ready 상태를 실제 UI에서 확인한다.
- 375px, 768px, 1280px에서 주요 task를 browser로 검증한다.
- keyboard navigation, visible focus, reduced motion과 chart text fallback을 검증한다.
- 실제 구현 완료 후 `/visual-qa`와 최종 implementation review를 통과한다.

---

+
## 15. Design System Research Log

- Embedded reference: `<LOCAL_FRONTEND_REFERENCE_REPOSITORY>`의 사용자 지정 허용 구간에서 콘솔 셸, 토큰, 패널, 차트, 목록·상세, loading/empty/focus 패턴을 추출했다.
- Contract source: `../contracts/API_SPEC.md`, `../architecture/TECH_STACK.md`, `../contracts/RISK_POLICY.md`와 이 문서 앞부분이 화면 데이터와 기능 범위의 기준이다.
- Existing frontend data model: DTO, adapter, mock, enum, 집계 로직은 참고하지 않는다.
- Lazyweb와 Imagen: 사용자가 구체적인 기존 UI reference를 지정했으므로 추가 디자인 방향 탐색은 수행하지 않았다.
- Direction: 어두운 운영형 보안 콘솔, 조밀하지만 판독 가능한 정보 계층, 상태 색상은 장식이 아니라 위험·건강 의미에만 사용한다.

## 16. Atmosphere & Identity

이 제품은 빠르게 이상 상태를 파악하고 근거 데이터로 이동할 수 있는 조용한 보안 관제 콘솔이다. 시그니처는 54px icon rail, 얇은 cyan active indicator, 세 단계의 dark surface와 제한된 상태 색상이다. 화면은 마케팅 Dashboard처럼 과장하지 않고, 숫자·상태·최근성·다음 이동 경로를 우선한다.

핵심 원칙:

- 위험 정보는 강하게, 정상 상태는 조용하게 표현한다.
- 색상만으로 상태를 전달하지 않고 text label과 icon 또는 count를 함께 제공한다.
- 한 화면에서 가능한 모든 데이터를 보여주지 않고 Overview에서 상세 화면으로 drill-down한다.
- Report, DLQ Monitor, Topology, Process Tree, Agent command처럼 계약에 없는 기능을 시각적으로 암시하지 않는다.

## 17. Color

Dark theme만 MVP 범위에 포함한다.

| 역할 | Token | 값 | 사용 |
| --- | --- | --- | --- |
| Page background | `--color-bg` | `#101215` | 전체 배경 |
| Shell background | `--color-shell` | `#0d0f12` | rail, top chrome |
| Surface primary | `--color-panel` | `#171c22` | 기본 panel |
| Surface secondary | `--color-panel-2` | `#202733` | row, control |
| Surface inset | `--color-panel-3` | `#11161c` | chart, inspector inset |
| Surface hover | `--color-panel-hover` | `#1b222c` | interactive hover |
| Border default | `--color-line` | `#323a46` | panel border |
| Border subtle | `--color-line-soft` | `#272e38` | divider, table row |
| Text primary | `--color-text` | `#eef2f7` | heading, primary value |
| Text secondary | `--color-muted` | `#9aa8ba` | description, metadata |
| Text tertiary | `--color-muted-2` | `#748296` | disabled, quiet label |
| Danger | `--color-red` | `#f2495c` | CRITICAL, RED, unavailable |
| Warning | `--color-amber` | `#ffb357` | HIGH, YELLOW, degraded |
| Success | `--color-green` | `#73bf69` | LOW, GREEN, online, healthy |
| Info | `--color-blue` | `#5794f2` | MEDIUM, neutral data series |
| Focus/accent | `--color-cyan` | `#56d0e6` | focus, active navigation, chart focus |

### 상태 mapping

| Domain | 값 | Color token |
| --- | --- | --- |
| Risk/Severity | `CRITICAL` | `--color-red` |
| Risk/Severity | `HIGH` | `--color-amber` |
| Risk/Severity | `MEDIUM` | `--color-blue` |
| Risk/Severity | `LOW` | `--color-green` |
| EDR state | `RED` | `--color-red` |
| EDR state | `YELLOW` | `--color-amber` |
| EDR state | `GREEN` | `--color-green` |
| Endpoint | `ONLINE` | `--color-green` |
| Endpoint | `OFFLINE` | `--color-amber` |
| Endpoint | `RETIRED` | `--color-muted-2` |
| Sensor | `HEALTHY` | `--color-green` |
| Sensor | `DEGRADED` | `--color-amber` |
| Sensor | `UNAVAILABLE` | `--color-red` |

### Color rules

- Cyan은 focus, selection, active navigation과 interactive chart affordance에만 사용한다.
- Red는 CRITICAL/RED 또는 실제 오류에만 사용한다.
- Background에 상태 색상을 넓게 채우지 않고 border, icon, text, 작은 fill로 제한한다.
- 모든 상태는 visible text를 함께 제공한다.
- 새 raw hex는 이 문서에 token을 먼저 추가한 뒤 사용한다.

## 18. Typography

### Font stack

- Primary: `Inter, "Segoe UI", system-ui, -apple-system, sans-serif`
- Mono: `"Cascadia Code", Consolas, "SFMono-Regular", monospace`
- 외부 font network 요청은 필수가 아니다. Inter가 번들에 없으면 system font를 사용한다.

### Type scale

| Token | Size | Weight | Line height | 사용 |
| --- | ---: | ---: | ---: | --- |
| `--font-micro` | 11px | 800 | 1.3 | uppercase overline, chart axis |
| `--font-caption` | 12px | 500 | 1.45 | 짧은 metadata, table |
| `--font-body-sm` | 13px | 500 | 1.45 | control label, compact navigation |
| `--font-body` | 14px | 400 | 1.55 | 기본 본문 |
| `--font-title-sm` | 15px | 700 | 1.35 | compact card title |
| `--font-title-md` | 16px | 800 | 1.3 | panel heading |
| `--font-title-lg` | 18px | 800 | 1.25 | page section title |
| `--font-display-sm` | 22px | 800 | 1.1 | secondary KPI |
| `--font-display-md` | 28px | 900 | 1.05 | chart center value |
| `--font-display-lg` | 34px | 900 | 1 | primary KPI |

규칙:

- 13px 이하는 짧은 UI label과 metadata에만 사용한다.
- 설명, 오류, guidance 본문은 최소 14px다.
- ID, hash, path, IP와 code는 mono font를 사용할 수 있다.
- 긴 값은 ellipsis로 의미를 숨기기보다 `overflow-wrap:anywhere`와 accessible title/detail을 사용한다.

## 19. Spacing & Layout

운영형 고밀도 UI를 유지하기 위해 2px base unit을 사용한다.

| Token | 값 | 사용 |
| --- | ---: | --- |
| `--space-1` | 2px | hairline offset |
| `--space-2` | 4px | inline tight gap |
| `--space-3` | 6px | compact control gap |
| `--space-4` | 8px | row/card internal gap |
| `--space-5` | 10px | compact padding |
| `--space-6` | 12px | 기본 panel padding/gap |
| `--space-7` | 14px | shell horizontal padding |
| `--space-8` | 16px | empty/error padding |
| `--space-10` | 20px | page bottom/section gap |
| `--space-12` | 24px | larger separation |
| `--space-16` | 32px | major section separation |

### Radius

| Token | 값 | 사용 |
| --- | ---: | --- |
| `--radius-control` | 4px | input, chip, row |
| `--radius-panel` | 6px | panel, card |
| `--radius-pill` | 999px | status pill, donut |

### Shell

- Desktop rail: 54px
- Desktop top bar: 58px
- Main shell: `min-height:100dvh`
- Main content는 viewport 내부에서 독립 scroll한다.
- Overview desktop: 3-column grid, 12px gap
- KPI desktop: 6-column strip, 12px gap
- Panel은 고정 높이가 필요할 때 내부만 scroll하며 page 전체와 중첩 scroll을 최소화한다.

### Responsive

| Width | Layout |
| --- | --- |
| 1280px 이상 | 3-column Overview, left icon rail |
| 768~1279px | 1~2-column, rail은 상단 navigation으로 이동 가능 |
| 767px 이하 | single-column read/triage layout, wide table horizontal scroll |

`body`에 고정 `min-width:1024px`를 사용하지 않는다. 375px, 768px, 1280px에서 주요 task가 동작해야 한다.

## 20. Components

### AppShell

- **Structure**: navigation rail/top navigation, global bar, optional filter bar, scrollable main.
- **States**: route active, compact responsive, loading auth.
- **Accessibility**: `nav` landmark, current route는 `aria-current="page"`, icon button에는 visible tooltip과 accessible name.
- **Motion**: responsive reflow에는 animation을 넣지 않는다.

### EdrStatePill

- **Structure**: status label, score, short reason summary, calculated time detail link.
- **Variants**: GREEN, YELLOW, RED.
- **States**: loading skeleton, current, stale/error.
- **Accessibility**: 색상과 함께 status text 제공. 자동 갱신은 live region으로 매번 읽지 않고 사용자가 상세를 열 때 확인한다.

### GlobalFilterBar

- **Structure**: 화면이 지원하는 filter select/input, active dismissible chip, Clear action.
- **Variants**: time, severity, Endpoint, status, event metadata.
- **States**: default, applied, disabled, invalid CUSTOM range.
- **Accessibility**: 각 control에 visible label, chip remove button accessible name.
- **Rule**: API가 지원하지 않는 전역 filter를 다른 화면에 전달하지 않는다.

### KpiCard

- **Structure**: icon, label, value, detail, optional navigation affordance.
- **Variants**: neutral, status/risk tone, interactive/non-interactive.
- **States**: default, hover, focus, disabled, loading.
- **Accessibility**: 이동 동작이 있으면 button 또는 link, 그렇지 않으면 article.
- **Motion**: arrow는 hover/focus에서 `translateX(2px)`와 opacity만 160ms.

### Panel

- **Structure**: `PanelHeading`, optional chip/action, body.
- **Variants**: chart, list, table, inspector, empty/error.
- **States**: loading, empty, error, last-success-with-warning.
- **Accessibility**: heading level은 page hierarchy를 따른다.

### StatusPill

- **Structure**: text label과 optional icon.
- **Variants**: severity, risk, endpoint, sensor, alert, incident, storage.
- **Accessibility**: 색상만으로 상태를 전달하지 않는다.

### SeverityDonut

- **Input**: Dashboard API의 `SeverityCountDto[]`.
- **Rule**: 원시 Alert를 집계하지 않는다.
- **States**: active category, zero/disabled, keyboard focus, empty.
- **Accessibility**: total과 각 category count를 text list로도 제공한다.

### TimeSeriesChart

- **Input**: Dashboard API의 timeSeries DTO.
- **Variants**: Alert, Event, Incident open/closed.
- **Rule**: 프론트에서 bucket을 다시 만들지 않는다. label 간격만 시각적으로 생략할 수 있으며 data point는 변경하지 않는다.
- **Accessibility**: chart summary와 tabular fallback을 제공한다.

### CountBars

- **Input**: 서버 집계 `Top*Dto[]`, MITRE count, health/storage distribution.
- **Rule**: bar width normalization만 presentation 계산으로 허용한다.
- **States**: empty, focusable navigation row when drill-down이 존재.

### MasterDetail

- **사용 화면**: Alerts, Incidents, Endpoints.
- **Desktop**: list와 detail 동시 표시 가능.
- **Mobile**: list에서 별도 detail route로 이동.
- **States**: no selection, selected, detail loading/error.

### DataTable

- **Structure**: sticky header, server-paginated rows, pagination.
- **States**: loading rows, empty, error, row selected.
- **Accessibility**: column header scope, keyboard reachable row action, sort state `aria-sort`.
- **Rule**: client `slice/reverse`로 pagination을 흉내 내지 않는다.

### ResponseGuidance

- **Input**: `AlertDetailDto.responseGuidance`.
- **Structure**: ordered step, title, description, manual-action badge.
- **Rule**: 읽기 전용이다. checkbox, run button, command status와 자동 완료 상태를 만들지 않는다.

### RiskFactorList

- **Input**: `EndpointRiskDto.riskFactors`.
- **Structure**: contribution, title, 설명, source link.
- **Action**: sourceType에 따라 Alert 또는 Incident 상세로 이동.
- **Rule**: contribution 합계를 재계산해 score를 교체하지 않는다.

### Skeleton, EmptyState, ErrorState

- Skeleton은 최종 layout과 같은 footprint를 사용한다.
- EmptyState는 정상적인 `[]` 결과와 filter 결과 없음 문구를 구분한다.
- ErrorState는 사용자 메시지, retry 가능 여부, `requestId`를 제공한다.
- 마지막 성공 데이터가 있으면 데이터를 유지하고 warning banner를 함께 표시한다.

## 21. Motion & Interaction

| 유형 | Duration | Easing | 사용 |
| --- | ---: | --- | --- |
| Micro | 160ms | ease-out | hover/focus affordance |
| Standard | 220ms | ease-in-out | drawer/panel state |
| Chart entry | 420~750ms | ease-out | 최초 chart reveal만 |
| Skeleton | 1250ms | ease-in-out | loading gradient |

규칙:

- `transform`, `opacity`, `filter`만 animate한다.
- polling refresh 때 chart entry animation을 반복하지 않는다.
- hover가 의미 없는 non-interactive card에는 motion을 넣지 않는다.
- `prefers-reduced-motion: reduce`에서는 chart reveal과 skeleton 이동을 제거하거나 정적인 대체 표현을 사용한다.
- focus-visible outline은 2px cyan, 2px offset을 사용한다.

## 22. Depth & Surface

전략은 얇은 border와 tonal shift를 결합한 mixed strategy다.

- 기본 panel: `--color-panel`, 1px `--color-line`, 6px radius.
- 내부 row: `--color-panel-2` 또는 `--color-panel-3`, 1px `--color-line-soft`.
- 기본 depth: `inset 0 1px 0 rgba(255,255,255,0.03)` 한 단계만 사용.
- hover: border contrast와 한 단계 밝은 surface로 표현한다.
- 큰 drop shadow, glass blur, 장식적 glow를 사용하지 않는다.
- 위험 상태는 좌측 3px border 또는 small accent로 표현한다.

## 23. Accessibility Constraints & Accepted Debt

### Target personas and tasks

| Persona/상황 | 주요 task | Pass 기준 |
| --- | --- | --- |
| 키보드 중심 Analyst | Alert 목록에서 상세·guidance·상태 변경 | 모든 action과 row를 keyboard로 도달하고 현재 focus가 보임 |
| 저시력 사용자 | EDR 상태, 위험 Endpoint와 오류 확인 | 200% zoom에서 정보 손실 없이 읽고 색상 외 label이 존재 |
| 색각 이상 사용자 | severity/status 비교 | 색상 없이 text/icon/count로 구분 가능 |
| reduced-motion 사용자 | Dashboard polling과 chart 확인 | 반복 motion 없이 동일 정보 확인 가능 |
| 좁은 화면의 운영자 | 긴급 상태 확인 후 상세 이동 | 375px에서 EDR 상태, 주요 KPI, navigation과 detail flow가 동작 |

### Constraints

- WCAG 2.2 AA를 목표로 한다.
- body text contrast 4.5:1, large text와 essential graphical object 3:1 이상.
- 모든 interactive element는 visible focus, accessible name, keyboard activation을 제공한다.
- table과 chart의 핵심 정보는 text 또는 tabular form으로도 접근 가능해야 한다.
- polling으로 focus, scroll position, 선택 row를 초기화하지 않는다.
- 오류 메시지는 color만으로 구분하지 않고 원인·다음 action·requestId를 포함한다.
- icon은 `lucide-react` 또는 동등한 SVG icon을 사용하고 emoji를 icon으로 쓰지 않는다.

### Accepted Debt

현재 승인된 design/accessibility debt는 없다. 구현 중 발견한 debt는 위치, 영향받는 사용자, 심각도, 수정안, owner와 종료 조건을 이 표에 기록하고 사용자 승인 없이 묵시적으로 수용하지 않는다.

| Item | Location | Affected users | Reason | Owner / Exit |
| --- | --- | --- | --- | --- |
| 없음 | - | - | - | - |

## 24. Design Implementation Gate

제품 화면을 만들기 전에 공통 primitive showcase에서 AppShell, button/link, StatusPill, KpiCard, Panel, filter control, DataTable, Skeleton/Empty/Error의 default, hover, focus, disabled, loading, empty, error 상태를 375px, 768px, 1280px에서 확인한다. 구현 완료 판단은 실제 브라우저 `/visual-qa`와 접근성·persona walkthrough 이후에만 한다.
