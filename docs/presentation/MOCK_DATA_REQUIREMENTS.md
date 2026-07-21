# EDR_C 발표용 목데이터 요구사항

- 작성일: 2026-07-21
- 대상 저장소: `C:\Users\geonh\Desktop\team-C`
- 문서 목적: 발표 시연·성능 개선·정확성 개선을 재현할 목데이터의 구현 요구사항 정의
- 현재 상태: 요구사항만 확정하며, 이 문서 작성 단계에서는 seed 코드를 구현하지 않음

## 1. 목표

목데이터는 다음 세 가지 발표 근거를 각각 재현할 수 있어야 한다.

1. 인트로의 가상 공격 시나리오를 Dashboard에서 조사하는 라이브 시연
2. Python 집계를 ClickHouse 집계로 옮긴 성능 개선의 데이터 규모
3. IP·Domain 상관분석에서 부분 문자열로 발생하던 오탐 제거

하나의 거대한 seed로 모든 목적을 해결하지 않는다. 용도별 데이터 규모와 실행 시간이 다르므로 세 개의 profile로 분리한다.

| Profile | 목적 | 예상 규모 | 발표 중 사용 방식 |
| --- | --- | ---: | --- |
| `presentation` | 라이브 Dashboard 조사 | 3 Endpoint, 64 Event, 3 Alert, 2 Incident | 발표 직전 seed 후 직접 조작 |
| `dns-correctness` | Domain 경계 오탐 검증 | 2 Endpoint, 8 Event 내외 | Screenshot 또는 짧은 녹화 |
| `performance` | ClickHouse Dashboard 집계 규모 재현 | 31일, 100 Endpoint, 248,000 생성 Event | 사전 측정 결과와 그래프 사용 |

`performance` profile은 실행 시간이 길고 다른 데이터를 초기화하므로 발표 직전에 실행하지 않는다.

## 2. 구현 코드 기준 source of truth

목데이터 구현자는 다음 파일을 먼저 확인한다.

- `backend/workers.py`
- `backend/detection.py`
- `backend/kafka.py`
- `backend/storage/postgres.py`
- `backend/storage/clickhouse.py`
- `rules/process/proc_powershell_encoded.v1.yaml`
- `rules/network/net_suspicious_egress.v1.yaml`
- `tests/seed_frontend_qa.py`
- `tools/seed_dashboard_long_range.py`
- `tests/test_dns_lookup.py`
- `docs/operations/PERFORMANCE_IMPROVEMENTS_HISTORY.md`

문서와 코드가 다르면 현재 구현 코드를 기준으로 한다.

## 3. 공통 필수 요구사항

### 3.1 재현성

- 동일한 `--seed`와 `--anchor`를 사용하면 Event 내용과 관계가 동일해야 한다.
- Event ID와 Batch ID는 임의 `uuid4` 대신 namespace가 분리된 deterministic UUID를 사용한다.
- 목록 정렬이 바뀌지 않도록 Event 발생 시각과 ID의 순서를 고정한다.
- 라이브 발표에서는 `--anchor now`, 녹화에서는 고정 RFC 3339 시각을 사용할 수 있어야 한다.
- `--anchor now`를 사용한 데이터는 `LATEST_24H` 범위에서 항상 보여야 한다.

### 3.2 안전한 초기화

- PostgreSQL과 ClickHouse를 초기화하는 실행은 반드시 `--confirm-reset`이 있어야 한다.
- `--dry-run`은 DB를 변경하지 않고 생성될 row 수와 시간 범위를 출력해야 한다.
- local 또는 QA 환경이 아니면 실행을 거부해야 한다.
- production DSN, 원격 production host 또는 실제 사용자 DB에는 실행할 수 없어야 한다.
- 실행 전 대상 DB host·database·예상 삭제 범위를 출력한다.

### 3.3 반복 실행

