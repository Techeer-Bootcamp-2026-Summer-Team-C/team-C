# EDR_C 8분 최종 발표대본

- 작성일: 2026-07-21
- 기준 시간: 본문 7분 45초 + 전환 여유 15초
- 기본 발표자 구성: 1인 발표
- 기준 문서: `PRESENTATION_PLAN.md`, `MOCK_DATA_REQUIREMENTS.md`
- 사실 기준: 현재 구현 코드

## 1. 사용 전 확인

이 대본은 현재 구현과 발표용 목데이터 요구사항을 기준으로 작성했다. 다만 `tools/seed_presentation_demo.py`는 아직 요구사항 단계이므로 실제 발표 전 다음 항목을 반드시 확인한다.

- `presentation` profile이 실제로 구현되어 있는가
- PowerShell Incident에 `PROC_POWERSHELL_ENCODED` Alert 2개만 연결되는가
- `NET_SUSPICIOUS_EGRESS` Alert는 별도 Incident로 생성되는가
- 발표자가 클릭할 Endpoint·Incident·Alert ID가 manifest와 일치하는가
- Architecture 이미지에서 `Kafka Table Engine`이 제거되고 두 Worker가 반영됐는가
- Kafka partition 수를 특정 숫자로 말하지 않도록 PPT와 대본이 일치하는가

목데이터가 아직 구현되지 않았다면 이 대본의 시연 구간은 “예정 시나리오”일 뿐이다. 기존 `tests/seed_frontend_qa.py` 화면으로 서로 다른 Rule의 Alert가 자동으로 하나의 Incident가 됐다고 설명하면 안 된다.

## 2. 발표 전체 시간표

| 누적 시간 | 구간 | 시간 | 화면 |
| ---: | --- | ---: | --- |
| 0:00~0:25 | 인트로 | 25초 | 가상 시나리오 영상 |
| 0:25~0:50 | EDR 소개 | 25초 | 슬라이드 2 |
| 0:50~1:20 | EDR_C 소개 | 30초 | 슬라이드 3 |
| 1:20~3:00 | 라이브 시연 | 1분 40초 | Dashboard |
| 3:00~3:20 | 전체 아키텍처 | 20초 | 슬라이드 5 |
| 3:20~4:10 | Kafka Pipeline | 50초 | 슬라이드 6 |
| 4:10~4:35 | 저장소 역할 | 25초 | 슬라이드 7 |
| 4:35~5:35 | 성능 트러블슈팅 | 1분 | 슬라이드 8 |
| 5:35~6:35 | 정확성 트러블슈팅 | 1분 | 슬라이드 9 |
| 6:35~7:15 | 구현 범위와 한계 | 40초 | 슬라이드 10 전반 |
| 7:15~7:45 | 인트로 회수와 결론 | 30초 | 슬라이드 10 후반 |
| 7:45~8:00 | 전환 여유 | 15초 | 종료 화면 |

## 3. 전체 발표대본

### 0:00~0:25 — 인트로 영상

화면:

- 초등학생 시절 느낌의 컴퓨터 화면
- 가상의 무료 게임 다운로드 페이지
- 출처가 불명확한 설치 파일 실행
- 화면에는 변화가 없지만 Encoded PowerShell과 외부 통신이 발생하는 연출
- 마지막 문구: `이 컴퓨터에서는 무슨 일이 일어난 걸까요?`
- 하단 고정 문구: `시연을 위해 재구성한 가상 시나리오`

발표자:

- 영상이 끝날 때까지 말하지 않는다.
- 마지막 질문 화면이 정지되면 슬라이드 2로 전환한다.

영상 실패 시 대체 멘트:

> 한 학생이 출처를 알 수 없는 게임 설치 파일을 실행했습니다. 화면에는 아무 변화가 없었지만, 백그라운드에서는 인코딩된 PowerShell 명령과 외부 통신이 발생했습니다. 이 컴퓨터에서는 무슨 일이 일어난 걸까요?

### 0:25~0:50 — EDR 소개

화면:

- 슬라이드 2 `EDR이란?`
- Endpoint에서 발생하는 행위가 시간순으로 쌓이고 조사로 이어지는 단순한 그림

대사:

