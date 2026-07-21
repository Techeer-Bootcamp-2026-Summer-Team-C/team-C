# Overview Dashboard Redesign Plan

- 상태: 후속 시각 개선 완료
- 기준일: 2026-07-17
- 작업 브랜치: `overview-visual-refinement`
- 적용 범위: `frontend/`와 관련 Frontend 문서·테스트
- 다음 작업: 없음
- 구현 작업지시서: [OVERVIEW_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md](./OVERVIEW_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md)
- 승인 시안: [overview-dashboard-target.png](./assets/references/overview-dashboard-target.png)

## 1. 이 문서의 역할

이 문서는 승인된 Overview 시안을 실제 데이터만으로 구현하기 위한 단일 실행 계획이다. 구현자는 작업을 시작하기 전에 이 문서, [DESIGN.md](./DESIGN.md), [FRONTEND_SPEC.md](./FRONTEND_SPEC.md)를 읽고 한 번에 하나의 Work Package만 수행한다.

문서 책임은 다음과 같이 나눈다.

| 문서 | 책임 |
| --- | --- |
| `DESIGN.md` | 장기 시각·레이아웃·상호작용 원칙 |
| `FRONTEND_SPEC.md` | Route, query, polling, 권한과 화면 동작 계약 |
| 이 문서 | 이번 Overview 변경 범위, 순서, 상태와 검증 증거 |

충돌하면 API·데이터 의미는 `docs/contracts/API_SPEC.md`와 `docs/contracts/RISK_POLICY.md`를 우선하고, 시각 판단은 `DESIGN.md`, 실행 순서는 이 문서를 따른다.

## 2. 확정 결정

1. 승인 시안을 1440px 데스크톱 시각 기준으로 사용한다.
2. Overview는 사용자가 재배치하는 dashboard가 아니라 고정된 의사결정 dashboard로 변경한다.
3. Frontend의 drag, drop, resize, hide, restore, layout edit, layout save·reset·migration을 제거한다.
4. `react-grid-layout`을 제거한다.
5. Backend의 dashboard layout API·DB schema는 다른 client와 이전 데이터 호환을 위해 이번 작업에서 삭제하지 않는다. Frontend만 호출을 중단한다.
6. 현재 DTO에 없는 delta, previous value, 담당자, SLA, 인과관계와 임의 집계를 만들지 않는다.
7. Detection Activity만 ECharts 대상으로 삼고, Alert Severity는 semantic SVG donut과 visible text list, 순위·queue는 semantic HTML과 CSS grid로 구현한다.
8. 모바일용 별도 시안은 만들지 않는다. 1440px을 정확도 기준으로 삼되 1024px·768px·360px에서 기존 핵심 흐름과 overflow 방지 조건은 유지한다.

## 3. 페이지의 단일 목적

SOC 운영자가 Overview에서 15초 안에 다음을 판단하게 한다.

1. 현재 전체 EDR 상태는 무엇인가?
2. 상태를 악화시킨 주요 축과 분포는 무엇인가?
3. 어떤 Endpoint와 Incident부터 조사해야 하는가?

장식, 자유 배치와 설정 기능은 이 판단보다 우선하지 않는다.

## 4. 고정 레이아웃

DOM 순서와 시각 순서는 아래와 같다.

```text
Service identity                         Endpoint · Time · Refresh

[ EDR state command strip ]

[ KPI ][ KPI ][ KPI ][ KPI ]

[ Detection Activity 2fr ][ Alert Severity ][ Fleet Distribution ]

[ Highest-risk Endpoints 1fr ][ Incident Queue 1fr ]
```

### Wide desktop: 1280–1719px

- EDR state: full-width command strip
- KPI: `grid-template-columns: repeat(4, minmax(0, 1fr))`
- 분석: Detection Activity를 왼쪽 두 행에 두고 Alert Severity와 Fleet Distribution을 오른쪽에 세로로 쌓는다.
- 조사 대기열: `grid-template-columns: repeat(2, minmax(0, 1fr))`
- panel gap: 12px
- page, toolbar와 grid의 좌우 edge를 일치시킨다.

### Wallboard: 1720px 이상

- 분석: `grid-template-columns: minmax(0, 2.1fr) minmax(0, .82fr) minmax(0, .92fr)`
- Detection Activity, Alert Severity와 Fleet Distribution을 한 행에 펼쳐 시간 추세와 두 분포를 같은 시야에서 비교한다.

### 1024–1279px

- EDR state는 첫 행 전체 또는 2열 폭을 사용한다.
- KPI는 2열로 재배치한다.
- Detection Activity와 Alert Severity는 각각 전체 폭으로 재배치한다.
- 조사 대기열은 공간이 부족하면 세로로 배치한다.

### 1023px 이하

- DOM 순서를 유지해 1–2열로 재배치한다.
- 별도 모바일 미학을 만들지 않지만 기능, focus, text와 overflow를 손상시키지 않는다.

## 5. 10개 Block과 데이터 계약

| 순서 | Block | 데이터 | 표현 |
| ---: | --- | --- | --- |
| 1 | EDR State | `edrState.status`, `score`, `reasonCodes`, `threatLevel`, `collectionHealth` | 종합 상태와 두 진단 bar |
| 2 | Total Alerts | `dashboard.alerts.total` | KPI |
| 3 | Critical Alerts | `dashboard.alerts.bySeverity`의 `CRITICAL` | KPI |
| 4 | HIGH-level Endpoints | `endpointSummary.risk.highRiskEndpointCount` | 정확한 `HIGH` 등급 KPI |
| 5 | Open Incidents | `dashboard.incidents.open` | KPI |
| 6 | Detection Activity | Event·Alert time series와 Incident `openCount` | 공통 X축 small multiples |
| 7 | Alert Severity | 서버 `bySeverity` | donut과 Critical/High/Medium/Low count·percentage 목록 |
| 8 | Fleet Distribution | `endpointSummary.risk.byLevel`, `sensorHealth` | 현재 Risk level bar와 Sensor Health stack·legend |
| 9 | Highest-risk Endpoints | `GET /endpoints` 위험도 정렬 결과 | rank, 점수·level, Alert·Incident count, 상세 link |
| 10 | Incident Queue | `GET /incidents?status=OPEN` | Severity, status, alert count, last detected |

표시 비율은 서버 count와 서버 total로 계산하는 presentation 값이다. Endpoint Risk, EDR score, time bucket과 severity count를 원본 record에서 다시 집계하지 않는다.

## 6. Query와 상태

Overview 진입 시 현재 time range와 optional `endpointId`를 다음 API에 전달한다.

- `GET /dashboard/summary`
- `GET /dashboard/endpoints/summary`
- `GET /dashboard/ingest/summary`
- `GET /endpoints?sortBy=riskScore&sortOrder=desc&page=1&size=5`
- `GET /incidents?status=OPEN&sortOrder=desc&page=1&size=5`

Endpoint scope 선택기는 기존 paged `q` search를 사용하며 전체 fleet 500건을 미리 가져오지 않는다. scope 선택값과 time range는 URL을 source of truth로 유지한다.

다음 상태를 구분한다.

- Initial loading: 최종 panel geometry와 같은 skeleton
- Refetching: 기존 값을 유지하고 갱신 상태만 표시
- Partial failure: 성공한 panel은 유지하고 실패한 영역만 오류 처리
- Stale: 마지막 성공 시각과 retry action 표시
- Empty: 0과 데이터 없음 구분
- Invalid time range: API 호출 전 field 가까이에 설명

## 7. 시각화 계약

### Detection Activity

- Events, Alerts, Open incidents의 세 small multiple을 한 panel에 세로로 배치한다.
- 세 plot은 같은 time domain과 crosshair를 공유한다.
- Backend bucket을 정렬하되 누락 bucket을 임의의 0으로 채우지 않는다.
- Tooltip은 timestamp, series label, exact value와 unit을 제공한다.
- 핵심 현재 값은 hover 없이도 읽을 수 있어야 한다.
- point가 충분하지 않으면 오해를 만드는 선 대신 값·empty 설명과 table fallback을 표시한다.
- ECharts는 필요한 module만 등록하고 Overview route에서 lazy load한다.

### Alert Severity

- 서버 aggregate를 사용하는 donut과 고정 순서 `CRITICAL → HIGH → MEDIUM → LOW`의 visible 목록을 함께 제공한다.
- 각 category의 label, count와 percentage를 hover 없이 표시한다.
- total이 0이면 `0%`로 안전하게 표시하고 빈 분모 계산을 하지 않는다.
- semantic status color와 text를 함께 사용한다.

### Fleet Distribution

- 서버 Endpoint Summary가 제공하는 `risk.byLevel`과 `sensorHealth` 집계만 사용한다.
- Risk는 `CRITICAL → HIGH → MEDIUM → LOW`, Sensor Health는 `HEALTHY → DEGRADED → UNAVAILABLE` 고정 순서로 표시한다.
- 현재 snapshot임을 명시하고 시간 추세, delta 또는 원본 Endpoint 재집계를 만들지 않는다.
- Risk 또는 Sensor 집계가 비어 있으면 0개 snapshot으로 꾸미지 않고 각각의 empty 설명을 표시한다.

### 조사 대기열

- 실제 선택 상태가 없는데 selected row를 꾸미지 않는다.
- interactive row는 hover와 `focus-visible`에서만 cyan border/surface를 사용한다.
- primary identifier는 명시적인 link로 제공한다.

## 8. 파일 변경 범위

### 제거

- `frontend/src/features/dashboardLayout.ts`
- `frontend/tests/dashboard-layout-editor.test.tsx`
- `frontend/tests/dashboard-layout.test.ts`
- `frontend/tests/dashboard-layout-v1.fixture.ts`
- `react-grid-layout` package와 CSS import
- Frontend API client의 layout GET/PUT/DELETE method
- layout editor 전용 translation과 CSS

### 재구성

- `frontend/src/pages/OverviewPage.tsx`: query, URL filter와 page state만 소유
- `frontend/src/features/overviewWidgetRegistry.tsx`: 동적 registry를 제거하고 고정 composition으로 대체
- `frontend/src/components/charts.tsx`: layout density 의존 제거, Detection Activity 계약 반영
- `frontend/src/components/ui.tsx`: EDR state 두 축과 공통 chart fallback 보강
- `frontend/src/styles/pages/overview.css`: 승인 시안의 고정 grid와 panel geometry
- `frontend/src/i18n/translations.ts`: layout editor copy 제거, 새 chart·state copy 추가
- `frontend/src/api/endpoints.ts`: 사용하지 않는 layout client 제거

### 권장 결과 구조

```text
frontend/src/features/overview/
  OverviewDashboard.tsx
  DetectionActivityPanel.tsx
  EndpointScopePicker.tsx
  AlertSeverityDonut.tsx
  InvestigationQueues.tsx
  overviewChartModel.ts
```

파일을 기계적으로 잘게 나누지 않는다. 두 곳 이상에서 재사용하거나 독립 테스트 가치가 있을 때만 분리한다.

## 9. Work Packages

한 번에 하나만 `진행 중`으로 변경한다.

### OVR-00. 기준 문서와 승인 시안

- 상태: 완료
- 승인 시안을 repo에 보관한다.
- 종료된 이전 리디자인 문서를 제거하고 장기 문서의 충돌 내용을 갱신한다.
- 새 branch와 이 실행계획을 생성한다.

