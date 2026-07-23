# OWL 8분 최종 발표 PPT 제작 요구서

- 작성일: 2026-07-21
- 발표 시간: 약 8분
- 최종 납품 형식: `.pptx`
- 화면 비율: 16:9
- 서비스명: `OWL`
- 내부 프로젝트명: `EDR_C`
- 문서 목적: PPT 제작자가 발표 방향과 기술적 경계를 이해하고 일관된 초안을 제작할 수 있도록 하는 기준 문서

> 이 문서는 PPT 시안이나 픽셀 단위 레이아웃 명세가 아니다. 발표의 메시지, 시각적 방향, 슬라이드별 역할, 기술적 사실 관계와 금지 표현을 고정한다. 구체적인 배치와 Screenshot 선정은 이 범위 안에서 제작자가 판단한다.

## 1. Source of truth와 작업 원칙

발표 내용의 최우선 기준은 현재 구현 코드다. 문서와 코드가 다르면 현재 코드의 동작을 기준으로 하고, 정리되지 않은 불일치는 발표 성과로 사용하지 않는다.

기획 기준 문서:

- `docs/presentation/PRESENTATION_PLAN.md`

핵심 구현 근거:

- `backend/kafka.py`
- `backend/collector.py`
- `backend/workers.py`
- `backend/storage/postgres.py`
- `backend/storage/clickhouse.py`
- `rules/process/proc_powershell_encoded.v2.yaml`
- `rules/network/net_suspicious_egress.v2.yaml`
- `tests/seed_frontend_qa.py`
- `tests/test_dns_lookup.py`
- `tests/test_storage_integration.py`
- `docs/operations/PERFORMANCE_IMPROVEMENTS_HISTORY.md`

제작 원칙:

- 구현하지 않은 기능을 발표 성과처럼 표현하지 않는다.
- 한 슬라이드에 핵심 메시지 하나만 둔다.
- 긴 기술 스택 목록보다 실제 데이터 흐름과 선택 이유를 보여준다.
- 실제 UI, Diagram, Before/After, 실측 수치를 장식용 이미지보다 우선한다.
- Screenshot은 메시지 전달에 필요할 때 사용하며, 사용 개수나 위치를 사전에 제한하지 않는다.
- 세부 시안보다 발표 방향과 기술적 정확성을 우선한다.

## 2. 확정된 전체 방향

### 2.1 브랜드

- 최종 서비스명은 `OWL`이다.
- 발표 전면에서는 `OWL`을 사용한다.
- `EDR_C`는 저장소나 내부 구현을 식별해야 할 때만 제한적으로 사용한다.
- Logo 방향은 단순화한 부엉이 눈 심볼과 `OWL` Wordmark의 조합이다.
- Logo는 보이지 않는 Endpoint 위협을 지속해서 관찰한다는 의미를 전달한다.
- 별도 표지 슬라이드에서 머무르지 않고 인트로 이후 `OWL`을 공개한다.

### 2.2 Visual concept

전체 콘셉트는 **Dark EDR Investigation**이다.

- 짙은 Navy 또는 Charcoal 계열을 기본 배경으로 사용한다.
- 실제 기업용 보안 관제 제품처럼 전문적이고 차분한 SOC Console 분위기를 만든다.
- 해커, 자물쇠, Matrix Code, 과도한 Neon Glow 같은 전형적인 보안 장식은 사용하지 않는다.
- 실제 Dashboard의 Dark UI와 PPT 사이에 시각적 단절이 없도록 한다.
- 화려함보다 관찰, 연결, 근거, 정확성을 시각적 키워드로 사용한다.

색상은 의미에 따라 제한적으로 사용한다.

- Event와 정상 데이터 흐름: Cyan 계열
- Alert와 주의 지점: Amber 계열
- Critical 또는 명확한 위험: Red 계열
- 본문과 보조 정보: White·Cool Gray 계열
- 정확한 Hex 값은 제작자가 접근성과 Dashboard 조화를 고려해 정한다.

### 2.3 정보량과 타이포그래피

