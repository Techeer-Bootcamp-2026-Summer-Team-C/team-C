# Theme and Custom Dashboard Implementation Work Order

- 상태: Approved / 실행 가능
- 작성일: 2026-07-17
- 실제 저장소: `/Users/geonha/Desktop/Techeer-12th-b/edr`
- 기준 remote: `origin/main` (`178704b`, 2026-07-17 확인)
- 작업 branch: `feat/theme-custom-dashboard`
- 구현 범위: Frontend only
- 시각 QA 범위: Desktop `1280px`, `1440px`만 확인
- Codex 시작 프롬프트: [THEME_CUSTOM_DASHBOARD_CODEX_PROMPT.md](./THEME_CUSTOM_DASHBOARD_CODEX_PROMPT.md)
- 참고 구현: [Team B IDS-COLLECTOR](https://github.com/2026-Techeer-Summer-BootCamp-Team-B/IDS-COLLECTOR/tree/71bb7a9f0d8e303b527488accaa5664a5ebb9584)
- Reference 검토 기준: `main`의 `71bb7a9` (`2026-07-17T08:38:45Z`, 최신 상태 재확인)
- `e38dc9..71bb7a9` 사이 7개 commit을 비교했다. `useTheme.jsx`, `OverviewLayoutContext.jsx`, `LogDashboard.jsx`, `dashboard/package.json`의 blob은 동일하고 `index.css` 변경은 font를 Noto Sans KR로 고정한 내용이므로 본 theme/DnD 동작 명세에는 영향이 없다.

## 1. 작업 목표

현재 Team C EDR Console에 다음 두 기능을 구현한다.

1. 전체 애플리케이션에서 동작하는 dark/light theme 전환
2. 기존 고정 Overview와 분리된 사용자 정의 dashboard 생성 및 drag/drop·resize 편집

완료 상태는 다음과 같다.

- 저장값이 없으면 기존 dark theme로 시작한다.
- 인증된 AppShell에서 dark/light를 전환하고 새로고침 후에도 유지한다.
- Login을 포함한 모든 route가 선택된 theme token을 사용한다.
- 현재 고정 Overview는 `Default` dashboard로 계속 제공하며 수정할 수 없다.
- 사용자는 별도의 custom dashboard를 여러 개 만들고 이름 변경·삭제할 수 있다.
- custom dashboard에는 기존 9개 Overview widget을 drag/drop으로 추가하고 이동·resize할 수 있다.
- Widget palette는 각 항목의 의미를 구분하는 preview glyph를 표시한다.
- 한 custom dashboard에는 같은 widget 종류를 하나만 추가할 수 있다.
- custom dashboard는 현재 로그인 사용자의 `userId`별 browser localStorage에만 저장한다.
- Backend layout API, OpenAPI, DTO, DB와 migration은 변경하지 않는다.

## 2. 이번 사용자 결정과 기존 문서의 관계

이 작업은 이전 완료 기록을 삭제하거나 다시 작성하는 작업이 아니다.

- `OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`의 OVR/REF 기록은 당시 구현·검증 이력으로 보존한다.
- 기존 D-015의 “고정 Overview”는 `Default` dashboard에 계속 적용한다.
- D-015의 “사용자 layout을 제공하지 않는다”는 부분은 custom dashboard에 한해 대체한다.
- D-023의 `dark-only` 결정은 본 작업의 dark/light dual theme 결정으로 대체한다.
- 이전 Backend dashboard layout API는 호환성 때문에 그대로 남겨 두지만 Frontend에서 호출하지 않는다.

이번 기능에 한해 충돌 시 다음 순서를 적용한다.

1. `docs/contracts/API_SPEC.md`, `docs/contracts/RISK_POLICY.md`
2. 이 작업지시서
3. `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`의 최신 결정
4. 현재 `frontend/src/` 구현
5. 완료된 이전 Overview 작업지시서와 실행계획은 역사적 근거
6. Team B reference는 UI와 interaction 참고 자료

Reference와 현재 API/DTO가 충돌하면 현재 Team C 계약을 우선한다.

## 3. 범위

### 3.1 포함

- global dark/light theme state와 persistence
- React가 mount되기 전 theme bootstrap
- `<html class="light">` 기반 token 전환
- browser `color-scheme`와 `theme-color` 동기화
- AppShell desktop top bar의 theme toggle
- ECharts, panel, form, table, popover, dialog, skeleton, 상태색의 theme 대응
- immutable Default dashboard
- 여러 custom dashboard 생성·선택·이름 변경·삭제
- semantic preview glyph를 포함한 widget palette와 drag/drop 추가
- custom widget 이동·resize·삭제
- widget type별 단일 instance와 중복 저장값 정규화
- 사용자별 localStorage persistence와 손상 데이터 복구
- desktop keyboard와 screen-reader 접근성
- unit/component/source-boundary test
- desktop browser QA

### 3.2 명시적 제외

- 모바일 화면 시각 검토, 모바일 screenshot, 모바일 viewport matrix
- 모바일 전용 dashboard builder 디자인
- 모바일에서 drag/drop·resize 제공
- Backend dashboard layout GET/PUT/DELETE 연결
- Backend layout v3, 새 API, DTO, OpenAPI 또는 DB migration
- server-side dashboard 공유와 여러 기기 동기화
- chart 종류 변경 UI
- widget별 새 API 요청
- 새 지표, delta, SLA, 담당자, coverage, health 또는 fake data 생성
- Team B 브랜드, 이름, logo, font, 색상 token 복제
- 기존 route/query/polling/auth/role 계약 변경
- Docker image rebuild와 전체 stack 재기동
- commit, push, PR 생성

### 3.3 모바일 경계

이번 작업에서는 모바일 화면을 열거나 시각 판정하지 않는다.

- browser QA는 `1280px`, `1440px` desktop에서만 실행한다.
- `1280px` 미만에서는 custom dashboard 편집 control을 비활성화한다.
- 기존 DOM reading order와 기존 responsive CSS를 의도적으로 제거하지 않는다.
- 모바일용 신규 레이아웃, drawer, palette 또는 resize UX를 만들지 않는다.
- 모바일에서 완벽하게 보인다고 완료 보고하지 않는다. 해당 범위는 `미검증`으로 남긴다.

## 4. 반드시 읽을 파일

작업 전 다음 순서로 끝까지 읽는다.

1. `frontend/AGENTS.md`
2. `docs/frontend/DESIGN.md`
3. 이 작업지시서
4. `docs/frontend/FRONTEND_SPEC.md`
5. `docs/contracts/API_SPEC.md`의 Dashboard·Endpoint·Incident·Auth 절
6. `docs/contracts/RISK_POLICY.md`
7. `docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`의 DnD/theme 관련 완료 기록

그다음 실제 코드를 확인한다.

- `frontend/src/main.tsx`
- `frontend/index.html`
- `frontend/src/auth/AuthContext.tsx`
- `frontend/src/components/AppShell.tsx`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/features/overview/OverviewDashboard.tsx`
- `frontend/src/features/overview/DetectionActivityPanel.tsx`
- `frontend/src/features/overview/AlertSeverityDonut.tsx`
- `frontend/src/features/overview/InvestigationQueues.tsx`
- `frontend/src/styles/tokens.css`
- `frontend/src/styles.css`
- `frontend/src/styles/shell.css`
- `frontend/src/styles/primitives.css`
- `frontend/src/styles/patterns.css`
- `frontend/src/styles/visualizations.css`
- `frontend/src/styles/pages/*.css`
- `frontend/src/i18n/translations.ts`
- `frontend/tests/source-boundaries.test.ts`
- `frontend/tests/app-shell-foundation.test.tsx`
- `frontend/tests/overview-redesign.test.tsx`
- `frontend/tests/locale.test.tsx`
- `frontend/tests/auth-routing.test.tsx`
- `frontend/package.json`

Reference에서는 아래 파일의 behavior만 확인한다.

- [`dashboard/src/hooks/useTheme.jsx`](https://github.com/2026-Techeer-Summer-BootCamp-Team-B/IDS-COLLECTOR/blob/71bb7a9f0d8e303b527488accaa5664a5ebb9584/dashboard/src/hooks/useTheme.jsx)
- [`dashboard/src/context/OverviewLayoutContext.jsx`](https://github.com/2026-Techeer-Summer-BootCamp-Team-B/IDS-COLLECTOR/blob/71bb7a9f0d8e303b527488accaa5664a5ebb9584/dashboard/src/context/OverviewLayoutContext.jsx)
- [`dashboard/src/views/LogDashboard.jsx`](https://github.com/2026-Techeer-Summer-BootCamp-Team-B/IDS-COLLECTOR/blob/71bb7a9f0d8e303b527488accaa5664a5ebb9584/dashboard/src/views/LogDashboard.jsx)
- [`dashboard/src/index.css`](https://github.com/2026-Techeer-Summer-BootCamp-Team-B/IDS-COLLECTOR/blob/71bb7a9f0d8e303b527488accaa5664a5ebb9584/dashboard/src/index.css)

Reference의 React 18 JavaScript 구현을 그대로 복사하지 않는다. Team C의 React 19, TypeScript, semantic token, i18n과 테스트 경계를 따른다.

## 5. Git 시작 절차

현재 작업 트리를 먼저 확인한다.

```bash
cd /Users/geonha/Desktop/Techeer-12th-b/edr
git status --short --branch
git branch --show-current
git fetch origin
git log -1 --oneline origin/main
```

규칙:

- 추적·미추적 변경이 있으면 reset, restore, checkout, stash하지 않는다.
- 사용자 변경을 발견하면 안전하게 분리할 수 있는지 확인하고, 덮어쓸 위험이 있으면 작업을 중단해 보고한다.
- `feat/theme-custom-dashboard`가 없으면 최신 `origin/main`에서 생성한다.
- 이미 branch가 있으면 그 branch의 상태와 base를 확인한 뒤 이어서 사용한다.
- 구현 과정에서 commit, push, PR을 만들지 않는다.

신규 branch 예시:

```bash
git switch -c feat/theme-custom-dashboard origin/main
```

## 6. 수정 전 baseline

dependency를 바꾸기 전에 다음을 실행하고 결과를 TCD-00 기록에 남긴다.

```bash
cd /Users/geonha/Desktop/Techeer-12th-b/edr/frontend
npm run openapi:check
npm run typecheck
npm run lint
npm test
```

2026-07-17 확인값은 21 test files / 97 tests 통과다. 개수가 달라지면 실패로 단정하지 말고 현재 실제 결과를 기록한다.

## 7. Theme 상세 설계

### 7.1 상태와 저장 키

```ts
type Theme = "dark" | "light";
const THEME_STORAGE_KEY = "edr.theme";
```

우선순위:

1. localStorage의 유효한 `dark` 또는 `light`
2. 없거나 손상됐으면 `dark`

OS `prefers-color-scheme`을 초기 기본값으로 사용하지 않는다. 기존 제품의 dark baseline을 보존하기 위해 무저장 기본값은 dark다.

### 7.2 Provider 위치

`ThemeProvider`는 인증과 무관해야 하므로 `AuthProvider` 바깥에 둔다.

```tsx
<QueryClientProvider client={queryClient}>
  <ThemeProvider>
    <AuthProvider>
      <LocaleProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </LocaleProvider>
    </AuthProvider>
  </ThemeProvider>
</QueryClientProvider>
```

Theme context 최소 API:

```ts
interface ThemeValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}
```

### 7.3 DOM 적용

- dark: `<html>`에서 `light` class 제거
- light: `<html class="light">`
- `document.documentElement.style.colorScheme` 또는 동일한 CSS 선언을 theme와 동기화
- `meta[name="color-scheme"]`를 `dark` 또는 `light`로 동기화
- `meta[name="theme-color"]`도 현재 canvas token에 맞춰 갱신
- `document.documentElement.lang`은 기존 LocaleContext가 계속 관리하며 theme 코드가 덮어쓰지 않음

### 7.4 초기 깜빡임 방지

`frontend/index.html`에서 `/src/main.tsx`보다 먼저 실행되는 짧은 bootstrap script를 둔다.

- `edr.theme`만 읽는다.
- 유효하지 않거나 storage access가 실패하면 dark를 사용한다.
- React ThemeProvider와 같은 key, 기본값, `light` class 규칙을 사용한다.
- bootstrap과 Provider의 규칙이 달라지지 않도록 source-level test를 추가한다.
- token, credential, route 또는 사용자 데이터는 읽지 않는다.

### 7.5 Toggle 위치와 접근성

- 인증된 AppShell top bar의 locale/account control 근처에 둔다.
- sun/moon icon은 `lucide-react`를 사용한다.
- 현재 상태가 아니라 실행할 action을 label로 설명한다.
- EN/KO 번역 key를 추가한다.
- button은 keyboard focus, focus ring, `aria-label`, `title`을 제공한다.
- 필요하면 `aria-pressed`를 사용하되 label과 의미가 충돌하지 않게 한다.
- Login에는 별도 theme toggle을 추가하지 않는다. 저장된 theme는 Login에도 적용한다.

### 7.6 CSS token

- 기존 `:root`의 Case 2 dark token을 유지한다.
- `:root.light`에 동일한 semantic token 이름의 light 값을 선언한다.
- component CSS에 theme별 raw color 분기를 퍼뜨리지 않는다.
- component는 계속 `--surface-*`, `--text-*`, `--border-*`, `--status-*`, `--chart-*` token을 사용한다.
- status 의미는 theme가 바뀌어도 유지한다.
- Critical/High/Warning/Success/Info를 장식색으로 오용하지 않는다.
- panel, control, divider의 기존 시각 계층을 light에서도 구분한다.
- focus ring은 두 theme에서 명확해야 한다.
- print rule의 `color-scheme: dark`도 함께 검토한다. 인쇄를 light로 고정할 경우 이를 문서와 테스트에 명시한다.

반드시 검색한다.

```bash
rg -n 'color-scheme|theme-color|data-theme|classList.*light' \
  frontend/index.html frontend/src frontend/tests
```

### 7.7 Chart

- ECharts option이 theme 또는 semantic CSS token 변화에 반응해야 한다.
- theme 전환 시 chart background, axis, grid, tooltip, legend, text와 series 색이 즉시 갱신돼야 한다.
- chart instance 전체를 불필요하게 중복 생성하지 않는다.
- existing data series, bucket sorting, missing-value와 accessible table fallback은 변경하지 않는다.

## 8. Custom dashboard 상세 설계

### 8.1 모드

Dashboard selector는 다음 두 종류를 표시한다.

1. `Default`: 기존 9-block Overview, immutable, 삭제·이름 변경·drag·resize 불가
2. custom dashboard: 사용자 생성, 편집 가능

Default는 localStorage dashboard 배열에 저장하지 않는다. 저장 데이터가 손상되거나 custom dashboard가 모두 삭제되면 Default로 돌아간다.

### 8.2 사용자 범위

현재 인증 계약의 숫자형 `user.userId`만 사용한다.

```text
edr.overviewDashboards.v1.user.${userId}
edr.overviewActiveDashboard.v1.user.${userId}
```

- `loginId` fallback을 만들지 않는다.
- 인증 전에는 dashboard storage를 읽거나 쓰지 않는다.
- ADMIN, ANALYST, VIEWER 모두 사용할 수 있다.
- 로그아웃 시 localStorage를 삭제할 필요는 없지만 다른 사용자 context가 이전 in-memory state를 재사용하면 안 된다.

### 8.3 Provider 위치

Overview route에서 `useAuth()`로 user를 얻은 뒤 provider를 mount한다.

```tsx
<OverviewLayoutProvider key={String(user.userId)} userId={user.userId}>
  <OverviewPageContent />
</OverviewLayoutProvider>
```

- `OverviewLayoutProvider`를 `AuthProvider` 바깥이나 전체 App 전역에 두지 않는다.
- `key={String(userId)}`로 사용자 변경 시 state를 재초기화한다.
- `RequireAuth` 아래라는 전제는 유지하되 null user를 방어적으로 처리한다.

### 8.4 저장 모델

권장 최소 model:

```ts
type OverviewWidgetType =
  | "edr-state"
  | "kpi-alerts"
  | "kpi-critical-alerts"
  | "kpi-high-risk-endpoints"
  | "kpi-open-incidents"
  | "detection-activity"
  | "alert-severity"
  | "highest-risk-endpoints"
  | "incident-queue";

interface CustomDashboardWidget {
  uid: string;
  type: OverviewWidgetType;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface CustomOverviewDashboard {
  id: string;
  name: string;
  widgets: CustomDashboardWidget[];
  createdAt: string;
  updatedAt: string;
}

interface OverviewDashboardStoreV1 {
  version: 1;
  dashboards: CustomOverviewDashboard[];
}
```

규칙:

- dashboard와 widget instance ID는 충돌하지 않는 browser-generated ID를 사용한다.
- 같은 widget `type`은 한 dashboard에 하나만 넣을 수 있으며, parser/normalizer는 중복 type 중 첫 번째 유효 instance만 유지한다.
- dashboard name은 trim하고 빈 이름은 저장하지 않는다.
- 알 수 없는 version, widget type, 비정상 좌표·크기, 중복 UID와 손상 JSON을 그대로 신뢰하지 않는다.
- parser/normalizer는 invalid item만 제거하거나 안전한 값으로 clamp한다.
- storage read/write 실패가 Overview 데이터 조회나 로그인까지 막지 않는다.
- create/update/delete는 함수형 state update를 사용해 stale closure를 피한다.

### 8.5 Widget catalog

현재 `OVERVIEW_BLOCK_IDS`의 9개 항목만 catalog에 등록한다.

각 catalog entry는 다음을 가진다.

```ts
interface OverviewWidgetDefinition {
  type: OverviewWidgetType;
  titleKey: TranslationKey;
  defaultW: number;
  defaultH: number;
  minW: number;
  minH: number;
  render: (context: OverviewWidgetRenderContext) => React.ReactNode;
}
```

- widget은 현재 Overview query 결과를 재사용한다.
- widget instance마다 새 API query를 만들지 않는다.
- palette item은 Widget 의미를 나타내는 semantic preview glyph, 이름과 기본 geometry를 함께 표시한다.
- 이미 Canvas에 배치된 type은 palette에서 숨기고 Widget을 제거하면 다시 표시한다.
- 기존 `ResourceFeedback`, `QueueFeedback`, stale/error/loading 의미를 보존한다.
- widget을 catalog로 분리하면서 drill-down URL, selected Endpoint scope와 Time range를 잃지 않는다.
- Signal ribbon은 dashboard grid 밖의 고정 영역으로 유지하며 palette에 넣지 않는다.

### 8.6 새 custom dashboard 기본 상태

- `New dashboard`는 아직 저장되지 않은 빈 builder를 연다.
- builder empty state에서 palette의 widget을 추가하라는 설명과 keyboard 대안을 표시한다.
- 이름이 비어 있거나 widget이 0개면 Save를 비활성화한다.
- Save할 때만 custom dashboard를 생성하고 해당 dashboard를 active로 전환한다.
- Cancel하면 dashboard와 localStorage에 아무것도 생성하지 않는다.
- Default dashboard를 자동 복제하지 않는다.

### 8.7 Dashboard 관리

제공할 control:

- dashboard selector
- `New dashboard`
- custom dashboard 이름 변경
- custom dashboard 삭제
- 삭제 confirmation
- 신규/기존 dashboard builder 열기/닫기

규칙:

- Default에서는 rename/delete/edit control을 숨기거나 비활성화한다.
- active custom dashboard를 삭제하면 Default로 전환한다.
- 기존 custom dashboard의 widget 추가·삭제와 이름 변경은 builder에서 Save할 때 반영한다.
- 저장된 custom dashboard 화면에서는 drag/resize 종료 결과를 자동 저장한다.
- dashboard 생성·이름 변경·삭제 후 즉시 저장한다.
- control, dialog, empty state와 오류 문구는 EN/KO를 제공한다.

### 8.8 react-grid-layout

다음 version을 사용한다.

```bash
cd frontend
npm install react-grid-layout@2.2.3
```

React 19 + TypeScript에서 우선 사용할 API:

```ts
import {
  ResponsiveGridLayout,
  getCompactor,
  useContainerWidth,
  type Layout,
  type LayoutItem,
  type ResponsiveLayouts,
} from "react-grid-layout";
```

- 같은 저장소의 과거 구현 이력이 있는 modern API를 우선한다.
- `react-grid-layout/legacy`와 `WidthProvider`는 modern API가 실제 type/runtime 검증에서 불가능할 때만 사용한다.
- package 자체 type을 먼저 사용하고 불필요한 `@types/react-grid-layout`을 추가하지 않는다.
- RGL CSS는 Overview builder 범위에만 영향을 주도록 import와 override를 관리한다.
- grid column은 desktop 12열을 기준으로 한다.
- browser-local geometry와 화면 geometry를 동일하게 유지하기 위해 `getCompactor(null, false, true)`로 non-compacting fixed grid를 구성한다. Gap과 grid bounds를 유지하고 collision은 조작 중인 Widget을 원위치로 되돌려 주변 Widget을 밀지 않는다.

### 8.9 Drag/drop와 resize

- palette item은 native drag source와 click/keyboard 추가 control을 함께 제공한다.
- custom MIME type과 안전한 text fallback을 사용할 수 있다.
- drop 시 widget definition의 default 크기를 사용한다.
- 기존 widget 위에 drop해도 기존 geometry는 변경하지 않고 신규 Widget만 drop 지점과 가장 가까운 비중첩 cell에 배치한다.
- drag/resize 중 모든 이벤트에서 localStorage에 쓰지 않는다.
- `onDragStop`, `onResizeStop`, widget add/delete, dashboard rename/delete에서 저장한다.
- 필요한 경우 짧은 debounce를 사용하되 마지막 변경을 잃지 않는다.
- widget header에 drag handle과 remove action을 명확히 분리한다.
- button, link, chart interaction을 시작할 때 panel drag가 발생하지 않게 handle selector를 사용한다.
- Escape, focus와 keyboard action이 기존 Overview toolbar와 충돌하지 않아야 한다.

### 8.10 Desktop 전용 편집

- 편집 breakpoint는 `min-width: 1280px`로 고정한다.
- `1280px` 이상에서만 drag/drop, resize handle과 builder palette를 활성화한다.
- 그 미만에서는 저장된 widget 순서를 DOM flow로 렌더링하되 편집은 비활성화한다.
- 이번 작업에서 1279px 이하 화면은 browser로 열어 보거나 screenshot을 만들지 않는다.

## 9. localStorage 책임 경계

현재 `source-boundaries.test.ts`는 localStorage 사용 파일을 `AppShell.tsx` 하나로 제한한다. 테스트를 삭제하지 말고 key별 allowlist로 확장한다.

승인 대상 예시:

| 파일 | 허용 key |
| --- | --- |
| `components/AppShell.tsx` | `edr.compactNavigation` |
| `theme/ThemeProvider.tsx` 또는 theme storage module | `edr.theme` |
| `features/overviewLayout/OverviewLayoutContext.tsx` 또는 storage module | `edr.overviewDashboards.v1.user.` / `edr.overviewActiveDashboard.v1.user.` |

추가 규칙:

- auth token과 UserDto는 기존처럼 `sessionStorage`의 `edr.authSession`에만 저장한다.
- localStorage 파일이 `token`, `accessToken`, password 또는 임의 API response를 저장하지 못하게 한다.
- bootstrap inline script는 TypeScript source scan 밖에 있으므로 `index.html`을 직접 읽는 test를 추가한다.

## 10. 테스트 요구사항

### 10.1 Theme

- 저장값 없음 → dark
- `dark`/`light` 복원
- invalid value → dark
- toggle 후 `<html>`의 `light` class와 localStorage 동기화
- `color-scheme`, `theme-color` 동기화
- Login에도 저장된 theme 적용
- AppShell toggle의 EN/KO label
- theme 변경 후 ECharts option/style 갱신
- bootstrap key/default/class가 Provider와 동일
- storage exception이 앱 mount를 막지 않음

### 10.2 Dashboard storage/model

- userId별 key 분리
- malformed JSON fallback
- version validation
- unknown widget 제거
- coordinate/size normalization
- duplicate type과 duplicate UID 방지
- dashboard create/rename/delete
- active dashboard 복원과 삭제 후 Default fallback
- userId 변경 시 in-memory state 재초기화
- storage exception이 Overview를 막지 않음

### 10.3 UI와 interaction

- Default dashboard는 immutable
- custom dashboard는 edit control 제공
- 신규 builder의 빈 canvas와 Save 비활성 상태
- 신규 builder Cancel 시 dashboard 미생성
- 이름과 widget 1개 이상을 갖춘 Save 시 dashboard 생성·active 전환
- palette add
- 같은 widget type의 click/drop 중복 추가 차단
- 배치된 widget type의 palette item 숨김과 제거 후 복귀
- drag stop, resize stop 저장
- widget 삭제
- Signal ribbon은 grid 밖에 한 번만 표시
- 기존 query 수가 widget instance 수에 따라 증가하지 않음
- drill-down URL, time/Endpoint scope 유지
- ADMIN/ANALYST/VIEWER 모두 local builder 사용 가능
- `1280px` 미만 편집 비활성 조건은 unit/component logic으로만 확인하고 모바일 browser QA는 하지 않음

### 10.4 기존 테스트 수정

- `app-shell-foundation.test.tsx`의 dark-only/no-toggle assertion을 dual theme assertion으로 교체한다.
- App/AppShell을 직접 render하는 모든 helper에 `ThemeProvider`를 추가한다.
- theme test 종료 시 `document.documentElement.classList.remove("light")`와 meta state를 복원한다.
- localStorage를 test마다 clear한다.
- `overview-redesign.test.tsx`의 Frontend layout API method 부재 검증은 유지한다.
- 기존 9 block ID, partial/stale/error, drill-down과 chart semantic test를 유지한다.

## 11. 작업 Package

각 Package는 하나씩 진행하고 완료 기록을 이 문서의 해당 절에 추가한다. 같은 원인의 실제 blocker가 아니면 사용자 확인을 기다리지 말고 다음 Package로 진행한다.

### TCD-00. 시작 상태와 baseline

- 상태: 완료
- branch와 working tree 확인
- 필수 문서·코드 audit
- baseline 4개 명령 실행
- 적용/보존/제외 목록 작성
- dependency 도입 전 결과 기록

- 시작 branch: 최신 `origin/main`의 `178704b`에서 `feat/theme-custom-dashboard`를 생성했다. 승인 전에 작성된 `DESIGN.md`, `FRONTEND_SPEC.md`, `frontend/AGENTS.md`와 본 작업지시서·시작 프롬프트의 미커밋 변경은 reset·restore·stash 없이 그대로 보존했다.
- Source audit: 현재 Frontend는 `ThemeProvider`와 `react-grid-layout`이 없고 `AppShell.tsx`의 `edr.compactNavigation`만 localStorage를 사용한다. Default Overview는 `OVERVIEW_BLOCK_IDS` 9개를 고정 DOM/CSS grid로 렌더링하고, `OverviewPage.tsx`의 Dashboard·Endpoint summary·queue query 결과를 한 번만 생성해 `OverviewDashboard`에 전달한다. Frontend API client에는 dashboard layout GET/PUT/DELETE method가 없다.
- 적용: Case 2 dark semantic token과 9-block Default 정보 위계를 보존하면서 동일 token 이름의 cool-neutral light theme, 인증 사용자 `userId`별 custom dashboard storage, 기존 query 결과를 재사용하는 widget catalog, desktop builder와 stop 시점 저장을 추가한다.
- 보존: Route·URL filter·polling·auth·role, `DashboardSummaryDto`/`EndpointSummaryDto`, partial/stale/error 의미, Signal ribbon의 grid 밖 고정 위치, ECharts table fallback, Default dashboard의 immutable 상태와 layout API method 부재 검증을 유지한다.
- 제외: Backend·API_SPEC·OpenAPI·generated schema·DTO·DB migration, server layout API, chart type 전환, 새 metric·delta·health·SLA·담당자·coverage, 모바일 시각 QA·모바일 전용 builder와 Docker rebuild는 변경하지 않는다.
- 디자인 방향: dark는 `#09090B` near-black과 royal blue를 유지한다. light는 같은 semantic 역할의 차가운 neutral canvas/panel과 royal blue action을 사용한다. 고유 interaction은 Default와 custom의 소유권 차이를 selector·builder mode로 명확히 보이는 것이며 새 장식·gradient·브랜드 요소는 추가하지 않는다.
- Baseline `npm run openapi:check` → `OpenAPI artifact is current`, generated schema check passed.
- Baseline `npm run typecheck` → passed.
- Baseline `npm run lint` → passed.
- Baseline `npm test` → 21 files / 97 tests passed.
- 변경 파일: 본 작업지시서의 TCD-00 기록만 추가했다. Runtime dependency와 source는 아직 변경하지 않았다.
- 남은 위험: custom dashboard UI는 RGL modern API의 React 19 runtime/type 적합성을 실제 설치 후 확인해야 하며, desktop browser QA는 TCD-05에서 수행한다.

### TCD-01. Theme state와 bootstrap

- 상태: 완료
- ThemeProvider와 `edr.theme`
- pre-mount bootstrap
- AppShell toggle과 EN/KO
- source-boundary 확장
- theme state targeted test

Targeted validation:

```bash
npm run typecheck
npm test -- app-shell-foundation.test.tsx locale.test.tsx source-boundaries.test.ts
```

- 변경 파일: `frontend/src/theme/ThemeProvider.tsx`, `frontend/src/main.tsx`, `frontend/index.html`, `frontend/src/components/AppShell.tsx`, `frontend/src/i18n/translations.ts`, `frontend/src/styles/shell.css`, `frontend/tests/theme.test.tsx`, `frontend/tests/app-shell-foundation.test.tsx`, `frontend/tests/locale.test.tsx`, `frontend/tests/auth-routing.test.tsx`, `frontend/tests/source-boundaries.test.ts`.
- 설계 판단: `edr.theme`의 `dark | light`만 허용하고 누락·손상·storage exception은 dark로 복구한다. `ThemeProvider`는 `AuthProvider` 바깥에서 Login 포함 전체 route에 적용하며, inline bootstrap은 React mount 전에 같은 key·default·`light` class·meta color를 적용한다. AppShell control은 현재 상태보다 실행 action을 EN/KO accessible label로 알린다.
- 검증: `npm run typecheck` → passed. `npm test -- app-shell-foundation.test.tsx locale.test.tsx source-boundaries.test.ts theme.test.tsx overview-redesign.test.tsx` → 5 files / 32 tests passed.
- 남은 위험: 실제 desktop의 theme 전환 시 모든 page surface 대비는 TCD-05 browser QA에서 확인한다.

### TCD-02. Light semantic token과 chart

- 상태: 완료
- `:root.light` semantic token
- 모든 page primitive 상태 확인
- meta/color-scheme/print 처리
- ECharts theme 반응
- raw color와 dark-only 잔여 검색

Targeted validation:

```bash
npm run typecheck
npm test -- components.test.tsx overview-redesign.test.tsx app-shell-foundation.test.tsx
```

- 변경 파일: `frontend/src/styles/tokens.css`, `frontend/src/styles.css`, `frontend/src/features/overview/DetectionActivityPanel.tsx`, `frontend/tests/theme.test.tsx`, `frontend/tests/overview-redesign.test.tsx`.
- 설계 판단: Case 2 dark 값과 semantic token 이름은 유지하고 `:root.light`에 cool-neutral canvas·surface·text·border와 light 대비용 status/chart 값을 같은 역할로 정의했다. component별 light selector나 raw color 분기는 만들지 않았다. ECharts는 현재 theme를 effect dependency로 사용해 전환 시 computed semantic token으로 option을 다시 생성한다. print는 현재 root theme의 `color-scheme`을 유지한다.
- 검증: `npm run typecheck` → passed. `npm test -- components.test.tsx overview-redesign.test.tsx app-shell-foundation.test.tsx theme.test.tsx` → 4 files / 26 tests passed. theme 전환 시 ECharts init/option 재생성과 bootstrap·Provider·token source 일치를 확인했다.
- 검색: `color-scheme|theme-color|classList.*light|raw hex`를 `index.html`, `src`, `tests`에서 확인했다. 새 light 값은 `tokens.css`, pre-mount meta color와 ThemeProvider 상수에만 있으며 component theme 분기는 없다. ECharts의 기존 dark hex는 semantic token 조회 실패 시 fallback으로만 남아 있다.
- 남은 위험: light의 실제 panel/control/status/chart 대비와 print 결과는 TCD-05 desktop QA에서 확인한다.

### TCD-03. Dashboard model과 사용자별 persistence

- 상태: 완료
- type, catalog, parser/normalizer
- userId key와 Provider lifecycle
- create/rename/delete/active dashboard
- model/context unit test

Targeted validation:

```bash
npm run typecheck
npm test -- overview-layout.test.ts overview-layout-context.test.tsx source-boundaries.test.ts
```

- 변경 파일: `frontend/src/features/overviewLayout/overviewLayoutModel.ts`, `overviewLayoutStorage.ts`, `OverviewLayoutContext.tsx`, `frontend/src/features/overview/OverviewDashboard.tsx`, `frontend/tests/overview-layout.test.ts`, `overview-layout-context.test.tsx`, `source-boundaries.test.ts`.
- 설계 판단: numeric `userId`만 두 storage prefix에 결합하고 storage 접근은 한 module에 격리했다. version 1 parser는 unknown version/widget, 손상 JSON, 중복 dashboard ID·widget UID를 제거하고 widget별 min/max와 12열·256행 bounds로 좌표를 보정한다. 같은 type의 서로 다른 UID는 유지한다. Context는 create/update/delete/layout stop 결과와 active dashboard를 함수형 state update로 저장하고 storage exception 시 in-memory 상태를 유지한다.
- 검증: `npm run typecheck` → passed. `npm test -- overview-layout.test.ts overview-layout-context.test.tsx source-boundaries.test.ts` → 3 files / 9 tests passed.
- 사용자 격리: user 21에서 만든 dashboard가 `key="22" userId={22}` provider 재마운트 뒤 보이지 않고 Default로 초기화되는 것을 component test로 확인했다.
- 남은 위험: 실제 auth route mount와 두 실제 계정 runtime 분리는 TCD-04 통합 및 TCD-05 browser 환경에서 확인한다.

실제 test 파일명은 구현 구조에 맞게 조정할 수 있지만 같은 책임을 검증해야 한다.

### TCD-04. Desktop drag/drop builder

- 상태: 완료
- `react-grid-layout@2.2.3`
- Default/custom selector
- palette, add, duplicate, drag, resize, remove
- Signal ribbon 고정
- 기존 query/data/URL state 보존
- `1280px` 미만 edit disabled logic

Targeted validation:

```bash
npm run typecheck
npm test -- overview-redesign.test.tsx custom-dashboard.test.tsx locale.test.tsx
```

- 변경 파일: `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/pages/OverviewPage.tsx`, `frontend/src/features/overviewLayout/OverviewDashboardWorkspace.tsx`, `frontend/src/styles/pages/overview-layout.css`, `frontend/src/i18n/translations.ts`, `frontend/tests/custom-dashboard.test.tsx`, `frontend/tests/overview-layout-context.test.tsx`, `frontend/tests/locale.test.tsx`.
- 설계 판단: `react-grid-layout` modern API의 `ResponsiveGridLayout`, `useContainerWidth`, `verticalCompactor`를 정확한 `2.2.3` 버전으로 사용했다. Default는 기존 `OverviewDashboard` 9-block DOM을 그대로 렌더링하고 custom dashboard만 12-column grid, 명시적 drag handle, southeast resize handle과 stop 시점 저장을 사용한다. Signal ribbon은 grid 밖에서 한 번만 렌더링한다.
- 작성 흐름: New는 저장되지 않은 빈 builder를 열고 이름과 widget 1개 이상이 있어야 Save가 활성화된다. Cancel은 저장하지 않으며, 기존 custom의 이름·widget 추가/삭제는 Save에서만 반영한다. 같은 widget type은 서로 다른 UID로 반복 추가할 수 있다.
- 역할·반응형: ADMIN, ANALYST, VIEWER 모두 local builder control을 사용할 수 있음을 component test로 확인했다. `1280px` 미만에서는 생성·편집·삭제 control을 비활성화하고 저장된 widget은 정적 DOM 순서로 렌더링한다.
- 계약 보존: `OverviewPage`의 Dashboard·Endpoint summary·queue query와 URL filter state를 그대로 한 번 생성해 Default/custom widget에 전달하며, layout API method나 query를 추가하지 않았다.
- 검증: `npm run typecheck` → passed. `npm test -- overview-redesign.test.tsx custom-dashboard.test.tsx overview-layout-context.test.tsx locale.test.tsx source-boundaries.test.ts` → 5 files / 34 tests passed.
- 남은 위험: 실제 1280px drag/drop·resize·reload persistence와 1440px page theme 대비는 TCD-05 desktop browser QA에서 확인한다.

### TCD-05. 통합 회귀와 문서 동기화

- 상태: 완료
- source boundary와 test cleanup 최종 확인
- `DESIGN.md`, `FRONTEND_SPEC.md`, 본 작업지시서 구현 결과 기록
- desktop browser QA
- 최종 release gate 1회 실행

- 문서 동기화: `frontend/AGENTS.md`에 본 작업지시서 read order와 TCD 기록 경계를 추가하고 `DESIGN.md` D-025, `FRONTEND_SPEC.md`에 dual theme, immutable Default, browser-local custom dashboard와 Backend layout API 미사용을 기록했다.
- 1440px QA: 저장된 light theme가 Login에 적용되고 Login에는 toggle이 없음을 확인했다. Default는 dark/light 모두 9 blocks, ECharts canvas 1개, page-level horizontal overflow 0건이었다. Alerts, Incidents, Endpoints, Events, Intelligence, Operations는 clean Playwright light session에서 모두 heading/main render와 overflow 0건을 확인했다. clean session console은 errors 0, warnings 0이었다.
- 대비 QA: panel 기준 dark의 최소 text 11.46:1, focus 5.68:1, status 5.22:1, chart 3.76:1, light의 최소 text 10.46:1, focus 5.99:1, status 5.43:1, chart 5.69:1을 computed semantic token으로 확인했다.
- 1280px QA: 빈 New builder, Save disabled, 이름 입력, 같은 Total alerts 2회 추가, Detection activity의 실제 palette drag/drop, explicit drag handle 이동, southeast resize, remove, rename, Save, reload active/layout 복원, Default 전환 9-block 복귀와 delete confirmation 후 Default fallback을 확인했다. 실제 drop에서 발견한 초기 geometry overlap은 가장 가까운 빈 12-column 좌표 배치로 수정했고 재검증 결과 `overlapCount=0`이었다. Signal ribbon은 custom에서 1개였다.
- 사용자 격리: browser runtime에서 계약 모양의 user 101과 202 auth session을 교체해 user 202는 Default만 보고 storage key가 없으며, user 101 복귀 시 자신의 active custom과 3 widgets가 복원됨을 확인했다. 실제 Backend credential을 사용하는 두 계정 로그인은 환경에 제공되지 않아 미검증이며, component test와 mocked browser runtime까지만 완료로 주장한다.
- Network: builder QA의 244개 기록 request에서 dashboard layout API GET/PUT/DELETE match는 0건이었다.
- 최종 release gate: `npm run openapi:check` → artifact current/generated schema check passed. `npm run typecheck` → passed. `npm run lint` → passed. `npm test` → 25 files / 117 tests passed. `npm run build` → passed. `git diff --check` → passed. build에는 기존 ECharts bundle의 500.14 kB chunk-size warning이 있었으나 실패는 없었다.
- Source/계약 경계: theme/dashboard storage key 검색을 확인했고 runtime layout client method는 추가하지 않았다. Backend, OpenAPI, contracts, Frontend API client diff는 0건이다. generated schema의 기존 layout endpoint는 보존했다.
- 제외와 남은 위험: 사용자 지시에 따라 모바일 viewport·screenshot·시각 QA는 수행하지 않았고 완료로 주장하지 않는다. production Backend를 사용하는 실제 두 계정 통합과 모바일 시각 품질은 미검증이다. commit, push, PR은 생성하지 않았다.

### TCD-06. Post-review persistence와 breakpoint 보강

- 상태: 완료
- 변경 파일: `frontend/src/features/overviewLayout/overviewLayoutStorage.ts`, `frontend/src/features/overviewLayout/OverviewDashboardWorkspace.tsx`, `frontend/tests/overview-layout.test.ts`, `frontend/tests/custom-dashboard.test.tsx`, 이 작업지시서.
- 저장 복원: parser가 유효한 dashboard 24개와 widget 64개 이후를 잘라내던 읽기 전용 상한을 제거했다. invalid item 제거, 중복 ID 방지와 좌표·크기 clamp는 유지하며 생성·쓰기·읽기 경로가 같은 유효 데이터를 보존한다. 25개 dashboard와 한 dashboard의 65개 widget이 모두 정규화되는 회귀 테스트를 추가했다.
- storage fallback: 선택적 storage 인자를 유지하되 실제 `window.localStorage` 취득을 함수 본문의 `try` 안으로 옮겼다. `getItem`/`setItem`뿐 아니라 localStorage property getter 자체가 `SecurityError`를 던져도 Default 또는 in-memory 상태를 유지한다.
- breakpoint: 열린 builder를 강제로 닫아 미저장 변경을 버리지 않고, `1280px` 아래로 전환되는 즉시 name field, palette drag/click, widget remove, RGL drag/resize와 Save를 비활성화한다. 삭제 confirmation도 같은 시점에 confirm action을 비활성화한다. viewport를 `true → false`로 전환하는 component test에서 저장이 발생하지 않고 static DOM flow로 바뀌는 것을 확인했다.
- 검증: `npm test -- overview-layout.test.ts custom-dashboard.test.tsx overview-layout-context.test.tsx source-boundaries.test.ts` → 4 files / 20 tests passed. 전체 `npm test` → 25 files / 120 tests passed. `npm run lint` → passed. `npm run typecheck`는 최초 sandbox의 기존 저장소 `tsconfig.app.tsbuildinfo` 쓰기 제한으로 실패했으나 허용된 동일 명령 재실행에서 passed. `npm run build` → passed. `git diff --check` → passed. build에는 기존 ECharts lazy chunk 500.14 kB warning이 남아 있으나 실패는 없다.
- 계약·QA 경계: Backend, API_SPEC, OpenAPI, generated schema, DTO, DB와 Frontend API client는 변경하지 않았다. 모바일 viewport와 screenshot은 열지 않았고 `1280px` 미만 편집 비활성 전환만 component logic으로 검증했다. commit, push, PR은 생성하지 않았다.

### TCD-07. Post-review interaction과 capacity 보강

- 상태: 완료
- 변경 파일: `frontend/src/components/AppShell.tsx`, `frontend/src/features/overviewLayout/overviewLayoutModel.ts`, `frontend/src/features/overviewLayout/overviewLayoutStorage.ts`, `frontend/src/features/overviewLayout/OverviewDashboardWorkspace.tsx`, `frontend/src/i18n/translations.ts`, `frontend/src/styles/pages/overview-layout.css`, `frontend/tests/app-shell-foundation.test.tsx`, `frontend/tests/custom-dashboard.test.tsx`, `frontend/tests/overview-layout.test.ts`, 이 작업지시서.
- storage 안정성: AppShell compact-navigation의 localStorage property 취득과 read/write를 모두 `try` 안으로 격리했다. getter가 `SecurityError`를 던지는 component test에서도 인증 shell과 in-memory compact toggle이 유지된다.
- grid capacity: 12열 × 256행 안에서 요청 위치와 가까운 비중첩 cell을 찾는 공통 배치 함수를 추가했다. click/drop과 저장 복원 모두 이 함수를 사용하며, 물리적으로 배치할 곳이 없으면 기존 배열을 유지하고 builder에 원인을 status message로 표시한다. 36개의 8 × 7 widget으로 grid를 채운 뒤 37번째 추가가 거부되고 모든 geometry가 범위 안이며 서로 겹치지 않는 것을 테스트했다. 저장 데이터의 겹친 widget도 가장 가까운 빈 cell로 복구한다.
- 미저장 state 보호: builder가 열린 동안 dashboard selector와 New/Edit/Delete를 잠가 dashboard 교체·삭제로 draft가 사라지는 경로를 막았다. Cancel 또는 Save로 builder를 닫으면 관리 control이 다시 활성화된다.
- keyboard 조작: drag handle에 Arrow 이동과 Shift+Arrow resize, 현재 column/row/width/height accessible name, `aria-keyshortcuts`와 screen-reader instruction을 추가했다. min/max·grid boundary·다른 widget 충돌을 넘는 조작은 거부하며 saved dashboard의 변경 geometry가 browser-local store에 반영되는 component test를 추가했다.
- 검증: targeted `npm test -- app-shell-foundation.test.tsx overview-layout.test.ts custom-dashboard.test.tsx overview-layout-context.test.tsx source-boundaries.test.ts` → 5 files / 29 tests passed. 전체 `npm test` → 25 files / 125 tests passed. `npm run lint` → passed. `npm run typecheck`는 최초 sandbox의 기존 저장소 `tsconfig.app.tsbuildinfo` 쓰기 제한으로 실패했으나 허용된 동일 명령 재실행에서 passed. `npm run openapi:check`도 최초 sandbox의 `~/.cache/uv` 접근 제한으로 중단됐으나 허용된 동일 명령 재실행에서 OpenAPI artifact current와 generated schema check passed. `npm run build` → passed. `git diff --check` → passed. build에는 기존 ECharts lazy chunk 500.14 kB warning이 남아 있으나 실패는 없다.
- 계약·QA 경계: Backend, API_SPEC, OpenAPI, generated schema, DTO, DB와 Frontend API client는 변경하지 않았다. 모바일 viewport와 screenshot은 열지 않았고 `1280px` 미만 편집 비활성 조건은 component logic test로만 확인했다. commit, push, PR은 생성하지 않았다.

### TCD-08. Keyboard geometry와 storage normalization 보강

- 상태: 완료
- 변경 파일: `frontend/src/features/overviewLayout/OverviewDashboardWorkspace.tsx`, `frontend/src/features/overviewLayout/overviewLayoutModel.ts`, `frontend/src/features/overviewLayout/overviewLayoutStorage.ts`, `frontend/src/i18n/translations.ts`, `frontend/src/styles/pages/overview-layout.css`, `frontend/tests/custom-dashboard.test.tsx`, `frontend/tests/overview-layout.test.ts`, 이 작업지시서.
- geometry 일치: RGL의 `verticalCompactor`를 `noCompactor`로 대체해 `allowOverlap: false` collision과 grid bounds는 유지하면서 명시적으로 저장된 gap과 keyboard `y/h` geometry를 자동 상향 압축하지 않게 했다. keyboard component test는 `ArrowDown`과 `Shift+ArrowDown` 뒤 localStorage·accessible geometry뿐 아니라 실제 `.react-grid-item` transform이 row 2의 56px 위치인지 확인한다.
- bounded normalization: 12 × 256 cell을 `Uint8Array` occupancy로 표현하고 저장 복원 중 한 번만 누적 갱신한다. 현재 occupancy에서 한 번도 들어갈 수 없는 `w × h`는 이후 공간이 줄어들어도 들어갈 수 없으므로 size cache로 즉시 건너뛴다. 5,000개 3 × 2 widget 입력에서 물리적으로 가능한 512개를 유지하는 회귀 guard를 추가했고, 같은 입력의 직접 계측은 수정 전 약 3,139ms에서 수정 후 10.2ms로 감소했다.
- 정확한 안내: 8 × 7 Detection Activity 36개 뒤 같은 크기 추가는 거부되지만 4 × 7 Alert Severity는 `x=8, y=249`에 배치되는 것을 테스트했다. 상태 문구는 전체 grid full이 아니라 “이 Widget을 배치할 공간이 없음”을 알리고 더 작은 widget 선택도 안내한다.
- 검증: targeted `npm test -- custom-dashboard.test.tsx overview-layout.test.ts overview-layout-context.test.tsx app-shell-foundation.test.tsx source-boundaries.test.ts` → 5 files / 30 tests passed. 전체 `npm test` → 25 files / 126 tests passed. `npm run typecheck`, `npm run lint`, `npm run openapi:check`, `npm run build` → passed. OpenAPI artifact와 generated schema는 current다. `git diff --check` → passed. build에는 기존 ECharts lazy chunk 500.14 kB warning이 남아 있으나 실패는 없다.
- 계약·QA 경계: Backend, API_SPEC, OpenAPI, generated schema, DTO, DB와 Frontend API client는 변경하지 않았다. 실제 desktop browser pointer drag·resize visual QA는 이 후속에서 다시 열지 않았고 RGL component DOM과 model/storage test로 검증했다. 모바일 viewport와 screenshot은 계속 범위에서 제외했다. commit, push, PR은 생성하지 않았다.

### TCD-09. Dashboard workbench 분리와 draft geometry 보강

- 상태: 완료
- 사용자 결정: Overview는 선택한 Dashboard를 읽기 전용으로 표시하고, 생성·이름 변경·Widget 추가·이동·resize·삭제는 별도 `/dashboards` 관리 route에서만 수행한다. 본문을 차지하던 Dashboard 관리 box는 제거하고 선택·생성·편집·삭제 control은 header의 `Dashboard 설정` modal로 분리한다.
- 수정 목표: 저장된 custom dashboard의 즉시 drag·resize와 stop 시점 자동 저장을 제거한다. 전용 builder가 기존 layout을 draft로 복제하고 Save에서만 한 번 저장하며 Cancel은 저장 상태를 보존한다.
- geometry guard: RGL이 전달한 좌표·크기를 widget registry min/max, 12열 × 256행과 비중첩 조건에 맞게 정규화하고, 유효하지 않은 layout item이나 drop placeholder가 저장 상태에 섞이지 않게 한다.
- 계약 경계: 기존 Dashboard·Endpoint·Incident query와 URL filter, polling, auth/role, Backend layout API 비호출, 사용자별 browser-local key를 유지한다. Backend, API_SPEC, OpenAPI, DTO와 DB는 변경하지 않는다.
- 변경 파일: `frontend/src/App.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/pages/OverviewPage.tsx`, `frontend/src/features/overviewLayout/OverviewDashboardWorkspace.tsx`, `frontend/src/features/overviewLayout/OverviewLayoutContext.tsx`, `frontend/src/i18n/translations.ts`, `frontend/src/styles/pages/overview-layout.css`, `frontend/tests/custom-dashboard.test.tsx`, `frontend/tests/overview-layout-context.test.tsx`, `frontend/tests/app-shell-foundation.test.tsx`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 작업지시서.
- 구현 결과: Sidebar `Overview` group에 `/dashboards`를 추가했다. Overview는 active Dashboard 선택 결과를 읽기 전용으로 렌더링하고, Workbench 본문은 active layout identity와 preview 또는 Draft builder만 표시한다. 선택·생성·편집·삭제는 page header/Overview toolbar의 `Dashboard 설정` modal로 이동했다.
- 저장 경계: 저장된 custom dashboard의 drag/resize handle은 비활성화된다. 편집 action은 저장 layout을 복제한 Draft를 열고 pointer·keyboard movement와 resize는 Draft만 갱신한다. Save는 이름과 전체 layout을 한 번 저장하며 Cancel은 기존 browser-local 상태를 유지한다. `updateDashboardLayout` 즉시 저장 API는 Context에서 제거했다.
- geometry guard: RGL stop/drop geometry를 widget registry min/max, 12열 × 256행으로 clamp하고 겹침이 있으면 가장 가까운 유효 위치로 복구한다. 복구가 불가능하면 마지막 저장 layout 전체를 보존한다.
- 자동 검증: targeted component test 3 files / 35 tests, `npm run typecheck`, `npm run lint` passed. 최종 `npm run openapi:check` passed, 전체 `npm test`는 25 files / 129 tests passed, `npm run build`와 `git diff --check` passed. build의 기존 ECharts 500.14 kB chunk warning은 실패가 아니다.
- Desktop browser QA: 1440 × 900에서 관리 box 제거, header 설정 modal, custom dashboard 생성과 4개 widget keyboard 배치, Save 후 read-only handle, reload persistence를 확인했다. 실제 pointer drag로 Total Alerts를 row 1에서 row 3으로 옮긴 뒤 Cancel·reload하여 저장 위치 row 1이 유지되는 것도 확인했다. 1280 × 900에서 Edit action과 4개 drag handle이 활성화되는 breakpoint를 확인했다. 최종 1440 화면은 `scrollWidth=clientWidth=1440`, console warning/error 0건이며 `/dashboards`의 저장된 `우선 조사` preview를 열어 두었다.
- 계약·배포 경계: 기존 Dashboard·Endpoint·Incident query, URL filter, polling, auth/role, Backend layout API 비호출과 사용자별 browser-local key를 유지했다. Backend, API_SPEC, OpenAPI, generated schema, DTO와 DB는 변경하지 않았다. Frontend container만 rebuild/recreate했고 Nginx `http://127.0.0.1:8080/`을 통해 live QA했다. 모바일 viewport와 screenshot은 계속 범위에서 제외했으며 commit, push, PR은 생성하지 않았다.

### TCD-10. 고정 Overview와 설정 진입 분리

- 상태: 완료
- 사용자 결정: `/` Overview는 active custom dashboard와 무관하게 기존 immutable 9-block 정보를 항상 전부 표시한다. Dashboard 편집은 Sidebar의 주 메뉴가 아니라 Overview toolbar의 톱니바퀴 `Dashboard 설정`을 통해 `/dashboards` workbench로 진입한다.
- 구현 결과: Primary navigation에서 `Dashboards`를 제거하되 인증 route와 breadcrumb는 유지했다. Overview에서는 custom selector·active layout identity·settings modal을 렌더링하지 않고 고정 `OverviewDashboard`만 사용하며, toolbar의 `Dashboard 설정` link가 현재 query를 보존해 `/dashboards`로 이동한다.
- 계약 경계: Workbench의 browser-local Dashboard 생성·편집·삭제, Draft Save/Cancel, geometry guard와 Dashboard/Endpoint/Incident query는 유지한다. Backend, API, DTO, OpenAPI와 DB는 변경하지 않는다.
- 자동 검증: `npm run typecheck`, `npm run lint`, targeted 3 files / 35 tests, `npm run openapi:check`, 전체 25 files / 129 tests, `npm run build`, `git diff --check`가 통과했다. build의 기존 ECharts 500.14 kB chunk warning은 실패가 아니다.
- Desktop browser QA: 1440 × 900과 1280 × 900 모두 `/`에서 고정 Overview 9개 block, toolbar의 `Dashboard 설정`, Sidebar `Dashboards` 미노출과 가로 overflow 없음(`scrollWidth=clientWidth`)을 확인했다. `/dashboards`에서 breadcrumb, 저장된 custom preview와 설정 modal을 확인했고 최종 Overview 화면의 console warning/error는 0건이다.
- 배포 경계: Frontend container만 rebuild/recreate했으며 `http://127.0.0.1:8080/`에서 확인했다. 모바일 viewport와 screenshot은 범위에서 제외했고 commit, push, PR은 생성하지 않았다.

### TCD-11. Custom Widget 무스크롤 밀도 보정

- 상태: 완료
- 사용자 결정: Custom Dashboard의 개별 Widget 안에 세로·가로 scrollbar를 만들지 않고 제목, 핵심 값, 설명과 목록을 Widget surface 안에서 한눈에 읽을 수 있게 한다. 같은 원인의 KPI, EDR state, chart, severity와 queue Widget에 공통 적용한다.
- 구현 결과: `.custom-dashboard-widget-body`의 nested `overflow:auto`를 제거하고 inline-size container로 전환했다. 외부 drag header와 중복되는 KPI·Panel·Chart title은 accessible text로 유지하면서 시각적 공간만 줄였고 KPI는 icon/value/detail 2단 구조로 바꿨다. Severity와 queue는 custom surface 안에서 compact composition을 사용한다.
- 안전 geometry: EDR State `12 × 4`, Detection Activity 최소 높이 `10`, Alert Severity `4 × 7`, Highest-risk Endpoint와 Incident Queue `6 × 7` 아래로 resize할 수 없게 했다. 저장된 과거 geometry는 기존 parser가 같은 registry min/max와 비중첩 규칙으로 안전하게 복구한다.
- 계약 경계: Widget 종류, Dashboard·Endpoint·Incident query, URL filter, Draft Save/Cancel, browser-local storage key와 12열 × 256행 geometry는 유지한다. Backend, API, DTO, OpenAPI와 DB는 변경하지 않는다.
- 변경 파일: `frontend/src/features/overviewLayout/overviewLayoutModel.ts`, `frontend/src/styles/pages/overview-layout.css`, `frontend/tests/custom-dashboard.test.tsx`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 작업지시서.
- 자동 검증: targeted 3 files / 26 tests, `npm run typecheck`, `npm run lint`, `npm run openapi:check`, 전체 25 files / 130 tests, `npm run build`, `git diff --check`가 통과했다. build의 기존 ECharts 500.14 kB chunk warning은 실패가 아니다.
- Desktop browser QA: 실제 Backend 데이터로 1440 × 900과 1280 × 900에서 9개 Widget을 모두 배치했다. 두 해상도 모두 각 `.custom-dashboard-widget-body`의 `scrollWidth=clientWidth`, `scrollHeight=clientHeight`, `overflow-x/y=hidden`이며 위반 0건이었다. 1280에서 document `scrollWidth=clientWidth=1280`, 최종 console warning/error 0건을 확인했다.
- QA 정리·배포 경계: 검증용 `Widget overflow QA` Dashboard는 삭제하고 기존 `우선 조사`를 active로 복원했다. Frontend container만 rebuild/recreate했고 `http://127.0.0.1:8080/dashboards`에 최종 화면을 열어 두었다. 모바일 시각 QA와 screenshot은 범위에서 제외했으며 commit, push, PR은 생성하지 않았다.

### TCD-12. Stable grid placement와 collision 차단

- 상태: 완료
- 사용자 재현: 1280px Draft에서 6 × 7 Widget 두 개가 나란히 들어갈 수 있는데도 두 번째 click 추가가 `1열 8행`으로 내려갔다. 두 번째 Widget을 빈 `7열 1행`으로 옮기는 pointer 경로에서는 첫 번째 Widget이 `1열 15행`으로 밀렸다.
- 구현 결과: `createOverviewWidget`의 기본 요청 좌표를 `0,0`으로 고정해 공통 빈칸 탐색이 상단 행의 왼쪽부터 공간을 사용하게 했다. RGL은 `getCompactor(null, false, true)` fixed-grid policy로 전환해 drag·resize 충돌 시 조작 중인 Widget을 되돌리고 주변 Widget을 밀지 않는다. Palette drop은 RGL의 전체 layout을 기존 Widget에 적용하지 않고 신규 Widget만 drop 지점과 가장 가까운 비중첩 cell에 배치한다.
- 보존 경계: 12열 × 256행, Widget min/max, Draft Save/Cancel, keyboard 충돌 거부, browser-local user scope, 기존 query·URL·Backend API 미사용과 1280px desktop 편집 경계를 유지한다.
- 변경 파일: `frontend/src/features/overviewLayout/overviewLayoutModel.ts`, `frontend/src/features/overviewLayout/OverviewDashboardWorkspace.tsx`, `frontend/tests/custom-dashboard.test.tsx`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 작업지시서.
- 자동 검증: targeted `npm test -- custom-dashboard.test.tsx overview-layout.test.ts overview-layout-context.test.tsx` → 3 files / 27 tests passed. 최종 `npm run openapi:check`, `npm run typecheck`, `npm run lint`, 전체 `npm test` → 25 files / 131 tests, `npm run build`, `git diff --check`가 모두 통과했다. Build의 기존 ECharts lazy chunk 500.14 kB warning은 실패가 아니다.
- Desktop browser QA: 수정된 Vite source를 기존 Nginx API proxy와 연결해 1280px에서 확인했다. 6 × 7 Widget 두 개를 click 추가하면 각각 `1열 1행`, `7열 1행`에 배치됐다. 오른쪽 Widget을 왼쪽 Widget 위로 pointer drag해 충돌시킨 뒤에도 두 geometry가 그대로 유지됐다. 검사용 Draft는 Cancel했고 저장된 Dashboard는 변경하지 않았다.
- 계약·QA 경계: Backend, API_SPEC, OpenAPI, generated schema, DTO, DB와 Frontend API client는 변경하지 않았다. 모바일 시각 QA와 모바일 전용 builder UX는 기존 사용자 결정대로 범위에서 제외했다.

### TCD-13. Widget catalog preview와 type 중복 방지

- 상태: 완료
- 사용자 결정: Widget palette에서 항목의 의미를 배치 전에 빠르게 식별할 수 있어야 하며, 한 Dashboard에 동일한 데이터 Widget을 반복 배치하지 않는다.
- 구현 결과: 기존 9개 Widget에 Lucide semantic glyph를 매핑해 이름·기본 geometry와 함께 표시한다. 이미 배치된 type은 palette에서 숨기고 제거하면 다시 표시하며, palette click, stale drop과 exported add helper가 동일 type을 다시 추가하지 않는다. 9종을 모두 배치하면 완료 안내를 표시한다. 추가 직후 새 Widget 이동 handle로, 제거 직후 복원된 palette item으로 keyboard focus를 이어 간다. Context create/update도 widgets를 저장하기 전에 type별 첫 instance만 남긴다. 빈 Draft에서도 RGL drop surface를 항상 렌더링하고 empty-state 안내가 pointer event를 가로채지 않게 해 첫 Widget의 palette drop을 보장한다.
- 복구 규칙: 과거 저장값에 동일 type이 여러 개 있으면 원래 순서에서 첫 번째로 유효하게 배치된 instance만 유지하고 나머지는 제거한다. 알 수 없는 type, 중복 UID, 비정상 geometry와 손상 JSON의 기존 방어는 유지한다.
- 보존 경계: Default Overview 9-block, Widget query와 drill-down URL, fixed-grid collision 정책, Draft Save/Cancel, 사용자별 browser-local storage key와 12열 × 256행 geometry를 유지한다. Backend, API_SPEC, OpenAPI, generated schema, DTO와 DB는 변경하지 않는다.
- 이전 기록 경계: TCD-03/04/05/07/08의 duplicate instance와 대용량 동일-type 복원 내용은 당시 완료 근거로 보존한다. 현재 제품 계약과 회귀 기준은 본 TCD-13의 type별 단일 instance가 대체한다.
- 변경 파일: `frontend/src/features/overviewLayout/OverviewDashboardWorkspace.tsx`, `frontend/src/features/overviewLayout/OverviewLayoutContext.tsx`, `frontend/src/features/overviewLayout/overviewLayoutModel.ts`, `frontend/src/features/overviewLayout/overviewLayoutStorage.ts`, `frontend/src/i18n/translations.ts`, `frontend/src/styles/pages/overview-layout.css`, `frontend/tests/custom-dashboard.test.tsx`, `frontend/tests/overview-layout-context.test.tsx`, `frontend/tests/overview-layout.test.ts`, `docs/frontend/DESIGN.md`, `docs/frontend/FRONTEND_SPEC.md`, 이 작업지시서.
- 자동 검증: targeted `npm test -- custom-dashboard.test.tsx overview-layout.test.ts overview-layout-context.test.tsx` → 3 files / 30 tests passed. `npm run openapi:check`, `npm run typecheck`, `npm run lint`, 전체 `npm test` → 25 files / 134 tests, `npm run build`, `git diff --check`가 모두 통과했다. Build의 기존 ECharts lazy chunk 500.14 kB warning은 실패가 아니다.
- Desktop browser QA: 수정 source를 기존 8080 Backend proxy와 연결해 1440 × 900과 1280 × 900에서 확인했다. 두 viewport 모두 palette glyph 9개와 이름의 잘림 0건, page `scrollWidth=clientWidth`, 9번째 item bottom 893.5px로 첫 화면 내 노출을 확인했다. 1280px 빈 Draft에서 Playwright DOM drag로 `Detection Activity`를 palette에서 Canvas로 옮기자 palette 9→8, Canvas 0→1, geometry `3열 1행, 너비 8, 높이 10`으로 배치되고 새 이동 handle이 focus를 받았다. App browser의 실제 pointer drag로 이 Widget을 `1열`에서 `4열`로 이동한 뒤에도 page `scrollWidth=clientWidth`였다. `전체 Alerts` 제거 후 복원된 palette button으로 focus가 돌아왔고 console warning/error는 0건이었다. 검사용 Draft는 Cancel했고 QA 브라우저와 전용 Vite server를 종료했다.

## 12. Desktop browser QA

모바일 viewport는 확인하지 않는다.

### 12.1 1440px

- dark Default dashboard
- light Default dashboard
- Login의 저장 theme 적용
- Alerts, Incidents, Endpoints, Events, Intelligence, Operations의 theme smoke
- panel/control/divider/focus/status/chart 대비
- console warning/error 0건
- page-level horizontal overflow 없음

### 12.2 1280px

- custom dashboard 생성
- widget drag/drop 추가
- palette의 Widget별 preview glyph와 이름 식별
- 같은 widget type 중복 추가 차단과 삭제 후 palette 복귀
- widget 이동·resize·삭제
- dashboard 이름 변경·삭제
- reload 후 active dashboard와 layout 복원
- Default로 전환하면 원래 9-block layout 유지
- Network에서 dashboard layout API GET/PUT/DELETE 요청 0건

### 12.3 사용자 격리

- user A custom dashboard 생성
- logout 후 user B 로그인
- user B에서 user A dashboard가 보이지 않음
- 다시 user A 로그인하면 자신의 dashboard 복원

실제 두 계정 검증이 불가능하면 component test로 증명하고 runtime 사용자 격리는 `환경 제약으로 미검증`이라고 보고한다.

## 13. 최종 Release Gate

전체 검증은 TCD-05에서 한 번 실행한다.

```bash
cd /Users/geonha/Desktop/Techeer-12th-b/edr/frontend
npm run openapi:check
npm run typecheck
npm run lint
npm test
npm run build
cd ..
git diff --check
git status --short
```

추가 검색:

```bash
rg -n 'color-scheme|theme-color|edr\.theme|overviewDashboards|overviewActiveDashboard' \
  frontend/index.html frontend/src frontend/tests docs/frontend
rg -n 'dashboardLayout|saveDashboardLayout|resetDashboardLayout' frontend/src frontend/tests
```

완료 조건:

- 모든 명령 성공
- desktop dark/light QA 성공
- custom dashboard persistence와 사용자 분리 성공
- Backend/API/OpenAPI/DB diff 없음
- dashboard layout API network call 없음
- 모바일 시각 QA를 했다고 주장하지 않음
- 본 문서 TCD-00~05에 변경 파일, 명령, 결과와 남은 위험 기록

## 14. 금지사항

- 사용자 변경 reset/restore/stash
- `origin/main` 또는 다른 branch 변경 덮어쓰기
- Backend layout API를 편의상 연결
- UserDto에 새 식별자 추가
- localStorage에 token 또는 API response 저장
- component마다 raw light color 추가
- theme별 상태 의미 변경
- widget마다 query hook 복제
- Default dashboard를 editable로 변경
- 모바일 UI polish, 모바일 screenshot 또는 viewport matrix 수행
- 불필요한 Docker rebuild
- 관련 없는 refactor
- 검증하지 않은 항목을 완료로 보고
- commit, push, PR 생성

## 15. 최종 보고 형식

다음 순서로 보고한다.

1. 구현 결과 요약
2. 변경 파일과 핵심 책임
3. reference에서 채택/변경/제외한 항목
4. 실행한 validation 명령과 정확한 결과
5. desktop browser QA 결과
6. Backend/API/DB 미변경 증거
7. 남은 위험과 미검증 항목
8. 현재 branch와 `git status --short`

모바일은 다음처럼 명시한다.

```text
모바일 시각 QA와 모바일 전용 builder UX는 사용자 요청에 따라 범위에서 제외했다.
1280px 미만 편집 비활성 조건만 코드와 자동 테스트로 확인했으며 모바일 화면 완성은 주장하지 않는다.
```