> 화면에 드러나지 않는 행위를 지속해서 관찰하는 시스템이 EDR입니다. PC 같은 Endpoint의 행위를 수집하고 위협을 탐지·조사·대응합니다. 백신이 악성 파일 차단에 주로 집중했다면, EDR은 공격 전후의 행위를 연결해 무슨 일이 있었는지 파악하는 데 초점을 둡니다.

강조:

- `파일 하나의 위험 여부`보다 `공격 전후의 행위와 근거`
- 백신과 EDR이 완전히 배타적이라고 말하지 않는다.

### 0:50~1:20 — 프로젝트 소개

화면:

- 슬라이드 3 `EDR_C`
- `Event → Alert → Incident → Investigation`
- Windows·macOS와 다섯 Event type을 간단한 아이콘으로 표시

대사:

> EDR_C는 Windows와 macOS에서 프로세스, 네트워크, 파일, DNS, L7 Event를 수집합니다. RuleV1으로 위협을 탐지해 Alert를 만들고, 같은 Endpoint·correlation key·시간 구간의 Alert를 Incident로 연결합니다. 이제 방금 영상의 상황을 실제 화면에서 보겠습니다.

전환:

- 마지막 문장에서 브라우저로 전환한다.
- 로그인과 `LATEST_24H` 선택은 발표 전에 끝내 둔다.

### 1:20~3:00 — 라이브 시연

#### 1:20~1:35 — Overview

조작:

- Overview가 열린 상태에서 Event·Alert·Incident 카드와 Highest-risk Endpoint를 짧게 가리킨다.
- 숫자를 하나씩 읽지 않는다.

대사:

> 영상의 행위가 Event로 수집돼 Dashboard에 반영됐습니다. 이 Endpoint가 가장 높은 Risk를 보이고, 탐지된 Alert와 Incident가 함께 나타납니다.

조작:

- `Incidents` 메뉴로 이동한다.

#### 1:35~1:50 — Incident 목록

조작:

- `Encoded PowerShell command detected` Incident를 선택한다.

대사:

> 분석가는 원본 Event를 처음부터 모두 읽는 대신, 우선순위가 높은 Incident부터 조사합니다. Encoded PowerShell Incident를 열어보겠습니다.

#### 1:50~2:20 — Incident 상세

조작:

- Endpoint, Severity, 탐지 시간과 연결 Alert 수를 가리킨다.
- 연결된 PowerShell Alert 2개가 보이도록 이동한다.

대사:

> 같은 Endpoint에서 30분 안에 반복된 Encoded PowerShell 탐지는 각각 Alert로 남습니다. 하지만 `suspicious-powershell` correlation key와 window가 같아 하나의 Incident에서 함께 조사할 수 있습니다.

주의:

- 화면에 `NET_SUSPICIOUS_EGRESS` Alert가 같은 Incident 안에 보이면 현재 fixture가 잘못된 것이다. 발표 전에 수정한다.

#### 2:20~2:50 — Alert·Event 근거

조작:

- 연결 Alert 하나를 연다.
- 원본 Event 또는 Evidence 영역에서 `powershell.exe`, `-EncodedCommand`, PID·PPID를 가리킨다.
- 가능하면 Investigation Graph에서 Incident → Alert → Event → Process 관계를 가리킨다.

대사:

> Alert를 열면 원본 Event 근거를 확인할 수 있습니다. 여기서는 `powershell.exe`의 command line에 `-EncodedCommand`가 있고, PID와 부모 Process도 남아 있습니다. 단순한 경고가 아니라 탐지 이유를 역추적할 수 있습니다.

#### 2:50~3:00 — 외부 통신 구분

조작:

- 별도 Egress Incident 또는 Alert가 있음을 짧게 가리키고 PPT로 전환한다.

대사:

> 의심스러운 외부 통신도 탐지했지만, correlation key가 다르므로 PowerShell과 억지로 합치지 않고 별도 Incident로 유지합니다.

시연 실패 시 전환 멘트:

> 라이브 화면 전환 대신 동일한 목데이터로 미리 녹화한 조사 흐름을 보여드리겠습니다.

녹화 영상을 재생한 뒤 같은 대사를 이어간다.

### 3:00~3:20 — 전체 아키텍처

화면:

- 슬라이드 5 전체 아키텍처
- Endpoint부터 Dashboard까지 한 방향으로 강조 애니메이션

대사:

> 저희는 Windows와 macOS Agent부터 mTLS 수집, Kafka, 두 Worker, 저장소와 Dashboard까지 전체 흐름을 구현했습니다. 이 중 핵심인 Kafka 처리 과정을 확대해 보겠습니다.