- 한 슬라이드에 하나의 주장만 남긴다.
- 본문은 발표자가 읽는 대본이 아니라 화면을 보조하는 키워드와 근거 중심으로 작성한다.
- 핵심 수치는 크게 표시하되 측정 조건과 범위를 같은 화면에 남긴다.
- 설명 문장은 한국어로 작성한다.
- `Endpoint`, `Event`, `Alert`, `Incident`, `Evidence`, `Kafka`, `ClickHouse` 등 기술·도메인 용어는 영어를 유지한다.
- 글꼴은 장식성이 없는 현대적 Sans-serif 계열을 사용한다.
- Topic, Rule code, key, 수치처럼 기술 식별이 필요한 짧은 문자열에만 Monospace 계열을 보조적으로 사용할 수 있다.

### 2.4 Animation

- Animation은 데이터 흐름이나 Before/After 순서를 설명할 때만 사용한다.
- 일반 슬라이드 전환은 짧은 Fade를 기본으로 한다.
- 회전, 튕김, 과도한 Zoom, 반복 Glow처럼 메시지와 무관한 효과는 사용하지 않는다.
- Animation 없이도 정지 화면에서 의미가 유지되는 구조로 만든다.

## 3. 발표가 남겨야 하는 인상과 핵심 문장

목표 인상:

> 기술적으로 완성도가 높고, 문제와 해결 과정을 정확하게 설명하며, 구현 범위와 한계까지 검토한 팀

발표 전체의 핵심 메시지:

> 수많은 Endpoint Event를 빠르게 처리하면서도, 잘못된 공격 관계를 만들지 않는 EDR을 구현했다.

OWL 공식 소개 문장:

> OWL은 Windows와 macOS Endpoint의 행위를 수집하고, 탐지된 위협을 Alert와 Incident로 연결해 공격 흐름과 대응 근거를 제공하는 EDR 시스템입니다.

최종 문장:

> 저희는 단순히 위험을 경고하는 시스템이 아니라, 수많은 Endpoint Event를 빠르고 정확하게 연결해 무슨 일이 일어났는지 설명할 수 있는 EDR을 구현했습니다.

## 4. 8분 발표 흐름

본문은 7분 30초~7분 45초에 끝내고, 영상·브라우저 전환을 위해 약 15초를 남긴다.

| 구간 | 권장 시간 | 목적 |
| --- | ---: | --- |
| 인트로 영상 | 25초 | 보이지 않는 공격 상황으로 관심 유도 |
| EDR 개념 | 25초 | 비보안 청중도 이해할 수 있는 기준 제공 |
| OWL 소개 | 30초 | 프로젝트 범위와 `Event → Alert → Incident` 흐름 제시 |
| 라이브 데모 | 1분 40초 | 실제 조사 경험과 구현 결과 증명 |
| 전체 Architecture | 20초 | Endpoint부터 Dashboard까지 구현 범위 조망 |
| Kafka Pipeline | 50초 | 수집·저장·탐지 경계와 신뢰성 설명 |
| 저장소 역할 | 25초 | ClickHouse·PostgreSQL·S3 분리 이유 설명 |
| 성능 Troubleshooting | 1분 | 병목 원인과 실측 개선 설명 |
| 정확성 Troubleshooting | 1분 | 잘못된 공격 관계를 줄인 과정 설명 |
| 현재 범위·결론 | 1분 10초 | 한계를 밝히고 인트로와 핵심 메시지 회수 |

설명 순서는 다음을 유지한다.

```text
짧은 설명
→ 라이브 데모
→ 깊은 기술 설명
→ 성능과 정확성 검증
→ 현재 범위와 결론
```

라이브 데모는 별도 콘텐츠 슬라이드가 아니라 실제 Dashboard로 전환한다. 전체 슬라이드 수는 전환 화면 포함 약 9~10장을 목표로 한다.

## 5. 구간별 제작 요구

아래 요구는 각 화면의 역할과 반드시 전달할 내용을 정의한다. 구체적인 Layout 시안은 제작자가 전체 톤 안에서 결정한다.

