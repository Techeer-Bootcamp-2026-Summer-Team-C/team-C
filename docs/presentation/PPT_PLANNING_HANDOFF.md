# EDR_C PPT 요구서 기획 핸드오프

- 작성일: 2026-07-21
- 작업 위치: `C:\Users\geonh\Desktop\team-C`
- 다음 대화의 목적: PPT 제작자에게 전달할 상세 요구서를 사용자와 함께 기획하고 문서화
- 선행 문서: `docs/presentation/PRESENTATION_PLAN.md`
- 목데이터 요구사항: `docs/presentation/MOCK_DATA_REQUIREMENTS.md`
- 발표대본: `docs/presentation/PRESENTATION_SCRIPT.md`

## 1. 새 대화에서 가장 먼저 할 일

다음 담당자는 작업을 시작하기 전에 `docs/presentation/PRESENTATION_PLAN.md`를 처음부터 끝까지 읽는다. 이 파일에는 발표 내용, 시간표, 구현 경계, 데모, Kafka, 두 트러블슈팅, 표현 규칙과 체크리스트가 정리되어 있다.

그다음 현재 코드와 아래 source file을 확인한다. 문서와 코드가 다르면 현재 구현 코드를 기준으로 한다.

- `README.md`
- `backend/kafka.py`
- `backend/collector.py`
- `backend/workers.py`
- `backend/storage/postgres.py`
- `backend/storage/clickhouse.py`
- `rules/process/proc_powershell_encoded.v1.yaml`
- `rules/network/net_suspicious_egress.v1.yaml`
- `tests/seed_frontend_qa.py`
- `tests/test_dns_lookup.py`
- `tests/test_storage_integration.py`
- `docs/operations/PERFORMANCE_IMPROVEMENTS_HISTORY.md`

## 2. 새 대화의 작업 목표

다음 대화에서는 PPT 파일을 바로 만들지 않는다. 사용자와 함께 PPT 요구사항을 먼저 확정한다.

최종 목표는 PPT를 만드는 팀원에게 그대로 전달할 수 있는 다음 산출물이다.

1. 슬라이드별 상세 요구서
2. 각 슬라이드의 목적, 핵심 문장, 화면 구성, 시각 요소, 발표 시간
3. 사용할 Diagram·Screenshot·Video·수치 목록
4. PPT 제작 시 반드시 지켜야 할 사실 관계와 금지 표현
5. 디자인 톤과 레이아웃 규칙
6. PPT 제작자에게 보낼 복사·붙여넣기용 메시지

권장 저장 경로:

```text
docs/presentation/PPT_REQUIREMENTS.md
```

## 3. 작업 방식에 대한 사용자 요구

사용자는 처음부터 완성안을 일방적으로 받기보다, 주요 결정을 하나씩 함께 논의하는 방식을 원한다.

다음 원칙을 지킨다.

- 곧바로 전체 PPT를 만들지 않는다.
- 먼저 이미 확정된 사항과 아직 결정하지 않은 사항을 구분한다.
- 한 번에 너무 많은 선택지를 던지지 않는다.
- 슬라이드 목적, 디자인, 정보량, 시연 전환을 순서대로 협의한다.
- 구현되지 않은 기능을 발표용으로 만들어내지 않는다.
- 사용자가 합의한 내용만 PPT 요구서의 확정 사항으로 기록한다.

## 4. 발표의 확정 조건

### 발표 시간

- 전체 약 8분
- 리허설 목표는 7분 30초~7분 45초
- 영상·브라우저 이동을 위한 15초 정도의 여유 확보

### 청중

- 시니어·수석 개발자
- 주니어 개발자
- 교수
- 기업 관계자
- 학생 개발자

따라서 발표는 비보안 청중도 이해할 수 있는 이야기로 시작하고, 기술 파트에서는 시니어 개발자가 검증할 수 있는 정확한 근거와 한계를 제시해야 한다.

### 목표 인상

> 기술적으로 완성도가 높고, 발표도 잘 준비한 팀

### 핵심 메시지

> 수많은 Endpoint Event를 빠르게 처리하면서도, 잘못된 공격 관계를 만들지 않는 EDR을 구현했다.

### 최종 메시지

> 저희는 단순히 위험을 경고하는 시스템이 아니라, 수많은 Endpoint Event를 빠르고 정확하게 연결해 무슨 일이 일어났는지 설명할 수 있는 EDR을 구현했습니다.

## 5. 확정된 발표 흐름