주의:

- Architecture에 `Kafka Table Engine`이 남아 있으면 이 슬라이드를 사용하지 않는다.
- FastAPI Collector와 Dashboard API를 완전히 별도 서비스라고 말하지 않는다.

### 3:20~4:10 — Kafka Pipeline

화면:

- 슬라이드 6
- `Collector → telemetry.raw → Event Storage Worker → ClickHouse → telemetry.validated → Detection Worker → PostgreSQL`

대사:

> Kafka를 사용한 핵심 이유는 수집 요청과 저장·탐지를 분리하기 위해서입니다. Collector는 Event를 `telemetry.raw`에 넣고 broker가 수락하면 응답합니다. 이 ACK는 저장이나 탐지 완료를 뜻하지 않습니다. Storage Worker가 검증과 ClickHouse 저장을 마친 뒤 `telemetry.validated`로 넘기고, Detection Worker가 Rule을 평가합니다. Consumer는 성공 후 offset을 수동 commit합니다. 재전달 가능한 at-least-once 구조이므로, Event와 Alert를 멱등 처리해 논리적 중복을 막았습니다.

강조:

- 화면에서 `ACK ≠ Detection complete`를 크게 표시한다.
- 특정 partition 개수를 말하지 않는다.
- 시간이 남으면 다음 한 문장만 추가한다.

> 같은 Endpoint ID를 key로 사용해 partition 내부의 Event 순서를 유지하고, 설정된 partition 수 범위에서 Worker를 독립적으로 확장할 수 있습니다.

### 4:10~4:35 — ClickHouse·PostgreSQL 역할 분리

화면:

- 슬라이드 7
- ClickHouse와 PostgreSQL을 좌우 비교
- S3 Archive는 하단에 작게 표시

대사:

> 대량 Event의 기간 검색과 집계는 ClickHouse가 담당합니다. 상태 변경과 관계 무결성이 중요한 Alert와 Incident는 PostgreSQL에 저장하고, 오래된 Event는 S3로 Archive합니다. 하지만 ClickHouse를 선택했다고 자동으로 빨라지는 것은 아니었습니다.

전환:

- 마지막 문장에서 성능 Before 화면을 표시한다.

### 4:35~5:35 — 트러블슈팅 1: Dashboard 집계 성능

화면:

- 슬라이드 8 제목: `ClickHouse를 사용했는데 왜 16초가 걸렸을까?`
- Before/After와 핵심 수치

대사:

> 초기에는 ClickHouse의 Event를 500건씩 가져오고, 불필요한 raw payload까지 전송한 뒤 Python에서 다시 집계했습니다. Event가 늘수록 DB 왕복과 전송량, 애플리케이션 연산이 함께 증가했습니다.
>
> 해결은 연산 위치를 바꾸는 것이었습니다. 집계를 ClickHouse에서 수행하고 필요한 column과 결과만 전달했습니다. 31일·100 Endpoint·248,000 Event 목데이터에서 24시간 조회는 16.31초에서 0.584초로 96.42% 감소했고, 응답은 약 135KB에서 7KB로 줄었습니다.
>
> 빠른 Database보다 데이터를 어디에서 계산할지가 중요했습니다.

주의:

- production 수치라고 말하지 않는다.
- `9 query → 2 query`를 4.5배 wall-clock 개선이라고 말하지 않는다.
- 슬라이드 하단에 `목데이터 환경 측정`을 표시한다.

### 5:35~6:35 — 트러블슈팅 2: IP·Domain 상관분석 정확성

화면:

- 슬라이드 9 제목: `검색 결과가 많으면 좋은 상관분석일까?`
- `yahoo.com` 입력에 대한 포함·제외 사례

대사:

> 두 번째 문제는 정확성이었습니다. 부분 문자열로 상관분석하면 `yahoo.com`을 조회할 때 `notyahoo.com`이나 `yahoo.com.evil.example`까지 포함됩니다. 이런 오탐은 존재하지 않는 공격 관계를 만들 수 있습니다.
>
> 그래서 일반 검색과 상관분석 조건을 분리했습니다. 상관분석은 정확히 같은 Domain이나 점 경계를 가진 실제 Subdomain만 허용합니다. DNS Answer도 `Array(String)`으로 추출해 `has()`로 정확한 원소를 비교하고, Endpoint filter는 ClickHouse까지 내려보냈습니다.
>
> 보안에서는 많이 찾는 것보다 왜 연결됐는지 설명할 수 있어야 합니다.

