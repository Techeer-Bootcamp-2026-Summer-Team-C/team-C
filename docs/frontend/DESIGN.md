# EDR Console Frontend Design

- 문서 상태: Approved v3.1
- 작성일: 2026-07-15
- 적용 대상: `frontend/`
- 역할: 프론트엔드 UI 개편의 시각·상호작용 source of truth
- 참고 기준: 현재 구현과 기존 문서는 현황 파악에 사용하되, 새 구현의 최종 판단은 이 문서의 `확정` 항목을 따른다.

## 1. 문서 운영 원칙

이 문서는 기존 화면을 설명하는 문서가 아니라 새 UI를 설계하고 구현하기 위한 작업 기준이다.

각 항목은 다음 상태 중 하나로 관리한다.

| 상태 | 의미 | 구현 가능 여부 |
| --- | --- | --- |
| `확정` | 팀이 채택한 목표 디자인 | 구현 가능 |
| `제안` | 검토 중인 기본안 | PoC까지만 가능 |
| `결정 필요` | 선택지가 남은 항목 | 본 구현 금지 |
| `제외` | 이번 개편 범위에 포함하지 않음 | 구현 금지 |

충돌 시 문서 우선순위는 다음과 같다.

1. API·데이터 의미: `docs/contracts/API_SPEC.md`, `docs/contracts/RISK_POLICY.md`
2. 시각·레이아웃·상호작용: 이 문서
3. 현재 Overview 개편의 범위·순서·진행 상태: `docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`
4. Route·query·polling·권한 동작: `docs/frontend/FRONTEND_SPEC.md`
5. 현재 구현: `frontend/src/`
6. 종료된 아이디어·회의 자료: Git history

기존 문서의 디자인 관련 내용은 자동으로 새 기준에 포함되지 않는다. 필요한 내용만 검토 후 이 문서에 옮기고 상태를 `확정`으로 변경한다.

## 2. 참고 자료와 보존 범위