완료 조건: 문서 링크 무결성, branch와 git diff 확인.

### OVR-01. DnD 제거와 고정 골격

- 상태: 완료
- `react-grid-layout`, layout editor state, 저장 호출과 migration을 제거한다.
- 10개 block의 고정 DOM과 responsive CSS grid를 만든다.
- Backend layout route와 schema는 수정하지 않는다.

완료 조건: layout editor UI·API 호출·dependency가 없고 10개 block skeleton이 승인 순서로 렌더링됨.

- 변경 파일: `frontend/src/pages/OverviewPage.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/api/endpoints.ts`, `frontend/src/components/charts.tsx`, `frontend/src/styles.css`, `frontend/src/styles/pages/overview.css`, `frontend/src/i18n/translations.ts`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/tests/overview-redesign.test.tsx`, `frontend/tests/locale.test.tsx`
- 설계 판단: 저장 registry를 DOM 순서의 source of truth로 사용하지 않고, `EDR + KPI 4` → `2:1:1` → `1:1`의 명시적인 CSS grid composition으로 교체했다. 1280px 미만은 1–2열, 767px 이하는 DOM 순서 단일 열로 배치한다.
- 삭제한 코드: `dashboardLayout.ts`, `overviewWidgetRegistry.tsx`, layout GET/PUT/DELETE client, RGL render/import/CSS, editor hook, debounce, revision conflict, v1 migration, hide/restore/reset, drag/resize keyboard surface, layout 전용 번역과 CSS, layout editor/unit test 3개.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx locale.test.tsx` → 2 files / 13 tests passed. `npm run typecheck` → passed. `rg -n "react-grid-layout|dashboardLayout|saveDashboardLayout|resetDashboardLayout" src tests package.json` → Frontend runtime은 0건, Backend 호환성을 유지하는 generated schema와 부재 검증 test 문자열만 남음.
- 브라우저 QA: Vite + Playwright contract-shaped mock으로 1440×1100 smoke. 10개 block DOM 순서, 첫 행 5열, 분석 2:1:1, queue 1:1, toolbar/grid 좌우 edge를 확인했다. DnD/edit/reset control은 accessibility snapshot에 없음. 기존 `EdrStatePill`의 이유 문구가 고정 첫 panel에서 잘리는 것은 OVR-02 수정 대상으로 확인함.
- Bundle 변화: `react-grid-layout`/`react-resizable` dependency와 lockfile entry를 제거함. production bundle 수치는 지시대로 OVR-05 build에서 1회 측정한다.
- 남은 위험: EDR 상태 panel은 두 진단 축을 아직 표시하지 않고, Endpoint scope는 아직 500건 prefetch select를 유지한다. 각각 OVR-02, OVR-04에서 제거한다.
- 다음 Package: OVR-02

### OVR-02. 상태와 KPI

- 상태: 완료
- EDR overall, Threat Level, Collection Health를 구현한다.
- Total Alerts, Critical Alerts, HIGH-level Endpoints, Open Incidents를 연결한다.
- reason code, 계산 시각, time scope와 drill-down을 보존한다.

완료 조건: API에 없는 delta 없이 normal·zero·empty·stale를 표시.

- 변경 파일: `frontend/src/components/ui.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/styles.css`, `frontend/src/styles/pages/overview.css`, `frontend/src/i18n/translations.ts`, `frontend/tests/overview-redesign.test.tsx`, `frontend/tests/components.test.tsx`, `frontend/tests/locale.test.tsx`
- 설계 판단: `edrState.status/score`를 overall posture로, 서버가 제공하는 `threatLevel`과 `collectionHealth`를 독립 진단 bar로 그대로 표시했다. KPI는 `alerts.totalCount`, 서버 `bySeverity`의 `CRITICAL`, `risk.highRiskEndpointCount`, `incidents.openCount`만 사용했고 delta·previous value는 만들지 않았다. High-risk Endpoint는 계약상 정확한 `HIGH` count이므로 `CRITICAL`을 합산하지 않았다.
- 삭제한 코드: 점수 하나와 일부 reason만 보이던 `EdrStatePill`과 관련 dead CSS를 제거했다. KPI에 임의 추세·delta·가짜 comparison을 추가하지 않았다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx components.test.tsx locale.test.tsx` → 3 files / 17 tests passed. normal EDR/KPI, 0점·빈 reason, 두 axis progressbar, stale warning, EN/KO key를 targeted test로 확인했다. `npm run typecheck` → passed.
- 브라우저 QA: contract-shaped mock으로 1440×1100을 다시 확인했다. overall 72/YELLOW, Threat 78/RED, Collection 61/YELLOW, 전체 reason과 계산 시각이 잘림 없이 보이며 4개 KPI와 drill-down URL이 accessibility snapshot에 노출된다. 증거: `frontend/output/playwright/overview-redesign/ovr-02-1440.png`.
- Bundle 변화: 새 runtime dependency 없음. EDR/KPI는 기존 React·CSS만 사용했으며 production 수치는 OVR-05 build에서 측정한다.
- 남은 위험: Detection Activity는 아직 기존 SVG이고 severity는 donut이다. Endpoint scope의 500건 prefetch와 queue 표현은 OVR-04 범위로 남아 있다.
- 다음 Package: OVR-03

### OVR-03. 정량 시각화

- 상태: 완료
- ECharts small multiples PoC와 lazy loading을 구현한다.
- Alert Severity와 Endpoint Risk를 HTML/CSS bar로 교체한다.
- table fallback, keyboard, resize, print와 bundle 변화를 기록한다.

완료 조건: exact tooltip, shared time domain, fallback, reduced motion과 build 통과.

- 변경 파일: `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/components/charts.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/features/overview/DetectionActivityPanel.tsx`, `frontend/src/features/overview/DistributionBars.tsx`, `frontend/src/features/overview/overviewChartModel.ts`, `frontend/src/styles/pages/overview.css`, `frontend/src/i18n/translations.ts`, `frontend/tests/overview-redesign.test.tsx`
- 설계 판단: ECharts는 `echarts/core`에서 Line, Grid, Tooltip, AxisPointer와 Canvas renderer만 등록하고 Overview composition에서 dynamic import했다. Events, Alerts, Open incidents를 세 grid에 그리되 union time domain만 공유하고 각 서버 series의 실제 point만 전달했다. polling data 갱신 뒤에는 `renderedRef`로 animation을 다시 켜지 않으며 reduced-motion에서는 최초 animation도 끈다. 핵심 최신 값, keyboard bucket과 table fallback은 canvas 밖의 semantic DOM으로 제공했다.
- 삭제한 코드: Overview 전용 SVG `DetectionActivityChart`, 3열 mini chart와 severity donut 구현을 제거했다. Alert Severity와 Endpoint Risk는 고정 `CRITICAL → HIGH → MEDIUM → LOW` HTML/CSS bar로 교체했다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx locale.test.tsx` → 2 files / 15 tests passed. time series 정렬, union domain, 누락 bucket 비보간, 고정 분포 순서, count/percentage와 total=0의 0% 처리를 확인했다. `npm run typecheck` → passed. 지시대로 production build는 OVR-05에서 한 번만 실행한다.
- 브라우저 QA: 1440px 정상 렌더와 console error 0을 확인했다. keyboard focus 시 `Jul 15, 09:00 PM: Events 1200, Alerts 6, Open incidents 2`, ECharts tooltip도 같은 timestamp와 exact value를 반환했다. 1440→1024 resize 후 canvas 폭 626→886px로 재계산되었고, print media에서는 canvas가 숨고 table이 표시되었다. reduced-motion media query `true` 경로를 확인했다. 증거: `frontend/output/playwright/overview-redesign/ovr-03-1440.png`과 `ovr03-interaction-qa.js`.
- Bundle 변화: `echarts@6.1.0`을 OVR-03에서만 추가했고 route 전용 lazy chunk 경계를 만들었다. tree-shaken production chunk 크기는 OVR-05 단일 build 결과에서 기록한다.
- 남은 위험: Endpoint scope는 아직 500건 prefetch select이고, queue는 link-list이다. chart의 최종 360px overflow, KO, 200% zoom과 release bundle 예산은 OVR-05 matrix에서 최종 확인한다.
- 다음 Package: OVR-04

### OVR-04. 조사 대기열과 UX 상태

- 상태: 완료
- Highest-risk Endpoints와 Incident Queue를 승인 시안에 맞춘다.
- Endpoint scope를 paged search로 바꾸고 500건 prefetch를 제거한다.
- loading, partial error, stale, empty와 focus 상태를 마무리한다.

완료 조건: 모든 link와 URL context, KO/EN, keyboard flow 통과.