### 5.1 인트로 영상

목적:

> 화면에는 변화가 없어도 Endpoint 내부에서는 조사해야 할 행위가 발생할 수 있다는 문제를 제시한다.

필수 흐름:

```text
출처가 불분명한 가상 게임 설치 파일 다운로드
→ 파일 실행
→ 겉으로는 별다른 변화가 없음
→ Encoded PowerShell 실행
→ 암호화된 외부 통신
→ “이 컴퓨터에서는 무슨 일이 일어난 걸까요?”
```

필수 조건:

- 20~25초 안에 끝낸다.
- 별도 표지 없이 영상으로 발표를 시작한다.
- Dashboard는 영상에서 미리 보여주지 않는다.
- 실제 게임, 불법 사이트, 악성코드 브랜드를 사용하지 않는다.
- 실제 팀원의 과거 경험이라고 주장하지 않는다.
- 화면 한쪽에 `시연을 위해 재구성한 가상 시나리오`를 표시한다.
- 마지막 질문 이후 발표자가 말을 시작하고 OWL을 공개한다.

보류 사항:

- 인트로 영상의 구체적인 그래픽 스타일은 현재 확정하지 않는다.
- 제작자는 위 흐름과 안전 조건을 지키는 범위에서 스타일을 제안할 수 있다.

### 5.2 EDR 개념

목적:

> EDR을 처음 듣는 청중도 이후 데모를 이해할 수 있게 한다.

핵심 대비:

```text
단일 경고
vs
Event → Alert → Incident → Evidence
```

전달 방향:

- 위험을 한 줄로 알리는 것과 무슨 일이 있었는지 관계를 설명하는 것의 차이에 집중한다.
- 현대 백신과 EDR은 기능이 겹칠 수 있으므로 절대적으로 양분하지 않는다.
- `백신은 파일만 보고 EDR은 행위만 본다`와 같은 표현은 사용하지 않는다.
- EDR의 지속 관찰·탐지·조사·대응 근거 제공 역할만 짧게 설명한다.

### 5.3 OWL 소개

목적:

> OWL의 입력, 탐지, 조사 결과를 한눈에 이해시킨다.

필수 문장:

> OWL은 Windows와 macOS Endpoint의 행위를 수집하고, 탐지된 위협을 Alert와 Incident로 연결해 공격 흐름과 대응 근거를 제공하는 EDR 시스템입니다.

필수 흐름:

```text
Windows·macOS Endpoint
→ Process·Network·File·DNS·L7 Event
→ RuleV1 + MITRE ATT&CK
→ Alert·Incident
→ Dashboard Investigation
```

표현 범위:

- 이 구간에서 `OWL` Logo와 Wordmark를 처음 명확하게 보여준다.
- Kafka, ClickHouse, PostgreSQL의 상세 설명은 넣지 않는다.
- 기술 목록보다 사용자가 보는 입력과 결과를 보여준다.

### 5.4 라이브 데모

목적:

> 분석가가 실제 Dashboard에서 공격 관계와 근거를 조사하는 경험을 보여준다.

권장 동선:

```text
Overview
→ Incident 목록
→ Incident 상세
→ Investigation Graph
→ Alert 상세
→ MITRE ATT&CK·Response Guidance
```

발표 방향:

- Demo에서는 Kafka Topic, offset, DB query를 설명하지 않는다.
- 조작보다 `Incident → Alert → Event → Process → Destination` 관계와 Evidence에 집중한다.
- Demo가 끝난 뒤에만 내부 Architecture와 Kafka를 설명한다.
- 발표 중 새 Event 수집이나 Kafka 완료를 기다리지 않고 검증된 목데이터를 미리 준비한다.
- Screenshot은 필요에 따라 사용할 수 있으며, 본문·전환·백업 중 어느 용도로 쓸지는 제작 단계에서 결정한다.

반드시 지킬 사실:

- 동일 Incident의 Alert 3개는 같은 Endpoint와 같은 `powershell-tls-egress-chain`, 같은 30분 고정 bucket을 사용한다.
- PowerShell Alert 2개와 TLS SNI 기반 Egress Alert 1개가 Rule v2 설정에 따라 하나의 Incident를 공유한다고 설명한다.
- 이 시간 기반 correlation을 PowerShell Process와 TLS 통신의 인과관계 증명으로 과장하지 않는다.

### 5.5 전체 Architecture

목적:

> 모든 기술을 설명하는 것이 아니라 Endpoint부터 Dashboard까지 구현한 전체 범위를 보여준다.

핵심 흐름:

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

Archive 흐름:

```text
ClickHouse
→ Storage Lifecycle Worker
→ Parquet/ZSTD
→ Amazon S3
```

필수 표현:

- Windows Agent는 C++20, macOS Agent는 Swift로 표현한다.
- Endpoint에서 Nginx까지 `HTTPS + mTLS`를 표시한다.
- `telemetry.raw`와 `telemetry.validated`를 구분한다.
- Event Storage Worker, Detection Worker, Storage Lifecycle Worker의 역할을 분리한다.
- Collector와 Dashboard API는 하나의 FastAPI Backend 안의 논리 모듈로 표현한다.
- 운영 Frontend는 Vercel, 로컬 Frontend는 Docker라는 경계를 혼동하지 않는다.
- Monitoring·CI/CD는 핵심 Event 흐름보다 낮은 우선순위로 분리한다.

제외:

- Kafka Table Engine
- 현재 구현과 다른 Python Endpoint Agent
- 핵심 흐름을 가리는 AWS·Library Logo 나열
- 모든 연결을 동일한 중요도로 보이게 하는 복잡한 선

### 5.6 Kafka Pipeline

목적:

> Collector 요청과 저장·탐지를 분리한 이유와 at-least-once 환경의 신뢰성 설계를 설명한다.

Architecture와 합치지 않고 별도 구간으로 제작한다.

필수 흐름:

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

필수 Callout:

- `Broker ACK`: Collector 요청과 후속 처리의 경계
- `endpointId key`: 같은 Endpoint Event를 같은 partition으로 routing
- `at-least-once + idempotency`: 재처리 시 논리적 중복 방지

설명할 사실:

- Collector는 Kafka Broker ACK를 받은 Event만 `acceptedEventIds`로 반환한다.
- Broker ACK는 ClickHouse 저장이나 Detection 완료를 뜻하지 않는다.
- Consumer auto commit은 비활성화되어 있고 처리 결과에 따라 수동 commit한다.
- Event는 동일 identity·payload에 대해 논리적 중복을 만들지 않는다.
- Alert는 `(event_id, rule_code, rule_version)`으로 멱등 생성한다.
- Producer idempotence를 활성화한다.
- Worker는 설정된 partition 수 범위에서 독립적으로 확장할 수 있다.

금지:

- exactly-once 보장
- 자동 또는 무한 Scaling 구현
- 현재 로컬 구성을 고가용성 Kafka Cluster로 표현
- 로컬 기본값 2를 production 고정값이나 고가용성 근거로 표현

### 5.7 저장소 역할

목적:

> 데이터 성격에 따라 저장소를 나눈 이유를 짧게 설명한다.

| 저장소 | 역할 |
| --- | --- |
| ClickHouse | 대량 Event 저장, 기간 검색, 집계 |
| PostgreSQL | 사용자·Endpoint·Alert·Incident·감사 로그의 상태와 Transaction |
| Amazon S3 | 오래된 Event Archive와 실패 원문 |

핵심 문장:

> 대량 Event의 기간 검색과 집계는 ClickHouse에, 상태 변경과 정합성이 중요한 Alert와 Incident는 PostgreSQL에 저장했습니다.

다음 연결 문장:

> 하지만 ClickHouse를 사용한다고 자동으로 빠른 것은 아니었습니다.

### 5.8 성능 Troubleshooting