- 같은 profile을 다시 실행해도 중복 Event, Alert, Incident가 생기지 않아야 한다.
- 실패 후 다시 실행해도 이전의 절반짜리 데이터가 남지 않아야 한다.
- 가능하면 profile별 namespace를 사용해 어떤 데이터가 seed에서 만들어졌는지 식별할 수 있어야 한다.

### 3.4 현재 규칙과의 정합성

- Alert와 Incident는 현재 RuleV1 설정으로 설명 가능한 결과여야 한다.
- 서로 다른 `correlation_key`의 Alert를 같은 Incident에 수동 연결하지 않는다.
- `PROC_POWERSHELL_ENCODED`와 `NET_SUSPICIOUS_EGRESS`는 각각 `suspicious-powershell`, `suspicious-egress`를 사용하므로 별도 Incident가 되어야 한다.
- 하나의 PowerShell Incident에 복수 Alert가 필요하면 같은 Endpoint의 Encoded PowerShell Event를 같은 30분 window 안에 2회 생성한다.
- 발표용 핵심 Alert·Incident는 `tests/seed_frontend_qa.py`의 수동 SQL 연결을 그대로 복사하지 않는다.

### 3.5 표시용 데이터와 운영 상태의 분리

- Event·Alert·Incident·Endpoint inventory는 seed할 수 있다.
- Kafka consumer lag, Worker heartbeat, Backend readiness 등 운영 상태는 실제 runtime 값을 사용한다.
- 실행되지 않은 Worker를 목데이터로 `HEALTHY`처럼 보이게 만들지 않는다.
- 직접 DB에 넣은 데이터는 “Kafka를 실시간 통과한 Event”라고 설명하지 않는다.

### 3.6 개인정보와 보안

- 실제 팀원 이름, 실제 어린 시절 정보, 실제 가정용 IP를 사용하지 않는다.
- Hostname과 사용자명에는 `DEMO`, `STUDENT` 등 가상 데이터임을 식별할 수 있는 값을 사용한다.
- 실제 악성코드, 실행 가능한 payload, 실제 불법 다운로드 링크를 포함하지 않는다.
- IP는 문서용 대역인 `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`를 사용한다.
- 일반 시연 Domain은 `.test` 또는 `example` 계열을 사용한다.

## 4. `presentation` profile

### 4.1 목적

인트로 영상 이후 Dashboard에서 다음 흐름을 자연스럽게 보여준다.

```text
가상 게임 설치 파일 실행
→ Encoded PowerShell 실행 Event
→ Rule이 Alert 생성
→ 같은 Endpoint·Rule·30분 window의 Alert가 하나의 Incident로 묶임
→ 분석가가 Incident에서 Alert와 원본 Event를 조사
```

시스템이 “불법 다운로드 자체”를 탐지했다고 설명하면 안 된다. 탐지 대상은 다운로드 이후 발생한 Encoded PowerShell 실행과 의심스러운 외부 통신이다.

### 4.2 사용자 계정

로컬 발표 환경에서는 기존 QA 계정을 유지한다.

| Role | Login ID | Password | 용도 |
| --- | --- | --- | --- |
| ADMIN | `frontend-admin` | `frontend-admin-password` | 발표 시연 |
| VIEWER | `frontend-viewer` | `frontend-viewer-password` | 권한 화면 확인이 필요할 때만 사용 |

이 값은 local/QA 전용이며 production credential로 사용하지 않는다.

### 4.3 Endpoint inventory

정확히 3개의 Endpoint를 만든다.

| Endpoint | OS·상태 | 역할 | 예상 화면 상태 |
| --- | --- | --- | --- |
| `DEMO-STUDENT-WIN-07` | Windows 11, ONLINE | 메인 공격 시나리오 | 가장 높은 Risk, 3 active Alerts, 2 open Incidents |
| `DEMO-DEV-WIN-02` | Windows 11, ONLINE | 정상 비교군과 Domain 검증 | Risk 낮음, active Alert 없음 |
| `DEMO-FINANCE-MAC-02` | macOS, OFFLINE | OS·상태 다양성 | 최근 Event는 있으나 active Alert 없음 |