```text
인트로 영상
→ EDR 개념 소개
→ EDR_C 소개
→ 큰 데이터 흐름
→ 라이브 시연
→ 전체 아키텍처
→ Kafka 상세
→ ClickHouse·PostgreSQL 역할 분리
→ 성능 트러블슈팅
→ 정확성 트러블슈팅
→ 인트로 회수와 결론
```

설명 순서는 `짧은 설명 → 시연 → 깊은 기술 설명`이다.

- 시연 전: EDR과 전체 흐름만 설명
- 시연 중: 사용자가 보는 공격 조사에 집중
- 시연 후: Kafka와 저장소 구조를 상세 설명

## 6. 권장 슬라이드 구조

현재 기획은 약 9~10장이다. 라이브 데모는 별도 슬라이드 대신 실제 Dashboard로 전환한다.

| 번호 | 슬라이드 | 시간 | 핵심 목적 |
| ---: | --- | ---: | --- |
| 1 | 인트로 영상 | 25초 | 보이지 않는 공격 상황으로 후킹 |
| 2 | EDR이란? | 25초 | 비보안 청중의 개념 이해 |
| 3 | EDR_C | 30초 | 프로젝트 범위와 `Event → Alert → Incident` 흐름 |
| 4 | 라이브 데모 전환 | 1분 40초 | 실제 Dashboard에서 조사 경험 증명 |
| 5 | 전체 아키텍처 | 20초 | Endpoint부터 Dashboard까지 구현 범위 조망 |
| 6 | Kafka Pipeline | 50초 | 수집·저장·탐지 분리와 신뢰성 설명 |
| 7 | 저장소 역할 | 25초 | ClickHouse·PostgreSQL·S3 선정 이유 |
| 8 | 성능 트러블슈팅 | 1분 | Python 집계에서 ClickHouse 집계로 이동 |
| 9 | 정확성 트러블슈팅 | 1분 | IP·Domain correlation 오탐 제거 |
| 10 | 결론 | 30초 | 인트로 회수와 현재 완성도 제시 |

PPT 요구서를 작성할 때 이 표를 그대로 복제하는 데서 끝내지 말고, 각 슬라이드의 시각적 역할과 화면 전환을 사용자와 협의한다.

## 7. 슬라이드별 현재 기획

### 슬라이드 1 — 인트로 영상

가상 시나리오:

```text
초등학생 시절 느낌의 컴퓨터
→ 출처가 불분명한 게임 설치 파일 다운로드
→ 실행했지만 화면에는 별다른 변화가 없음
→ Encoded PowerShell 실행
→ 암호화된 외부 통신
→ “이 컴퓨터에서는 무슨 일이 일어난 걸까요?”
```

필수 표시:

> 시연을 위해 재구성한 가상 시나리오

주의사항:

- 실제 팀원의 과거 경험이라고 주장하지 않는다.
- 실제 게임, 실제 불법 사이트, 실제 악성코드 브랜드를 사용하지 않는다.
- Dashboard는 영상에서 미리 보여주지 않는다.
- 영상은 20~25초 이내다.

### 슬라이드 2 — EDR이란?

전달할 개념:

- EDR은 Endpoint Detection and Response다.
- Endpoint 행위를 지속 관찰한다.
- 탐지 이후 공격 전후 관계를 조사하고 대응 근거를 제공한다.
- 현대 백신과 기능이 겹칠 수 있으므로 백신과 EDR을 절대적으로 구분하지 않는다.

시각 방향:

```text
경고 한 줄
vs
Event → Alert → Incident → Evidence
```

### 슬라이드 3 — EDR_C

한 문장:

> EDR_C는 Windows와 macOS Endpoint에서 발생하는 행위를 수집하고, 탐지된 위협을 Alert와 Incident로 연결하여 공격 흐름과 대응 근거를 제공하는 EDR 시스템입니다.

큰 흐름:

```text
Windows·macOS Endpoint
→ Process·Network·File·DNS·L7 Event
→ RuleV1 + MITRE ATT&CK
→ Alert·Incident
→ Dashboard 조사
```

이 슬라이드에서는 Kafka와 DB의 상세 내용을 설명하지 않는다.

### 라이브 데모

권장 동선:

```text
Overview
→ Incident 목록
→ Incident 상세
→ Investigation Graph
→ Alert 상세
→ MITRE·Response Guidance
```

상세 클릭 동선과 멘트는 `PRESENTATION_PLAN.md` 7장을 따른다.

### 슬라이드 5 — 전체 아키텍처

목적은 모든 기술을 설명하는 것이 아니라 구현 범위를 보여주는 것이다.

정확한 핵심 흐름:

```text
Windows/macOS Agent
→ Nginx(mTLS)
→ FastAPI Collector
→ Kafka telemetry.raw
→ Event Storage Worker
→ ClickHouse
→ Kafka telemetry.validated
→ Detection Worker
→ PostgreSQL Alert/Incident
→ FastAPI Dashboard API
→ React Dashboard
```

현재 공유된 Architecture PNG는 수정이 필요하다. 다음 대화에서 이미지가 필요하면 사용자가 다시 첨부하거나 편집 가능한 원본 위치를 확인한다.

필수 수정 사항:

- Endpoint Python 아이콘을 C++20·Swift로 교체
- Kafka Table Engine 제거
- Event Storage Worker와 Storage Lifecycle Worker 추가
- `telemetry.raw`와 `telemetry.validated` 분리
- Nginx mTLS 표시
- Vercel·Docker·AWS 경계 수정
- Monitoring·CI/CD를 핵심 Event 흐름과 시각적으로 분리

### 슬라이드 6 — Kafka Pipeline

전체 아키텍처와 분리된 별도 슬라이드로 만든다.

```text
Collector
   ↓
telemetry.raw
   ↓
Event Storage Worker ──→ ClickHouse
   ↓
telemetry.validated
   ↓
Detection Worker ──→ PostgreSQL
```

반드시 보여줄 세 가지 callout:

- `Broker ACK`: Collector 요청과 후속 처리 분리
- `endpointId key`: 같은 Endpoint Event를 같은 partition으로 라우팅
- `at-least-once + idempotency`: 재처리 시 논리적 중복 방지

설명할 코드 기반 사실:

- Collector는 Kafka ACK를 받은 Event만 `acceptedEventIds`로 반환한다.
- Kafka ACK는 ClickHouse 저장·탐지 완료를 의미하지 않는다.
- consumer auto commit은 꺼져 있고 처리 결과에 따라 수동 commit한다.
- Event는 동일 identity·payload에 대해 논리적 중복을 만들지 않는다.
- Alert는 `(event_id, rule_code, rule_version)`으로 멱등 생성한다.
- Producer는 idempotence를 활성화한다.

금지 표현:

- exactly-once를 보장한다.
- Worker가 자동으로 무한 확장된다.
- 로컬 Kafka 구성이 고가용성 cluster다.

### 슬라이드 7 — 저장소 역할

| 저장소 | 역할 |
| --- | --- |
| ClickHouse | 대량 Event의 저장·기간 검색·집계 |
| PostgreSQL | 사용자·Endpoint·Alert·Incident·감사 로그의 상태와 트랜잭션 |
| S3 | 오래된 Event Archive와 실패 원문 |

다음 문장으로 성능 트러블슈팅에 연결한다.

> 하지만 ClickHouse를 사용한다고 자동으로 빠른 것은 아니었습니다.

### 슬라이드 8 — 성능 트러블슈팅

제목:

> ClickHouse를 사용했는데 왜 16초가 걸렸을까?

Before:

```text
ClickHouse 원본 Event 반복 조회
→ raw_payload 포함 전송
→ Python에서 집계
```

After:

```text
ClickHouse GROUP BY
→ 필요한 Column만 projection
→ 집계 결과만 전달
```

핵심 문구:

> 연산 위치를 Application에서 Database로 이동

표시할 실측값:

- LATEST_24H: 16.31초 → 0.584초
- 응답 크기: 약 135KB → 약 7KB
- 지연 감소: 96.42%
- 속도 향상: 27.93배

수치 조건:

- 31일
- 100 Endpoint
- 248,000 Event
- 목데이터 환경

`9 query → 2 query`는 후속 round-trip 감소이며 wall-clock 4.5배 개선이라고 말하지 않는다.

### 슬라이드 9 — 정확성 트러블슈팅

제목:

> 검색 결과가 많으면 좋은 상관분석일까?

Before 예시:

```text
입력: yahoo.com

정상  yahoo.com
정상  mail.yahoo.com
오탐  notyahoo.com
오탐  yahoo.com.evil.example
```

After:

- Domain normalize
- exact match
- `.` 경계를 가진 실제 Subdomain만 허용
- DNS Answer는 JSON 배열 exact membership으로 비교
- Endpoint filter는 ClickHouse query로 pushdown

핵심 문구:

> 보안 시스템에서는 많이 찾는 것보다, 왜 연결됐는지 설명할 수 있는 정확성이 중요했습니다.

이 사례에는 wall-clock 수치가 없으며 correctness 개선으로 표현한다.

### 슬라이드 10 — 결론