- 변경 파일: `frontend/src/pages/OverviewPage.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/features/overview/EndpointScopePicker.tsx`, `frontend/src/features/overview/InvestigationQueues.tsx`, `frontend/src/styles/pages/overview.css`, `frontend/src/i18n/translations.ts`, `frontend/tests/overview-redesign.test.tsx`
- 설계 판단: 위험 Endpoint ranking은 `size=5` 서버 정렬 query로 분리했고 선택 scope에서는 `endpointIds`를 서버에 전달한다. scope picker는 열릴 때와 검색어 변경 시 `size=20` paged `q` search를 수행하며 URL의 `endpointId`만 source of truth로 갱신한다. 두 queue는 caption, column header, row header와 명시적 상세 link가 있는 semantic table로 바꿨고 선택 class는 사용하지 않는다. queue별 pending/error/stale/data를 독립 처리해 한 영역 실패 시 성공 영역을 유지한다.
- 삭제한 코드: 전체 fleet `size=500` prefetch, client-side selected Endpoint filtering과 5건 slice, native 500-option select, 시각적으로 계속 선택된 link-list row를 제거했다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx components.test.tsx locale.test.tsx` → 3 files / 19 tests passed. 20-row search request와 `q`, selected URL id, partial queue failure 시 성공 table 유지, empty/stale 공통 상태, 상세 link와 selected-row 부재를 확인했다. `npm run typecheck` → passed. Frontend source에서 `size: 500`, inventory query와 기존 select는 0건이다.
- 브라우저 QA: 실제 요청 `GET /endpoints?page=1&size=20&q=FIN&sortBy=riskScore&sortOrder=desc`, 두 table의 접근성 이름, Endpoint link keyboard focus, selected row 0건을 확인했다. 1024px page-level horizontal overflow는 없었고 console error/warning 0건이다. 증거: `frontend/output/playwright/overview-redesign/ovr-04-1440.png`과 `ovr04-interaction-qa.js`.
- Bundle 변화: 새 dependency 없음. 기존 native select 대신 route-local React Query search UI와 semantic table만 추가했다. production 수치는 OVR-05 build에서 측정한다.
- 남은 위험: 전체 viewport matrix, KO/EN 전환, 200% zoom, reduced motion, normal/zero/empty/partial/stale 브라우저 상태와 실제 build chunk 크기는 OVR-05 Release Gate에서 한 번에 검증한다.
- 다음 Package: OVR-05

### OVR-05. 통합 검증과 문서 동기화

- 상태: 완료
- 1440px에서 승인 시안과 screenshot diff를 검토한다.
- 1280, 1024, 768, 360px에서 overflow와 핵심 흐름을 확인한다.
- 테스트, build, OpenAPI drift와 bundle 결과를 기록한다.
- 최종 Frontend spec과 실제 코드를 동기화한다.

완료 조건: 아래 Release Gate 전부 통과.

- 변경 파일: OVR-01~04에 기록된 Frontend source·test·package·문서 파일과 이 실행계획. Backend runtime, OpenAPI artifact, migration과 dashboard layout 저장 row는 변경하지 않았다.
- 설계 판단: 승인 시안의 정보 위계를 고정하되 실제 계약이 없는 delta·담당자·SLA는 넣지 않았다. Release audit에서 서로 다른 time series의 누락 bucket을 union domain의 명시적 `null`로 보존해 ECharts가 빈 구간을 선으로 잇지 않게 했고, chart에 실제 bucket range·`Asia/Seoul` timezone·server bucket 단위를 명시했다.
- 삭제한 코드: OVR-01~04의 DnD/layout editor·API client·dependency·500건 prefetch·donut·Overview SVG mini chart 제거를 최종 확인했다. `react-grid-layout`은 `npm ls` 결과 없음이며 Backend 호환 generated layout schema는 유지된다.
- 실행한 검증: 전체 `npm run test` → 21 files / 88 tests passed. `npm run typecheck` → passed. `npm run lint`는 최초 local QA evidence script와 unused import를 찾아 수정한 뒤 passed. `npm run openapi:check`는 최초 sandbox의 `~/.cache/uv` 권한으로 실패했으나 허용된 동일 명령 재실행에서 `OpenAPI artifact is current`와 generated schema check가 passed. `npm run build` → passed. Release audit의 null-gap/time-context 보정 뒤 targeted 2 files / 16 tests, lint와 final production build도 passed. `git diff --check` → passed.
- 브라우저 QA: 1440, 1280, 1024, 768, 360px 모두 10/10 block visible, page-level overflow `false`. KO/EN label, Endpoint search focus, chart bucket keyboard summary, queue link focus를 확인했다. CDP page scale 2에서 overflow `false`, reduced-motion에서 ECharts `data-animation=disabled`. normal, zero(0 KPI·8개 0%), empty(activity·Endpoint·Incident empty), partial failure(Incident table 유지), stale(마지막 dashboard 유지)를 확인했다. final normal console은 error/warning 0건이다.
- 승인 시안 비교: `overview-dashboard-target.png`와 `frontend/output/playwright/overview-redesign/ovr-05-final-1440.png`를 직접 비교했다. 상태+KPI 한 행, 분석 `2:1:1`, queue `1:1`, dark-neutral panel hierarchy와 조사 우선순위는 일치한다. 현재 DTO에 없는 시안의 delta/추가 metadata는 의도적으로 생략했다. canvas 크기가 달라 자동 pixel diff 수치는 사용하지 않았다.
- Bundle 변화: final `OverviewPage` 16.46 kB / 5.19 kB gzip, Overview 전용 lazy `DetectionActivityPanel` 499.35 kB / 170.80 kB gzip, 공통 index 355.19 kB / 110.98 kB gzip. `react-grid-layout`은 제거되고 ECharts는 route lazy chunk로 격리됐다. 변경 전 production artifact가 없어 허위 절감 delta는 계산하지 않았다.
- 남은 위험: ECharts lazy chunk 170.80 kB gzip은 기능·분리 기준은 통과했지만 크므로 후속 bundle budget에서 재평가할 가치가 있다. 최종 시각·상태 QA는 현재 API 계약 모양의 browser mock으로 수행했으며 이 세션에서 실행 중인 Backend가 없어 live integration screenshot은 검증하지 않았다.
- 다음 Package: 없음

## 10. Test Plan

자동 테스트:

- 9개 block의 DOM 순서와 필수 label
- layout edit, drag, resize, hide control 부재
- layout API가 호출되지 않음
- EDR 두 진단 축과 reason 표시
- severity donut count/percentage의 정상·0 처리
- time series 정렬과 누락 bucket 보존
- 위험 Endpoint 최대 5개와 상세 link
- Incident 필수 field와 상세 link
- Endpoint/time URL state
- EN/KO translation
- keyboard focus와 fallback table

검증 명령:

- OVR-01~04에서는 변경 영역의 targeted test와 Package 종료 시 typecheck만 실행한다.
- 전체 test, lint, build, OpenAPI check와 viewport matrix는 OVR-05에서 한 번 실행한다.
- Frontend-only 범위이므로 Docker build/rebuild, 전체 stack 재기동과 Backend 전체 test는 기본 검증에서 제외한다.

```bash
cd frontend
npm run openapi:check
npm run typecheck
npm run lint
npm run test
npm run build
```

Browser QA:

- 1440px: EDR strip, KPI 4열, 분석 `2:1`, 대기열 `1:1`
- 1280px: label 충돌·horizontal overflow 없음
- 1024px·768px: DOM 순서와 주요 action 유지
- 360px: 기능 손실과 page-level horizontal overflow 없음
- KO/EN, keyboard-only, 200% zoom, reduced motion
- normal, zero, empty, partial failure, stale
- chart tooltip, table fallback와 print

## 11. Release Gate

- [x] 승인 시안과 1440px 정보 위계가 일치한다.
- [x] drag/drop/resize/layout edit 코드와 dependency가 없다.
- [x] Frontend가 dashboard layout API를 호출하지 않는다.
- [x] Backend 계약과 저장 데이터는 이번 변경으로 손상되지 않는다.
- [x] API에 없는 값과 오해 가능한 추정을 표시하지 않는다.
- [x] 핵심 값은 hover 없이 읽을 수 있다.
- [x] chart에 단위, time range, timezone과 table fallback이 있다.
- [x] keyboard, focus, 200% zoom과 reduced motion을 확인했다.
- [x] 1440, 1280, 1024, 768, 360px에서 overflow를 확인했다.
- [x] KO/EN에서 label과 control이 깨지지 않는다.
- [x] OpenAPI check, typecheck, lint, test와 build가 통과한다.
- [x] bundle 변화와 남은 위험을 기록했다.

## 12. 완료 기록 형식

각 Package를 완료할 때 해당 절에 다음을 추가한다.

```text
상태:
변경 파일:
설계 판단:
삭제한 코드:
실행한 검증:
브라우저 QA:
Bundle 변화:
남은 위험:
다음 Package:
```

검증하지 않은 항목을 완료로 표시하지 않는다. commit, push와 PR은 사용자가 별도로 요청한 경우에만 수행한다.

## 13. Post-review remediation

코드리뷰에서 확인한 회귀를 Backend 계약 변경 없이 수정한다. 기존 OVR-01~05의 완료 기록은 당시 실행 증거로 보존하고, 아래 Package를 한 번에 하나씩 진행한다.

### FIX-01. Core partial failure

- 상태: 완료
- Dashboard Summary와 Endpoint Summary를 독립 panel state로 분리한다.
- 성공한 summary·queue panel은 sibling resource의 초기 실패와 관계없이 유지한다.
- 모든 panel resource가 실패한 경우에만 page-level error를 표시한다.
- 변경 파일: `frontend/src/pages/OverviewPage.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/styles/pages/overview.css`, `frontend/tests/overview-redesign.test.tsx`, 이 실행계획.
- 설계 판단: Dashboard Summary 의존 6개 block, Endpoint Summary 의존 2개 block, Endpoint·Incident queue를 독립 resource state로 분리했다. 일부 resource만 실패하면 고정 10-block DOM에서 해당 block만 error를 표시하고, 모든 panel resource가 data 없이 실패한 경우에만 page-level error를 사용한다. refetch error에 기존 data가 있으면 기존 stale 경로를 유지한다.
- 삭제한 코드: 두 core query가 모두 성공해야 dashboard 전체를 만들던 `dashboardData` gate와 page-level core loading gate를 제거했다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx` → 1 file / 10 tests passed. Dashboard 성공·Endpoint Summary 실패와 반대 조합에서 성공 panel, partial warning, 실패 block error와 10개 DOM 순서를 확인했다. `npm run typecheck` → passed. `git diff --check` → passed.
- 브라우저 QA: contract-shaped mock 1440×1100에서 Endpoint Summary 실패 시 Total Alerts 128과 Alert Severity 유지, Endpoint Risk만 error, 10 blocks, partial warning, overflow `false`; Dashboard Summary 실패 시 High-risk Endpoints 2, Endpoint Risk와 Incident Queue 유지, Dashboard 의존 block error, 10 blocks, overflow `false`. 증거: `frontend/output/playwright/overview-redesign/fix-01-endpoint-summary-failure-1440.png`, `fix-01-dashboard-summary-failure-1440.png`.
- Bundle 변화: runtime dependency와 lazy import 변화 없음. production bundle은 FIX-04 단일 build에서 비교한다.
- 남은 위험: KPI drill-down time scope와 chart null/selection 계약은 FIX-02 범위로 남아 있다.
- 다음 Package: FIX-02

### FIX-02. Time scope와 chart 데이터 계약

- 상태: 완료
- KPI drill-down에 현재 time range를 보존한다.
- 누락 bucket의 접근성 요약과 유효하지 않은 chart selection을 수정한다.
- 변경 파일: `frontend/src/pages/OverviewPage.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/features/overview/DetectionActivityPanel.tsx`, `frontend/tests/overview-redesign.test.tsx`, 이 실행계획.
- 설계 판단: Total Alerts, Critical Alerts와 Open Incidents는 현재 `timePreset`과 선택 Endpoint를 drill-down URL에 보존하고, `CUSTOM`이면 계약의 `from`·`to`도 그대로 전달한다. 현재 위험 snapshot인 High-risk Endpoints는 `endpointIds`만 유지하고 시간 필터를 붙이지 않는다. 차트 접근성 요약은 union domain의 최신 timestamp에 series point가 없으면 `None`으로 읽으며, polling model에 기존 timestamp가 남아 있을 때만 선택을 보존한다.
- 삭제한 코드: KPI를 시간 context 없이 이동시키던 단순 URL 조합을 제거했고, 누락 최신 bucket을 `0`으로 대체하던 접근성 fallback을 제거했다. 서버 bucket을 새로 생성하거나 보간하지 않았다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx locale.test.tsx` → 2 files / 20 tests passed. preset·CUSTOM·Endpoint query 보존, snapshot query 분리, 누락 최신 bucket의 `None`, 유효하지 않은 selection 해제를 확인했다. `npm run typecheck` → passed. `git diff --check` → passed.
- 브라우저 QA: 1440×1100에서 `LATEST_15M`과 `CUSTOM`의 Alerts·Incidents href에 time range와 `endpointId=2`가 유지되고, High-risk Endpoints href에는 `endpointIds=2`만 있으며 time query가 없음을 확인했다. 누락 bucket 요약은 `Events None`, 선택된 `Jul 15, 09:00 AM` bucket이 polling 후 사라지면 live selection과 pressed button이 모두 0건이 됐다. 10 blocks, page overflow `false`, 해당 실행의 console error/warning 0건. 증거: `frontend/output/playwright/overview-redesign/fix-02-time-scope-chart-1440.png`.
- Bundle 변화: runtime dependency와 lazy chunk 경계 변화 없음. production bundle은 FIX-04 단일 build에서 재측정한다.
- 남은 위험: Endpoint picker의 outside-pointer close가 trigger로 focus를 되돌리는 회귀는 FIX-03 범위로 남아 있다.
- 다음 Package: FIX-03

### FIX-03. Endpoint picker focus

- 상태: 완료
- close reason별 focus 복귀 정책과 pointer·keyboard 회귀 테스트를 추가한다.
- 변경 파일: `frontend/src/features/overview/EndpointScopePicker.tsx`, `frontend/tests/overview-redesign.test.tsx`, 이 실행계획.
- 설계 판단: 바깥 pointer down은 사용자가 이동하려는 새 대상의 focus를 보존하도록 trigger focus 복귀를 생략한다. Escape와 option 선택은 picker 안에서 시작한 작업의 종료이므로 기존처럼 animation frame 뒤 Endpoint scope trigger로 focus를 복귀한다.
- 삭제한 코드: 모든 close reason에서 무조건 trigger에 focus를 덮어쓰던 동작을 제거했다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx` → 1 file / 13 tests passed. 외부 button pointer close 후 외부 focus 유지와 Escape close 후 trigger focus 복귀를 확인했다. `npm run typecheck` → passed. `git diff --check` → passed.
- 브라우저 QA: 1440×1100 실제 UI에서 열린 Endpoint picker 밖의 Time range를 클릭하면 Endpoint dialog가 닫히고 active element가 `Time range`로 유지되며 해당 dialog가 열렸다. Escape와 All endpoints 선택 뒤에는 animation frame을 기다려 active element가 모두 `Endpoint scope`로 돌아왔다. picker 재개방 시 search input focus, 10 blocks, page overflow `false`, 해당 실행의 console error/warning 0건. 증거: `frontend/output/playwright/overview-redesign/fix-03-endpoint-focus-1440.png`.
- Bundle 변화: dependency와 lazy chunk 변화 없음. boolean close policy와 targeted test만 추가했다.
- 남은 위험: Release QA의 block visibility 판정이 width만 검사하는 문제와 전체 회귀 재검증은 FIX-04 범위로 남아 있다.
- 다음 Package: FIX-04