Endpoint ID를 코드에 하드코딩해 발표자가 추측하게 하지 않는다. 실행 결과 manifest에 실제 ID를 기록한다.

### 4.4 Event 총량과 분포

`presentation` profile의 예상 결과는 다음과 같다.

- Endpoint: 3
- Event: 정확히 64
- Alert: 정확히 3
- Incident: 정확히 2
- `DEMO-STUDENT-WIN-07`: Event 24
- `DEMO-DEV-WIN-02`: Event 24
- `DEMO-FINANCE-MAC-02`: Event 16

64개 Event에는 `PROCESS_EXECUTION`, `NETWORK_CONNECTION`, `FILE_EVENT`, `DNS_QUERY`, `L7_EVENT`가 모두 포함되어야 한다. 메인 공격 Event를 제외한 배경 Event는 활성 Rule에 우연히 걸리지 않는 값으로 만든다.

### 4.5 메인 공격 Timeline

두 Encoded PowerShell Event가 30분 경계 양쪽으로 갈라지지 않도록, 먼저 하나의 완성된 correlation window를 선택한 뒤 그 안에 시각을 배치한다.

| 순서 | 상대 시각 | Event | 핵심 값 | 예상 탐지 결과 |
| ---: | ---: | --- | --- | --- |
| 1 | window + 5분 | DNS Query | `game-mirror.test` | Alert 없음 |
| 2 | window + 7분 | File Create | `C:\Users\student\Downloads\game-installer.exe` | Alert 없음 |
| 3 | window + 9분 | Process Execution | `game-installer.exe` | Alert 없음 |
| 4 | window + 10분 | Process Execution | `powershell.exe -EncodedCommand <safe-demo-value>` | HIGH Alert 1 |
| 5 | window + 12분 | Process Execution | 같은 PID 계열의 두 번째 Encoded PowerShell | HIGH Alert 2 |
| 6 | window + 14분 | Network Connection | `update-cache.test:443`, `203.0.113.88` | CRITICAL Alert 3 |

`<safe-demo-value>`는 실행 목적이 없는 고정 문자열이어야 한다. Rule은 `-EncodedCommand` 포함 여부를 판단하므로 실제 공격 payload는 필요하지 않다.

### 4.6 예상 Alert와 Incident

| 구분 | Rule | Severity | 관계 |
| --- | --- | --- | --- |
| Alert 1 | `PROC_POWERSHELL_ENCODED` | HIGH | PowerShell Incident에 연결 |
| Alert 2 | `PROC_POWERSHELL_ENCODED` | HIGH | 같은 PowerShell Incident에 연결 |
| Alert 3 | `NET_SUSPICIOUS_EGRESS` | CRITICAL | Egress Incident에 연결 |
| Incident 1 | `suspicious-powershell` | HIGH | Alert 1·2, `alert_count=2` |
| Incident 2 | `suspicious-egress` | CRITICAL | Alert 3, `alert_count=1` |

발표 시 “PowerShell과 외부 통신이 한 Incident로 자동 결합됐다”고 말하지 않는다. 오히려 서로 다른 상관 키를 함부로 합치지 않는 현재 동작을 정확하게 유지한다.

### 4.7 시연 화면별 데이터 조건

#### Overview

- `LATEST_24H`에서 64 Event, 3 Alert, 2 open Incident가 보여야 한다.
- `DEMO-STUDENT-WIN-07`이 Highest-risk Endpoint 첫 번째에 보여야 한다.
- Event type과 시간대별 차트가 비어 있지 않아야 한다.
- 최근 Incident 목록에서 두 Incident를 찾을 수 있어야 한다.

#### Endpoint Detail

- 메인 Endpoint에 3 active Alert와 2 open Incident가 보여야 한다.
- 최근 Event에 DNS → File → Process → PowerShell → Network 흐름이 시간순으로 확인되어야 한다.
- Sensor health는 표현 다양성을 위해 정상과 일부 저하 상태를 포함할 수 있지만, 실제 Worker health와 혼동되는 문구를 쓰지 않는다.