| 자료 | 새 문서에서의 역할 |
| --- | --- |
| `FRONTEND_SPEC.md` | 현재 Route, API mapping, 상태 처리와 기존 Design System 참고 |
| `OVERVIEW_DASHBOARD_REDESIGN_PLAN.md` | 승인된 Overview 시안, 현재 구현 범위·순서와 검증 증거 |
| `assets/references/overview-dashboard-target.png` | 1440px Overview 시각·정보 위계 기준 |
| `frontend/src/styles.css` | 현재 token과 responsive 동작의 baseline |
| `frontend/src/components/` | 공통 컴포넌트 재사용성 판단 근거 |
| `frontend/src/pages/` | 화면별 실제 데이터와 동작 범위 확인 |
| [VoltAgent Awesome DESIGN.md](https://github.com/VoltAgent/awesome-design-md) | AI가 읽기 좋은 디자인 문서 구조와 pattern vocabulary 참고 |
| [Sentri-inspired DESIGN.md 사례](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/sentry/DESIGN.md) | token, typography, component, elevation을 구체적으로 기록하는 문서 형식만 참고. marketing visual은 참고하지 않음 |
| [Taste Skill](https://www.tasteskill.dev/) | audit-first, consistency lock, anti-generic, pre-flight 원칙 참고 |
| [Shadcnblocks Admin Dashboard](https://shadcnblocks-admin.vercel.app/ecommerce/dashboard-1) | KPI, chart, table, toolbar의 정보 계층과 hover interaction을 보는 1차 UI 참고 |
| [v0 Shadcn Dashboard](https://v0.app/templates/shadcn-dashboard-Pf7lw1nypu5) | responsive dashboard와 data table pattern 비교 참고 |
| [Shopeers Analytics](https://dribbble.com/shots/26628350-Shopeers-AI-Powered-B2B-eCommerce-Analytics-Dashboard) | dark B2B dashboard의 분위기와 accent 사용 참고 |
| [Sales Analytics CRM](https://dribbble.com/shots/27107098-Sales-Analytics-CRM-Dashboard-Design) | dark surface에서의 hierarchy와 data density 참고 |
| [Finbro Dashboard](https://v0.app/templates/finbro-dashboard-shuOX59VNOv), [SalesOps Dashboard](https://v0.app/templates/salesops-dashboard-9q2Mfgu6cDi) | palette와 composition 비교 참고. domain 구조는 차용하지 않음 |

종료된 회의·실행 문서는 확정 내용을 이 문서로 이관한 뒤 Git 이력에 보존하고 working tree에서는 제거할 수 있다.

### 2.1 팀 토의 이미지 해석 — `확정`

2026-07-15에 확인한 팀 토의 이미지는 화면을 복제하기 위한 시안이 아니라, 아래 pattern의 필요성을 설명하는 시각 참고로 사용한다.

| 파일 | 참고할 pattern | 적용 경계 |
| --- | --- | --- |
| `Image20260715205307.png` | Incident Workbench의 `legend + graph + selected context`, Attack Timeline과 Process Tree의 연속 조사 구조 | 브랜드, 데이터, node 배치, 색상을 그대로 복제하지 않음 |
| `Image20260715205314.png` | Endpoint egress topology와 선택 context, graph 아래 evidence table의 병행 | API에 없는 network 관계나 탐지 결과를 생성하지 않음 |
| `Image20260715205319.png` | Overview의 KPI strip, detection trend, source distribution, realtime event stream, Incident table 계층 | 저해상도 구성 참고로만 사용하며 화면을 그대로 복제하지 않음 |
| `Image20260715205913.png` | Grafana식 동일 gutter panel grid, compact time control, chart와 stat panel의 혼합 | 범용 monitoring 지표를 EDR 지표로 단순 치환하지 않음 |

기존 팀 토의 이미지 원본은 repo 외부 자료다. 2026-07-16에 승인된 Overview 구현 시안만 `docs/frontend/assets/references/overview-dashboard-target.png`로 보존하며, 이 시안은 실제 DTO로 구현 가능한 정보와 고정 레이아웃의 기준으로 사용한다. 토의 메모에 포함된 `Image20260715211828.png`는 확인되지 않아 해석하지 않는다.

### 2.2 Reference traceability — `확정`

외부 레퍼런스는 링크를 나열하는 데서 끝내지 않고 채택할 pattern과 적용하지 않을 요소를 함께 기록한다. 이 표가 외부 화면보다 우선한다.

| Reference | 채택할 pattern | 적용하지 않을 요소 | 적용 절 |
| --- | --- | --- | --- |
| Awesome DESIGN.md | theme, semantic color role, full type hierarchy, component state, layout, elevation, responsive, Do/Don't, agent handoff 구조 | 외부 브랜드 token과 identity 복사 | 6, 7, 8, 12, 14 |
| Sentri-inspired DESIGN.md | token에 값·역할·사용처를 함께 기록하고 type·shape·depth를 표로 고정하는 방식 | violet/lime palette, starfield, sticker mascot, marketing hero | 6.3–6.6 |
| Shadcnblocks Admin Dashboard | KPI의 현재 값·비교 기준·delta 계층, 일관된 card geometry, chart header와 legend, compact toolbar, hover/focus detail | e-commerce 정보 구조, 제품명·색상·컴포넌트 복제 | 7.3, 8.5–8.8, 9.2 |
| v0 Shadcn Dashboard | server data와 연결되는 sorting·filtering table, responsive dashboard 구성 | record drag reorder, Tailwind·shadcn/ui·TanStack Table의 자동 도입 | 8.7, 13 |
| Shopeers, Sales Analytics CRM | dark B2B surface, accent로 핵심 값에 시선 집중, 높은 정보 밀도 속 명확한 hierarchy | AI assistant 내용, sales metric, purple brand palette | 6.1, 14.1 |
| Finbro, SalesOps | dark analytics composition의 비교 자료 | finance·sales domain, animation, glass UI | 14.2 |
| 팀 토의 이미지 4장 | Investigation context, Egress evidence, Overview hierarchy, Grafana식 panel grid | 브랜드·데이터·node 배치의 직접 복제 | 7.3, 9.2, 9.4, 9.7 |

Shadcnblocks와 v0는 pattern reference다. 현재 React/CSS 구조를 유지하는 것이 기본이며, Tailwind나 shadcn/ui 전체 migration은 별도 architecture decision과 PoC 없이 수행하지 않는다.

## 3. 현재 상태 요약

### 3.1 기술과 구조

- React 19, TypeScript, Vite 기반이다.
- Route는 Overview, Alerts, Incidents, Endpoints, Events, Intelligence, Operations, Archives로 구성된다.
- 아이콘은 `lucide-react`를 사용한다.
- 공통 UI는 `AppShell.tsx`, `ui.tsx`, `filters.tsx`, `charts.tsx`에 집중되어 있다.
- 전체 시각 스타일과 반응형 규칙은 단일 `styles.css`에 집중되어 있다.
- 기본 화면은 dark color scheme이며 compact navigation을 지원한다.

### 3.2 유지할 기반

다음 항목은 새 디자인에서도 유지하는 것을 기본안으로 한다.

- 보안 운영 화면에 맞는 dark-first 환경
- 색만으로 상태를 구분하지 않는 label·icon·text 병행
- Lucide icon 사용과 emoji icon 금지
- URL로 복원 가능한 filter·sort·page 상태
- chart·graph의 text 또는 table fallback
- Loading, Empty, Error, Stale, Partial failure 구분
- keyboard focus, skip link, reduced motion 지원
- 실제 API에 없는 흐름이나 인과관계를 시각적으로 꾸며내지 않는 원칙

### 3.3 현재 구현과 목표의 차이

현재 Overview 구현의 문제 목록, 우선순위와 처리 상태는 [Overview Dashboard Redesign Plan](./OVERVIEW_DASHBOARD_REDESIGN_PLAN.md)에서 관리한다. 이 문서에는 장기 목표 디자인과 유지할 기반만 남긴다.

## 4. 제품 경험 원칙

### 4.1 Investigation first — `확정`

사용자가 장식 요소보다 현재 상태, 근거, 조사 우선순위와 다음 행동을 먼저 발견할 수 있어야 한다.

### 4.2 Context preservation — `확정`

목록에서 상세로 이동하고 다시 돌아와도 filter, sort, page, time range와 조사 맥락을 잃지 않아야 한다.

### 4.3 Honest visualization — `확정`

관측된 데이터와 계산된 추론을 구분한다. API가 제공하지 않는 처리 흐름, 시간 이력, 인과관계, bandwidth를 애니메이션이나 graph로 암시하지 않는다.

### 4.4 Dense but calm — `확정`

운영 콘솔에 필요한 정보 밀도는 유지하되, 모든 panel이 같은 시각적 강도로 경쟁하지 않게 한다. 강조는 위험도, 실패, 선택 상태와 주요 action에 한정한다.

### 4.5 Accessible by default — `확정`

keyboard, screen reader, 200% zoom, reduced motion, locale 확장성을 완료 후 보정 항목이 아닌 기본 설계 조건으로 취급한다.

## 5. Information Architecture

### 5.1 Route — `확정`

기존 URL 계약은 유지한다.

| Route | 화면 목적 |
| --- | --- |
| `/` | 전체 상태와 조사 시작점 |
| `/alerts` | Alert 분류와 처리 |
| `/alerts/:alertId` | Alert 근거와 상태 변경 |
| `/incidents` | Incident 조사 대기열 |
| `/incidents/:incidentId` | 연결된 Alert·Event 조사 |
| `/endpoints` | Endpoint 위험과 수집 상태 탐색 |
| `/endpoints/:endpointId` | 개별 Endpoint 조사 |
| `/events` | 원본 Event 검색 |
| `/events/:eventId` | Event evidence 확인 |
| `/intelligence` | MITRE·egress·signal 관계 분석 |
| `/operations` | 수집·처리·저장 상태 확인 |
| `/operations/archives` | Archive 조회와 restore |

### 5.2 Navigation grouping — `확정`

사이드바는 조사 흐름에 맞춰 아래 group과 순서로 구현한다.

```text
OVERVIEW
  Overview

TRIAGE
  Alerts
  Incidents

EVIDENCE
  Endpoints
  Events

ANALYSIS
  Intelligence

PLATFORM
  Operations
    Archives
```

- URL은 변경하지 않는다.
- desktop은 group label을 제공하고 compact 상태에서는 tooltip과 accessible name을 유지한다.
- mobile은 focus를 가두는 modal drawer를 사용한다.
- 상세 화면에는 목록으로 돌아가는 link와 breadcrumb를 제공한다.
- `Archives`는 `Operations` 하위 route와 breadcrumb로 제공한다.
- 전역 검색 1차 범위는 현재 구현 범위를 명시하며 Alert·Event ID, hostname, Rule 확장은 별도 계약 후 진행한다.

## 6. Visual Direction

### 6.1 분위기 — `확정`

- 전문적인 EDR investigation console
- neutral surface를 중심으로 한 낮은 채도의 dark UI
- blue-violet은 primary action과 active navigation에, 별도 periwinkle은 keyboard focus에 제한
- red, orange, yellow, blue, green, cyan은 의미가 정해진 severity·health·information 상태에만 사용
- Case 1 dark theme에서는 gradient를 사용하지 않고 surface 명도 차이와 여백으로 깊이를 구분
- panel 수보다 정보 위계와 whitespace로 구획
- 이번 개편은 dark-only로 배포하되 semantic token은 future light theme를 추가할 수 있게 역할 기반으로 정의

### 6.2 Gradient — `사용 안 함`

Case 1 dark theme의 background, surface, selection과 chart series fill에는 gradient를 사용하지 않는다. 정보의 깊이는 `canvas → shell → panel → raised` 명도 단계, border와 whitespace로 구분한다. glow, glass effect와 상태색 기반 ambient background도 사용하지 않는다.

### 6.3 Color 역할 — `값 확정 / Case 1`

2026-07-17 전달된 `case-1-design-tokens.yaml`의 color 값을 구현 기준으로 확정했다. component에는 raw color를 추가하지 않고 `frontend/src/styles/tokens.css`의 semantic token을 사용한다. 전달 파일에 포함된 font와 typography 값은 이번 변경 범위가 아니므로 6.4의 임시 baseline을 유지한다.

| Semantic token | Prototype baseline | 역할 |
| --- | --- | --- |
| `--surface-canvas` | `#121318` | 전체 배경 |
| `--surface-shell` | `#17181D` | Navigation, top bar |
| `--surface-panel` | `#27282E` | 기본 panel |
| `--surface-raised` | `#32333B` | popover, selected surface |
| `--surface-inset` | `#1D1E24` | input, code, nested block |
| `--surface-hover` | `#34353D` | interactive hover |
| `--border-default` | `#707381` | control과 panel 경계 |
| `--border-subtle` | `#3A3C46` | 내부 구분선과 chart grid |
| `--focus-ring-color` | `#8EA2FF` | keyboard focus |
| `--text-primary` | `#F2F3F7` | 제목과 핵심 값 |
| `--text-secondary` | `#C7C9D2` | 설명과 보조 정보 |
| `--text-tertiary` | `#9A9DAA` | 낮은 우선순위 meta |
| `--accent-primary` | `#8296FF` | primary action과 active navigation |
| `--status-critical` | `#FF5968` | Critical, RED, unavailable |
| `--status-high` | `#FF8A4C` | High severity와 high risk |
| `--status-medium` | `#F4B942` | Medium severity |
| `--status-low` | `#8DB5FF` | Low severity |
| `--status-warning` | `#E5D36C` | YELLOW, offline, degraded, stale |
| `--status-success` | `#6AD7A3` | GREEN, online, healthy, resolved |
| `--status-info` | `#4BC8E8` | Open, in progress, informational state |
| `--status-neutral` | `#A6A9B6` | Closed, retired, unknown |
| `--chart-events` | `#4BC8E8` | Detection Activity Events |
| `--chart-alerts` | `#8B7CFF` | Detection Activity Alerts |
| `--chart-incidents` | `#F06DB2` | Detection Activity Open Incidents |

규칙:

- semantic status color를 brand 장식에 재사용하지 않는다.
- text contrast는 WCAG AA를 기본 목표로 한다.
- 상태는 색상 외에 text, icon, shape 중 하나 이상을 함께 사용한다.
- chart series 색상과 상태 색상은 용도를 구분한다.
- red는 화면 면적의 5% 미만으로 제한하고 card fill 또는 장식 border에 사용하지 않는다.
- 위험 KPI는 수치와 icon에만 semantic color를 주고 zero 값은 neutral로 표시한다.

### 6.4 Typography — `역할 확정 / 값 임시`

본문·제목·수치·metadata·code의 역할과 가독성 규칙은 확정한다. 아래 font family, size, weight와 scale은 팀이 최종 서체 체계를 지정하기 전까지 사용하는 구현 baseline이다. 후속 변경은 typography token과 root font stack에서 일괄 교체한다.

현재 UI는 `Inter`, `Segoe UI`, system UI 순서, ID·hash·path·raw payload는 `Cascadia Code`, `Consolas`, monospace 순서를 임시로 사용한다.

| Token | Size | Weight | Line height | Letter spacing | 사용처 |
| --- | ---: | ---: | ---: | ---: | --- |
| `--type-page-title` | 24px | 800 | 1.2 | -0.01em | Page title |
| `--type-section-title` | 18px | 800 | 1.25 | -0.005em | 주요 section과 workspace title |
| `--type-panel-title` | 15px | 700 | 1.35 | 0 | Panel, table, inspector title |
| `--type-kpi-primary` | 34px | 900 | 1 | -0.015em | 가장 중요한 KPI 값 |
| `--type-kpi-secondary` | 22px | 800 | 1.1 | -0.01em | 보조 KPI, chart center value |
| `--type-body` | 14px | 400 | 1.5 | 0 | 기본 설명과 table cell |
| `--type-body-strong` | 14px | 600 | 1.5 | 0 | 강조 본문과 primary row value |
| `--type-label` | 13px | 600 | 1.35 | 0 | Field label, compact control |
| `--type-meta` | 12px | 500 | 1.4 | 0.01em | timestamp, secondary metadata |
| `--type-code` | 13px | 500 | 1.45 | 0 | ID, hash, path, IP, raw value |

규칙:

- 13px 이하는 짧은 label과 metadata에만 사용하고 설명, 오류, guidance 본문은 최소 14px이다.
- 숫자 비교가 중요한 KPI와 table column에는 `font-variant-numeric: tabular-nums`를 적용한다.
- uppercase는 짧은 eyebrow, group label, enum에만 제한한다.
- 긴 ID·hash·path는 의미를 ellipsis로만 숨기지 않고 accessible detail과 copy 경로를 제공한다.
- EN과 KO에서 title과 label이 두 줄이 되어도 control 높이와 focus 영역이 깨지지 않아야 한다.

### 6.5 Spacing과 shape — `확정`

- 4px 기반 spacing scale로 정리한다.
- 주요 spacing: 4, 8, 12, 16, 20, 24, 32px
- control radius: 4px
- panel radius: 6px
- pill은 상태와 짧은 metadata에만 사용한다.
- shadow보다 border와 surface 차이를 우선한다.
- 기본 data density는 compact다. Form, guidance, 긴 설명처럼 읽기 여유가 필요한 영역만 comfortable spacing을 사용한다.
- 이번 개편에서는 사용자 density 전환 기능을 만들지 않는다.

### 6.6 Depth and Elevation — `확정`

`awesome-design-md`의 문서 구조를 따라 surface 계층과 elevation 역할을 명시한다.

| Level | 대상 | 표현 |
| --- | --- | --- |
| 0 Canvas | page background | shadow 없음 |
| 1 Shell | navigation, top bar | canvas와 surface 차이, 1px divider |
| 2 Panel | table, chart, summary | border와 surface 차이, inset highlight 제한 사용 |
| 3 Raised | popover, menu, tooltip | 명확한 border와 짧은 shadow |
| 4 Modal | dialog, blocking workflow | backdrop와 가장 강한 shadow |

- elevation은 중요도 장식이 아니라 실제 stacking과 interaction 관계를 설명해야 한다.
- 모든 card에 같은 shadow를 주지 않는다.
- nested panel은 shadow 대신 inset surface와 divider를 우선한다.
- selected, hover, focus는 elevation이 아니라 border, background, focus ring으로 구분한다.

## 7. Layout System

### 7.1 Breakpoint — `확정`

| 구간 | 너비 | 기본 동작 |
| --- | ---: | --- |
| Wide desktop | 1440px 이상 | 다열 dashboard, queue+detail |
| Desktop | 1024–1439px | 2–3열, 필요 시 compact navigation |
| Tablet | 768–1023px | 1–2열, drawer navigation, inspector 하단 이동 |
| Mobile | 360–767px | 단일 열, card/list 전환, filter drawer |

- 문서 최소 지원 viewport는 360px이다.
- `html`, `body`, `#root`의 고정 `min-width: 768px`는 제거 대상이다.
- content 최대 너비는 data-heavy 화면에서 1720px을 넘기지 않는다.
- 주요 page padding은 mobile 16px, tablet 20px, desktop 24px을 기본값으로 한다.

### 7.2 공통 화면 골격 — `확정`

```text
Page header
  Eyebrow / Title / Description
  Primary action / Last refreshed

Filter summary
  Time range / Primary filters / Applied chips / Clear

Decision summary
  KPI / Distribution / Change / Data caveat

Primary workspace
  Queue or table / Detail or inspector / Supporting evidence

Footer controls
  Result range / Page size / Pagination
```

### 7.3 Dashboard frame과 compact toolbar — `확정`

Grafana와 팀 토의 이미지는 panel 밀도와 control 압축 방식만 참고한다.

- `PageHeader`, toolbar, dashboard grid는 하나의 `DashboardFrame` horizontal inset을 공유한다.
- child grid가 음수 margin으로 frame 밖으로 나가지 않게 하며 첫·마지막 panel edge가 toolbar edge와 일치해야 한다.
- Overview desktop은 목적별 고정 CSS grid와 12px gutter를 사용한다. 범용 12-column 사용자 배치 grid는 사용하지 않는다.
- panel 내부 padding은 compact 12px, standard 16px을 기본으로 하며 한 화면에서 같은 역할의 panel은 동일 값을 사용한다.
- 좁은 화면에서는 column 수를 줄이고 DOM reading order와 keyboard order를 유지한다.

Overview 고정 grid:

```text
[ EDR state command strip ]
[ KPI ][ KPI ][ KPI ][ KPI ]
[ Detection Activity 2fr ][ Alert Severity 1fr ]
[ Highest-risk Endpoints 1fr ][ Incident Queue 1fr ]
```

Overview toolbar 기본 구조:

```text
[Endpoint scope] [Time range ▾] [Refresh] [Last updated]
```

- Time range와 Endpoint scope는 항상 펼쳐진 큰 bar가 아니라 button + Popover 또는 Drawer로 제공한다.
- 현재 time range와 Endpoint scope는 button label과 applied filter chip으로 확인할 수 있어야 한다.
- filter와 time range는 URL query를 source of truth로 유지한다.
- Overview block은 drag, drop, resize, hide, restore와 사용자 layout 저장을 제공하지 않는다.
- mobile에서는 주요 control을 첫 줄에 유지하고 나머지는 `More filters` Drawer로 이동한다.

## 8. Component Model

새 컴포넌트는 세 계층으로 관리한다.

### 8.1 Primitive — `확정`

- `Button`
- `IconButton`
- `TextField`
- `Select`
- `Checkbox`
- `Badge`
- `Tooltip`
- `Dialog`
- `Drawer`
- `Tabs`
- `Disclosure`

Primitive는 domain enum과 API DTO를 직접 알지 않는다.

### 8.2 Pattern — `확정`

- `PageHeader`
- `Panel`
- `FilterBar`
- `AppliedFilterList`
- `DataTable`
- `Pagination`
- `MasterDetail`
- `Inspector`
- `StateCard`
- `Skeleton`
- `ChartFrame`

Pattern은 loading, empty, error, permission, responsive behavior를 포함한다.

### 8.3 Domain — `확정`

- `EdrStateSummary`
- `SeverityBadge`
- `RiskSummary`
- `AlertQueue`
- `EvidenceChain`
- `ProcessTree`
- `AttackTimeline`
- `MitreMatrix`
- `EgressTopology`
- `PipelineHealth`
- `ArchiveLifecycle`

Domain component는 API contract의 enum과 의미를 따르며 frontend에서 값을 재해석하지 않는다.

### 8.4 공통 상태 — `확정`

| 상태 | 표현 규칙 |
| --- | --- |
| Initial loading | 최종 layout과 같은 크기의 skeleton |
| Refetching | 기존 content 유지, 갱신 상태를 작게 표시 |
| Stale | 마지막 성공 시각과 retry action 표시 |
| Partial failure | 정상 영역 유지, 실패 영역만 error 처리 |
| Empty | 데이터 자체 없음과 filter 결과 없음 구분 |
| Invalid filter | 문제 field 가까이에 원인과 해결 방법 표시 |
| Read only | control 제거 또는 명확한 disabled 이유 제공 |
| Permission denied | session을 유지하고 권한 부족을 설명 |
| Archive not ready | 일반 오류와 구분하고 restore 경로 제공 |

### 8.5 Component state contract — `확정`

| Component | Default | Hover / Focus | Active / Selected | Disabled / Loading / Error |
| --- | --- | --- | --- | --- |
| Button | text·icon·hierarchy가 명확함 | hover는 surface 변화, focus는 2px ring | pressed는 짧은 surface 변화 | disabled 이유를 인접 text 또는 tooltip으로 설명, loading 중 label 유지 |
| Field | label, value, optional helper | focus ring과 label 관계 유지 | 입력값과 applied 상태 구분 | invalid message는 field 근처에 제공, disabled는 submit 대상이 아님을 표시 |
| Panel | title, optional subtitle·meta, content | interactive panel만 hover 처리 | selected는 border와 inset surface로 구분 | skeleton은 최종 크기 유지, partial error는 panel 내부에서 격리 |
| Tooltip | 닫힌 상태에서 layout에 영향 없음 | hover와 keyboard focus 모두 열림 | 해당 없음 | trigger가 disabled면 설명 가능한 wrapper 사용 |
| Popover | trigger에 현재 값과 expanded state 제공 | focus-visible 유지 | 열린 동안 `aria-expanded=true`, Escape와 outside click 지원 | loading과 error를 popover 안에서 표시하고 trigger를 잃지 않음 |
| DataTable | caption, header, row, pagination | row hover와 keyboard 가능한 primary link focus | selected row는 `aria-selected`와 surface로 표시 | loading row, empty, error를 서로 다른 상태로 표시 |
| ChartFrame | title, unit, range, legend, plot | mark hover와 focus가 같은 detail 제공 | selected series·mark와 Inspector 연결 | skeleton, empty, partial error, table fallback 제공 |

색상만으로 state를 구분하지 않는다. hover state가 없는 touch 환경에서도 동일한 정보와 action에 접근할 수 있어야 한다.

### 8.6 KPI card anatomy — `확정`

Shadcnblocks의 비교 구조를 EDR 지표에 맞게 다음 순서로 사용한다.

```text
Label
Current value
Comparison basis · Previous value
Signed delta · Direction text
Optional caveat / Last updated
```

- KPI는 단위, 집계 범위, time range를 함께 제공한다.
- previous value나 delta가 API에 없으면 계산하거나 `0%`로 꾸미지 않고 비교 행을 생략한다.
- delta는 `+/-`, 값, `vs previous period` 같은 비교 기준을 함께 표시한다.
- 증가가 항상 좋은지 나쁜지 지표 의미에 따라 판단하며 green/red를 단순 증감에 자동 적용하지 않는다.
- KPI 전체를 link로 만들지 않는다. drill-down이 있으면 명시적인 label 또는 trailing action을 제공한다.
- 정의나 계산식은 Tooltip으로 보조할 수 있지만 현재 값과 상태는 hover 없이 읽혀야 한다.

### 8.7 Tooltip과 Popover — `확정`

Tooltip은 짧은 보조 설명, Popover는 선택·설정·상세 interaction에 사용한다.

Tooltip 허용:

- KPI 정의와 비교 기간 설명
- chart mark의 exact timestamp, value, unit
- truncated identifier의 전체 값
- icon-only control의 accessible name 보조

Popover 허용:

- Time range preset과 custom range
- refresh interval
- Endpoint switcher 검색 결과
- column visibility 또는 layout option

규칙:

- Tooltip은 pointer hover와 keyboard focus에서 열리고 Escape로 닫혀야 한다.
- Popover trigger는 `aria-expanded`, `aria-controls`와 현재 선택값을 제공한다.
- 핵심 오류, 위험 상태, primary action과 필수 입력은 Tooltip에만 넣지 않는다.
- touch 환경은 click/tap으로 동일 content에 접근할 수 있어야 한다.
- interactive content가 있으면 Tooltip이 아니라 Popover 또는 Dialog를 사용한다.

### 8.8 DataTable — `확정`

- semantic `<table>`, caption 또는 accessible label, `scope=col` header를 유지한다.
- sticky header, server pagination, loading row, empty, error, selected row를 공통 pattern으로 제공한다.
- sortable header는 현재 field와 direction을 `aria-sort`와 icon으로 표시한다.
- 숫자와 timestamp column은 tabular number와 일관된 정렬을 사용한다.
- primary identifier는 첫 column의 명시적인 link로 제공하고 전체 row click에만 의존하지 않는다.
- secondary action은 마지막 column 또는 row action menu에 두며 hover에서만 나타나지 않는다.
- 긴 ID·path는 wrap, copy, detail 중 하나를 제공하고 ellipsis만 사용하지 않는다.
- records와 dashboard block은 drag reorder하지 않는다.
- mobile은 중요한 column을 우선 유지하고 horizontal scroll 또는 list fallback을 제공한다.
- row divider를 모든 경계의 장식으로 중복 사용하지 않고 header, group, selected state 중심으로 hierarchy를 만든다.

## 9. Page Blueprint

### 9.1 Login — `확정`

- 이번 시각 개편에 포함한다.
- 제품·환경 설명과 인증 form을 분리한다.
- locale 정책과 관계없이 인증 오류, session 만료, keyboard 흐름을 유지한다.

### 9.2 Overview — `확정`

Overview는 다음 세 질문만 답한다.

1. 지금 전체 상태는 정상, 주의, 위험 중 무엇인가?
2. 그 상태를 만든 가장 중요한 원인은 무엇인가?
3. 지금 어떤 Alert, Incident, Endpoint부터 조사해야 하는가?

기본 구조:

- EDR state와 주요 원인
- Total Alerts, Critical Alerts, High-risk Endpoints, Open Incidents KPI
- Detection activity
- Alert severity
- Highest-risk Endpoints
- Incident queue

KPI card는 8.6의 anatomy를 따르며 API가 비교값을 제공하지 않으면 previous value와 delta를 만들지 않는다. Time range, Endpoint scope와 refresh는 7.3의 compact toolbar에 둔다.

신규 기본 Overview에서 제거할 8개:

1. Endpoint operating systems
2. Sensor health
3. Top rules
4. MITRE detection distribution
5. Process and network signals
6. File, DNS, and L7 signals
7. Failure distribution
8. Storage distribution

소유 화면:

| 제외 후보 | 소유 화면 |
| --- | --- |
| Endpoint operating systems | Endpoints inventory와 filter |
| Sensor health | Endpoint Detail의 개별 상태, Operations의 전체 Collection Health |
| Top rules | Alerts filter와 Intelligence 분석 |
| MITRE detection distribution | Intelligence |
| Process, Network, File, DNS, L7 signals | Intelligence 집계와 Events 원본 근거 |
| Failure distribution | Operations |
| Storage distribution | Operations와 Archives |

기본 Overview는 위 9개 block으로 제한한다. Endpoint risk distribution은 중복 위계와 공간 낭비를 줄이기 위해 Overview에서 제거하지만 High-risk Endpoints KPI와 서버 Endpoint summary query는 유지한다. 위 8개 widget은 표시하지 않고 기존 사용자 저장 layout도 Frontend에서 읽거나 migration하지 않는다. Backend layout API와 저장 데이터는 호환성을 위해 유지한다. Events·Online Endpoints·Storage·Guidance 요약은 각각 Detection Activity·Collection Health·Archives·Alert Detail로 이동하거나 통합한다. 팀 이미지의 realtime event stream은 Overview 기본 block으로 직접 복제하지 않는다.

### 9.3 Alerts — `확정`

- desktop: triage queue와 Alert detail의 split layout
- 기본 정렬: 처리 상태 → Severity → Risk, 최신 시각은 보조 기준. 사용자가 정렬을 변경할 수 있음
- 주요 정보: Severity, Risk, Status, Rule, Endpoint, detected time
- 상태 변경은 권한과 성공·실패 결과를 명확히 표시
- `저장`과 `저장 후 다음`을 분리해 사용자가 이동 여부를 선택한다.

Alert Detail의 Response guidance:

- Alert의 `ruleCode`, `ruleVersion`과 함께 읽기 전용 guidance임을 표시한다.
- 각 step은 order, title, description, `MANUAL ACTION` badge 순으로 읽힌다.
- compact mode에서도 title과 description을 숨기지 않으며 긴 목록은 처음부터 잘라내지 않고 disclosure 또는 scroll container를 사용한다.
- guidance가 없으면 `[]`에 대응하는 명확한 Empty state를 제공한다.
- checkbox, Run button, command status, 자동 완료, Agent command ID, 원격 격리, 프로세스 종료, 파일 삭제 action을 만들지 않는다.
- Rule provenance나 영향 Alert 연결처럼 현재 DTO에 없는 per-step 정보는 별도 API contract 없이는 표시하지 않는다.

Overview에 Response guidance summary를 유지하는 경우 현재 Dashboard DTO 범위인 affected Alert 수, Rule 수, manual action step 수, highest severity와 ordered step만 표시한다. Alert Detail을 상세 소유 화면으로 사용하고 실행 가능한 playbook처럼 표현하지 않는다.

### 9.4 Incidents — `확정`

- OPEN Incident를 먼저 조사할 수 있는 queue 제공
- desktop 상세의 대표 구조는 `Legend | Investigation graph | Selected context`이며 tablet 이하에서는 Selected context를 graph 아래로 이동
- graph node 선택은 관련 Alert·Event·Endpoint를 Inspector에 표시하고 같은 선택을 timeline과 evidence list에 연결
- Legend는 Incident, Alert, Process, Network edge, Event의 실제 포함 여부와 count를 표시
- 상세 하단은 관측 순서 Attack Timeline과 Process Tree 또는 evidence table로 구성
- Process Tree는 관련 Endpoint와 time range가 확보된 경우에만 제공
- 관측 순서를 확인된 공격 인과관계처럼 표현하지 않는다.
- graph를 구성할 충분한 evidence가 없으면 관련 Alert·Event 목록을 기본 fallback으로 제공한다.

### 9.5 Endpoints — `확정`

- 목록 우선순위: Risk, stale/status, active Alert, open Incident, last seen, OS
- fleet inventory table은 유지하며 Endpoint page 전체를 dropdown으로 대체하지 않는다.
- Endpoint Detail header에 searchable `EndpointSwitcher` combobox를 제공한다.
- switcher option은 hostname을 primary label, Endpoint ID·agent ID·status·risk를 secondary 정보로 사용한다.
- keyboard에서 입력, option 이동, 선택, Escape 닫기가 가능하고 선택 시 `/endpoints/:endpointId` route를 갱신한다.
- 목록에서 상세로 진입한 filter·sort·page와 time range는 복귀 context로 보존한다.
- Backend의 paged Endpoint search contract를 추가해 hostname, agent ID와 exact Endpoint ID autocomplete를 제공한다.
- client에서 전체 Endpoint를 무제한 prefetch하지 않고 query와 pagination을 유지한다.
- 상세는 risk factor, collection health, related Alert·Incident, recent Event, profile을 분리하고 위험·수집 상태를 먼저 배치한다.
- Profile은 OS, IP, Agent version/build/arch, capability, certificate를 의미 group으로 나눈다.
- 실제 time series가 없는 profile·sensor snapshot을 추이 chart처럼 만들지 않는다.
- Process Tree는 endpoint와 time range가 확보될 때만 진입점을 제공

### 9.6 Events — `확정`

- 기본 filter: time, Endpoint, Event type
- 상세 field는 Process, File, Network, DNS, HTTP/TLS, Identity group으로 구분
- Process Tree를 raw payload보다 먼저 배치
- raw payload는 접힌 상태로 제공하고 copy와 내부 검색을 지원

### 9.7 Intelligence — `확정`

- MITRE는 tactic·technique matrix와 선택 Inspector 구성
- egress는 graph와 table fallback을 함께 제공
- desktop Egress Topology는 `Legend | Graph | Selected context` 구조를 사용하고 좁은 화면에서는 세로로 재배치
- Endpoint node, target node와 edge의 alert/observed 상태를 color, label, line style로 함께 구분
- node·edge 선택 상태와 연결된 Event·Alert를 명확히 표시하고 graph 아래 evidence table의 같은 row를 강조
- edge detail은 protocol, Event count, Alert count, last observed time만 사용하며 현재 데이터에 없는 bytesOut을 추정하지 않음
- node가 많을 때 Top-N, 검색, filter를 제공

### 9.8 Operations와 Archives — `확정`

- Operations는 Collection, Detection, Storage 중 문제 영역을 먼저 설명
- pipeline은 현재 snapshot임을 표시하고 과거 흐름처럼 움직이지 않음
- Archives는 조회, lifecycle, restore action을 담당
- restore 요청 직후 완료처럼 보이지 않게 `RESTORE_REQUESTED`를 유지

## 10. Data Visualization

### 10.1 선택 원칙 — `확정`

- 값 비교: ranked bar 우선
- 시간 변화: line 또는 area chart
- 여러 단위의 시간 변화: small multiples
- 구성비: category가 적고 합계가 명확할 때만 donut
- 계층: tree
- 관계: node-edge graph와 Inspector
- 단계 상태: lifecycle board 또는 state list

### 10.2 공통 요구사항 — `확정`

- title, unit, time range, timezone, last updated를 제공한다.
- hover 없이도 핵심 값과 상태를 이해할 수 있어야 한다.
- keyboard로 선택 가능한 mark에는 명확한 focus를 제공한다.
- 빈 데이터와 0을 구분한다.
- text 또는 table fallback을 제공한다.
- animation을 정보 전달의 유일한 수단으로 사용하지 않는다.

### 10.3 기술 선택 — `확정`

| 범위 | 확정 기술 | 적용 조건 |
| --- | --- | --- |
| 정량 chart | ECharts | PoC에서 keyboard, resize, print, bundle size를 통과한 chart부터 기존 SVG를 교체 |
| 관계 graph | React Flow + Dagre | Incident와 Topology에 feature flag로 단계 적용하고 table/list fallback 유지 |
| motion | CSS 우선 | 복잡한 상태 전환에만 Motion for React를 제한적으로 추가 가능 |

PoC는 데이터 크기, keyboard 접근성, resize, print, bundle size를 함께 검증해야 한다.

## 11. Motion and Feedback

### 11.1 허용 — `확정`

- hover, focus, expand, collapse의 120–180ms transition
- filter 적용 후 선택 mark 위치 유지
- 선택 node·edge·row 강조
- 저장, retry, polling 상태의 짧은 feedback

### 11.2 금지 — `확정`

- polling마다 chart 전체가 다시 등장하는 animation
- 확인되지 않은 공격 인과관계 animation
- 실제 이동량이 아닌 값을 흐르는 edge로 표현
- 지속적으로 깜박이거나 회전하는 위험 효과
- `prefers-reduced-motion`에서 핵심 정보를 잃는 표현

## 12. Accessibility and Localization

### 12.1 접근성 — `확정`

- 주요 task는 keyboard만으로 완료 가능해야 한다.
- focus order는 시각적 순서와 일치해야 한다.
- dialog와 mobile navigation drawer는 focus를 관리한다.
- table은 caption 또는 accessible label, header association을 제공한다.
- chart와 graph는 요약 text와 data fallback을 제공한다.
- 200% zoom에서 기능과 content가 사라지지 않아야 한다.
- 최소 pointer target은 36px, 주요 mobile control은 44px을 목표로 한다.

### 12.2 언어와 용어 — `확정`

- EDR, Alert, Incident, Endpoint, Event, Rule, MITRE 등 domain noun은 의미 보존을 우선한다.
- 번역은 글자 치환이 아니라 실제 데이터와 동작 의미를 기준으로 한다.
- EN과 KO에서 button, table header, error message가 layout을 깨지 않아야 한다.
- enum label과 API value를 혼동하지 않는다.
- 날짜·숫자 표시는 locale을 따르되 API timestamp와 URL 값은 변경하지 않는다.

## 13. CSS와 파일 구조 — `확정`

```text
frontend/src/styles/
  tokens.css
  reset.css
  primitives.css
  shell.css
  patterns.css
  visualizations.css
  pages/
```

- 기존 `styles.css`를 한 번에 삭제하지 않고 단계적으로 이동한다.
- semantic token은 component selector보다 먼저 도입한다.
- page 전용 selector가 primitive behavior를 덮어쓰지 않게 한다.
- inline style은 data-driven geometry와 CSS custom property 전달에만 사용한다.

## 14. AI Design Workflow

### 14.1 Design Read — `확정`

프론트 구현을 시작하기 전에 다음 한 줄을 작업 기준으로 선언한다.

> 기존 multi-step EDR investigation console을 SOC 운영자가 빠르게 판단하고 조사하도록 개편한다. Serious B2B, trust-first, data-dense, dark-neutral 언어를 사용하고 motion은 기능적 feedback으로 제한한다.

Taste Skill의 조절 개념은 EDR 제품 UI에 맞게 다음처럼 고정한다.

| Dial | 값 | 해석 |
| --- | ---: | --- |
| Design variance | 3/10 | 비대칭 장식보다 예측 가능한 조사 흐름 우선 |
| Motion intensity | 2/10 | 상태 변화와 조작 feedback만 사용 |
| Visual density | 8/10 | 운영 정보 밀도는 높게, hierarchy는 차분하게 유지 |

### 14.2 Awesome DESIGN.md 활용 — `확정`

`awesome-design-md`는 완성된 브랜드 스타일을 복사하는 catalog가 아니라 다음을 점검하는 문서 구조 참고 자료로 사용한다.

- Visual theme와 atmosphere가 한 문장으로 설명되는가?
- color token에 이름, 값, 기능적 역할이 함께 있는가?
- typography hierarchy에 size, weight, line-height, 사용처가 있는가?
- component에 default, hover, focus, disabled, loading 상태가 있는가?
- layout, spacing, responsive, depth 규칙이 명시되어 있는가?
- Do와 Don't가 구현 판단으로 사용할 만큼 구체적인가?
- coding agent가 그대로 사용할 수 있는 handoff prompt가 있는가?

Sentry, IBM, ClickHouse 등 유사 사례는 비교 대상으로만 사용한다. 외부 브랜드의 color, font, illustration, trademark, layout을 그대로 복제하지 않는다. 채택할 pattern은 EDR task와 데이터 의미를 근거로 이 문서에 다시 기록한다.

### 14.3 Taste Skill 선택 적용 — `확정`

Taste Skill의 기본 설치는 현재 v2 experimental이며 brief inference, design-system mapping, redesign audit와 hard pre-flight를 폭넓게 제공한다. 동시에 hero와 marketing block에 관한 규칙도 포함하므로 이 EDR console에서는 [Taste Skill customization 원칙](https://www.tasteskill.dev/docs)에 따라 프로젝트 고유 `DESIGN.md`를 우선하고 필요한 규칙만 선별 적용한다. Shadcnblocks를 reference로 사용한다는 이유만으로 Tailwind나 shadcn/ui package를 자동 도입하지 않는다.

적용한다:

- 기존 코드와 화면을 먼저 scan하고 문제를 diagnose한 뒤 targeted fix 수행
- user, audience, task, brand, accessibility constraint를 구현 전에 확인
- Route, navigation label, form field, API contract를 조용히 변경하지 않음
- action accent, radius, theme를 화면 전체에서 일관되게 유지
- AI-purple gradient, 무의미한 glassmorphism, 과도한 pill, 장식용 status dot 금지
- 기존 dependency를 확인하고 새 package 도입 시 이유와 검증 기준 명시
- 구현 완료 전 hard pre-flight checklist 수행

적용하지 않는다:

- AIDA와 marketing hero 구조
- 무작위 layout 선택이나 창의성 자체를 위한 variance 증가
- cinematic section, scroll hijack, GSAP 중심 motion
- 사진, texture, ambient gradient를 빈 영역 채우기 용도로 추가
- data table과 운영 card를 marketing bento pattern으로 치환
- 가독성 근거 없이 Inter 또는 기존 font를 교체
- 하나의 accent 규칙을 semantic severity color까지 제거하는 방식으로 해석

Taste Skill consistency lock은 다음처럼 제품 UI에 맞게 해석한다.

| Lock | EDR 적용 방식 |
| --- | --- |
| Color consistency | brand/action accent는 하나로 유지하되 severity와 health semantic color는 예외 |
| Shape consistency | control과 panel radius 체계를 유지하되 status pill은 문서화된 예외 |
| Theme consistency | 한 화면 안에서 surface polarity를 임의로 뒤집지 않음 |

### 14.4 Do and Don't — `확정`

| Do | Don't |
| --- | --- |
| task와 데이터 의미에서 layout을 결정 | 예쁜 reference와 닮게 만들기 위해 task를 변경 |
| 한 화면의 primary action을 분명히 지정 | 모든 action에 accent color 사용 |
| table, queue, inspector의 밀도와 hierarchy를 조율 | 모든 정보를 같은 card 형태로 감싸기 |
| semantic token과 component state로 구현 | page마다 임의 hex와 radius 추가 |
| real data로 Loading, Empty, Error, Stale 검증 | happy path screenshot만 보고 완료 처리 |
| desktop과 mobile의 정보 우선순위를 별도로 설계 | desktop layout을 그대로 축소 |
| chart의 단위, 시간, timezone, fallback 제공 | 장식용 graph와 추정 animation 추가 |
| 외부 사례의 원리와 trade-off를 기록 | 브랜드 token이나 UI를 그대로 복사 |

### 14.5 작업 순서 — `확정`

1. 현재 화면과 코드, user task, API boundary를 audit한다.
2. 위 Design Read와 세 dial이 작업 범위에 맞는지 확인한다.
3. `awesome-design-md`에서 2-3개의 관련 pattern만 비교한다.
4. 선택한 pattern을 그대로 복사하지 않고 EDR task에 맞는 근거와 차이를 기록한다.
5. token 또는 primitive부터 구현하고 한 개 대표 화면에서 검증한다.
6. EN/KO, Loading, Empty, Error, Stale, permission 상태를 함께 구현한다.
7. 아래 pre-flight를 통과한 뒤 다음 화면으로 확장한다.

### 14.6 Agent Handoff Prompt

프론트 디자인 작업을 다른 coding agent에 맡길 때 다음 형식을 사용한다.

```text
Read docs/frontend/DESIGN.md first and treat its Confirmed items as the visual and interaction source of truth.
If the task changes Overview, read docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md and work on exactly one assigned Work Package.
Preserve docs/contracts/API_SPEC.md and docs/frontend/FRONTEND_SPEC.md behavior.

Design Read:
Existing multi-step EDR investigation console for SOC operators.
Serious B2B, trust-first, data-dense, dark-neutral, restrained functional motion.
Variance 3/10, motion 2/10, density 8/10.

Before editing:
1. Audit the current screen and shared components.
2. State what will be preserved, changed, and excluded.
3. Use external DESIGN.md examples only for pattern comparison, never brand copying.
4. Apply the selective Taste Skill rules in DESIGN.md section 14.3.
5. Do not implement a Work Package before its dependencies in the active plan are complete.

After editing:
Run the section 14.7 pre-flight and report evidence for each applicable item.
Update only the assigned Work Package status and evidence in OVERVIEW_DASHBOARD_REDESIGN_PLAN.md.
```

### 14.7 Hard Pre-flight

- [ ] Design Read와 dial에 맞는 결과인가?
- [ ] 2.2 Reference traceability의 채택·비채택 경계를 지켰는가?
- [ ] 기존 Route, URL state, API enum과 권한을 보존했는가?
- [ ] primary action과 정보 우선순위가 명확한가?
- [ ] action accent, semantic color, radius와 surface 계층이 일관적인가?
- [ ] generic gradient, glass, pill, status dot, card 반복을 근거 없이 추가하지 않았는가?
- [ ] KPI의 단위·time range·비교 기준이 있고 없는 delta를 생성하지 않았는가?
- [ ] Tooltip과 Popover를 keyboard·touch에서 사용할 수 있고 핵심 정보를 hover에만 숨기지 않았는가?
- [ ] DataTable의 caption, header association, sort, selected, loading, empty, error 상태를 확인했는가?
- [ ] toolbar와 dashboard grid가 같은 frame edge와 gutter를 사용하는가?
- [ ] Loading, Empty, Error, Stale, Partial failure를 확인했는가?
- [ ] keyboard, focus, 200% zoom, reduced motion을 확인했는가?
- [ ] 360, 768, 1024, 1440px에서 주요 task를 확인했는가?
- [ ] EN과 KO에서 overflow와 의미 왜곡이 없는가?
- [ ] chart와 graph에 단위, 시간, timezone, accessible fallback이 있는가?
- [ ] 외부 reference의 브랜드 자산과 token을 복제하지 않았는가?
- [ ] typecheck, lint, test, production build 결과를 기록했는가?

하나라도 실패하면 완료로 표시하지 않는다. 실패 항목과 다음 조치를 기록한다.

## 15. 구현 계획과의 경계

이 문서는 장기 디자인 기준만 관리한다. 현재 Overview 개편의 작업 순서, 진행 상태, 구현 파일과 완료 증거는 [Overview Dashboard Redesign Plan](./OVERVIEW_DASHBOARD_REDESIGN_PLAN.md)에서 관리한다.

- 이 문서의 `확정` 항목은 실행 계획이 변경되어도 유지되는 기준이다.
- `제안`은 계획에서 PoC로만 배정할 수 있고, `결정 필요`는 blocker 해제 전 본 구현할 수 없다.
- 공통 품질 기준은 14.7 Hard Pre-flight에 유지한다.
- 개편이 끝나면 실행 계획은 완료 기록으로 보존하거나 Git 이력으로 archive하고, 이 문서는 계속 갱신한다.

## 16. 결정 기록

결정이 확정될 때 아래 표에 기록하고 관련 본문 상태를 함께 변경한다.

| ID | 날짜 | 결정 | 근거 | 영향 파일 |
| --- | --- | --- | --- | --- |
| D-001 | 2026-07-15 | 기존 자료는 참고용으로 보존하고 `DESIGN.md`를 새 UI 기준 문서로 사용 | 기존 구현 명세와 새 디자인 목표의 책임 분리 | `docs/frontend/DESIGN.md` |
| D-002 | 2026-07-15 | Awesome DESIGN.md의 문서 구조와 외부 사례 비교 방식을 도입 | AI handoff에 필요한 token, component, depth, guardrail 명확화 | `docs/frontend/DESIGN.md` |
| D-003 | 2026-07-15 | Taste Skill은 EDR 제품 UI에 맞는 audit, consistency, anti-generic, pre-flight 원칙만 선택 적용 | v2 experimental의 broad web·marketing 규칙보다 프로젝트 고유 디자인 기준을 우선 | `docs/frontend/DESIGN.md` |
| D-004 | 2026-07-15 | 목적이 명확한 gradient 사용을 허용 | chart 연속성, 선택 context, 시선 시작점을 보조하되 semantic status와 contrast를 보호 | `docs/frontend/DESIGN.md`, `frontend/src/styles/` |
| D-005 | 2026-07-15 | Sidebar를 Overview, Triage, Evidence, Analysis, Platform group 순서로 확정 | 상태 판단에서 분류·조사·근거·분석·운영으로 이어지는 흐름 유지 | `docs/frontend/DESIGN.md`, `frontend/src/components/AppShell.tsx` |
| D-006 | 2026-07-15 | 팀 토의 이미지 4장은 pattern 참고로만 사용 | Investigation, topology, Overview hierarchy, Grafana density를 화면 목적에 맞게 분리 적용 | `docs/frontend/DESIGN.md` |
| D-007 | 2026-07-15 | 장기 디자인 기준과 단발성 개편 계획을 분리 | `DESIGN.md`의 지속 가능성을 유지하고 실행 진행률과 blocker의 수명을 분리 | `docs/frontend/DESIGN.md`, active plan, `frontend/AGENTS.md` |
| D-008 | 2026-07-15 | 외부 reference마다 채택·비채택 pattern과 적용 절을 기록 | 링크 나열이나 브랜드 복제를 막고 구현 판단까지 추적 | `docs/frontend/DESIGN.md` |
| D-009 | 2026-07-15 | Shadcnblocks의 KPI, Tooltip·Popover, DataTable, compact toolbar pattern을 EDR 계약에 맞게 채택 | 레퍼런스의 실제 interaction을 구현 가능한 공통 규칙으로 변환 | `docs/frontend/DESIGN.md` |
| D-010 | 2026-07-15 | Endpoint switcher, 읽기 전용 Response guidance, Incident·Egress selected context를 Page Blueprint에 명시 | 팀 토의 이미지와 기능 요청을 장기 제품 동작으로 연결 | `docs/frontend/DESIGN.md` |
| D-011 | 2026-07-15 | Workshop의 모든 권장안을 확정하고 Login을 포함한 dark-only compact UI로 개편 | 구현 중 반복 의사결정을 제거하고 화면 간 일관성을 고정 | `docs/frontend/DESIGN.md`, Git history의 Workshop 기록 |
| D-012 | 2026-07-15 | Overview 10개 block, 8개 widget 제거와 1회 자동 layout migration을 확정 | Overview를 상태·원인·우선 조사 대상에 집중. Frontend migration 결정은 D-015로 대체 | `docs/frontend/DESIGN.md`, Git history의 완료 계획 |
| D-013 | 2026-07-15 | ECharts와 React Flow + Dagre를 PoC·feature flag·accessible fallback 조건으로 채택 | 정량 chart와 관계 graph의 역할을 분리하고 단계 배포 | `docs/frontend/DESIGN.md`, `frontend/package.json` |
| D-014 | 2026-07-15 | UI 완성에 필요한 Backend query, search, layout migration과 investigation read model을 이번 개편에 포함 | paged UI에서 client 추정과 전체 prefetch를 방지 | `docs/contracts/API_SPEC.md`, `backend/`, `frontend/src/api/` |
| D-015 | 2026-07-16 | Overview를 승인 시안 기반 고정형 10-block dashboard로 전환하고 Frontend layout 편집·저장·migration을 제거 | 자유 배치보다 상태·원인·우선 조사 대상의 일관된 정보 위계가 중요하며 구현·검증 복잡도를 줄임 | `docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`, `frontend/src/pages/OverviewPage.tsx` |
| D-016 | 2026-07-17 | Color와 typography는 semantic 역할·접근성 규칙만 확정하고 실제 palette·font 값은 팀 지정 전 임시 baseline으로 관리 | 구조 개선과 브랜드 결정을 분리하고 후속 변경을 token 교체로 제한 | `docs/frontend/DESIGN.md`, `frontend/src/styles/tokens.css` |
| D-017 | 2026-07-17 | Overview를 EDR command strip, KPI 4개, Detection Activity, Alert Severity donut, 조사 queue 2개의 고정 9-block으로 조정하고 Endpoint Risk panel 제거 | 위험 표현 중복과 상단 dead space를 줄이고 현재 상태와 조사 대상을 빠르게 판독 | `docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`, `frontend/src/features/overview/OverviewDashboard.tsx` |
| D-018 | 2026-07-17 | Case 1 dark color palette를 확정하고 severity, health, interaction과 chart series를 별도 semantic token으로 분리 | red 피로도와 상태 의미 충돌을 줄이고 후속 색상 교체를 token 단위로 제한 | `case-1-design-tokens.yaml`, `frontend/src/styles/tokens.css` |

## 17. 관련 문서와 코드

- [Frontend 구현 명세](./FRONTEND_SPEC.md)
- [Overview Dashboard Implementation Work Order](./OVERVIEW_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md)
- [Overview Dashboard Redesign Plan](./OVERVIEW_DASHBOARD_REDESIGN_PLAN.md)
- [승인된 Overview 시안](./assets/references/overview-dashboard-target.png)
- [API 계약](../contracts/API_SPEC.md)
- [Risk 정책](../contracts/RISK_POLICY.md)
- [App route](../../frontend/src/App.tsx)
- [AppShell](../../frontend/src/components/AppShell.tsx)
- [공통 UI](../../frontend/src/components/ui.tsx)
- [공통 filter](../../frontend/src/components/filters.tsx)
- [현재 style baseline](../../frontend/src/styles.css)
- [Awesome DESIGN.md](https://github.com/VoltAgent/awesome-design-md)
- [Sentri-inspired DESIGN.md 사례](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/sentry/DESIGN.md)
- [Taste Skill](https://www.tasteskill.dev/)
- [Taste Skill documentation](https://www.tasteskill.dev/docs)