### FIX-04. Release Gate 재검증

- 상태: 완료
- viewport rendered/intersection 검사를 분리하고 screenshot 증거를 보강한다.
- 전체 test, lint, typecheck, build, OpenAPI check와 browser matrix를 한 번 실행한다.
- 변경 파일: `frontend/src/features/overview/DetectionActivityPanel.tsx`, `frontend/output/playwright/overview-redesign/ovr05-release-qa.js`, 이 실행계획. FIX-01~03의 source·test 변경을 함께 Release Gate로 검증했다.
- 설계 판단: viewport QA에서 폭만 양수인 element를 visible로 간주하지 않는다. computed style·width·height로 rendered block을 집계하고, 초기 viewport 교차 수와 각 block을 순차 스크롤한 실제 교차 id를 별도로 기록한다. chart selection 정리는 lint-safe한 이전 model 비교 state로 유지해 유효한 timestamp만 polling 간 보존한다.
- 삭제한 코드: `getBoundingClientRect().width > 0`만 사용하던 `visibleBlockCount`를 제거했다. selection을 effect에서 동기 setState하던 구현도 conditional previous-model state 조정으로 교체했다.
- 실행한 검증: 전체 `npm run test` → 21 files / 93 tests passed. `npm run lint` → passed. `npm run typecheck` → passed. `npm run build` → passed. `npm run openapi:check`는 첫 sandbox 실행이 `~/.cache/uv` 접근 권한으로 실패했고, 허용된 환경에서 동일 명령을 재실행해 `OpenAPI artifact is current`와 generated schema check가 passed. `git diff --check` → passed. `npm ls react-grid-layout --depth=0` → empty.
- 브라우저 QA: 1440, 1280, 1024, 768, 360px 모두 10 blocks rendered, 순차 scroll intersection 10/10, page overflow `false`. 초기 viewport intersection은 실제 화면 높이에 따라 각각 10/10/6/5/3으로 기록해 fold 아래 block을 visible로 과장하지 않았다. KO/EN label, Endpoint search keyboard focus, chart bucket summary, queue link focus, CDP 200% zoom(scale 2, overflow `false`), reduced motion(`animation=disabled`)을 확인했다. zero(0 KPI·8개 0%), empty(activity·Endpoint·Incident), partial failure(경고·Endpoint error·Incident table 유지), stale(경고·dashboard 유지)를 확인했다. final normal capture는 console error/warning과 page error가 모두 0건이다. 증거: `frontend/output/playwright/overview-redesign/ovr-05-{1440,1280,1024,768,360}.png`, `ovr-05-final-1440.png`, `ovr05-release-qa.js`.
- 승인 시안 비교: `docs/frontend/assets/references/overview-dashboard-target.png`와 final 1440 screenshot을 직접 다시 열었다. 상태+4 KPI, 분석 `2:1:1`, queue `1:1`, dark-neutral panel hierarchy와 조사 우선순위는 일치한다. 기존 App Shell과 실제 계약 기반 content 차이는 유지하며 pixel diff 수치는 사용하지 않았다.
- Bundle 변화: final `OverviewPage` 17.11 kB / 5.41 kB gzip, lazy `DetectionActivityPanel` 499.50 kB / 170.83 kB gzip, 공통 index 355.19 kB / 110.98 kB gzip. 기존 OVR-05 기록 대비 OverviewPage는 +0.65 kB / +0.22 kB gzip, DetectionActivityPanel은 +0.15 kB / +0.03 kB gzip이며 공통 index는 동일하다. `react-grid-layout`은 계속 0건이다.
- 남은 위험: ECharts lazy chunk 170.83 kB gzip은 route 격리는 유지하지만 여전히 크다. 브라우저 상태 matrix는 현재 API 계약 모양의 mock으로 검증했으며 이 세션에서 live Backend integration은 검증하지 않았다. partial·stale QA의 의도된 400 응답은 browser network console에 오류를 남기지만 final normal 상태는 clean하다.
- 다음 Package: 없음

## 14. Post-merge visual refinement

2026-07-17 팀 피드백을 반영하되 색상값과 font family는 다음 수정에서 팀이 별도로 확정한다. 이번 후속 작업은 현재 semantic token을 임시값으로 재사용하며 새 raw color나 외부 font를 추가하지 않는다. 팀 token이 전달되면 component selector를 다시 수정하지 않고 `frontend/src/styles/tokens.css`의 역할 token만 교체할 수 있어야 한다.

확정 범위:

- 상단 EDR 상태를 full-width command strip으로 분리하고 4개 KPI의 불필요한 높이를 줄인다.
- red는 Critical/RED/error에만 사용하고 Total Alert와 일반 OPEN Incident에는 사용하지 않는다.
- Alert Severity를 실제 서버 count/total 기반 donut으로 변경한다.
- Endpoint Risk 분포 block을 Overview에서 제거하고 전체를 9-block으로 재구성한다.
- Detection Activity의 세로 series label과 timestamp button 군집을 제거하고 명시적 legend, compact bucket inspector와 table fallback을 유지한다.
- Highest-risk Endpoint는 progress bar와 badge가 반복하는 위험 표현을 제거하고 compact ranked ledger로 변경한다.
- Incident Queue는 title, severity, status, Alert count와 last detected를 compact queue row로 제공한다.
- Overview의 중복 breadcrumb/page heading을 제거하고 AppShell에 service name을 표시한다. 미확정 service name은 `VITE_SERVICE_NAME`으로 주입하며 fallback은 기존 `EDR Console`이다.

계약 경계:

- Backend, API, DTO, enum, OpenAPI와 Risk 계산 정책을 변경하지 않는다.
- 누락 bucket은 `0`으로 바꾸지 않고 `None`/`없음` 의미를 유지한다.
- 담당자, SLA, delta, previous value, sparkline과 원본 record client 집계를 추가하지 않는다.
- 다른 page의 breadcrumb와 page header는 유지한다.

### REF-01. 디자인 계약과 service identity 구조

- 상태: 완료
- 색상·font token의 임시값 정책을 기록한다.
- `VITE_SERVICE_NAME`과 fallback을 AppShell brand/top bar에 연결한다.
- Overview에서만 중복 breadcrumb와 visible PageHeader를 제거하되 document heading은 유지한다.

완료 조건: 기존 route breadcrumb 회귀 없이 Overview 상단에 service name 하나와 screen-reader heading이 존재하고 targeted test·typecheck가 통과한다.

- 변경 파일: `frontend/src/config/branding.ts`, `frontend/src/components/AppShell.tsx`, `frontend/src/pages/OverviewPage.tsx`, `frontend/src/styles/shell.css`, `frontend/tests/app-shell-foundation.test.tsx`, 이 실행계획.
- 설계 판단: service name은 build-time `VITE_SERVICE_NAME`을 source로 사용하고 미지정 시 기존 `EDR Console`로 fallback한다. Overview route에서만 top bar breadcrumb와 visible PageHeader를 제거하고 service name 하나를 표시했으며, 접근성 heading은 visually hidden `h1`으로 유지했다. 다른 route breadcrumb와 page title은 변경하지 않았다.
- 삭제한 코드: Overview의 visible `CURRENT POSTURE / Overview / description` PageHeader와 root route의 `EDR / Overview` breadcrumb 중복을 제거했다.
- 실행한 검증: `npm run test -- app-shell-foundation.test.tsx overview-redesign.test.tsx` → 2 files / 16 tests passed. `npm run typecheck` → passed. `git diff --check` → passed.
- 브라우저 QA: 1440×1100에서 top bar service name `EDR Console`, Overview breadcrumb 0건, visible `h1` 0건, page-level overflow `false`를 확인했다. accessibility snapshot에는 Overview heading이 유지된다. 증거: `frontend/output/playwright/overview-redesign/ref-01-1440.png`, `ref-01-snapshot.md`.
- Bundle 변화: runtime dependency 없음. 작은 build-time config module만 추가했으며 production 수치는 REF-05에서 측정한다.
- 남은 위험: 실제 service name과 팀 color/font token은 아직 미확정이며 다음 수정에서 `VITE_SERVICE_NAME`과 token 값으로 교체해야 한다.
- 다음 Package: REF-02

### REF-02. EDR Command Strip과 compact KPI

- 상태: 완료
- EDR State를 full-width command strip으로 옮긴다.
- KPI 4개를 별도 compact row로 구성하고 single-value dead space와 red 피로도를 줄인다.

완료 조건: 1440px에서 EDR strip과 KPI row의 정보 위계가 명확하고 normal·zero·partial state가 유지된다.