#### Incident Detail

- PowerShell Incident에는 정확히 2개의 연결 Alert가 보여야 한다.
- 두 Alert의 Event는 동일 Endpoint, 동일 correlation window여야 한다.
- Alert Detail에서 원본 Process Event와 `commandLine`, PID, PPID, 사용자명을 확인할 수 있어야 한다.

#### Intelligence

- 별도의 `dns-correctness` fixture를 함께 seed한 경우 Domain 경계 검증이 가능해야 한다.
- Live DNS 결과와 `OBSERVED_EVENTS` 결과를 화면에서 구분한다.

#### Operations

- 이 profile이 Worker health나 Kafka lag를 조작하지 않는다.
- Operations 화면을 발표에 넣으려면 실제 서비스 상태를 별도로 사전 점검한다.

### 4.8 배경 Event 조건

- 정상 Process 예시: `chrome.exe`, `explorer.exe`, `code.exe`, `python.exe`, macOS의 `launchd`.
- 정상 Domain 예시: `docs.example.test`, `cdn.example.test`, `updates.example.test`.
- `update-cache`, `rare-beacon`, `api.corp`, `artifact-`, `payload-` 등 활성 Rule에 걸리는 문자열을 배경 데이터에 넣지 않는다.
- L7의 POST·PUT과 `update-cache` 또는 `storage.` 조합을 피한다.
- Severity, Alert, Incident는 임의로 분포시키지 않고 위 3개 Alert와 2개 Incident만 생성한다.

## 5. `dns-correctness` profile

### 5.1 목적

Domain 검색을 단순 부분 문자열로 처리할 때 관련 없는 Domain까지 포함되던 문제를 재현하고, exact·subdomain boundary 방식으로 오탐이 제거됐음을 증명한다.

현재 regression test의 기준 입력은 `yahoo.com`이다. 구현 검증은 이 기준을 유지한다.

### 5.2 필수 Event 행

다음 값을 서로 다른 Event field에 분산해 넣는다.

| 값 | Field 예시 | 예상 결과 |
| --- | --- | --- |
| `yahoo.com` | `remote_domain` | 포함: exact match |
| `mail.yahoo.com` | `http_host` | 포함: subdomain |
| `api.yahoo.com` | `dns_query` | 포함: subdomain |
| `notyahoo.com` | `tls_sni` | 제외 |
| `yahoo.com.evil.example` | `http_host` | 제외 |
| `yahoo.co` | `remote_domain` | 제외 |

DNS answer에는 문서용 IP를 사용하고, JSON 배열 멤버십도 검증할 수 있게 한다.

```json
["203.0.113.10", "203.0.113.11"]
```

문자열 `"203.0.113.1"`이 위 배열에 부분 문자열로 존재한다는 이유로 match되면 안 된다.

### 5.3 기대 결과

`yahoo.com`을 대상으로 상관분석했을 때 다음을 만족한다.

- `yahoo.com`, `mail.yahoo.com`, `api.yahoo.com`에서 관측된 관계만 포함한다.
- `notyahoo.com`, `yahoo.com.evil.example`, `yahoo.co`는 결과에 포함하지 않는다.
- exact Domain과 subdomain은 각각 구분 가능해야 한다.
- Endpoint filter를 지정하면 해당 Endpoint의 관측값만 반환한다.
- DNS answer IP는 JSON array member가 정확히 같은 경우만 포함한다.
- 외부 Live DNS 응답이 추가되더라도 `OBSERVED_EVENTS` 기반 기대값은 변하지 않아야 한다.

### 5.4 발표 표현

Before는 부분 문자열 비교의 개념적 결과로 보여주고, After는 실제 코드·테스트 결과로 보여준다.

```text
Before: yahoo.com이 문자열 안에 있으면 포함
After: yahoo.com과 *.yahoo.com만 포함
```

성능 개선 수치로 표현하지 않는다. 이 항목의 핵심은 정확성과 오탐 제거다.

