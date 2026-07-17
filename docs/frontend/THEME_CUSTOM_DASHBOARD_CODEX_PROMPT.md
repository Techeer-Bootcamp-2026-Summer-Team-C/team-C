# Codex Start Prompt — Theme and Custom Dashboard

아래 코드 블록 전체를 새 Codex 작업의 첫 메시지로 전달한다.

```text
작업 위치는 반드시 아래 실제 Team C 저장소다.

/Users/geonha/Desktop/Techeer-12th-b/edr

목표는 현재 EDR Console에 전체 dark/light theme 전환과 사용자별 custom Overview dashboard builder를 구현하는 것이다. 계획만 작성하고 멈추지 말고 구현, 자동 테스트, desktop browser QA, 문서 기록까지 완료해라.

가장 먼저 다음 파일을 순서대로 끝까지 읽어라.

1. frontend/AGENTS.md
2. docs/frontend/DESIGN.md
3. docs/frontend/THEME_CUSTOM_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md
4. docs/frontend/FRONTEND_SPEC.md
5. docs/contracts/API_SPEC.md의 Dashboard, Endpoint, Incident, Auth 관련 절
6. docs/contracts/RISK_POLICY.md
7. docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md의 DnD/theme 관련 완료 기록

그다음 작업지시서 4절의 현재 source와 test를 직접 audit해라. README나 이전 완료 문구만 믿지 말고 실제 코드, package, generated schema와 test 경계를 기준으로 판단해라.

Source of truth가 충돌하면 다음 순서를 적용해라.

1. API_SPEC.md와 RISK_POLICY.md의 API/데이터 의미
2. THEME_CUSTOM_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md의 이번 기능 범위
3. DESIGN.md와 FRONTEND_SPEC.md의 최신 결정
4. 현재 frontend/src 구현
5. 이전 Overview 작업 문서는 완료 이력
6. Team B IDS-COLLECTOR는 UI/interaction reference

이번 사용자 결정은 기존 dark-only 결정을 dual theme으로 대체한다. 기존 Default Overview는 immutable 상태로 유지하지만, 그와 분리된 custom dashboard에서는 drag/drop과 resize를 허용한다. 이전 완료 계획의 OVR/REF 상태를 다시 열거나 과거 증거를 덮어쓰지 마라. 새 작업 진행 기록은 THEME_CUSTOM_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md의 TCD-00~TCD-05에 남겨라.

시작 절차:

- cd /Users/geonha/Desktop/Techeer-12th-b/edr
- git status --short --branch와 현재 branch를 확인해라.
- 사용자 변경이 있으면 reset, restore, checkout, stash하지 마라.
- git fetch origin 후 최신 origin/main을 확인해라.
- feat/theme-custom-dashboard branch가 없으면 최신 origin/main에서 생성해라.
- 이미 있으면 base와 작업 상태를 확인한 뒤 안전하게 이어가라.
- commit, push, PR은 만들지 마라.

수정 전에 frontend에서 아래 baseline을 실행하고 실제 결과를 TCD-00에 기록해라.

- npm run openapi:check
- npm run typecheck
- npm run lint
- npm test

구현 핵심 조건:

1. Theme
   - key는 edr.theme 하나다.
   - 값이 없거나 손상되면 dark가 기본이다.
   - <html class="light">로 light token을 적용한다.
   - ThemeProvider는 AuthProvider 바깥에 둔다.
   - React mount 전 index.html bootstrap으로 저장 theme를 적용한다.
   - AppShell top bar에 접근 가능한 EN/KO theme toggle을 추가한다.
   - Login에는 별도 toggle을 만들지 않지만 저장 theme는 적용한다.
   - color-scheme, theme-color, print rule과 ECharts도 함께 동기화한다.
   - 기존 semantic token 이름을 유지하고 component별 raw color 분기를 만들지 마라.

2. Dashboard mode
   - Default는 현재 9-block Overview이며 immutable이다.
   - Signal ribbon은 grid 밖에 고정한다.
   - custom dashboard는 여러 개 생성, 선택, 이름 변경, 삭제할 수 있다.
   - New dashboard는 저장되지 않은 빈 builder를 연다.
   - 이름과 widget 1개 이상이 있을 때만 Save할 수 있고, Save 시 생성·active 전환해라.
   - Cancel하면 dashboard와 localStorage에 아무것도 만들지 마라.
   - 기존 custom dashboard의 widget 추가·삭제와 이름 변경은 builder Save로 반영해라.
   - 저장된 custom dashboard 화면의 drag/resize 종료 결과는 자동 저장해라.
   - 같은 widget type을 여러 번 추가할 수 있고 instance마다 고유 uid를 가진다.
   - 현재 9개 OVERVIEW_BLOCK_IDS만 widget catalog로 제공한다.
   - chart type 전환은 만들지 마라.

3. 사용자별 저장
   - 인증 DTO의 숫자형 user.userId만 사용해라.
   - edr.overviewDashboards.v1.user.${userId}
   - edr.overviewActiveDashboard.v1.user.${userId}
   - loginId fallback과 인증 전 storage 접근을 만들지 마라.
   - OverviewLayoutProvider는 인증된 Overview route 내부에 두고 key={String(userId)}로 사용자 변경 시 재마운트해라.
   - ADMIN, ANALYST, VIEWER 모두 사용할 수 있다.
   - malformed JSON, unknown version/widget, 비정상 layout과 storage exception을 안전하게 처리해라.

4. Drag/drop
   - react-grid-layout@2.2.3을 설치해라.
   - React 19/TypeScript에서 ResponsiveGridLayout, useContainerWidth, verticalCompactor modern API를 우선해라.
   - legacy/WidthProvider는 modern API가 실제 검증에서 불가능할 때만 사용해라.
   - palette drag/drop뿐 아니라 click/keyboard 추가 대안도 제공해라.
   - drag와 resize의 매 이벤트마다 저장하지 말고 stop 시점에 저장해라.
   - button/link/chart interaction이 drag handle과 충돌하지 않게 해라.
   - widget instance가 늘어도 API query가 중복 생성되지 않게 기존 Overview query 결과를 재사용해라.

5. Backend 경계
   - Backend dashboard layout API를 호출하지 마라.
   - Backend, API_SPEC, OpenAPI, generated schema, DTO, DB migration을 바꾸지 마라.
   - frontend가 새 지표, health, delta, SLA, 담당자 또는 coverage를 추정하지 마라.
   - overview-redesign.test.tsx의 layout client method 부재 검증을 유지해라.

6. localStorage/test 경계
   - source-boundaries.test.ts를 삭제하거나 느슨하게 만들지 마라.
   - AppShell, theme storage, Overview layout storage를 key별 allowlist로 좁게 확장해라.
   - App/AppShell을 직접 render하는 test helper에는 ThemeProvider를 추가해라.
   - test마다 localStorage, html light class와 변경한 meta state를 정리해라.
   - index.html bootstrap과 ThemeProvider의 key/default/class가 같은지 source-level test로 확인해라.

모바일 화면은 볼 필요가 없다.

- browser QA는 1280px과 1440px desktop만 수행해라.
- 모바일 screenshot, 360/375/768/1024 viewport matrix, 모바일 전용 UI polish를 하지 마라.
- 1280px 미만에서는 custom dashboard 편집을 비활성화하는 코드 조건만 유지해라.
- 기존 responsive DOM/CSS를 의도적으로 제거하지 마라.
- 모바일 화면 완성을 검증했다고 보고하지 마라.

TCD-00부터 TCD-05까지 한 번에 하나씩 진행 중/완료 상태로 갱신해라. 각 Package 종료 시 변경 파일, 판단, targeted test와 결과를 작업지시서에 기록해라. 실제 blocker가 아니면 Package 하나가 끝날 때마다 내 확인을 기다리지 말고 최종 Release Gate까지 계속 진행해라.

전체 test/lint/build/OpenAPI check와 desktop browser QA는 TCD-05에서 한 번 최종 실행해라. Docker rebuild나 full-stack restart는 하지 마라. 현재 계약형 mock 또는 이미 실행 중인 local backend를 사용할 수 있지만, 오래된 runtime image의 동작을 최신 source 계약으로 오해하지 마라.

최종 검증:

- npm run openapi:check
- npm run typecheck
- npm run lint
- npm test
- npm run build
- git diff --check
- git status --short

최종 답변에는 다음을 포함해라.

1. 구현 결과
2. 변경 파일과 책임
3. reference에서 채택/변경/제외한 내용
4. 각 검증 명령의 정확한 결과
5. 1280/1440 desktop dark/light 및 DnD QA 결과
6. Backend/API/DB 미변경과 layout API network call 0건 증거
7. 남은 위험과 미검증 항목
8. branch와 git status

모바일 시각 QA는 사용자 요청으로 제외했으며 완료를 주장하지 않는다고 명시해라. commit, push, PR은 하지 마라.
```
