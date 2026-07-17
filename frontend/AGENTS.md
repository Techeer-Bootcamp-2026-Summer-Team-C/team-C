# Frontend Design Instructions

프론트엔드 UI, layout, style, component 또는 interaction을 변경하기 전에 다음 순서를 따른다.

1. `../docs/frontend/DESIGN.md`를 끝까지 읽는다.
2. dark/light theme 또는 custom Overview dashboard 작업이면 `../docs/frontend/THEME_CUSTOM_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md`를 끝까지 읽고 TCD Package를 따른다.
3. 그 외 Overview 개편 작업이면 `../docs/frontend/OVERVIEW_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md`를 끝까지 읽는다.
4. `../docs/frontend/OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`를 끝까지 읽고 현재 작업지시서가 지정한 Package 하나만 수행한다.
5. 시각·상호작용 판단은 `DESIGN.md`의 `확정` 항목을 따른다.
6. Route, query, polling, auth와 권한은 `../docs/frontend/FRONTEND_SPEC.md`를 따른다.
7. API와 데이터 의미는 `../docs/contracts/API_SPEC.md`와 `../docs/contracts/RISK_POLICY.md`를 따른다.
8. 구현 전 현재 화면과 공통 component를 audit하고 보존, 변경, 제외 범위를 먼저 정리한다.

Overview 개편은 동시에 여러 Package를 진행하지 않는다. 작업을 시작할 때 지정 Package를 `진행 중`으로, 완료할 때 검증 명령과 결과를 기록한 뒤 `완료`로 변경한다. Theme/custom dashboard 작업은 완료된 OVR/REF 기록을 다시 열지 않고 `THEME_CUSTOM_DASHBOARD_IMPLEMENTATION_WORK_ORDER.md`의 TCD 기록만 갱신한다. Backend 계약이 바뀌면 API 문서, Pydantic, manifest, OpenAPI, generated schema와 Frontend client를 같은 Package에서 동기화한다. commit, push, PR은 사용자가 별도로 요청한 경우에만 수행한다.

외부 디자인 자료는 다음 경계 안에서 사용한다.

- Awesome DESIGN.md 사례는 pattern과 문서 구조 비교에만 사용한다. 외부 브랜드의 token, font, layout과 identity를 복제하지 않는다.
- Taste Skill은 `DESIGN.md` 14.3절의 선택 적용 규칙만 사용한다.
- Taste Skill의 marketing hero, AIDA, random layout, cinematic motion, scroll hijack 규칙은 이 EDR 제품 UI에 적용하지 않는다.

작업 완료 전 `DESIGN.md` 14.7절의 Hard Pre-flight를 수행하고, 해당하는 검증 결과를 보고한다. Theme/custom dashboard 작업의 모바일 시각 QA는 사용자 결정에 따라 제외하고 desktop `1280px`, `1440px`만 확인한다. Theme/custom dashboard 결과는 새 작업지시서의 TCD Package에 기록하고, 그 외 Overview 개편 결과는 `OVERVIEW_DASHBOARD_REDESIGN_PLAN.md`의 지정 Work Package에 기록한다.