제목 방향:

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
→ 필요한 Column만 Projection
→ 집계 결과만 전달
```

가운데 핵심 문구:

> 연산 위치를 Application에서 Database로 이동

반드시 표시할 수치:

- LATEST_24H: `16.31초 → 0.584초`
- 응답 크기: `약 135KB → 약 7KB`
- 지연 감소: `96.42%`
- 속도 향상: `27.93배`

같은 화면에 표시할 측정 조건:

> 31일 · 100 Endpoint · 248,000 Event 목데이터 환경의 동일 API 변경 전·후 측정

금지:

- Production Benchmark라고 표현
- P50·P95·P99 측정 결과라고 표현
- Dashboard가 항상 0.584초라고 표현
- Query 수 `9 → 2`를 Wall-clock 4.5배 개선으로 표현
- 남아 있는 `FINAL`, `ARRAY JOIN`, Archive Scan 비용을 모두 해결했다고 표현

### 5.9 정확성 Troubleshooting

제목 방향:

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

- Domain 앞뒤 공백 제거와 소문자 정규화
- 마지막 `.` 제거
- Exact match 허용
- `.` 경계를 가진 실제 Subdomain만 허용
- DNS Answer를 JSON 배열의 Exact membership으로 비교
- Endpoint filter를 ClickHouse Query로 Pushdown

핵심 문장:

> 보안 시스템에서는 많이 찾는 것보다, 왜 연결됐는지 설명할 수 있는 정확성이 중요했습니다.

표현 범위:

- 이 사례는 성능이 아니라 Correctness 개선으로 설명한다.
- Wall-clock 개선 수치를 만들지 않는다.
- `notyahoo.com`, `yahoo.com.evil.example`이 제외되는 테스트 근거를 사용한다.

### 5.10 현재 범위와 결론

목적:

> 인트로의 질문에 답하고, 구현된 범위와 남은 범위를 구분한 뒤 발표 메시지를 회수한다.

권장 흐름:

```text
Event 관찰
→ Rule 기반 Alert
→ Endpoint·correlation key·window 기준 Incident
→ Evidence와 Response Guidance
```

반드시 밝힐 현재 한계:

- Response Guidance는 분석가를 위한 읽기 전용·수동 조치 안내다.
- 자동 격리, 원격 Process 종료, File 삭제는 구현하지 않았다.
- cross-rule correlation은 명시적으로 같은 key/window를 공유하는 좁은 시간 기반 묶음만 구현했다.
- Npcap·tcpdump에서 Metadata를 추출하지만 원본 PCAP은 저장하지 않는다.

인트로의 시각 Motif를 다시 사용해 처음의 질문에 답한다. 마지막에는 다음 문장을 그대로 사용한다.

> 저희는 단순히 위험을 경고하는 시스템이 아니라, 수많은 Endpoint Event를 빠르고 정확하게 연결해 무슨 일이 일어났는지 설명할 수 있는 EDR을 구현했습니다.

## 6. 기술적 사실 관계와 금지 표현

### 6.1 Correlation과 presentation fixture

현재 RuleV1:

- `PROC_POWERSHELL_ENCODED`: `correlation_key: powershell-tls-egress-chain`, `window_seconds: 1800`
- TLS SNI 기반 `NET_SUSPICIOUS_EGRESS`: `correlation_key: powershell-tls-egress-chain`, `window_seconds: 1800`

현재 Incident UPSERT 기준:

```text
(endpoint_id, correlation_key, window_start_at)
```

따라서 두 Rule의 Alert는 같은 Endpoint와 같은 30분 고정 bucket에서 하나의 Incident를 공유한다. presentation profile은 PowerShell Alert 2개와 TLS SNI Egress Alert 1개, 총 3개를 이 경로로 연결한다.

발표에서 다중 Alert Incident를 보여줄 때 사실 기반 시나리오:

```text
같은 Endpoint
→ 같은 30분 고정 bucket의 Encoded PowerShell Event 두 건
→ 같은 bucket의 TLS ClientHello SNI Event 한 건
→ PowerShell Alert 두 개와 TLS SNI Egress Alert 한 개
→ 같은 powershell-tls-egress-chain Incident에 연결
```

이 연결은 시간 근접성을 조사 단서로 제공하며 Process와 TLS 통신의 인과관계를 증명하지 않는다.

### 6.2 Kafka partition 기준

- `backend/kafka.py`: 기본값 2
- `compose.yaml`: 기본값 2
- `docs/architecture/TECH_STACK.md`: 기본값 2

PPT에서 수치가 필요하면 로컬 기본값 2라고 표현한다. Worker 확장성은 다음 범위로 제한한다.

> 설정된 Kafka partition 수 범위에서 Worker를 독립적으로 확장할 수 있습니다.

### 6.3 허용·금지 표현 요약

| 주제 | 사용 가능한 표현 | 사용하지 않을 표현 |
| --- | --- | --- |
| Kafka ACK | Broker가 Event를 수락한 경계 | 저장·탐지까지 완료됨 |
| 전달 보장 | at-least-once와 멱등성 | exactly-once 보장 |
| Worker | partition 범위에서 독립 확장 | 자동·무한 Scaling |
| Local Kafka | 개발·시연용 로컬 구성 | 고가용성 Cluster |
| Incident | 명시적으로 같은 Endpoint·key·fixed window의 Alert 연결 | Process와 통신의 인과관계 증명 |
| Presentation fixture | Rule v2의 3 Alert·1 Incident 검증 결과 | 과거 fixture나 영상의 결과를 현재 실행처럼 표현 |
| 성능 | 목데이터 동일 API 전후 측정 | Production P95/P99 |
| DNS | Domain boundary 기반 Correctness 개선 | 성능 수치 개선 |
| Response | 분석가용 Guidance | 자동 격리·종료·삭제 |

## 7. 제작자가 자유롭게 결정할 수 있는 범위

다음은 본 요구서가 고정하지 않는 제작 영역이다.

- 각 슬라이드의 세부 Grid와 요소 위치
- 필요에 따른 Dashboard Screenshot 사용 여부와 Crop 범위
- Architecture와 Kafka Diagram의 구체적인 도형 스타일
- Owl Eye Symbol의 세부 형태
- 정확한 Color Hex와 Font Family
- 인트로 영상의 구체적인 그래픽 스타일
- 의미를 해치지 않는 범위의 Icon 선택

다음 항목은 정보가 제공되기 전까지 발표자 종속 요소를 넣지 않는다.

- 발표자 수와 교대 지점
- 행사장 영상·음향·인터넷 조건
- 최종 제작 마감일

## 8. 납품 전 검수 체크리스트

### 형식과 디자인

- [ ] 최종 파일이 `.pptx`인가
- [ ] 화면 비율이 16:9인가
- [ ] 서비스명이 `OWL`로 통일됐는가
- [ ] Dark EDR Investigation과 차분한 SOC Console 분위기를 유지하는가
- [ ] 과도한 Neon·해커·자물쇠 장식을 제거했는가
- [ ] 한 슬라이드에 핵심 메시지가 하나인가
- [ ] Animation이 데이터 흐름 설명에만 제한됐는가

### 내용

- [ ] 별도 표지 없이 인트로로 시작하는가
- [ ] 인트로에 가상 시나리오 문구가 있는가
- [ ] EDR을 단일 경고와 관계 설명의 차이로 전달하는가
- [ ] OWL 공식 소개 문장을 사용했는가
- [ ] Demo에서는 사용자 조사 경험에 집중하는가
- [ ] Architecture와 Kafka 상세가 분리됐는가
- [ ] 성능 수치와 목데이터 조건이 같은 화면에 있는가
- [ ] DNS 개선을 Correctness로 표현하는가
- [ ] 현재 한계가 결론에 포함됐는가

### 기술 정확성

- [ ] PowerShell Alert 2개와 TLS SNI Egress Alert 1개가 같은 key·고정 bucket으로 연결됐는가
- [ ] 시간 기반 correlation을 Process와 통신의 인과관계로 과장하지 않았는가
- [ ] Kafka partition 개수를 표시한다면 현재 로컬 기본값 2와 일치하는가
- [ ] exactly-once, 자동 Scaling, 고가용성 Cluster를 주장하지 않았는가
- [ ] Broker ACK를 저장·탐지 완료로 설명하지 않았는가
- [ ] 성능 수치를 Production Benchmark로 표현하지 않았는가
- [ ] Response Guidance를 자동 대응 기능으로 표현하지 않았는가

### 시간

- [ ] 본문이 7분 30초~7분 45초 안에 끝나는가
- [ ] Intro 25초, Demo 1분 40초, Kafka 50초, 두 Troubleshooting 각 1분 범위를 지키는가
- [ ] 영상과 브라우저 전환을 위한 약 15초의 여유가 있는가

## 9. PPT 제작자에게 보낼 복사·붙여넣기용 메시지

```text
안녕하세요. OWL 8분 최종 발표용 PPT 제작을 요청드립니다.