- 변경 파일: `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/components/ui.tsx`, `frontend/src/styles/pages/overview.css`, 이 실행계획.
- 설계 판단: EDR state를 KPI와 같은 높이에 묶지 않고 `overall / Threat·Collection axes / reason·calculated time` 3구역의 full-width command strip으로 분리했다. KPI는 4열 124px row로 줄였다. Total Alerts는 neutral, Critical Alerts만 critical, HIGH snapshot과 일반 OPEN Incident는 warning tone을 사용해 red가 모든 문제 지표를 장식하지 않게 했다.
- 삭제한 코드: EDR state와 KPI 4개를 억지로 같은 180px 높이에 맞추던 5열 summary row, Total Alerts와 OPEN Incident의 critical tone을 제거했다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx components.test.tsx locale.test.tsx` → 3 files / 24 tests passed. normal·zero EDR와 independent partial failure를 포함한다. `npm run typecheck` → passed. `git diff --check` → passed.
- 브라우저 QA: 1440×1100에서 EDR strip 124px, KPI 4개 각 124px, critical KPI 1개, DOM 10-block, page overflow `false`를 확인했다. 증거: `frontend/output/playwright/overview-redesign/ref-02-1440.png`.
- Bundle 변화: dependency와 lazy chunk 경계 변화 없음. CSS grid와 icon 교체만 포함하며 production 수치는 REF-05에서 측정한다.
- 남은 위험: Alert Severity와 Endpoint Risk는 아직 기존 bar이고 Detection Activity의 Y-axis label·bucket buttons도 남아 있다.
- 다음 Package: REF-03

### REF-03. Detection Activity와 Alert Severity donut

- 상태: 완료
- Detection Activity의 rotated Y-axis label과 timestamp button 군집을 제거한다.
- chart series legend와 keyboard bucket inspector를 제공한다.
- Alert Severity를 server aggregate 기반 donut과 visible category list로 구현한다.

완료 조건: missing bucket 보존, exact value inspection, reduced motion, resize, print와 table fallback이 통과한다.

- 변경 파일: `frontend/src/features/overview/AlertSeverityDonut.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/features/overview/DetectionActivityPanel.tsx`, `frontend/src/styles/tokens.css`, `frontend/src/styles/pages/overview.css`, `frontend/src/i18n/translations.ts`, `frontend/tests/overview-redesign.test.tsx`, 이 실행계획. `frontend/src/features/overview/DistributionBars.tsx`는 삭제했다.
- 설계 판단: Alert Severity donut은 새 chart dependency 없이 semantic SVG와 항상 보이는 `Critical → High → Medium → Low` count/percentage list로 구현했다. 원호는 서버 `bySeverity / totalCount` presentation 비율만 사용하고 0 total은 중립 track으로 유지한다. Detection Activity는 series label을 horizontal legend로 옮기고 모든 timestamp button 대신 전체 server bucket을 가진 keyboard select 한 개를 제공한다. Alert series는 semantic critical red가 아닌 chart accent, Open Incident는 warning chart token을 사용한다.
- 삭제한 코드: Endpoint Risk Overview block, horizontal distribution bar component, Detection Activity rotated Y-axis series label과 timestamp button 군집을 제거했다. Backend Endpoint Summary query와 Risk 정책은 KPI를 위해 유지한다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx locale.test.tsx components.test.tsx` → 3 files / 24 tests passed. 9-block 순서, donut normal·zero, missing bucket `None`, invalid selection reset과 table fallback을 확인했다. `npm run typecheck` → passed. `git diff --check` → passed.
- 브라우저 QA: 1440×1100에서 9 blocks, Endpoint Risk block 0건, donut segment 4개, bucket button 0건, select option 5개와 exact selected summary를 확인했다. 분석 grid는 약 `2:1`, overflow `false`다. 1024×900 resize 후 분석 panel은 1열 912px, chart와 donut content width 886px, overflow `false`였다. 증거: `frontend/output/playwright/overview-redesign/ref-03-1440.png`, `ref-03-1024.png`.
- Bundle 변화: dependency와 ECharts module registration 변화 없음. CSS/SVG donut만 추가하고 제거된 HTML bar component를 대체했다. production 수치는 REF-05에서 측정한다.
- 남은 위험: queue는 아직 `min-width: 620px` table과 중복 risk progress/badge를 사용한다. 최종 reduced-motion·print·clean console은 REF-05에서 다시 검증한다.
- 다음 Package: REF-04

### REF-04. Investigation queue 시각화

- 상태: 완료
- Highest-risk Endpoint를 progress bar 없는 ranked ledger로 변경한다.
- Incident Queue를 responsive compact rows로 변경하고 긴 text, 숫자 정렬, compact date와 empty height를 보정한다.

완료 조건: 360px까지 page-level·panel-level horizontal scroll 없이 full value 접근 경로와 primary link가 유지된다.

- 변경 파일: `frontend/src/features/overview/InvestigationQueues.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/lib/format.ts`, `frontend/src/styles/pages/overview.css`, `frontend/tests/overview-redesign.test.tsx`, 이 실행계획.
- 설계 판단: Highest-risk Endpoint는 순위, hostname·agent ID, score·level, Alert·Incident count의 ranked ledger로 바꿨다. score는 숫자와 level text로만 강조하고 같은 값을 반복하던 progress bar와 pill을 제거했다. Incident Queue는 title link, severity pill, plain status, Alert count와 `MM-DD HH:mm` last detected를 compact metadata로 배치했다. 두 list는 content 양에 따라 높이가 결정되며 긴 primary text는 ellipsis와 `title` 전체값을 함께 제공한다.
- 삭제한 코드: 두 queue의 semantic table와 `min-width: 620px`, risk progressbar, level badge 중복, 두 severity/status pill 조합, 강제 280px queue 높이를 제거했다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx locale.test.tsx components.test.tsx` → 3 files / 25 tests passed. sibling partial failure, primary links, long text title, list semantics와 progress/table 부재를 확인했다. `npm run typecheck` → passed. `git diff --check` → passed.
- 브라우저 QA: 1440×1100에서 Endpoint 5개와 Incident 2개, progress 0건, queue table 0건, panel overflow `false`, page overflow `false`, 모든 metric label과 `07-16 21:00` compact time을 확인했다. 360×900에서 두 queue panel overflow `false`, main scrollLeft `0`, hostname title 접근 경로를 확인했다. 증거: `frontend/output/playwright/overview-redesign/ref-04-1440.png`, `ref-04-360-queues.png`.
- Bundle 변화: dependency 없음. 공통 table wrapper 대신 route-local ordered list와 CSS grid를 사용했다. production 수치는 REF-05에서 측정한다.
- 남은 위험: 전체 viewport matrix와 상태·locale·accessibility·build 검증, 장기 문서의 10-block drift 정리가 남아 있다.
- 다음 Package: REF-05

### REF-05. 통합 Release Gate

- 상태: 완료
- 전체 test, lint, typecheck, build, OpenAPI check를 한 번 실행한다.
- 1440, 1280, 1024, 768, 360px, KO/EN, keyboard-only, 200% zoom, reduced motion을 검증한다.
- normal, zero, empty, partial failure, stale와 final screenshot을 확인하고 bundle 변화를 기록한다.

완료 조건: DESIGN.md 14.7 Hard Pre-flight와 이 문서 Release Gate를 실제 증거로 다시 통과한다.

- 변경 파일: REF-01~04에 기록된 Frontend source·test 파일, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 실행계획. Backend runtime, OpenAPI artifact, DB migration과 dashboard layout 저장 row는 변경하지 않았다.
- 설계 판단: 2026-07-17 visual refinement를 현재 9-block 계약으로 장기 문서에 동기화했다. color와 typography는 semantic 역할·접근성 규칙만 확정하고 실제 palette, font family, size와 weight는 팀 지정 전 임시 token 값으로 명시했다. final 비교는 과거 10-block 시안의 정보 우선순위를 기준으로 하되, 후속 요구인 full-width EDR strip, compact KPI, severity donut, Endpoint Risk 제거와 compact queue를 현재 목표로 판정했다.
- 삭제한 코드: Overview의 중복 breadcrumb·visible PageHeader, 5열 EDR+KPI 강제 높이, `DistributionBars.tsx`, Endpoint Risk block, Detection Activity의 rotated series label·timestamp button 군집, queue table·risk progressbar·강제 높이를 최종 확인했다. Backend layout API와 generated schema는 보존했다.
- 실행한 검증: 전체 `npm run test` → 21 files / 96 tests passed. `npm run typecheck` → passed. `npm run lint`는 최초 donut offset의 render 후 mutation 1건을 발견했고 순수 누적 계산으로 수정한 뒤 passed. 수정 후 `overview-redesign.test.tsx` → 1 file / 14 tests passed. final `npm run build` → passed. `npm run openapi:check`는 최초 sandbox의 `~/.cache/uv` 접근 제한으로 실패했으나 허용된 동일 명령에서 `OpenAPI artifact is current`와 generated schema check가 passed. `git diff --check` → passed. `npm ls react-grid-layout --depth=0` → empty.
- 브라우저 QA: API 계약 모양 mock과 기존 Vite를 사용했다. 1440, 1280, 1024, 768, 360px 모두 9 blocks rendered, 순차 intersection 9/9, document와 `.main-content` overflow `false`, Endpoint Risk·queue table·risk progress 0건이었다. 1440/1280의 초기 viewport에는 9/9, 1024/768은 6/9, 360은 5/9가 실제 fold 안에 있어 아래 block을 보이는 것으로 과장하지 않았다. KO/EN, Endpoint search focus, bucket select exact summary, queue link focus, CDP 200% zoom(scale 2, overflow `false`), reduced motion(`animation=disabled`)을 확인했다. print에서는 canvas `display:none`과 fallback table 3개를 확인했다. normal, zero(0% 4개), empty(activity·Endpoint·Incident), partial failure(Endpoint error·Incident list 유지), stale(마지막 dashboard 유지)가 통과했고 final normal console warning/error와 page error는 0건이다.
- 승인 시안 비교: `docs/frontend/assets/references/overview-dashboard-target.png`와 `frontend/output/playwright/overview-redesign/ref-05-final-1440-full.png`를 직접 열었다. dark-neutral panel 계층, 상태 → 정량 활동 → 조사 queue 흐름은 유지한다. 후속 피드백에 따라 시안의 EDR+KPI 5열은 strip+KPI 행으로, severity bar는 donut으로 바뀌었고 Endpoint Risk panel은 의도적으로 제거됐다. 현재 DTO에 없는 delta·담당자·SLA·sparkline은 추가하지 않았다. 화면 크기와 목표 구조가 달라 자동 pixel diff 수치는 사용하지 않았다.
- Bundle 변화: final `OverviewPage` 17.13 kB / 5.52 kB gzip, lazy `DetectionActivityPanel` 499.67 kB / 170.84 kB gzip, 공통 index 359.33 kB / 112.84 kB gzip. REF 시작 기준 대비 각각 +0.02/+0.11, +0.17/+0.01, +4.14/+1.86 kB이고 새 runtime dependency는 없다. `react-grid-layout`은 계속 0건이다.
- 남은 위험: 실제 service name, color palette와 typography 값은 팀 지정 전이라 `EDR Console` fallback과 기존 token baseline을 사용한다. ECharts lazy chunk는 170.84 kB gzip으로 route 격리는 유지하지만 크다. 브라우저 상태 matrix는 API 계약 모양 mock으로 검증했으며 이번 후속 작업에서 live Backend integration은 재검증하지 않았다.
- 다음 Package: 없음

### Live preview handoff

- 상태: 완료
- 이유: 사용자가 현재 변경을 일반 브라우저에서 직접 사용하도록 요청했지만 host Vite의 proxy 대상 Backend `127.0.0.1:8000`과 통합 접속점 `127.0.0.1:8080`이 모두 중지되어 있다. Frontend test와 Playwright route mock만으로는 사용자 직접 조작과 실제 API session을 제공할 수 없으므로 Docker 예외 조건을 충족한다.
- 실행 경로: repository가 지원하는 `docker compose up -d --build --wait`로 현재 Frontend source와 Backend·infra를 함께 띄운다. 기존 volume과 runtime credential은 보존하고 down/reset은 수행하지 않는다.
- 예상 비용: 11개 service의 image 확인·필요 시 Backend/Frontend rebuild와 health wait가 발생해 수 분이 걸릴 수 있고, PostgreSQL·ClickHouse·Kafka·MinIO·Worker를 포함해 수 GB 메모리를 사용할 수 있다.
- 검증 예정: `docker compose ps`, `http://127.0.0.1:8080/nginx-health`, Dashboard 응답과 일반 Chrome 접속.
- 실행 메모: 첫 `--build`는 Docker Hub에서 `node:24.12.0-alpine`과 Dockerfile frontend metadata를 조회하다 `DeadlineExceeded`로 중단됐고 container는 생성되지 않았다. 기존 `edr-c-local-*` service image와 모든 infra image는 local cache에 있으므로, 재빌드 없이 Compose를 기동하고 현재 host Vite를 `EDR_BACKEND_PROXY_TARGET=http://127.0.0.1:8080`으로 연결하는 fallback을 사용한다. 이 경로는 현재 working tree Frontend를 유지하면서 cached Backend API를 사용한다.
- 실제 결과: `docker compose up -d --wait`가 local cache image로 완료됐고 Backend, Frontend, Nginx, PostgreSQL, ClickHouse, Kafka와 MinIO health가 모두 정상이다. Nginx health는 `ok`, host Vite `/login`은 HTTP 200이며 `runtime/demo/credentials.json` 생성도 확인했다. 현재 working tree Vite는 5173에서 Compose 8080 API로 proxy하고, 사용자가 직접 조작할 수 있는 visible browser tab을 `http://127.0.0.1:5173/login`에 열어 두었다.
- Demo data handoff: 공식 `tools.seed_dashboard_long_range`를 `7 days / 20 Endpoints / 100 Events per Endpoint-day / seed 20260715`로 실행해 기존 local QA DB를 초기화했다. 생성 결과는 Event 14,000건, Alert 280건, Incident 40건, Event failure 35건과 HOT bucket 160개이며 base QA fixture의 Alert 2건과 Incident 1건도 함께 유지된다. `frontend-admin`으로 로그인하고 `LATEST_7D`를 선택한 실제 Overview에서 Total Alerts 282, Critical Alerts 71, Open Incidents 21, 8개 daily bucket과 Endpoint·Incident queue가 응답하는 것을 확인했으며 visible browser tab을 `http://127.0.0.1:5173/?timePreset=LATEST_7D`에 열어 두었다.