인트로의 게임 다운로드 화면을 다시 사용한다.

```text
Event 관찰
→ Rule 기반 Alert
→ correlation key·window 기준 Incident
→ Evidence와 Response Guidance
```

현재 한계:

- Response Guidance는 읽기 전용이다.
- 자동 격리, 프로세스 종료, 파일 삭제는 구현하지 않았다.
- cross-rule Incident correlation은 구현하지 않았다.

마지막 문장:

> 저희는 단순히 위험을 경고하는 시스템이 아니라, 수많은 Endpoint Event를 빠르고 정확하게 연결해 무슨 일이 일어났는지 설명할 수 있는 EDR을 구현했습니다.

## 8. 구현 코드 기준 필수 주의사항

### 8.1 PowerShell과 encrypted egress는 자동으로 같은 Incident가 아니다

현재 RuleV1:

- PowerShell: `correlation_key: suspicious-powershell`
- encrypted egress: `correlation_key: suspicious-egress`

현재 Incident UPSERT 기준:

```text
(endpoint_id, correlation_key, window_start_at)
```

따라서 두 Rule은 자동으로 하나의 Incident에 합쳐지지 않는다.

현재 `tests/seed_frontend_qa.py`는 두 Alert를 하나의 Incident에 직접 삽입하지만, 이는 실제 Detection Worker correlation 결과가 아니다.

코드와 일치하는 다중 Alert Incident 시연:

```text
같은 Endpoint
→ 30분 이내 Encoded PowerShell Event 반복
→ 같은 Rule의 Alert 두 개
→ 같은 suspicious-powershell Incident
```

### 8.2 Kafka partition 수 문서 불일치

- `backend/kafka.py`: 기본 2
- `compose.yaml`: 기본 2
- `docs/architecture/TECH_STACK.md`: 최소 3으로 기록

정리 전까지 PPT에 특정 partition 수를 넣지 않는다. 다음 표현만 사용한다.

> 설정된 Kafka partition 수 범위에서 Worker를 독립적으로 확장할 수 있다.

### 8.3 성능 수치 범위

- production benchmark가 아니다.
- 목데이터 기반 동일 API 변경 전·후 기록이다.
- P50/P95/P99를 측정했다고 말하지 않는다.
- ClickHouse `FINAL`, `ARRAY JOIN`, Archive scan 비용은 남아 있다.

### 8.4 EDR 현재 범위

- Windows C++20 Agent와 macOS Swift Agent를 사용한다.
- Npcap·tcpdump에서 metadata를 추출하지만 원본 PCAP은 저장하지 않는다.
- Response Guidance는 수동 조치 안내다.
- 원격 자동 대응은 현재 범위가 아니다.

## 9. PPT 디자인에서 아직 결정하지 않은 사항

다음 대화에서 사용자와 하나씩 결정한다.

- PPT 제작 도구와 최종 파일 형식
- 발표용 화면 비율
- 팀 또는 서비스의 최종 이름과 Logo
- Dark EDR Console 스타일을 그대로 사용할지 여부
- 메인 색상과 강조 색상
- 인트로 영상의 그래픽 스타일
- 슬라이드에 포함할 실제 Screenshot 범위
- Architecture Diagram의 편집 가능한 원본 존재 여부
- 발표자 수와 발표자 교대 지점
- 발표 장소에서 영상·음향·인터넷 사용 가능 여부
- PPT 제작자에게 전달할 마감일

아직 정하지 않은 디자인 요소를 임의로 확정하지 않는다.

## 10. PPT 요구서에 포함할 디자인 원칙 초안

이 내용은 다음 대화에서 사용자 확인 후 확정한다.

- 16:9 발표 화면을 기본 후보로 검토
- 한 슬라이드에 하나의 메시지
- 긴 기술 스택 표를 만들지 않음
- Architecture와 Kafka 상세를 서로 다른 슬라이드로 분리
- 성능과 정확성은 각각 Before/After 구조 사용
- 핵심 수치는 큰 숫자로 표시하고 측정 조건은 같은 화면에 표기
- 영어 기술 용어는 유지하고 설명 문장은 한국어 사용
- Dashboard Screenshot은 장식이 아니라 발표자가 실제로 언급할 영역만 사용
- 지나치게 많은 AWS·Library Logo를 나열하지 않음
- Monitoring·CI/CD는 핵심 Event 흐름보다 낮은 시각 우선순위 사용
- 인트로와 결론에서 같은 시각 motif를 재사용해 이야기를 회수

## 11. 새 대화의 권장 진행 순서