작업 전 아래 요구서를 처음부터 끝까지 확인해 주세요.

- docs/presentation/PPT_REQUIREMENTS.md
- 참고 기획: docs/presentation/PRESENTATION_PLAN.md

최종 납품 형식은 .pptx이며 화면 비율은 16:9입니다. 별도 표지에서 머무르지 않고 인트로 영상으로 바로 시작한 뒤 OWL을 공개하는 흐름입니다.

전체 Visual concept은 Dark EDR Investigation입니다. 짙은 Navy·Charcoal 기반의 전문적이고 차분한 SOC Console 분위기로 제작해 주세요. Event는 Cyan, Alert는 Amber, Critical은 Red 계열을 제한적으로 사용하고, 과도한 Neon 효과나 해커·자물쇠 같은 일반적인 보안 장식은 사용하지 말아 주세요.

한 슬라이드에는 핵심 메시지 하나만 두고, 실제 UI·Diagram·Before/After·실측 수치를 우선해 주세요. 설명 문장은 한국어로 작성하되 Endpoint, Event, Alert, Incident, Kafka, ClickHouse 같은 기술 용어는 영어를 유지해 주세요. Screenshot은 메시지 전달에 필요하면 자유롭게 사용할 수 있습니다.

발표 흐름은 인트로 → EDR 개념 → OWL 소개 → 라이브 데모 → 전체 Architecture → Kafka Pipeline → 저장소 역할 → 성능 Troubleshooting → 정확성 Troubleshooting → 현재 범위와 결론입니다. 라이브 데모는 실제 Dashboard로 전환하므로 별도의 일반 콘텐츠 슬라이드로 만들지 않습니다. Architecture와 Kafka 상세는 반드시 분리해 주세요.