### REF-06. Case 1 color token 적용

- 상태: 완료
- 입력: `case-1-design-tokens.yaml`의 color, status mapping, KPI alias, chart series와 color implementation policy. 같은 파일의 font·typography는 이번 변경에서 제외한다.
- 범위: 전역 dark surface·border·text·interaction token, Overview KPI·EDR·severity donut·risk ledger·Detection Activity와 queue의 semantic color를 교체한다.
- 설계 판단: red는 Critical/RED/error의 수치·icon·작은 signal에만 사용하고 card fill·장식 border에는 사용하지 않는다. High/Medium/Low와 warning/health/info를 서로 다른 token으로 분리하며 chart series는 status color와 독립시킨다. Case 1에서는 gradient를 사용하지 않는다.
- 변경 파일: `frontend/src/styles/tokens.css`, `frontend/src/styles.css`, `frontend/src/styles/reset.css`, `frontend/src/styles/primitives.css`, `frontend/src/styles/pages/overview.css`, `frontend/src/components/ui.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/features/overview/DetectionActivityPanel.tsx`, `frontend/tests/overview-redesign.test.tsx`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 실행계획.
- 삭제한 코드: 이전 cyan 중심 palette 값, High/Warning·Medium/Info·Low/Success의 중복 mapping, color-mix로 파생하던 primary hover, accent·chart gradient, KPI와 EDR status의 장식 border color를 제거했다. Backend, API, DTO와 data 계산은 변경하지 않았다.
- 실행한 검증: `npm test -- overview-redesign.test.tsx components.test.tsx app-shell-foundation.test.tsx` → 3 files / 20 tests passed. `npm run typecheck` → passed. `npm run lint` → passed. `npm run build` → passed. `git diff --check` → passed. 이전 palette hex를 Frontend source와 장기 문서에서 검색한 결과 0건이다.
- 브라우저 QA: 기존 live Backend seed와 로그인 session을 재사용했다. 현재 visible browser의 403×853 viewport에서 9 blocks, KO 전환, document overflow `false`를 확인했다. computed token은 canvas `#121318`, panel `#27282e`, accent `#8296ff`, Critical `#ff5968`, High `#ff8a4c`, Medium `#f4b942`, Low `#8db5ff`, Warning `#e5d36c`, Success `#6ad7a3`, Info `#4bc8e8`, chart `#4bc8e8/#8b7cff/#f06db2`, gradient `none`이었다. Total 282는 accent, Critical 71은 critical, Open Incident 21은 info, High-risk Endpoint 0은 neutral로 렌더링됐고 KPI border는 모두 neutral이었다. severity donut 4개 segment도 새 status mapping과 일치했다. console은 Vite HMR debug와 React DevTools info만 있고 warning/error는 없었다. 현재 browser viewport 제약 때문에 별도 1440px color screenshot은 이번 Package에서 검증하지 않았다.
- Bundle 변화: REF-05 대비 `OverviewPage` 17.14 kB / 5.53 kB gzip으로 +0.01 / +0.01 kB, lazy `DetectionActivityPanel` 499.66 kB / 170.84 kB gzip으로 -0.01 / ±0.00 kB, 공통 index 359.33 kB / 112.84 kB로 동일하다. 새 dependency는 없다.
- 남은 위험: service name과 font·typography token은 아직 팀 확정 전이다. 전달 palette의 border default가 기존보다 밝아졌으므로 큰 화면의 전체 border 밀도는 팀 시각 검토에서 추가 조정될 수 있다. 1440px 색상 전용 screenshot 비교는 미검증이다.
- 다음 Package: 팀 font·typography 전달 또는 다음 시각 피드백.

### REF-07. 공격 실험 UX·다계층 수집 운영 콘솔 통합

- 상태: 완료
- 입력: Team B에서 참고할 공격 실험 UX와 다계층 수집 방식, 추가 의견의 운영 콘솔 방향. Team C의 현재 API·DTO·권한·route·error/stale/partial-failure 처리는 계약 기준으로 유지한다.
- 범위: dark/light semantic token, 244px SOC navigation shell, `Signal → Evidence → Decision` 조사 흐름, Overview observed signal stream, Alert Evidence Chain, ATT&CK observed heat, Operations 9단계 collection path, Login product path와 375/768/1440 responsive layout.
- 설계 판단: 외부 프로젝트는 화면 구조와 조사 흐름만 참고했다. 현재 API가 제공하지 않는 Rule Coverage, health probe, replay, 공격 실행, 추세와 담당자/SLA는 생성하지 않는다. ATT&CK는 관측된 tactic/technique count만 표현하며 coverage는 unavailable로 명시한다. Collection Path는 현재 health 응답과 worker 상태만 연결하고 Agent·Nginx처럼 probe가 없는 계층은 `NO PROBE`로 표시한다. Alert chain은 실제 Endpoint/Event/Rule/Alert/Incident 식별자가 있을 때만 link 또는 observed 상태로 렌더링한다.
- 변경 파일: `frontend/src/theme/ThemeProvider.tsx`, `frontend/src/main.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/pages/AlertDetailPage.tsx`, `frontend/src/pages/IntelligencePage.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/OperationsPage.tsx`, 관련 style·i18n·test, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 실행계획. Backend, OpenAPI artifact와 generated schema는 변경하지 않았다.
- 실행한 검증: `npm run typecheck` passed, `npm run lint` passed, 전체 `npm run test` → 21 files / 97 tests passed, `npm run build` passed, `npm run openapi:check` → OpenAPI artifact current와 generated schema check passed, `git diff --check` passed. 새 theme storage key는 source-boundary test에서 `edr.theme` 하나만 좁게 허용하며 credential·route storage 금지는 유지한다.
- 브라우저 QA: live local Backend와 로그인 session에서 Overview 1440/768/375, Intelligence ATT&CK, Operations collection path, Alert Evidence Chain, Login과 dark/light 전환을 확인했다. console에는 React development 안내 외 warning/error가 없었다. 증거: `frontend/output/playwright/team-b-redesign/overview-signal-v1-1440.png`, `overview-tablet-768.png`, `overview-mobile-375.png`, `intelligence-attack-surface-v1.png`, `operations-collection-path-v1.png`, `alert-evidence-chain-v1.png`, `alert-evidence-chain-light.png`, `login-light-v1.png`.
- 런타임 관찰: local 8080의 cached Backend는 Alert list의 `sortBy=priority` 요청에 400을 반환했지만 Alert detail은 정상 응답했다. 이번 Frontend 계약이나 query를 변경하지 않았으며, 현재 source/OpenAPI와 local cached Backend image 사이의 환경 drift로 분리한다.
- Bundle 변화: final `OverviewPage` 18.04 kB / 5.65 kB gzip, `OperationsPage` 14.95 kB / 4.28 kB gzip, `IntelligencePage` 20.22 kB / 5.32 kB gzip, 공통 index 366.17 kB / 114.58 kB gzip. 새 runtime dependency는 없다.
- 남은 위험: 실제 공격 실행 control과 replay는 제품 계약에 없으므로 구현하지 않았다. live Backend image를 최신 source로 rebuild하기 전 Alert queue runtime drift는 남아 있다. 시각 검토 후 density·copy 미세 조정은 별도 후속 Package로 진행할 수 있다.
- 다음 Package: 팀 시각 피드백에 따른 polish 또는 최신 Backend image 통합 검증.

### REF-08. Case 2 final-selected token·typography 적용

- 상태: 완료
- 입력: `case-2-design-tokens.yaml`, `case-2-filled-design-spec.md`의 dark-only color, typography, font hosting, gradient와 상태색 제약.
- 범위: dual theme 제거, 전역 surface·border·text·action·status·chart token 교체, Inter Variable·Pretendard Variable·IBM Plex Mono self-host, Overview chart area fill과 숫자·table typography, 장기 Frontend 문서·회귀 테스트 동기화. Backend, API, DTO와 data 계산은 변경하지 않았다.
- 설계 판단: near-black canvas와 shell 위에서 royal blue를 primary action과 active navigation에만 사용한다. Violet은 Detection Activity Alerts series에만 남기고 일반 UI·상태·action에서는 제거했다. 일반 component gradient와 card shadow는 제거하고 Detection Activity line 아래의 낮은 opacity 수직 area fill만 허용했다. Theme switch와 `edr.theme` 저장은 삭제했다.
- Font: NPM의 OFL-1.1 font package를 bundle source로 사용한다. Inter Latin variable WOFF2, Pretendard Variable WOFF2, IBM Plex Mono 400/500/600 Latin WOFF2만 빌드에 포함하며 모두 `font-display: swap`이다. 외부 font CDN 요청은 없다.
- 실행한 검증: `npm run typecheck` passed, `npm run lint` passed, 핵심 6 files / 34 tests passed, 전체 `npm run test` → 21 files / 97 tests passed, `npm run build` passed. production font asset은 Inter 48.26 kB, IBM Plex Mono 14.71/14.89/15.62 kB, Pretendard Variable 2,057.69 kB다. ECharts lazy chunk는 500.11 kB / 171.04 kB gzip으로 route 격리를 유지한다.
- 브라우저 QA: live local Backend와 7일 seed를 연결한 `http://127.0.0.1:5175/?timePreset=LATEST_7D`에서 1440×1100, 375×812, EN/KO를 검증했다. computed token은 canvas `#09090B`, shell `#17161B`, panel `#0C0C0F`, accent `#2563E9`, focus `#4C85FF`, chart `#2563E9/#7C83FD/#16A249`다. Inter Variable, Pretendard Variable, IBM Plex Mono 400/500/600은 모두 loaded, theme control 0건, document/main horizontal overflow 0건, console warning/error 0건이었다.
- 증거: `frontend/output/playwright/team-b-redesign/case-2-overview-1440.png`, `case-2-overview-375.png`, `case-2-overview-375-bottom.png`, `case-2-overview-ko-1440.png`.
- 남은 위험: Service name은 입력 명세에서 `TBD`이므로 기존 `EDR Console` fallback을 유지한다. Pretendard Variable 단일 asset은 2.06 MB이므로 초기 한글 사용 시 font 전송량 최적화 여지가 있다. ECharts chunk warning은 기존 route-local chart dependency에서 계속 발생한다.
- 다음 Package: 실제 service name 반영 또는 팀 시각 피드백에 따른 미세 조정.