## 6. `performance` profile

### 6.1 기존 생성기 사용

현재 구현된 `tools/seed_dashboard_long_range.py`를 우선 사용한다.

Dry run:

```powershell
uv run python tools/seed_dashboard_long_range.py --days 31 --endpoints 100 --events-per-endpoint-day 80 --seed 20260715 --dry-run
```

실행:

```powershell
uv run python tools/seed_dashboard_long_range.py --days 31 --endpoints 100 --events-per-endpoint-day 80 --seed 20260715 --confirm-reset
```

계산상 생성 Event 수는 다음과 같다.

```text
31일 × 100 Endpoint × Endpoint당 하루 80 Event = 248,000 Event
```

### 6.2 총 Event 수 검증 주의사항

현재 long-range 생성기는 먼저 `tests/seed_frontend_qa.py`의 base fixture를 실행한 뒤 248,000개의 장기 Event를 추가한다. 따라서 콘솔의 `Events added: 248,000`은 생성기가 추가한 수이며, DB 전체 row 수가 반드시 248,000이라는 뜻은 아니다.

성능을 다시 측정할 때는 반드시 다음 중 하나를 선택하고 기록한다.

1. 측정 query의 시간·namespace 범위를 장기 생성 Event로 제한한다.
2. base fixture를 제외한 성능 전용 초기화 경로를 만든다.
3. 실제 API 범위의 Event count를 측정 기록에 함께 적는다.

발표에서는 기존 상세 실행 기록의 조건인 `31일·100 Endpoint·248,000 Event 목데이터 환경`을 사용하되, 새로 측정한 것처럼 말하지 않는다.

### 6.3 기존 발표 수치

| 항목 | 변경 전 | 변경 후 | 해석 |
| --- | ---: | ---: | --- |
| LATEST_24H | 16.31초 | 0.584초 | 지연 96.42% 감소, 27.93배 |
| 24시간 응답 크기 | 약 135KB | 약 7KB | 94.81% 감소 |

- 위 수치는 production benchmark가 아니다.
- `9 query → 2 query`는 DB round trip 변화이며 wall-clock 4.5배 개선을 뜻하지 않는다.
- 새 측정값이 다르면 기존 기록을 덮어쓰지 말고 환경·commit·측정 시각과 함께 별도 기록한다.

### 6.4 재측정 시 기록할 항목

- Git commit SHA
- OS, CPU, RAM
- Docker와 DB resource limit
- ClickHouse·PostgreSQL version
- 측정 API와 query parameter
- 실제 측정 범위의 Event count
- cold run과 warm run 구분
- 반복 횟수
- P50·P95·P99 또는 최소한 모든 raw timing
- response byte

한 번의 가장 빠른 결과만 선택하지 않는다.

## 7. Seed 실행 인터페이스 요구사항

신규 발표용 seed의 권장 인터페이스는 다음과 같다.

```powershell
uv run python tools/seed_presentation_demo.py --profile presentation --seed 20260721 --anchor now --dry-run
uv run python tools/seed_presentation_demo.py --profile presentation --seed 20260721 --anchor now --confirm-reset
uv run python tools/seed_presentation_demo.py --profile dns-correctness --seed 20260721 --anchor now --confirm-reset
```

필수 option:

- `--profile presentation|dns-correctness`
- `--seed <int>`
- `--anchor now|<RFC3339>`
- `--dry-run`
- `--confirm-reset`

선택 option:

- `--output-manifest <path>`
- `--emit-through-collector`
- `--wait-timeout-seconds <int>`

`--emit-through-collector`는 Collector·Kafka·Worker가 실제 실행 중일 때만 사용한다. 기본 seed가 repository를 통해 직접 적재한다면, 실행 결과에 `ingestionMode=direct-seed`를 명시한다.

## 8. 생성 결과 manifest

seed가 끝나면 다음과 같은 파일을 생성한다.

권장 경로:

```text
runtime/demo/presentation-manifest.json
```