기술적 사실 관계는 요구서의 '기술적 사실 관계와 금지 표현'을 반드시 지켜 주세요. 특히 다음 내용을 주의해 주세요.

1. PowerShell과 TLS SNI egress Rule은 `powershell-tls-egress-chain`과 1,800초 window를 공유해 같은 Endpoint·고정 bucket에서 하나의 Incident를 만듭니다.
2. 이 관계는 시간 기반 correlation이며 Process와 통신의 인과관계 증명으로 표현하지 않습니다.
3. Kafka partition 기본값은 코드·Compose·TECH_STACK 모두 2입니다.
4. 성능 수치는 31일·100 Endpoint·248,000 Event 목데이터 환경의 동일 API 전후 측정이며 Production Benchmark가 아닙니다.
5. Response Guidance는 읽기 전용·수동 조치 안내이며 자동 격리·프로세스 종료·파일 삭제 기능이 아닙니다.

이 문서는 세부 시안이 아니라 제작 방향과 사실 관계를 고정하는 요구서입니다. 각 슬라이드의 세부 배치, Screenshot Crop, Diagram 도형 스타일과 정확한 색상값은 전체 방향을 해치지 않는 범위에서 판단해 주세요. 구현되지 않은 기능이나 측정하지 않은 수치를 추가하지 말아 주세요.
```
