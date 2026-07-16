# Overview Dashboard Implementation Work Order

- 상태: Approved / 실행 가능
- 작성일: 2026-07-16
- 작업 branch: `overview-dashboard-redesign`
- 작업 위치: `/Users/geonha/Desktop/team-C`
- 실행 범위: `OVR-01`부터 `OVR-05`까지 순차 완료
- 진행 기록: [OVERVIEW_DASHBOARD_REDESIGN_PLAN.md](./OVERVIEW_DASHBOARD_REDESIGN_PLAN.md)
- 시각 기준: [overview-dashboard-target.png](./assets/references/overview-dashboard-target.png)

## 1. 작업 목표

현재 사용자 편집형 Overview를 승인 시안과 같은 고정형 10-block EDR 의사결정 dashboard로 재구성한다.

완료된 화면은 SOC 운영자가 15초 안에 다음을 판단할 수 있어야 한다.

1. 현재 EDR 상태가 정상·주의·위험 중 무엇인가?
2. 상태를 만든 주요 축과 위험 분포가 무엇인가?
3. 어떤 Endpoint와 Incident부터 조사해야 하는가?

이 작업은 단순 계획이나 PoC 제출로 끝내지 않는다. 구현, 자동 테스트, 실제 브라우저 시각 QA, 실행계획의 증거 기록까지 완료한다.

## 2. 권장 Codex 설정

### 1순위

- Model: `gpt-5.6-sol` (`GPT-5.6 Sol`)
- Reasoning: `High`
- Speed: Standard

이 작업은 기존 대규모 컴포넌트 해체, 계약 보존, 시각 판단, ECharts 검증과 다중 viewport QA가 함께 있어 빠른 반복보다 분석·검증·완성도가 중요하다.

Codex App에 model slug 대신 preset만 표시되면 `Smarter` 쪽을 선택한다. `GPT-5.6 Sol`을 직접 선택할 수 없으면 기본 `Power`를 사용한다.

### 대안

- 속도 우선: `GPT-5.6 Terra` + `High`
- `Luna` 또는 Codex Spark는 명확한 반복 작업에는 적합하지만 이번 전체 구현의 main model로 사용하지 않는다.
- `Max`는 단일 난제에서 High로 부족할 때만 올린다.
- `Ultra`는 사용하지 않는다. 이번 작업은 같은 파일과 Work Package 상태를 순차적으로 갱신하므로 병렬 agent가 얻는 이점보다 충돌 위험이 크다.