### REF-09. Panel border hierarchy 완화

- 상태: 완료
- 입력: 데스크톱 화면에서 각 box 외곽선이 content보다 밝게 튄다는 팀 시각 피드백.
- 범위: 공통 panel·card·filter·state surface, Overview toolbar·signal·posture, Alert Evidence Chain, Login form과 Event Raw Payload의 외곽선. Button, input, popover, focus ring과 semantic status line은 제외한다.
- 설계 판단: control boundary 접근성을 담당하는 `border-default`는 유지하고, panel 외곽선 전용 `border-panel`을 `border-subtle`과 `border-default` 사이 명도로 분리한다. Surface 구획은 유지하되 고밀도 화면에서 모든 panel이 같은 강도로 경쟁하지 않게 한다.
- 변경 파일: `frontend/src/styles/tokens.css`, `frontend/src/styles/patterns.css`, `frontend/src/styles/pages/overview.css`, `frontend/src/styles/pages/alerts.css`, `frontend/src/styles/pages/endpoints-events.css`, `frontend/src/styles/pages/login.css`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 실행계획.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx app-shell-foundation.test.tsx components.test.tsx` → 3 files / 21 tests passed. `npm run lint`, `npm run typecheck`, `npm run build`, `git diff --check` 모두 passed.
- 브라우저 QA: 계약형 mock과 Vite를 사용한 1440×1100 Overview에서 9 blocks, document/main horizontal overflow `false`, console error/warning 0건을 확인했다. panel 외곽선은 `#34353C`, control 외곽선은 `#5D5E67`, 내부 divider는 `#25262B`로 분리됐고 Login form은 panel token, autofocus input은 focus ring을 유지했다. 증거: `frontend/output/playwright/team-b-redesign/qa-border-refinement-final-1440.png`.
- Bundle 변화: CSS token과 selector 교체만 포함하며 새 runtime dependency와 JS 동작 변화는 없다. Production build는 passed했고 기존 ECharts lazy chunk warning은 동일하다.
- 남은 위험: 없음. 모바일은 사용자 요청에 따라 이번 시각 판정에서 제외했다.
- 다음 Package: 없음.

### REF-14. 최종 UI annotation 반영

- 상태: 완료
- 입력: 2026-07-20 브라우저 annotation으로 수집한 Overview의 조회 기간 조작, EDR 수치 위계, 설명 문구, Detection Activity 공간 사용, Fleet/위험 Endpoint copy와 공통 화면의 최종 UI 정리 요청.
- 범위: Default Overview와 해당 화면을 둘러싼 공통 shell, list/detail 화면의 표시 copy·레이아웃·현지화·접기 interaction만 수정한다. API·DTO·OpenAPI·URL query·polling·권한·Backend lifecycle은 변경하지 않는다.
- 설계 원칙: 중복 eyebrow·설명·상태 badge는 제거하고 화면 제목과 실제 데이터에 시선을 집중시킨다. Overview 조회 기간은 상단의 단일 dropdown에서 바로 변경한다. Incident ledger와 graph/table은 한 줄 정보 보존, 동일한 table surface, Inspector 내부 overflow 방지를 우선한다.
- 예상 변경 파일: 공통 shell/component, Overview/Alerts/Incidents/Endpoints/Events/Intelligence/Operations/Archives page, 관련 page CSS·i18n·test와 이 실행계획. 새 runtime dependency는 추가하지 않는다.
- 검증 계획: 관련 Vitest, 전체 typecheck·lint·test·build·OpenAPI check·`git diff --check`, 실제 Backend를 연결한 1088·1280·1440px 브라우저 QA와 console/overflow 검사를 수행한다.
- 다음 Package: 검증 결과에 따라 없음 또는 잔여 결함 보정.

- 최종 요청 반영: Overview 조회 기간은 별도 popover 없이 상단 단일 dropdown에서 최근 15분·1시간·24시간·7일·UTC 직접 설정을 바로 선택하도록 확정했다.
- 구현 결과: 공통 shell과 list page의 중복 문구를 정리하고 Overview 수치·그래프·Fleet copy를 보정했다. Alerts/Incidents/Events/Intelligence/Operations/Archives annotation을 반영했으며 알려진 Detection 제목·설명·Incident graph node를 locale별로 표시한다. Incident ledger 설명 2개는 desktop 한 줄로 보존하고, 1088px Alert 상세는 queue/detail을 상하 배치해 증거 값의 세로 글자 깨짐을 제거했다.
- 자동 검증: `npm run typecheck`, `npm run lint`, 전체 `npm run test -- --run` 25 files / 144 tests, `npm run build` passed. 변경 전 API 계약 검증인 `npm run openapi:check`도 passed 상태를 유지한다.
- 브라우저 QA: 실제 local Backend와 seed data를 연결한 `http://127.0.0.1:5173`에서 KO 1088×731 및 Incident 1440×1000을 검증했다. 모든 대상 route의 document horizontal overflow 0px, console/page error 0건, 삭제 문구 재노출 0건이었다. Lifecycle 정책과 연결된 Alert 설명은 1088px에서 각각 16px 한 줄, `clientWidth === scrollWidth === 267px`, `white-space: nowrap`이었다.
- 증거: `frontend/output/playwright/final-ui-polish/overview-time-dropdown-1088.png`, `alert-detail-1088.png`, `incident-detail-ledger-1088.png`, `incident-detail-1440.png`, `intelligence-1088.png`.
- Bundle 변화: 새 runtime dependency 없음. production `OverviewPage` 115.90 kB / 35.37 kB gzip, `IncidentDetailPage` 17.33 kB / 5.15 kB gzip, 기존 route-local `DetectionActivityPanel` 326.07 kB / 113.10 kB gzip.
- 남은 위험: React Flow canvas는 내부 좌표계 특성상 viewport element의 scrollWidth가 clientWidth보다 크지만 document overflow는 0px이며 시각적 clipping·page overflow는 재현되지 않았다.
- 다음 Package: 없음.

### REF-10. 대형 관제 Overview 정보 밀도 복원

- 상태: 완료
- 입력: Overview는 일반 요약 페이지가 아니라 대형 화면에 상시 표시하는 SOC 관제 화면이므로, 시간 추세와 분포 시각 자료를 같은 시야에 유지해야 한다는 사용자 피드백과 승인된 `overview-wallboard-before-after.html` After 안.
- 범위: immutable Default Overview의 기존 Signal ribbon, EDR command strip, KPI 4개, Detection Activity, Alert Severity, 조사 Queue 2개를 보존하고 Endpoint Summary가 이미 제공하는 Risk level과 Sensor Health 집계를 하나의 Fleet distribution panel로 복원한다. Custom Dashboard widget catalog와 다른 route는 변경하지 않는다.
- 계약 경계: `EndpointSummaryDto.risk.byLevel`과 `sensorHealth`만 사용한다. 원본 Endpoint 재집계, 추세 추정, delta, 담당자, SLA와 새 API·DTO는 추가하지 않는다. Fleet 정보는 현재 snapshot임을 명시하고 시간 추세처럼 표현하지 않는다.
- 변경 파일: `frontend/src/features/overview/FleetDistributionPanel.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/src/styles/pages/overview.css`, `frontend/src/i18n/translations.ts`, `frontend/tests/overview-redesign.test.tsx`, `frontend/tests/custom-dashboard.test.tsx`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 실행계획.
- 설계 판단: 1440px에서는 Detection Activity를 왼쪽 두 행에 두고 Alert Severity와 Fleet Distribution을 오른쪽에 쌓아 chart 폭을 지켰다. 1720px 이상에서는 세 분석 panel을 `2.1fr + .82fr + .92fr` 한 행으로 펼쳐 대형 관제 화면의 동시 판독성을 높였다. Default Overview만 10-block으로 확장하고 Custom Dashboard catalog는 기존 9개를 유지했다.
- empty·overflow 처리: Risk와 Sensor 집계가 없으면 명시적 empty copy를 표시하고 임의의 0 snapshot을 만들지 않는다. panel grid child에 `min-width: 0`, 긴 label에 안전한 줄바꿈과 bar·legend 최소 폭을 적용했다.
- 실행한 검증: `npm run test -- overview-redesign.test.tsx custom-dashboard.test.tsx locale.test.tsx components.test.tsx` → 4 files / 44 tests passed. `npm run typecheck`, `npm run lint`, `npm run build`, `npm run openapi:check`, `git diff --check` passed. 전체 `npm run test`는 25 files 중 24 files / 135 tests passed 후, 작업 전부터 있던 untracked duplicate `overviewLayoutStorage 2.ts`, `ThemeProvider 2.tsx`의 `localStorage` 사용을 source-boundary allowlist가 거부해 1 test가 실패했다. 이 두 사용자 파일은 변경·삭제하지 않았다.
- 브라우저 QA: 계약형 mock으로 1440×1100, 1920×1200, 2560×1440을 확인했다. 세 크기 모두 document/main/panel 가로 overflow가 없고 2560에서는 10개 block과 두 queue가 한 viewport에 모두 들어왔다. 1440은 오른쪽 stack, 1920·2560은 세 분석 panel 한 행으로 렌더링되며 텍스트 겹침을 발견하지 않았다. 증거: `frontend/output/playwright/overview-wallboard/ref-10-1440-full.png`, `ref-10-1920.png`, `ref-10-2560.png`.
- Bundle 변화: 새 runtime dependency 없음. production `OverviewPage` 112.34 kB / 34.40 kB gzip, route-local `DetectionActivityPanel` 500.26 kB / 171.11 kB gzip. 기존 ECharts lazy chunk 경고는 유지된다.
- 남은 위험: 전체 test의 source-boundary 1건은 위 untracked duplicate 파일 때문에 계속 실패한다. 모바일 시각 QA는 사용자 요청에 따라 제외했다.
- 다음 Package: 없음.

### REF-11. 대형 관제 가독성·의미·overflow 보완