강조:

- `yahoo.com`, `mail.yahoo.com`: 포함
- `notyahoo.com`, `yahoo.com.evil.example`: 제외
- 이 항목을 성능 개선으로 표현하지 않는다.

### 6:35~7:15 — 현재 구현 범위와 한계

화면:

- 슬라이드 10 전반
- `Implemented`와 `Next`를 두 영역으로 표시

대사:

> 현재는 Windows와 macOS의 metadata 수집부터 Alert·Incident 조사까지 구현했습니다. 수집 구간은 mTLS로 인증하고, 원본 PCAP은 저장하지 않습니다. 대응은 분석가용 Guidance까지 제공하며 원격 격리나 Process 종료를 자동 실행하지 않습니다. 자동 대응과 cross-rule correlation은 근거와 정책을 보강한 뒤 확장할 범위입니다.

의도:

- 구현하지 않은 기능을 숨기는 시간이 아니다.
- 현재 범위를 스스로 통제한 설계 판단으로 설명한다.

### 7:15~7:45 — 인트로 회수와 결론

화면:

- 처음의 게임 설치 화면을 흐리게 다시 표시
- 그 위에 `Event → Alert → Incident → Investigation`

대사:

> 처음 영상에는 Encoded PowerShell과 외부 통신이라는 두 신호가 남았습니다. EDR_C는 이를 빠르게 처리하면서도 근거가 다른 관계를 억지로 합치지 않고, 각 Alert와 원본 Event를 확인하게 합니다.
>
> 저희는 위험을 경고하는 데서 끝나지 않고, Endpoint Event를 빠르고 정확하게 연결해 무슨 일이 있었는지 설명하는 EDR을 구현했습니다. 감사합니다.

종료:

- 마지막 문장 후 1초 정지한다.
- `Q&A` 또는 팀 Logo 화면으로 전환한다.

## 4. 발표자용 초단기 큐시트

발표자가 긴 대본 대신 무대 옆에서 볼 수 있는 버전이다.

| 시간 | 키워드 | 반드시 말할 내용 |
| ---: | --- | --- |
| 0:00 | 영상 | 가상 시나리오 표기, 질문에서 정지 |
| 0:25 | EDR | 지속 관찰, 공격 전후 행위와 근거 |
| 0:50 | EDR_C | 5 Event type, RuleV1, Event→Alert→Incident |
| 1:20 | Demo | Overview→PowerShell Incident→Alert→Event |
| 2:50 | 분리 | Egress는 별도 correlation key·Incident |
| 3:00 | Architecture | Endpoint부터 Dashboard까지 구현 |
| 3:20 | Kafka | 비동기 분리, ACK 경계, 두 Topic, 수동 commit, 멱등성 |
| 4:10 | DB | Event=ClickHouse, 상태·관계=PostgreSQL, Archive=S3 |
| 4:35 | 성능 | Python 전체 집계→ClickHouse 집계, 16.31→0.584초 |
| 5:35 | 정확성 | 부분 문자열 오탐→Domain boundary·JSON exact membership |
| 6:35 | 범위 | metadata-only, no PCAP, Guidance only, no auto response |
| 7:15 | 결론 | 빠르고 정확하게, 무슨 일이 있었는지 설명 |

## 5. 시간 초과 시 줄이는 순서

### 15초 초과

- Demo의 Overview 숫자 설명을 생략한다.
- Architecture에서 기술 이름을 하나씩 읽지 않고 “전체 흐름을 구현했습니다”만 말한다.

### 30초 초과

- Investigation Graph 조작을 생략하고 Alert Detail의 command line만 보여준다.
- 저장소 설명의 S3 Archive 문장을 생략한다.

### 45초 이상 초과

- 현재 범위에서 Agent 언어와 Event type 나열을 생략한다.
- 다음 축약 문장만 사용한다.

> 현재는 metadata 수집부터 탐지와 조사, Response Guidance까지 구현했으며 자동 원격 대응은 다음 범위입니다.

성능 수치, Domain 오탐의 핵심 예시, 최종 문장은 줄이지 않는다.

## 6. 다인 발표 시 권장 분담