필수 필드:

```json
{
  "profile": "presentation",
  "seed": 20260721,
  "anchor": "RFC3339 timestamp",
  "ingestionMode": "direct-seed or collector-kafka",
  "timeRange": {
    "from": "RFC3339 timestamp",
    "to": "RFC3339 timestamp"
  },
  "counts": {
    "endpoints": 3,
    "events": 64,
    "alerts": 3,
    "incidents": 2
  },
  "ids": {
    "presentationEndpointId": 0,
    "powershellIncidentId": 0,
    "egressIncidentId": 0,
    "powershellAlertIds": [],
    "egressAlertId": 0
  },
  "urls": {
    "overview": "http://127.0.0.1:8080/...",
    "endpointDetail": "http://127.0.0.1:8080/endpoints/...",
    "powershellIncident": "http://127.0.0.1:8080/incidents/...",
    "egressAlert": "http://127.0.0.1:8080/alerts/..."
  }
}
```

manifest에는 실제 production secret을 기록하지 않는다.

## 9. 직접 seed와 실제 Pipeline 주입의 구분

### Direct seed

- 발표 전 빠르게 동일 상태를 복원하기 위한 기본 방식이다.
- Event는 ClickHouse, Endpoint·Alert·Incident는 PostgreSQL에 repository를 통해 적재할 수 있다.
- Alert·Incident 생성은 현재 Rule과 Detection logic을 재사용해야 한다.
- 직접 SQL로 서로 다른 Rule의 Alert 관계를 조작하지 않는다.
- 발표에서는 이 실행 자체를 Kafka 처리 증거로 사용하지 않는다.

### Collector·Kafka injection

- Kafka 흐름을 실제로 보여줘야 할 때만 사용하는 선택 방식이다.
- Collector가 broker ACK를 받은 Event ID와, Worker 처리 후 ClickHouse·PostgreSQL에 나타난 ID를 분리해 확인한다.
- accepted response를 Detection 완료로 해석하지 않는다.
- timeout 안에 예상 Event·Alert·Incident가 모두 조회되는지 poll하고 결과를 manifest에 기록한다.
- 실패 시 라이브 발표를 중단시키지 않도록 녹화 영상 fallback을 준비한다.

## 10. 검증 요구사항

### 자동 검증

최소한 다음을 test로 고정한다.

- `presentation` dry-run count가 3·64·3·2인지 확인
- deterministic seed에서 ID와 Timeline이 반복 실행마다 같은지 확인
- 두 PowerShell Alert가 하나의 `suspicious-powershell` Incident에 연결되는지 확인
- Egress Alert가 별도 `suspicious-egress` Incident에 연결되는지 확인
- 61개의 비탐지 Event가 추가 Alert를 만들지 않는지 확인
- `notyahoo.com`과 `yahoo.com.evil.example`이 `yahoo.com` 결과에서 제외되는지 확인
- DNS answer JSON array가 exact membership으로 처리되는지 확인
- Endpoint filter가 DB query까지 전달되는지 확인
- local/QA가 아닌 환경에서 seed가 거부되는지 확인
- `--confirm-reset` 없이 변경이 발생하지 않는지 확인

### API 검증

seed 후 다음 API 또는 대응 service 결과를 검증한다.

- Dashboard summary count
- Endpoint list와 Endpoint detail risk count
- Alert list와 Alert detail
- Incident list, Incident detail, 연결 Alert 수
- Event list와 Event detail
- Domain correlation 결과

### 화면 검증

- 1920×1080 기준 화면 잘림이 없어야 한다.
- 발표자가 클릭할 대상이 첫 화면 또는 명확한 filter 결과에 있어야 한다.
- 데이터가 너무 많아 메인 Incident를 찾기 어렵지 않아야 한다.
- time preset을 `LATEST_24H`로 바꿔도 핵심 Event가 사라지지 않아야 한다.
- 한글·영문 혼용으로 제목이 잘리지 않는지 확인한다.

## 11. 발표·녹화 운영 요구사항

