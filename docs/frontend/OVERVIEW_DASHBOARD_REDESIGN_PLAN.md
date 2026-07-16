# Overview Dashboard Redesign Plan

- 상태: 완료
- 기준일: 2026-07-16
- 작업 브랜치: `overview-dashboard-redesign`
- 적용 범위: `frontend/`와 관련 Frontend 문서·테스트
- 다음 작업: `작업 완료`
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
7. Detection Activity만 ECharts PoC 대상으로 삼고, 분포·순위는 semantic HTML과 CSS bar로 구현한다.
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
Page title / description                  Endpoint · Time · Refresh

[ EDR state 1.25fr ][ KPI ][ KPI ][ KPI ][ KPI ]

[ Detection Activity 2fr ][ Alert Severity 1fr ][ Endpoint Risk 1fr ]

[ Highest-risk Endpoints 1fr ][ Incident Queue 1fr ]
```

### Wide desktop: 1280px 이상

- 상태·KPI: `grid-template-columns: 1.25fr repeat(4, minmax(0, 1fr))`
- 분석: `grid-template-columns: minmax(0, 2fr) repeat(2, minmax(0, 1fr))`
- 조사 대기열: `grid-template-columns: repeat(2, minmax(0, 1fr))`
- panel gap: 12px
- page, toolbar와 grid의 좌우 edge를 일치시킨다.

### 1024–1279px

- EDR state는 첫 행 전체 또는 2열 폭을 사용한다.
- KPI는 2열로 재배치한다.
- Detection Activity는 전체 폭, 두 분포 panel은 2열로 배치한다.
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
| 4 | High-risk Endpoints | `endpointSummary.risk` | KPI |
| 5 | Open Incidents | `dashboard.incidents.open` | KPI |
| 6 | Detection Activity | Event·Alert time series와 Incident `openCount` | 공통 X축 small multiples |
| 7 | Alert Severity | 서버 `bySeverity` | Critical/High/Medium/Low horizontal bars |
| 8 | Endpoint Risk | 서버 `risk.byLevel` | Critical/High/Medium/Low horizontal bars |
| 9 | Highest-risk Endpoints | `GET /endpoints` 위험도 정렬 결과 | 점수 bar, Alert·Incident count, 상세 link |
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

### Alert Severity와 Endpoint Risk

- donut을 사용하지 않고 고정 순서 `CRITICAL → HIGH → MEDIUM → LOW`의 horizontal bar를 사용한다.
- 각 row에 label, count와 percentage를 함께 표시한다.
- total이 0이면 `0%`로 안전하게 표시하고 빈 분모 계산을 하지 않는다.
- semantic status color와 text를 함께 사용한다.

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
  EdrStatePanel.tsx
  DetectionActivityPanel.tsx
  DistributionBars.tsx
  RiskEndpointList.tsx
  IncidentQueue.tsx
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
- Total Alerts, Critical Alerts, High-risk Endpoints, Open Incidents를 연결한다.
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

- 10개 block의 DOM 순서와 필수 label
- layout edit, drag, resize, hide control 부재
- layout API가 호출되지 않음
- EDR 두 진단 축과 reason 표시
- severity·risk count/percentage의 정상·0 처리
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

- 1440px: 상태+KPI 한 행, 분석 `2:1:1`, 대기열 `1:1`
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