- 상태: 완료
- 입력: 실제 local Backend를 연결한 1920×1200, 2560×1440, 3840×2160 감사에서 확인한 4K 미사용 폭과 작은 meta text, `highRiskEndpointCount`의 오해 가능한 label, Sensor 상태의 전체 합계만 노출되는 문제, 1920 세로 scroll, 빈 Incident Queue 높이 불일치와 차트 Y축 label 겹침.
- 범위: Default Overview만 수정한다. 다른 route, API·DTO·OpenAPI, query/polling, Custom Dashboard 9개 widget catalog는 변경하지 않는다. 모바일은 사용자 요청에 따라 시각 QA 범위에서 제외한다.
- 의미 보완: `highRiskEndpointCount`는 `CRITICAL + HIGH`가 아니라 정확한 `HIGH` count이므로 KPI를 `HIGH-level Endpoints` / `HIGH 등급 Endpoints`로 명시했다. Fleet Risk와 Sensor 상태를 locale별 label로 표시하고, `sensorHealth`의 기존 `sensor + status + count` 행을 재집계 없이 Sensor별 compact stack과 접근성 요약으로 노출했다.
- wallboard 보완: 2400px 이상은 Overview가 main 폭을 사용하고 2560×1440에는 meta 13px·body 15px·panel title 17px, 3000px·1600px 이상에는 meta 15px·body 17px·panel title 20px을 적용한다. 4K Fleet은 Risk와 Sensor를 두 열로 배치하며 Detection chart와 분석 panel 높이를 확장한다. 1920×1200은 analysis·queue 간격과 row padding을 압축하고 빈 Queue를 반대쪽 panel 높이에 맞춘다.
- chart·overflow 보완: ECharts grid를 container 비율로 계산하고 220px 미만 compact chart는 Y축을 2분할·정수 간격으로 제한해 label 겹침을 제거했다. EDR 점수와 donut 중앙값의 line box를 실제 glyph 높이보다 크게 확보했고 2400px 이상 Signal header 폭도 확대했다.
- 자동 검증: `npm run test -- overview-redesign.test.tsx custom-dashboard.test.tsx locale.test.tsx components.test.tsx` → 4 files / 44 tests passed. `npm run typecheck`, `npm run lint`, `npm run build`, `npm run openapi:check`, `git diff --check` passed. 전체 `npm run test`는 24 files / 135 tests passed 후 사용자 소유 untracked duplicate `overviewLayoutStorage 2.ts`, `ThemeProvider 2.tsx` 때문에 기존과 동일한 source-boundary 1건만 실패했다.
- 실제 브라우저 QA: 1920×1200에서 main `clientHeight 1132px / scrollHeight 1132px`로 기존 약 208px scroll을 제거했고 10개 block overflow는 0건이었다. 2560×1440은 main 폭의 97.9%를 사용하고 block overflow 0건, 3840×2160은 98.7%를 사용하며 block overflow와 clipped strong text가 모두 0건이었다. 4K에서 실제 7일 Detection Activity, Severity donut, Fleet Sensor별 분해와 두 Queue를 동시에 확인했고 console error/warning은 0건이었다.
- 증거: `frontend/output/playwright/overview-wallboard/complement-live-1920-chart.png`, `complement-live-3840-chart.png`.
- Bundle 변화: 새 runtime dependency 없음. production `OverviewPage` 113.63 kB / 34.75 kB gzip, route-local `DetectionActivityPanel` 500.42 kB / 171.17 kB gzip. 기존 ECharts lazy chunk warning은 유지된다.
- 다음 Package: 없음.

### REF-12. 관제 상태 의미·대형 화면 fit 오류 교정

- 상태: 완료
- 입력: Hallmark 재감사에서 확인한 Sensor `UNAVAILABLE` 의미 색상 drift, Sensor별 exact count의 비시각 노출, 2560×1440 세로 overflow와 4K 세로 공간 미사용.
- 범위: Default Overview의 Fleet Distribution과 2400px 이상 wallboard layout만 수정한다. 기존 색상 체계, panel 구조, API·DTO·query·polling, Custom Dashboard와 다른 route는 변경하지 않는다. 모바일은 사용자 요청에 따라 시각 QA에서 제외한다.
- 의미 교정: 기존 디자인 계약대로 `UNAVAILABLE` stack·legend를 `--status-critical`로 복구했다. Sensor별 compact row에는 `Healthy/Degraded/Unavailable` label과 exact count를 항상 표시하고, 같은 내용을 accessible list name으로 제공해 색상이나 hover에 의존하지 않게 했다.
- wallboard fit: 2400~2999px의 중간 높이 구간에서 Detection Activity canvas를 높이 기준으로 조정해 2560×1440의 43px 세로 overflow를 제거했다. 3000px·1600px 이상에서는 Overview page와 dashboard workspace가 main viewport 높이를 사용하고 Detection Activity가 남는 세로 공간을 흡수한다.
- 자동 검증: `npm run test -- overview-redesign.test.tsx custom-dashboard.test.tsx locale.test.tsx components.test.tsx` → 4 files / 44 tests passed. `npm run typecheck`, `npm run lint`, `npm run build`, `npm run openapi:check`, `git diff --check` passed. 전체 `npm run test`는 24 files / 135 tests passed 후 사용자 소유 untracked duplicate `overviewLayoutStorage 2.ts`, `ThemeProvider 2.tsx` 때문에 기존과 동일한 source-boundary 1건만 실패했다.
- 실제 브라우저 QA: 1920×1200과 2560×1440에서 main client/scroll height가 각각 `1132/1132`, `1372/1372`였고, 3840×2160은 `2092/2092`였다. 세 화면 모두 block overflow와 visible text overflow 0건, Sensor별 exact count client/scroll width 일치, `UNAVAILABLE` computed color `rgb(240, 68, 68)`, console error/warning 0건을 확인했다. 4K Overview page는 main content 높이 2044px을 사용한다.
- 증거: `frontend/output/playwright/overview-wallboard/fix-final-1920.png`, `fix-final-2560.png`, `fix-final-3840.png`.
- Bundle 변화: 새 runtime dependency 없음. production `OverviewPage` 113.83 kB / 34.78 kB gzip, route-local `DetectionActivityPanel` 500.42 kB / 171.18 kB gzip이며 기존 ECharts chunk warning은 유지된다.
- 다음 Package: 없음.

### REF-15. 브라우저 단일 세로 스크롤

- 상태: 완료
- 입력: 긴 Overview에서 browser document와 `main.main-content`가 각각 세로 scrollbar를 소유해 오른쪽에 scrollbar가 두 개 표시되는 오류.
- 범위: AppShell의 page-level 세로 scroll ownership과 관련 문서·회귀 테스트만 수정했다. Table, payload, dialog 등 경계가 명확한 내부 scroller와 API·DTO·Backend는 변경하지 않았다.
- 설계 판단: `.console-shell`의 고정 `height: 100dvh`를 `min-height`와 document-flow row로 바꾸고 `.main-content`의 `overflow: auto`를 제거했다. Navigation rail과 top bar는 sticky로 유지해 긴 page에서도 탐색 문맥을 보존한다. 중복 legacy·modular CSS가 다시 충돌하지 않도록 두 파일을 동일하게 수정했다.
- 변경 파일: `frontend/src/styles.css`, `frontend/src/styles/shell.css`, `frontend/tests/release-gates.test.ts`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 실행계획.
- 자동 검증: targeted Vitest 3 files / 28 tests passed, `npm run typecheck` passed, `npm run lint` passed, `npm run build` passed. 새 회귀 테스트는 두 CSS entry 모두에서 document-owned scroll 계약을 검사한다.
- 브라우저 QA: 사용자 Chrome의 local session이 로그인 화면으로 만료되어 인증 후 Overview 실화면 검증은 수행하지 않았다. 자격 증명이나 browser storage는 조회·변경하지 않았다.
- Bundle 변화: CSS layout rule과 test·문서만 변경했으며 새 runtime dependency는 없다. Production build는 passed했다.
- 남은 위험: 로그인된 실제 Backend 화면에서 Overview와 짧은 route 각각의 scrollbar가 하나인지 최종 육안 확인이 필요하다.
- 다음 Package: 로그인 세션이 준비되면 Overview와 다른 route의 단일 scrollbar 시각 QA만 수행한다.

### REF-13. 영어 wallboard overflow 오류 교정

- 상태: 완료
- 입력: 최종 데스크톱 QA에서 재현한 1920×1200 영어 Fleet Distribution 하단 3px overflow와 1920×1200·3840×2160 영어 `Observed signal stream` 제목 잘림.
- 범위: Default Overview의 wallboard 전용 CSS만 수정한다. 기존 10-block 구조, 380px 분석 행, 색상·타이포·데이터 계약, API·DTO·query·polling, Custom Dashboard와 다른 route는 변경하지 않는다. 모바일은 사용자 요청에 따라 시각 QA에서 제외한다.
- 수정 원칙: 1920 compact Fleet은 전체 행 높이를 늘리지 않고 내부 gap과 snapshot note padding에서 필요한 4px만 회수한다. Signal ribbon은 1720px 이상과 3000px 이상에서 영어 제목이 한 줄로 표시되는 최소 header 폭만 확보한다.
- 변경 파일: `frontend/src/styles/pages/overview.css`, 이 실행계획. 검증 artifact로 `frontend/output/playwright/overview-wallboard/ref-13-overflow-qa.js`와 EN/KO 1920·4K screenshot을 생성했다.
- 구현 결과: 1720px 이상 Signal header를 210px, 3000px·1600px 이상을 270px로 조정했다. 1250px 이하 compact Fleet은 panel body gap과 snapshot note padding을 각각 6px에서 4px로 줄여 전체 분석 행 높이를 바꾸지 않고 4px 여유를 확보했다.
- 자동 검증: `npm run test -- overview-redesign.test.tsx custom-dashboard.test.tsx locale.test.tsx components.test.tsx` → 4 files / 44 tests passed. `npm run typecheck`, `npm run lint`, `npm run build`, `npm run openapi:check`, `git diff --check` passed. 전체 `npm run test`는 24 files / 135 tests passed 후 사용자 소유 untracked duplicate `overviewLayoutStorage 2.ts`, `ThemeProvider 2.tsx` 때문에 기존과 동일한 source-boundary 1건만 실패했다.
- 실제 브라우저 QA: 계약형 mock으로 EN/KO 각각 1920×1200, 2560×1440, 3840×2160을 측정했다. 여섯 화면 모두 main client/scroll width·height가 일치하고 10개 block overflow 0건, Sensor exact count width overflow 0건, console error/warning과 page error 0건이었다. 영어 1920 Fleet은 block `380/380px`, body `316/316px`, note boundary 초과 0px이며 Signal 제목은 `170/170px`이다. 영어 4K Signal 제목도 `230/230px`로 잘림이 없다.
- 증거: `frontend/output/playwright/overview-wallboard/ref-13-en-1920.png`, `ref-13-en-3840.png`, `ref-13-ko-1920.png`, `ref-13-ko-3840.png`.
- Bundle 변화: 새 runtime dependency와 JS 변화 없음. production `OverviewPage` 113.83 kB / 34.78 kB gzip, route-local `DetectionActivityPanel` 500.42 kB / 171.17 kB gzip이며 기존 ECharts chunk warning은 유지된다.
- 남은 위험: 전체 test의 source-boundary 1건은 위 사용자 소유 중복 파일 때문에 계속 실패한다. 이번 CSS 오류 교정과 직접 관련된 미해결 사항은 없다.
- 다음 Package: 없음.