1. 이 핸드오프와 `PRESENTATION_PLAN.md`를 읽는다.
2. 현재 작업 tree와 핵심 구현 파일을 확인한다.
3. 확정 사항과 미결정 사항을 짧게 사용자에게 정리한다.
4. 전체 PPT의 visual concept을 사용자와 결정한다.
5. 슬라이드 1부터 한 장씩 목적과 구성을 합의한다.
6. Architecture와 Kafka Diagram의 표현 방식을 합의한다.
7. Video·Demo·PPT 전환 방식을 합의한다.
8. 합의 결과를 `PPT_REQUIREMENTS.md`에 작성한다.
9. PPT 제작자에게 보낼 복사·붙여넣기 메시지를 문서 끝에 추가한다.
10. 사용자가 요구서를 승인한 뒤에만 실제 PPT 제작 단계로 넘어간다.

## 12. 작업 안전 범위

- 이 단계에서는 애플리케이션 코드를 수정하지 않는다.
- QA 시드의 correlation 불일치는 요구서에 기록만 하고, 사용자가 별도로 요청할 때 수정한다.
- Architecture PNG를 사용자 승인 없이 덮어쓰지 않는다.
- Git stage, commit, push는 사용자가 요청하기 전까지 하지 않는다.
- 현재 작업 tree의 다른 변경은 사용자 또는 다른 작업의 소유물이므로 건드리지 않는다.

## 13. 새 대화 시작용 복사·붙여넣기 프롬프트

아래 내용을 새 Codex 대화에 그대로 전달한다.

```text
작업 폴더는 C:\Users\geonh\Desktop\team-C 입니다.

EDR_C 8분 최종 발표의 PPT를 만드는 팀원에게 전달할 상세 요구서를 같이 기획하고 싶습니다. 바로 PPT나 전체 완성안을 만들지 말고, 저와 주요 결정을 하나씩 논의한 뒤 요구서를 작성해 주세요.

먼저 다음 네 파일을 처음부터 끝까지 읽어 주세요.

1. docs/presentation/PRESENTATION_PLAN.md
2. docs/presentation/PPT_PLANNING_HANDOFF.md
3. docs/presentation/MOCK_DATA_REQUIREMENTS.md
4. docs/presentation/PRESENTATION_SCRIPT.md

중요 원칙:

- 현재 구현 코드를 source of truth로 사용하세요.
- 필요하면 backend/kafka.py, backend/collector.py, backend/workers.py, RuleV1 YAML, tests/seed_frontend_qa.py, 성능 보고서와 DNS 테스트를 다시 확인하세요.
- 구현하지 않은 기능을 발표 성과로 쓰지 마세요.
- PowerShell과 encrypted egress Rule은 correlation_key가 달라 현재 코드에서 자동으로 같은 Incident가 되지 않습니다.
- 현재 QA seed는 두 Alert를 한 Incident에 수동 연결하므로 실제 Detection Worker 결과처럼 설명하면 안 됩니다.
- Kafka partition 기본값은 코드·Compose에서 2지만 TECH_STACK 문서에는 3으로 적혀 있으므로, 정리 전에는 PPT에 특정 개수를 넣지 마세요.
- 성능 수치는 31일·100 Endpoint·248,000 Event 목데이터 환경의 결과이며 production benchmark가 아닙니다.
- 목데이터의 세 profile, 예상 count, correlation 제약, 안전한 reset 조건은 MOCK_DATA_REQUIREMENTS.md를 따르세요.

새 대화의 목표 산출물은 docs/presentation/PPT_REQUIREMENTS.md 와 PPT 제작자에게 보낼 복사·붙여넣기용 메시지입니다.

먼저 기존 기획에서 이미 확정된 내용과 아직 결정하지 않은 PPT 디자인 요소를 구분해서 알려주고, 첫 번째로 결정할 사항부터 저와 상의해 주세요.
```

## 14. 완료 기준

다음 조건이 충족되면 PPT 요구서 기획이 완료된 것으로 본다.

- 슬라이드별 목적과 핵심 메시지가 한 문장으로 정의됨
- 각 슬라이드의 레이아웃과 시각 자료가 정의됨
- Video·Demo·PPT 전환 시점이 정의됨
- Architecture와 Kafka Diagram의 수정 요구가 정의됨
- 두 트러블슈팅의 수치와 표현 범위가 정확함
- 구현되지 않은 기능이 성과로 포함되지 않음
- PPT 제작자가 추가 질문 없이 초안을 만들 수 있음
- 제작자에게 보낼 메시지가 문서 끝에 준비됨
- 사용자가 전체 요구서를 승인함