발표자가 여러 명이면 슬라이드마다 교대하지 않고 의미 단위로 나눈다.

| 담당 | 구간 | 교대 문장 |
| --- | --- | --- |
| 발표자 A | 인트로·EDR·EDR_C | `이제 방금 영상의 상황을 실제 화면에서 보겠습니다.` |
| 발표자 B | 라이브 시연 | `이 결과가 내부에서 어떻게 만들어졌는지 설명드리겠습니다.` |
| 발표자 C | Architecture·Kafka·DB | `하지만 ClickHouse를 선택했다고 자동으로 빨라지는 것은 아니었습니다.` |
| 발표자 D | 두 트러블슈팅·범위·결론 | 마지막까지 진행 |

2인 발표라면 A가 인트로부터 시연까지, B가 Architecture부터 결론까지 담당한다.

## 7. 예상 Q&A 답변

### 왜 Kafka가 꼭 필요한가요?

> Collector의 응답과 저장·탐지 지연을 분리하기 위해 사용했습니다. `telemetry.raw`와 `telemetry.validated` 경계를 두어 저장·검증 이후 Detection이 실행되도록 했습니다.

### Kafka ACK를 받으면 탐지가 끝난 건가요?

> 아닙니다. Collector의 ACK는 broker가 Event를 수락했다는 의미입니다. ClickHouse 저장과 Detection은 Worker가 비동기로 처리합니다.

### 메시지가 중복 전달되면 어떻게 하나요?

> Consumer는 성공 후 offset을 수동 commit하고, 재전달 가능성을 전제로 Event ID와 Alert의 유일성을 이용해 멱등 처리합니다. exactly-once라고 주장하지 않습니다.

### PowerShell과 외부 통신을 왜 하나의 Incident로 합치지 않았나요?

> 현재 Incident key는 Endpoint, Rule의 correlation key, time window입니다. 두 Rule은 correlation key가 다르므로 별도 Incident가 됩니다. Cross-rule correlation은 잘못된 관계를 만들지 않도록 추가 근거와 정책을 설계한 뒤 확장할 범위입니다.

### 왜 DB를 두 개 사용했나요?

> 대량 append Event의 검색·집계와, 상태 변경·관계 무결성이 중요한 Alert·Incident의 workload가 다르기 때문입니다. 전자는 ClickHouse, 후자는 PostgreSQL에 맡겼습니다.

### 0.584초는 운영 환경에서도 보장되나요?

> 아닙니다. 31일·100 Endpoint·248,000 Event 목데이터 환경의 기록입니다. 운영 성능으로 일반화하려면 별도의 P50·P95·P99 측정이 필요합니다.

### 원본 Packet도 저장하나요?

> 원본 Packet이나 PCAP은 저장하지 않습니다. Agent가 DNS·HTTP·TLS 등 분석에 필요한 metadata를 추출하고 원본은 폐기합니다.

### 자동으로 Endpoint를 격리할 수 있나요?

> 현재는 분석가가 검토할 수 있는 read-only Response Guidance를 제공합니다. 원격 격리, Process 종료, 파일 삭제는 현재 구현 범위가 아닙니다.

### 인트로는 실제 팀원의 경험인가요?

> 시연을 위해 재구성한 가상 시나리오입니다. 실제 악성코드를 실행한 것이 아니라 검증된 목데이터로 조사 흐름을 재현했습니다.

## 8. 최종 리허설 체크

- [ ] 영상 포함 본문이 7분 45초 안에 끝남
- [ ] 영상에 `시연을 위해 재구성한 가상 시나리오`가 보임
- [ ] Dashboard가 로그인된 상태로 `LATEST_24H`에 열려 있음
- [ ] PowerShell Incident에 PowerShell Alert 2개만 연결됨
- [ ] Egress Alert가 별도 Incident임
- [ ] manifest의 URL과 화면 ID가 일치함
- [ ] Architecture 이미지가 현재 Worker·Topic 흐름과 일치함
- [ ] Kafka ACK와 Detection 완료를 구분해 말함
- [ ] 특정 Kafka partition 수를 말하지 않음
- [ ] 성능 슬라이드에 `목데이터 환경` 표기가 있음
- [ ] Domain 포함·제외 사례가 화면과 일치함
- [ ] 영상·시연 녹화본·PDF가 발표 PC에 로컬 저장됨
- [ ] 인터넷 없이도 전체 발표가 가능함