모델 선택 근거는 작성 시점의 [GPT-5.6 model guide](https://developers.openai.com/api/docs/guides/latest-model.md)와 [Codex Manual](https://developers.openai.com/codex/codex-manual.md)을 따른다. 공식 가이드는 `gpt-5.6-sol`을 복잡한 workflow의 flagship model로 안내하고 Frontend layout·visual hierarchy·design judgment 개선을 명시한다. 모델이 계정에 보이지 않아도 작업을 중단하지 말고 현재 사용 가능한 Power/Smarter 설정으로 진행한다.

## 3. 시작 상태와 Git 규칙

작업 시작 직후 다음을 확인한다.

```bash
cd /Users/geonha/Desktop/team-C
git branch --show-current
git status --short --branch
```

필수 상태:

- branch는 `overview-dashboard-redesign`이어야 한다.
- 문서 생성·수정·삭제와 승인 시안 추가가 미커밋 상태로 존재할 수 있다. 이것은 이전 작업에서 의도적으로 만든 변경이며 보존한다.
- `main`으로 돌아가지 않는다.
- 기존 변경을 reset, restore, checkout 또는 stash하지 않는다.
- 사용자와 무관한 변경을 발견하면 건드리지 않고 범위를 분리한다.
- commit, push, PR은 사용자가 별도로 요청하기 전까지 수행하지 않는다.

branch가 다르면 임의로 새 branch를 만들지 말고 현재 worktree 상태를 확인한 뒤 `overview-dashboard-redesign`로 안전하게 전환한다. 전환이 기존 변경을 덮을 위험이 있으면 중단하고 근거를 보고한다.

## 4. 반드시 읽을 문서와 코드

다음 순서로 끝까지 읽는다.

1. `frontend/AGENTS.md`
2. `docs/frontend/DESIGN.md`
3. 이 작업지시서
4. `docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`
5. `docs/frontend/FRONTEND_SPEC.md`
6. `docs/contracts/API_SPEC.md`의 Dashboard·Endpoint·Incident 절
7. `docs/contracts/RISK_POLICY.md`

그다음 아래 코드를 실제 구현 기준으로 audit한다.

- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/features/dashboardLayout.ts`
- `frontend/src/features/overviewWidgetRegistry.tsx`
- `frontend/src/components/charts.tsx`
- `frontend/src/components/ui.tsx`
- `frontend/src/api/endpoints.ts`
- `frontend/src/i18n/translations.ts`
- `frontend/src/styles/pages/overview.css`
- `frontend/src/styles.css`
- `frontend/src/styles/visualizations.css`
- `frontend/package.json`
- `frontend/tests/overview-redesign.test.tsx`
- `frontend/tests/dashboard-layout-editor.test.tsx`
- `frontend/tests/dashboard-layout.test.ts`
- `frontend/tests/components.test.tsx`
- `frontend/tests/locale.test.tsx`
- `frontend/tests/release-gates.test.ts`

구현 전에 승인 시안 이미지를 직접 열어 panel 비율, 정보 순서, typography, spacing과 강조 위치를 확인한다. 시안의 숫자를 fixture나 production data로 복사하지 않는다.

## 5. Source of Truth

충돌 시 다음 순서를 적용한다.

1. API와 데이터 의미: `docs/contracts/API_SPEC.md`, `docs/contracts/RISK_POLICY.md`
2. 장기 시각·UX 기준: `docs/frontend/DESIGN.md`
3. 이번 변경 범위·완료 기준: `docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`
4. Route·query·polling·권한: `docs/frontend/FRONTEND_SPEC.md`
5. 실제 구현: `frontend/src/`
6. 승인 시안: geometry와 hierarchy의 시각 기준

시안과 데이터 계약이 충돌하면 계약을 우선하고, 시안에서 구현할 수 없는 정보는 만들지 않는다.

## 6. 절대 경계

### 반드시 제거

- Overview drag and drop
- resize handle
- layout edit mode
- hidden widget tray
- hide·restore·reset control
- layout save 상태, debounce와 revision conflict 처리
- Frontend layout migration
- Frontend dashboard layout GET/PUT/DELETE 호출
- `react-grid-layout` dependency와 관련 CSS import
- layout 전용 translation, CSS와 테스트

### 반드시 유지

- Dashboard, Endpoint Summary, Ingest Summary의 기존 DTO 의미
- optional `endpointId` scope
- time range URL state
- 30초 polling과 stale data 보존
- KO/EN locale
- current route와 drill-down link
- loading, empty, error, stale와 partial failure 구분
- keyboard focus, reduced motion와 accessible table/text fallback
- Backend dashboard layout route, OpenAPI schema, DB migration과 저장 row

### 금지

- Backend layout API 또는 migration 삭제
- 새 API·DTO·enum 추가
- 기존 DTO에 optional field를 임의 추가
- previous value, delta, 담당자, SLA 또는 추정 지표 생성
- 원본 Alert/Event를 client에서 재집계해 server aggregate를 대체
- 누락된 time bucket을 근거 없이 0으로 채우기
- 모든 card에 gradient, glow, glass 효과 추가
- 실제 selection state가 없는 queue row를 계속 선택된 것처럼 표시
- backend, unrelated page 또는 graph 기능의 opportunistic refactor

Backend 계약 변경이 정말 필요하다고 판단되면 구현하지 말고 현재 계약·코드 근거, 막히는 완료 조건과 최소 대안을 보고한다.

## 7. 실행 방식

`OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`의 Work Package를 다음 순서로 수행한다.

```text
OVR-01 → OVR-02 → OVR-03 → OVR-04 → OVR-05
```

규칙:

1. 한 번에 하나의 Package만 `진행 중`으로 표시한다.
2. Package 구현 전 관련 코드와 test를 다시 확인한다.
3. 구현 후 targeted test와 해당 viewport를 검증한다.
4. 실행계획의 Package 절에 변경 파일, 판단, 명령, 결과와 남은 위험을 기록한다.
5. 검증이 끝난 Package만 `완료`로 바꾼다.
6. 다음 Package로 계속 진행한다. 단순히 한 Package가 끝났다는 이유로 사용자 확인을 기다리지 않는다.
7. 같은 원인의 실제 blocker가 아니면 OVR-05와 최종 Release Gate까지 작업을 이어간다.

## 8. Package별 작업지시

### OVR-01. DnD 제거와 고정 골격

목표:

- `OverviewPage.tsx`에서 layout fetch, editor hook, RGL render와 save/migration state를 제거한다.
- `react-grid-layout`을 package와 lockfile에서 제거한다.
- Frontend API client의 layout method만 제거한다.
- `dashboardLayout.ts`와 layout editor test·fixture를 제거한다.
- 승인 시안의 10개 block을 고정 DOM과 CSS grid로 렌더링한다.

구조 원칙:

- `OverviewPage.tsx`는 query, URL filter, refresh와 page state에 집중한다.
- 동적 registry가 더 이상 이점을 주지 않으면 고정 `OverviewDashboard` composition으로 교체한다.
- 기존 사용자 layout 응답을 읽거나 병합하지 않는다.
- 1280px 이상은 `state+4 KPI / 2:1:1 / 1:1`의 세 행이다.

이 Package에서는 chart 외형을 완성하려고 범위를 넓히지 않는다. 실제 content 또는 skeleton이 최종 DOM 순서와 geometry를 증명하면 된다.

### OVR-02. EDR State와 KPI

목표:

- EDR overall status와 score를 표시한다.
- Threat Level과 Collection Health score/status를 horizontal diagnostic bar로 표시한다.
- reason code와 calculated time을 숨기지 않는다.
- Total Alerts, Critical Alerts, High-risk Endpoints, Open Incidents를 연결한다.

주의:

- Critical Alerts는 서버 `bySeverity`에서 찾는다.
- High-risk Endpoints는 Endpoint Summary contract의 정의를 그대로 사용한다.
- API가 비교값을 제공하지 않으므로 delta 행을 만들지 않는다.
- KPI를 클릭 가능하게 만들 때는 실제 route와 filter가 존재할 때만 명시적인 link를 둔다.

### OVR-03. Detection Activity와 분포

목표:

- Detection Activity를 Events, Alerts, Open incidents의 세 small multiples로 구현한다.
- 공통 time domain, crosshair와 exact tooltip을 제공한다.
- Alert Severity와 Endpoint Risk는 semantic HTML/CSS horizontal bar로 구현한다.

ECharts 규칙:

- 현재 dependency에 없다면 이 Package에서만 `echarts`를 추가한다.
- `echarts/core`와 필요한 chart/component/renderer만 등록한다.
- Overview route에서 lazy load해 초기 route bundle과 분리한다.
- 첫 render 이후 polling에서 entry animation을 반복하지 않는다.
- `prefers-reduced-motion`을 존중한다.
- Canvas/SVG chart와 별개로 항상 접근 가능한 요약과 table fallback을 제공한다.
- keyboard, resize, print 또는 bundle 기준을 충족하지 못하면 무리하게 완료 처리하지 말고 원인과 대안을 기록한다.

시간축 규칙:

- Backend bucket timestamp를 정렬한다.
- 각 series의 누락값은 `null`로 유지한다.
- 서로 다른 bucket을 client에서 새 의미로 재집계하지 않는다.
- point가 부족하면 선을 과장하지 않고 값·empty 설명과 table을 제공한다.

### OVR-04. 조사 대기열과 UX 상태

목표:

- Highest-risk Endpoints를 risk score bar, active Alert, open Incident와 detail link로 구현한다.
- Incident Queue를 title, severity, status, alert count, last detected와 detail link로 구현한다.
- Endpoint scope를 paged search로 전환하고 현재 500건 prefetch를 제거한다.
- section별 loading, partial error, stale, empty를 완성한다.

주의:

- 기본 ranking은 server risk sort의 첫 5개다.
- selected Endpoint scope에서는 실제 scoped result만 표시한다.
- 전체 row click에만 의존하지 않고 primary link를 제공한다.
- hover에서만 action이나 핵심 count를 노출하지 않는다.
- polling으로 focus, scroll, 열린 popover와 URL selection을 초기화하지 않는다.

### OVR-05. 통합 QA와 문서 동기화

목표:

- 승인 시안과 1440px screenshot을 비교해 hierarchy, geometry, whitespace와 강조를 조정한다.
- 1280, 1024, 768, 360px과 KO/EN을 검증한다.
- keyboard-only, 200% zoom, reduced motion, normal/zero/empty/partial/stale를 검증한다.
- `DESIGN.md`, `FRONTEND_SPEC.md`와 실제 구현의 drift를 제거한다.
- 실행계획의 Release Gate와 모든 Package 증거를 완료한다.

시각 QA에서는 장식의 미세한 차이보다 다음을 우선한다.

1. 10개 block 순서
2. 첫 행의 EDR state와 4 KPI
3. 분석 행의 `2:1:1` 비율
4. 대기열 행의 `1:1` 비율
5. toolbar와 panel의 동일 좌우 edge
6. 핵심 값의 hover-independent readability
7. label collision과 horizontal overflow 부재

## 9. 검증 명령

이번 작업은 Frontend-only이며 Backend 계약·runtime을 변경하지 않는다. Docker image build, `docker compose build`, 전체 stack 재기동과 Backend 전체 test는 기본 검증에 포함하지 않는다.

### 빠른 작업 루프: OVR-01~OVR-04

각 Package에서는 변경 영역의 test만 실행한다. 같은 명령을 작은 CSS 조정마다 반복하지 않고 Package 완료 직전에 한 번 실행한다.

예시:

```bash
cd /Users/geonha/Desktop/team-C/frontend
npm run test -- overview-redesign.test.tsx components.test.tsx locale.test.tsx
npm run typecheck
```

- 실제 변경과 무관한 test file은 명령에서 제외한다.
- visual 확인은 이미 실행 중인 Backend와 Vite dev server를 재사용한다.
- package마다 모든 viewport를 반복하지 않는다. OVR-01~04는 1440px smoke와 해당 변경에 필요한 대표 viewport만 확인한다.
- `npm run build`, 전체 `npm run test`, 전체 lint, OpenAPI check와 전체 viewport matrix는 OVR-05까지 미룬다.
- API 문서·schema·generated client를 변경하지 않았다면 중간 Package에서 OpenAPI export/check를 반복하지 않는다.

### 최종 검증: OVR-05에서 한 번

```bash
cd /Users/geonha/Desktop/team-C/frontend
npm run openapi:check
npm run typecheck
npm run lint
npm run test
npm run build
```

Docker를 사용하는 최종 full-stack 검증은 다음 세 조건을 모두 만족할 때만 예외적으로 수행한다.

1. 기존 실행 중 서비스나 Frontend test로 핵심 동작을 검증할 수 없다.
2. 실패가 Frontend 코드인지 integration 환경인지 구분하는 데 필요하다.
3. 실행계획에 필요한 이유와 예상 비용을 먼저 기록한다.

단순한 시각 QA, TypeScript 검증, ECharts bundle 확인과 Frontend route 테스트를 위해 Docker를 rebuild하지 않는다.

추가 확인:

```bash
rg -n "react-grid-layout|dashboardLayout|saveDashboardLayout|resetDashboardLayout" src tests package.json
git diff --check
git status --short --branch
```

`dashboardLayout` 문자열은 Backend나 generated schema가 아니라 Frontend runtime·test에서 제거됐는지를 구분해 판단한다.

## 10. 완료 조건

다음이 모두 충족돼야 작업이 끝난다.

- OVR-01~OVR-05가 모두 `완료`다.
- DnD·resize·layout editor와 Frontend layout API 호출이 없다.
- Backend layout 계약과 데이터는 변경되지 않았다.
- 10개 block이 승인 순서와 desktop 비율로 표시된다.
- 모든 값이 실제 현재 DTO에서 나온다.
- Detection Activity와 두 분포가 정확한 단위·범위·fallback을 제공한다.
- Endpoint scope가 전체 fleet prefetch 없이 동작한다.
- loading, empty, error, stale와 partial failure가 구분된다.
- KO/EN, keyboard, 200% zoom과 reduced motion을 통과한다.
- 1440, 1280, 1024, 768, 360px에서 page-level overflow가 없다.
- OpenAPI check, typecheck, lint, test와 production build가 통과한다.
- 실행계획에 실제 명령, 결과, bundle 변화와 남은 위험이 기록됐다.

## 11. 중단 조건

다음 경우에만 작업을 중단하고 사용자에게 보고한다.

- 현재 branch나 기존 변경을 보존한 채 작업을 시작할 수 없음
- 현재 API 계약으로 승인된 핵심 값을 만들 수 없음
- 필요한 dependency 설치가 권한·network 때문에 반복 실패함
- 동일 blocker가 안전한 대안을 검토한 뒤에도 해결되지 않음
- Backend 계약 변경 없이는 Release Gate를 통과할 수 없음

일반적인 test 실패, TypeScript 오류, CSS 조정과 chart 구현 난이도는 중단 사유가 아니다. 원인을 진단하고 범위 안에서 수정한다.

## 12. 최종 보고 형식

최종 응답은 다음 순서로 작성한다.

1. 구현 결과 한 문단
2. 주요 변경 4–7개
3. 제거한 DnD/layout 범위
4. 실제 데이터와 시각화 계약
5. 실행한 자동 검증과 결과
6. viewport·접근성·KO/EN 시각 QA 결과
7. bundle 변화
8. 남은 위험 또는 `없음`
9. commit/push 여부

검증하지 않은 항목을 성공으로 표현하지 않는다.

## 13. 새 스레드 시작 프롬프트

아래 문장을 새 Codex 스레드의 첫 메시지로 사용한다.

```text
/Users/geonha/Desktop/team-C에서 Overview dashboard 개편을 끝까지 구현해줘.

먼저 frontend/AGENTS.md, docs/frontend/DESIGN.md,
docs/frontend/OVERVIEW_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md,
docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md를 순서대로 끝까지 읽고,
작업지시서가 지정한 나머지 source of truth와 현재 코드를 확인해.

현재 overview-dashboard-redesign branch의 미커밋 문서 변경과 승인 시안은
의도된 선행 작업이므로 절대 reset, restore, stash하거나 버리지 마.

OVR-01부터 OVR-05까지 한 번에 하나씩 진행 중으로 표시하고,
각 Package의 구현·테스트·브라우저 QA·증거 기록을 끝낸 뒤 다음 Package로 계속 진행해.
단순 중간 보고만 하고 멈추지 말고 Release Gate까지 완료해.

Backend dashboard layout API와 DB schema는 유지하되 Frontend의 DnD, resize,
layout editor, layout 저장·migration과 react-grid-layout은 제거해.
현재 DTO에 없는 값이나 가짜 지표는 만들지 마.

Frontend-only 작업이므로 Docker build/rebuild와 전체 stack 재기동은 기본 검증에서 제외해.
OVR-01~04는 targeted test와 대표 viewport만 확인하고,
전체 test, lint, build, OpenAPI check와 viewport matrix는 OVR-05에서 한 번만 실행해.

커밋, push, PR은 하지 말고 최종 결과와 검증 증거를 보고해.
```
