# Frontend Design Instructions

프론트엔드 UI, layout, style, component 또는 interaction을 변경하기 전에 다음 순서를 따른다.

1. `../docs/frontend/DESIGN.md`를 끝까지 읽는다.
2. Route, query, 수동 갱신, auth와 권한은 `../docs/frontend/FRONTEND_SPEC.md`를 따른다.
3. API와 데이터 의미는 `../docs/contracts/API_SPEC.md`와 `../docs/contracts/RISK_POLICY.md`를 따른다.
4. 구현 전 현재 화면과 공통 component를 audit하고 보존, 변경, 제외 범위를 먼저 정리한다.
5. 시각·상호작용 판단은 `DESIGN.md`의 `확정` 항목과 현재 코드를 함께 검증한다.

완료된 작업지시서와 실행 증거는 Git history에서 확인한다. 새 대규모 개편은 별도 작업계획을 만들되 장기 기준을 `DESIGN.md`와 `FRONTEND_SPEC.md`에 반영한다. Backend 계약이 바뀌면 API 문서, Pydantic, manifest, OpenAPI, generated schema와 Frontend client를 같은 변경에서 동기화한다. commit, push, PR은 사용자가 별도로 요청한 경우에만 수행한다.

외부 디자인 자료는 다음 경계 안에서 사용한다.

- Awesome DESIGN.md 사례는 pattern과 문서 구조 비교에만 사용한다. 외부 브랜드의 token, font, layout과 identity를 복제하지 않는다.
- Taste Skill은 `DESIGN.md` 14.3절의 선택 적용 규칙만 사용한다.
- Taste Skill의 marketing hero, AIDA, random layout, cinematic motion, scroll hijack 규칙은 이 EDR 제품 UI에 적용하지 않는다.

작업 완료 전 `DESIGN.md` 14.7절의 Hard Pre-flight를 수행하고, 해당하는 검증 결과를 보고한다. 모바일 시각 QA는 사용자 결정에 따라 제외하고 desktop `1280px`, `1440px`을 확인한다. 지속되는 제품 결정은 `DESIGN.md` 또는 `FRONTEND_SPEC.md`에 기록한다.