- 라이브 발표 하루 전과 발표 직전에 같은 명령으로 seed해본다.
- 영상 녹화는 고정 `--anchor`를 사용해 목록 순서와 숫자를 유지한다.
- 라이브 시연은 `--anchor now`를 사용해 “최근 Event”로 보이게 한다.
- 영상과 라이브 화면의 ID가 달라도 발표 대본은 manifest의 이름을 기준으로 작성한다.
- 인터넷 장애에 대비해 Intro, 라이브 Dashboard 시연, DNS 정확성 화면을 각각 별도 영상으로 준비할 수 있다.
- 화면 녹화에는 비밀번호 입력 장면과 local credential 파일을 노출하지 않는다.

## 12. 구현 산출물

목데이터 구현 담당자는 최소 다음을 제공한다.

1. `tools/seed_presentation_demo.py`
2. `tools/verify_presentation_demo.py`
3. 발표 seed 자동 test
4. `runtime/demo/presentation-manifest.json` 생성 기능
5. 실행·복구 방법을 적은 짧은 runbook
6. presentation과 performance profile의 destructive reset 경고
7. 발표자가 사용할 정확한 로그인 정보, URL, 클릭 순서

기존 `tools/seed_dashboard_long_range.py`는 성능 profile에 재사용하되, base fixture가 추가하는 Event와 실제 측정 범위를 검증한다.

## 13. 완료 기준

다음 조건을 모두 충족해야 발표용 목데이터가 준비된 것으로 본다.

- 한 명령으로 presentation profile을 재생성할 수 있다.
- Overview에서 64 Event·3 Alert·2 Incident가 확인된다.
- PowerShell Incident에 같은 Rule의 Alert 2개가 연결된다.
- Egress Alert는 별도 Incident로 존재한다.
- 메인 Endpoint에서 전체 Timeline을 클릭해 조사할 수 있다.
- Domain exact·subdomain만 포함되고 두 대표 오탐 Domain은 제외된다.
- 248,000 생성 Event 성능 profile의 dry-run과 실행 방법이 검증된다.
- seed 경로와 실제 Kafka Pipeline 경로를 발표자가 구분해 설명할 수 있다.
- 목데이터임을 숨기거나 production 실측처럼 표현하는 문장이 없다.
- 라이브 시연 실패 시 사용할 녹화 영상이 준비된다.

## 14. 구현 담당자에게 보낼 요구 메시지

```text
EDR_C 최종 발표용 목데이터를 만들어 주세요.

먼저 docs/presentation/MOCK_DATA_REQUIREMENTS.md를 전체 확인하고, 현재 구현 코드를 source of truth로 사용해 주세요.

핵심 요구사항은 다음과 같습니다.

1. presentation profile: 3 Endpoint, 64 Event, 3 Alert, 2 Incident
2. 같은 Endpoint의 Encoded PowerShell Event 2개를 같은 30분 window에 넣어 하나의 suspicious-powershell Incident로 연결
3. NET_SUSPICIOUS_EGRESS Alert는 correlation_key가 다르므로 별도 suspicious-egress Incident로 생성
4. 서로 다른 Rule의 Alert를 SQL로 한 Incident에 수동 연결하지 않기
5. dns-correctness profile에서 yahoo.com exact·subdomain은 포함하고 notyahoo.com, yahoo.com.evil.example은 제외
6. --dry-run, --confirm-reset, --seed, --anchor 지원
7. 실행 후 Endpoint·Alert·Incident ID와 발표용 URL이 담긴 manifest 생성
8. local/QA가 아니면 destructive seed 실행 거부
9. 직접 seed와 Collector·Kafka를 통한 실제 주입 모드를 명확히 구분
10. 기존 tools/seed_dashboard_long_range.py의 31일·100 Endpoint·하루 80 Event 조건도 검증

구현 후에는 자동 test, API 검증 결과, 실제 생성 count, 발표자가 사용할 실행 명령과 클릭 순서를 함께 알려주세요.
```
