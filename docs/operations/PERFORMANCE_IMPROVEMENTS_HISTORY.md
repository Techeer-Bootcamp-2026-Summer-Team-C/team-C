# 전체 Git 이력 기반 성능 개선 보고서

작성일: 2026-07-20
대상 저장소: `team-C`
분석 범위: 모든 로컬/원격 ref에서 도달 가능한 62개 커밋(일반 커밋 42개, 병합 커밋 20개), 2026-07-13~2026-07-20
제외 범위: 사용자의 요청에 따라 모바일 레이아웃·터치 상호작용·모바일 실기기 성능은 평가하지 않았다.

## 1. 결론

가장 큰 실측 개선은 Dashboard summary 집계를 Python의 전체 Event 반복 조회에서 ClickHouse 집계로 옮긴 작업이다. 31일·100 Endpoint·248,000 Event 목데이터 환경에서 다음 결과가 기록되어 있다.

| 조회 범위 | 변경 전 | 변경 후 | 지연 감소 | 속도 향상 |
|---|---:|---:|---:|---:|
| LATEST_15M | 3.84초 | 0.385초 | 89.97% | 9.97배 |
| LATEST_24H | 16.31초 | 0.584초 | 96.42% | 27.93배 |
| LATEST_7D | 20초 초과 | 0.722초 | 96.39% 초과 | 27.70배 초과 |
| 24시간 응답 크기 | 약 135KB | 약 7KB | 94.81% | 19.29배 작음 |

상세 실행 기록에는 dataset이 `31일·100 Endpoint·248,000 Event`로 남아 있다. 별도의 축약 색인 한 줄에는 `31 endpoints`라고 잘못 요약된 흔적이 있어, 이 문서는 더 구체적인 상세 실행 기록을 기준으로 했다. latency와 payload 값은 두 기록에서 동일하다.

이후 추가 정리에서 Dashboard의 HOT ClickHouse 집계 쿼리 수를 9개에서 2개로 줄였다. 이는 DB 왕복 횟수 기준 77.78% 감소, 4.5배 감소다. 다만 이 수치는 쿼리 수의 변화이며, 2개 쿼리의 실제 wall-clock 시간이 4.5배 개선됐다는 뜻은 아니다.

그 외에는 대량 목록의 서버 측 pagination, 조사 화면의 N+1 제거, S3/Parquet streaming, Agent batch 조립, SQLite prepared statement 재사용, Route/ECharts lazy loading, font dynamic subset 적용에서 큰 구조적 개선이 있었다.

## 2. 수치 해석 기준

이 문서는 효과를 다음 네 단계로 구분한다.

- **실측**: 동일한 API 경로의 변경 전/후 시간이 실제로 기록된 값이다.
- **확정 연산량**: 코드와 테스트로 쿼리 수, prepare 횟수, 최대 처리 건수 등이 결정되는 값이다.
- **복잡도 개선**: `O(N²) → O(N)`처럼 데이터가 커질수록 차이가 커지는 구조적 개선이다.
- **기대 효과**: lazy loading, index, chunk 분리처럼 방향은 명확하지만 이 저장소에서 전후 wall-clock을 측정하지 않은 항목이다.

서로 다른 항목의 비율은 합산하지 않았다. 예를 들어 Dashboard 27.93배와 쿼리 수 4.5배를 곱해 전체 개선치로 표현하지 않는다.

## 3. Dashboard와 Summary API

### 3.1 Python 전체 집계 제거 — `b8864d4`

문제:

- `SummaryService._event_items`가 Event를 500건씩 반복 조회했다.
- ClickHouse에서 `raw_payload`를 포함한 전체 Event row를 애플리케이션으로 가져왔다.
- total, event type, time bucket, Top Process/IP/Domain/File Hash/DNS/L7을 Python에서 다시 집계했다.
- latest ingest 시각도 전체 기간 ingest summary 경로를 사용했다.
- Event 수가 늘수록 ClickHouse 왕복, 전송량, Python object 생성 및 집계 비용이 함께 증가했다.

수정:

- `backend/storage/clickhouse.py`에 Dashboard 전용 `dashboard_summary` 집계를 추가했다.
- total, event type, 시간 bucket, 여섯 Top dimension을 ClickHouse `GROUP BY`, `ORDER BY`, `LIMIT 10`으로 계산했다.
- `backend/event_service.py`에서 HOT ClickHouse 집계와 RESTORED S3 Event를 합치되 기존 archive readiness 규칙은 유지했다.
- `backend/summary_service.py`에서 원본 Event page loop를 제거했다.
- latest ingest는 `maxOrNull(ingested_at)` 전용 쿼리로 변경했다.

효과:

- 위 표의 API latency 및 payload 실측 결과를 얻었다.
- 애플리케이션으로 전송되는 값이 전체 Event row에서 집계 결과로 바뀌었다.
- N건의 Event를 Python에 적재·순회하던 경로가 HOT 데이터 기준 소수의 aggregate row를 받는 경로로 바뀌었다.
- `raw_payload`가 Dashboard query projection에서 제거된 사실은 테스트로 고정되어 있다.

검증 근거:

- 핵심 집계/복원 테스트 8개 통과 기록
- 전체 Ruff와 pytest 통과 기록
- Backend container healthy 확인 기록
- `tests/test_dashboard_event_aggregation.py`

### 3.2 ClickHouse 집계 9 query → 2 query — `00e0e45`

문제:

- 최초 서버 집계 구현은 total 1개, event type 1개, time series 1개, Top dimension 6개로 HOT ClickHouse query가 총 9개였다.
- 동일한 기간과 Endpoint 조건으로 반복적인 DB 왕복이 발생했다.

수정:

- event type과 time bucket을 하나의 activity query로 합치고, 이 결과의 합으로 total도 계산했다.
- 여섯 Top dimension은 tuple 배열과 `ARRAY JOIN`, `LIMIT 10 BY target`을 사용해 한 query로 합쳤다.

효과:

- HOT ClickHouse query: **9개 → 2개**
- DB round trip: **7개 감소, 77.78% 감소, 4.5배 감소**
- `tests/test_dashboard_event_aggregation.py`가 `len(client.queries) == 2`를 검증한다.

주의:

- dimension query는 각 Event를 내부적으로 여섯 dimension 후보로 펼친다. 따라서 round trip 감소와 DB CPU 감소를 동일하게 보아서는 안 된다.
- RESTORED S3 병합이 필요한 요청은 별도의 archive scan 비용이 추가된다.

### 3.3 중복 Storage summary 제거 — `00e0e45`

문제:

- Dashboard summary가 `_storage_summary`를 계산한 뒤 `_edr_state` 내부에서 다시 같은 summary를 조회했다.

수정:

- 이미 계산한 `storage_summary`를 `_edr_state`에 전달했다.

효과:

- 한 Dashboard 요청의 Storage summary 호출: **2회 → 1회, 50% 감소**
- 동일한 집계 결과를 다시 만드는 DB/애플리케이션 작업을 제거했다.

### 3.4 Alert·Incident·Failure·Storage summary의 DB 집계 — `77b80c3`

문제:

- 여러 summary가 모든 Alert, Incident, Failure, ingest metadata row를 읽어 Python에서 상태별·심각도별·시간별 count를 계산했다.

수정:

- 각 repository에 DB-side `summary()` 집계를 추가했다.
- Dashboard와 Endpoint/Ingest summary가 grouped count를 직접 사용하도록 변경했다.
- Endpoint summary는 최대 10,000 Endpoint guard를 추가했다.

효과:

- 전송·Python 순회량이 원본 N row에서 category/time-bucket 수에 비례하는 aggregate row로 축소됐다.
- 10,000 Endpoint를 초과하는 무제한 summary 계산을 명시적으로 차단했다.
- wall-clock 전후 값은 별도로 기록되지 않았다.

## 4. 목록 조회와 조사 워크플로우

### 4.1 목록의 서버 측 pagination — `77b80c3`

공통 문제는 DB에서 모든 검색 결과를 가져온 뒤 Python에서 정렬·filter·slice하던 것이었다. 변경 후 API page size는 최대 500건이며, 대부분의 HOT 경로는 DB `LIMIT/OFFSET`과 별도 count를 사용한다.

| 경로 | 변경 전 | 변경 후 | 확정 효과 |
|---|---|---|---|
| Event HOT 목록 | 검색 결과 전체 전송 후 Python slice | ClickHouse `LIMIT/OFFSET` + `count_search` | 전송 row `N → P`, `P ≤ 500` |
| Failure 목록 | 현재 Failure 전체 전송 | ClickHouse `LIMIT/OFFSET` + `count_current` | 전송 row `N → P` |
| Alert 목록 | PostgreSQL 전체 결과 전송 | SQL `LIMIT/OFFSET` + `count_rows` | 전송 row `N → P` |
| Incident 목록 | PostgreSQL 전체 결과 전송 | SQL `LIMIT/OFFSET` + `count_rows` | 전송 row `N → P` |
| Endpoint 목록 | 전체 risk snapshot 후 Python 검색·정렬·slice | `risk_page`, SQL filter/sort, `COUNT(*) OVER()`, `LIMIT/OFFSET` | 애플리케이션 전송 `N → P` |
| Endpoint 상세 | 전체 Endpoint risk snapshot에서 1건 탐색 | `endpoint_ids=[id]` pushdown | 결과 row `N → 1` |
| Archive bucket 목록 | 전체 metadata row 후 Python slice | PostgreSQL pagination + count | 결과 row `N → P` |

`P`는 요청 page size이며 현재 계약상 최대 500이다. DB의 정렬·count 자체가 항상 `O(P)`가 되는 것은 아니므로, 이 변화는 우선 네트워크 전송량과 Python 메모리/CPU 감소로 해석해야 한다. 깊은 OFFSET page의 DB 비용은 여전히 남아 있다.

RESTORED archive가 섞인 Event 목록은 단순 SQL page만 사용할 수 없어 다음 보완이 적용됐다.

- HOT/RESTORED 후보를 bounded top-k heap으로 합친다.
- RESTORED page window를 최대 10,000건으로 제한한다.
- metadata의 `event_count`를 이용해 현재 page보다 오래된 bucket을 건너뛸 수 있다.

### 4.2 조사 화면의 Event N+1 제거 — `77b80c3`

문제:

- Incident timeline과 investigation 구성 과정에서 Alert마다 `events.detail()`을 호출했다.
- K개 Alert가 있으면 HOT Event detail query가 최대 K번 발생했다.

수정:

- Event identity를 먼저 수집하고 `details_bulk()`로 한 번에 조회했다.
- HOT Event는 `events.details(hot_identities)` 한 query로 가져온다.
- RESTORED Event는 같은 archive bucket별로 묶어서 읽는다.
- topology Alert count도 전체 Alert loading 대신 `counts_by_event_ids`를 사용한다.

효과:

- HOT detail query: **K회 → 1회**
- RESTORED scan: Event별 호출에서 **고유 archive bucket 수 B회**로 축소
- timeline 최대 Alert 5,000건, investigation 최대 Alert 250건, process tree/topology Event 최대 10,000건의 guard를 추가했다.

### 4.3 Endpoint filter SQL pushdown — `292280c`, `23bd34d`

두 단계의 pushdown이 있었다.

- `292280c`: Endpoint scope를 `risk_snapshot(endpoint_ids=...)`의 PostgreSQL `ANY(...)` 조건으로 전달했다.
- `23bd34d`: DNS/IP correlation이 전역 ClickHouse 결과를 받아 Python에서 Endpoint를 거르던 방식을 `endpoint_id IN {endpoint_ids:Array(UInt64)}`로 변경했다.

선택 전 전체 일치 row가 N건, 선택 Endpoint 일치 row가 M건일 때 애플리케이션으로 전달되는 row는 `N → M`이 된다. 정확한 wall-clock은 측정되지 않았지만, M이 N보다 작을수록 전송량과 Python filter 비용이 직접 감소한다.

### 4.4 DNS correlation projection·상한 — `77b80c3`

수정:

- correlation scan은 필요한 6개 열만 projection한다: `remote_domain`, `http_host`, `tls_sni`, `remote_ip`, `dns_query`, `dns_answers_json`.
- Event는 최대 10,000건, related value는 최대 20,000개로 제한했다.

효과:

- 전체 Event column 및 `raw_payload`를 archive에서 읽는 비용을 제거했다.
- 비정상적으로 넓은 correlation 요청이 프로세스 메모리를 무제한 소비하지 못하게 했다.

## 5. Archive와 저장소 처리

### 5.1 Parquet 전체 적재 → Scanner streaming — `77b80c3`

문제:

- RESTORED Parquet object를 한 번에 table로 읽는 경로가 있었다.
- list, dashboard, DNS correlation이 각 용도보다 많은 column과 row를 읽었다.

수정:

- `pyarrow.dataset.Scanner`를 사용했다.
- filter pushdown과 용도별 column projection을 적용했다.
- `batch_size=1,024`, `to_batches()`, `use_threads=False`로 순차 처리했다.
- Dashboard용 projection은 11개 column만 사용한다.
- RESTORED Dashboard Event는 최대 1,000,000건으로 제한한다.
- Dashboard dedupe와 dimension count는 temporary SQLite에 적재해 process heap의 무제한 증가를 막았다.

효과:

- Parquet read의 애플리케이션 메모리 복잡도는 전체 object `O(N)` 적재에서 batch 중심으로 바뀌었다.
- 한 batch의 명시적 크기는 1,024 row다. 단, Arrow 내부 buffer와 SQLite/dedupe 상태까지 정확히 1,024 row만 메모리에 존재한다는 뜻은 아니다.

### 5.2 ClickHouse archive export streaming — `77b80c3`

문제:

- archive 대상 Event를 Python list로 모두 만든 뒤 Parquet/S3로 내보내면 bucket 크기만큼 메모리가 증가한다.

수정:

- ClickHouse `query_row_block_stream`을 감싼 `archive_row_batches()`를 추가했다.
- lifecycle worker가 block을 순차적으로 Zstandard Parquet에 기록하고 temporary file을 S3로 전송한다.
- archive candidate는 기본 10개, restore pending 조회는 candidate limit의 10배 등 worker 한 회의 처리량을 제한했다.

효과:

- Python row 보관 메모리: **`O(N)` → `O(ClickHouse block size)`**
- 디스크 temporary file은 여전히 archive 크기에 비례하고, 실제 block size는 ClickHouse driver 설정에 좌우된다.

### 5.3 저장소 탐색 index — `77b80c3`

추가된 index:

- ClickHouse `event_id` bloom filter index: false-positive 설정 `0.001`, granularity 1
- PostgreSQL partial index `idx_ingest_metadata_restore_pending`
- PostgreSQL partial index `idx_ingest_metadata_archive_candidates`
- PostgreSQL `idx_incidents_last_detected`

기대 효과:

- Event detail/bulk identity 조회에서 불필요한 ClickHouse granule scan을 줄인다.
- restore/archive worker의 pending candidate 탐색과 Incident 최신순 조회를 index로 지원한다.
- 실제 `EXPLAIN ANALYZE` 전후 시간은 기록되지 않았다.

## 6. Endpoint Agent

### 6.1 macOS SQLite prepared statement 재사용 — `00e0e45`

문제:

- 여러 buffer row의 상태를 갱신할 때 row마다 SQL statement를 prepare/finalize했다.

수정:

- statement를 loop 밖에서 한 번 prepare했다.
- 각 row 처리 후 `sqlite3_reset`과 `sqlite3_clear_bindings`로 재사용했다.

효과:

- N건 update의 prepare/finalize: **N회 → 1회**
- 100건 기준 prepare: **100회 → 1회, 99% 감소**
- SQL step 자체는 N회로 동일하다.

### 6.2 macOS batch 크기 탐색 — `00e0e45`

문제:

- 최대 100개의 Event를 하나씩 추가하면서 1개, 2개, …, N개 batch 전체를 매번 JSON encode했다.
- encode 호출은 `O(N)`, 누적 직렬화 대상 Event 수는 `1+2+...+N`, 즉 `O(N²)`였다.

수정:

- 첫 Event가 5MiB 제한을 만족하는지 확인한 뒤, 들어갈 수 있는 최대 Event 수를 binary search한다.
- `JSONEncoder`와 `sentAt`을 재사용한다.

100건이 모두 5MiB 제한에 들어가는 경우:

- JSON encode 호출: **100회 → 8회, 92% 감소, 12.5배 감소**
- encode된 누적 Event 단위: **5,050개 → 606개, 88.0% 감소, 8.33배 감소**
- 직렬화 복잡도: **`O(N²) → O(N log N)`**

### 6.3 Windows batch JSON 조립 — `00e0e45`

문제:

- Event 하나를 추가할 때마다 지금까지 선택한 모든 Event JSON과 전체 envelope를 다시 만들었다.
- `utc_now()`도 후보 Event마다 호출했다.

수정:

- envelope prefix와 timestamp를 한 번 만든다.
- Event JSON은 한 번씩 append하고 예상 byte size만 계산한다.
- 최종 body는 선택 완료 후 한 번 조립한다.

100건이 모두 제한에 들어가는 경우:

- 전체 candidate body 생성: **100회 → 1회, 99% 감소**
- timestamp 생성: **100회 → 1회, 99% 감소**
- 반복적으로 포함·복사되던 Event JSON 단위: **5,050개 → 100개, 98.02% 감소, 50.5배 감소**
- 조립 복잡도: **`O(N²) → O(N)`**

## 7. Frontend

### 7.1 Route code splitting — `b8431e2`

문제:

- Login 외 12개 page module을 `App.tsx`에서 정적으로 import해 첫 bundle에 포함했다.

수정:

- 12개 인증 route를 모두 `React.lazy` 동적 import로 바꿨다.
- 이후 추가된 Dashboard 관리 route도 lazy boundary를 유지해 현재는 13개 lazy route다.

효과:

- 첫 화면에서 즉시 필요하지 않은 **12개 기존 page module**을 초기 route bundle에서 분리했다.
- 실제 초기 JS byte와 FCP/LCP 전후 값은 이력에 남아 있지 않다.

### 7.2 ECharts 지연 로딩과 chunk 분리 — `53e13b0`, `699eda5`

- `53e13b0`: `DetectionActivityPanel`을 lazy import하고 `Suspense` fallback을 추가했다. ECharts 시각화는 Overview가 실제로 필요할 때 로드된다.
- `699eda5`: Vite `manualChunks`에서 `zrender`를 별도 chunk로 분리했다. 큰 chart dependency의 cache/chunk 경계를 안정화한다.

두 작업 모두 bundle 구조 개선이지만 전후 다운로드 byte나 browser timing은 측정되지 않았다. `zrender` 분리는 총 다운로드량 자체를 줄이는 작업이 아니라, route loading 및 cache 재사용 단위를 나누는 작업이다.

### 7.3 ECharts instance 재생성 제거 — `00e0e45`

문제:

- `DetectionActivityPanel`의 effect가 data model, label, theme 변경 때마다 cleanup에서 chart를 dispose하고 다시 `init`했다.
- render 도중 state를 동기화하는 코드도 있었다.

수정:

- chart lifecycle effect를 `hasDomain` 변화와 분리했다.
- data/theme 변경은 기존 instance의 `setOption`만 실행한다.
- selection 동기화는 별도 effect로 옮겼다.

효과:

- domain이 유지되는 data/theme update 1회당 chart init/dispose pair: **1회 → 0회**
- canvas와 event listener를 반복 생성·해제하는 비용을 제거했다.
- 실제 frame time은 측정되지 않았다.

### 7.4 Pretendard 전체 font → dynamic subset — `8b85a9c`, `00e0e45`

변경 흐름:

- `8b85a9c`에서 전체 `PretendardVariable.woff2`를 사용하는 CSS가 도입됐다.
- `00e0e45`에서 `pretendardvariable-dynamic-subset.css`로 교체됐다.

현재 설치 asset 기준:

- 전체 variable WOFF2: **2,057,688 bytes**
- dynamic subset: **92개 shard**, shard당 **8,252~43,920 bytes**
- 한 shard를 전체 font와 비교하면 **97.87~99.60% 작다**.
- CSS 자체는 481 bytes에서 55,760 bytes로 55,279 bytes 증가한다.

주의:

- browser는 페이지에 사용된 Unicode range의 shard만 요청하므로 일반적으로 큰 font 한 파일을 피할 수 있다.
- 92개 shard 전체 합은 2,957,724 bytes로 오히려 전체 font 한 파일보다 크다. 따라서 실제 절감량은 해당 화면의 글자 범위와 browser cache에 따라 달라지며, 위 shard 비율을 page 전체 절감률로 해석하면 안 된다.

### 7.5 Dashboard layout 저장 요청 병합 — `5054e01`

새 Dashboard drag/drop 기능은 처음부터 다음 성능 장치를 포함했다.

- drag/resize 연속 변경을 650ms debounce한다.
- 저장 중 추가 변경은 모든 중간 상태를 보내지 않고 최신 layout 하나만 queue한다.
- Backend upsert는 CTE에서 update/insert를 처리한다.
- `(user_id, dashboard_key)` unique key와 user index를 추가했다.

효과:

- 650ms 안에 연속으로 발생한 M개 layout 변경은 network save를 **M회가 아니라 1회**로 합칠 수 있다.
- 느린 network에서 저장 중 변경이 여러 번 발생해도 대기 queue는 최신 layout 하나로 제한된다.
- 기능 도입과 동시에 적용된 설계라서 이전 구현과의 wall-clock 비교는 없다.

### 7.6 Custom Dashboard 정규화 상한 강화 — `5bce15c`, `0ab7200`

- `5bce15c`: localStorage의 과대 widget 배열을 최대 512개까지만 정규화하고, 5,000개 입력을 1초 이내에 처리하는 test guard를 도입했다.
- `0ab7200`: 같은 widget type의 중복을 `Set`으로 제거해 expensive placement와 결과 보관을 현재 정의된 9개 type까지만 수행하도록 강화했다.

5,000개 중복형 입력 test 기준:

- 보관/placement 최대치: **512개 → 9개**
- 최대 작업·결과 수: **98.24% 감소, 56.89배 감소**
- test guard: **5,000개 입력 정규화 < 1,000ms**

입력 배열 자체는 유효성 검사를 위해 순회하므로 전체 loop는 `O(N)`이다. 개선 지점은 중복 widget의 geometry placement 및 결과 메모리다.

### 7.7 Production mode 상수 주입 — `5054e01`

- Vite build mode에 따라 `process.env.NODE_ENV`를 `production` 또는 `development` 상수로 정의했다.
- production guard가 있는 dependency code의 dead-code elimination을 가능하게 하고, production runtime branch를 명확히 한다.
- 실제 bundle byte 차이는 측정되지 않아 기대 효과로만 분류한다.

## 8. 초기부터 존재한 성능 설계

다음 항목은 특정 이전 구현을 개선한 것이 아니라 최초 커밋 `d6b2c4a`부터 존재했다. 전체 성능 설계 누락을 막기 위해 별도로 기록한다.

### Storage와 DB

- ClickHouse Event: `ReplacingMergeTree(updated_at)`, 일 단위 partition, `(endpoint_id, occurred_at, event_type, event_id)` 정렬 key
- `os_type`, `event_type` 등 반복 문자열에 `LowCardinality`
- Failure: 월 partition, 97일 TTL
- PostgreSQL 최초 explicit index 11개: Endpoint 상태/last seen, Agent key, audit lookup, ingest overlap, Alert/Incident risk·time window 등
- ClickHouse insert는 row별 insert가 아니라 batch `client.insert`를 사용

### Agent

- Event batch 최대 100건, body 최대 5MiB, flush interval 5초
- SQLite pending queue index `(status, next_retry_at, local_event_buffer_id)`
- 다중 상태 변경을 transaction으로 처리

### Frontend request 제어

- hidden tab에서는 polling interval이 `false`가 되어 scheduled polling을 중단한다.
- React Query도 `refetchIntervalInBackground: false`를 사용한다.
- Overview의 30초 polling query 3개 기준 hidden 상태에서 시간당 최대 360회의 예정 polling을 피한다.
- Operations 15초 polling은 시간당 최대 240회, Archive 기본 30초 polling은 최대 120회를 피한다. 단, 각 page가 실제로 mount된 경우의 환산값이다.
- retry는 503에만 최대 3회, 5/15/30초 delay로 제한한다.

### 운영 구성

`1e91909`에서 production Nginx에 `worker_processes auto`, `worker_connections 1024`를 설정하고 Kafka partition 수를 환경 설정으로 조절할 수 있게 했다. 이는 production capacity baseline이며, 당시 default partition 수가 3에서 2로 바뀌었으므로 순수한 throughput 개선으로 계산하지 않았다.

## 9. 아직 수치화하지 못한 부분과 남은 병목

- `b8864d4` 외 항목은 대부분 실제 production P50/P95/P99 전후 측정이 없다.
- Dashboard HOT query는 여전히 `FINAL`을 사용한다. ReplacingMergeTree 중복 정합성을 보장하지만 데이터가 더 커지면 비용이 커질 수 있다.
- 2-query dimension 집계는 `ARRAY JOIN`으로 row를 여섯 후보로 펼치므로 ClickHouse CPU·read_rows·memory usage를 실제 query log로 확인해야 한다.
- DB pagination은 application 전송량을 줄였지만 OFFSET이 깊어질수록 DB가 건너뛰는 비용은 남는다. 대규모 탐색에는 keyset pagination 검토가 필요하다.
- Endpoint `risk_page`는 결과 전송을 page로 제한하지만 risk 계산 CTE와 count는 후보 전체를 평가할 수 있다.
- RESTORED Dashboard 최대 1,000,000건과 correlation 최대 10,000건은 장애 방지 guard이지, 해당 상한까지 빠르다는 보장은 아니다.
- font dynamic subset은 화면별 실제 glyph와 cache 상태에 따라 요청 shard 수가 달라진다. browser trace 없이는 page 절감 byte를 확정할 수 없다.
- Route/ECharts lazy loading과 `zrender` chunk 분리는 Lighthouse/Web Vitals 전후 값이 없다.
- 모바일은 이번 평가 범위에서 제외했다.

다음 측정이 있으면 보고서를 production 수치로 보완할 수 있다.

1. ClickHouse `system.query_log`의 query duration, read_rows, read_bytes, memory_usage
2. API LATEST_15M/24H/7D/31D의 30회 이상 P50/P95/P99
3. Event/Endpoint/Alert/Incident page 1과 깊은 page의 `EXPLAIN ANALYZE`
4. Agent 1/10/100건 batch의 CPU time, allocation, SQLite prepare count
5. Desktop browser의 initial JS/font transfer, route 전환 시간, chart update frame time

## 10. 전체 일반 커밋 판정표

병합 커밋 20개도 양쪽 parent와 merge tree를 확인했다. 성능 변경은 아래 원본 일반 커밋으로 귀속했으며, 병합 자체의 수치로 중복 계산하지 않았다.

판정 기호:

- `P-실측`: 실제 전후 시간/크기 측정이 있음
- `P-확정`: query/연산/상한 변화가 코드로 확정됨
- `P-기대`: 성능 지향 구조지만 전후 runtime 측정 없음
- `기준선`: 최초부터 존재한 설계
- `제외`: 기능·정확성·UI·문서·CI·배포 안정성 변경으로, 직접 성능 개선으로 계산하지 않음

| 날짜 | 커밋 | 판정 | 검토 결과 |
|---|---|---|---|
| 2026-07-20 | `0bbce5d` | 제외 | Dashboard/조사 UX 개선, 별도 성능 delta 없음 |
| 2026-07-20 | `00e0e45` | P-확정 | 9→2 집계 query, 중복 summary 제거, Agent/Chart/font 최적화 |
| 2026-07-20 | `23fa5aa` | 제외 | Agent 상시 실행 문서 |
| 2026-07-19 | `84c8cec` | 제외 | service image SHA pin |
| 2026-07-19 | `0269535` | 제외 | Swagger 한글화 |
| 2026-07-19 | `699eda5` | P-기대 | `zrender` manual chunk; 나머지는 운영 검증/healthcheck |
| 2026-07-19 | `77b80c3` | P-확정 | pagination, summary, streaming, N+1 제거, index, guard |
| 2026-07-19 | `29a1e93` | 제외 | Frontend 디자인 보완 |
| 2026-07-18 | `0ab7200` | P-확정 | 중복 widget type 제거, 최대 placement 512→9 |
| 2026-07-18 | `f8ec711` | 제외 | 배포 전 검증·migration 안전장치 |
| 2026-07-18 | `5bce15c` | P-기대 | Custom Dashboard 512 cap과 5,000건 <1초 guard 도입 |
| 2026-07-17 | `e3371f5` | 제외 | Vercel API proxy |
| 2026-07-17 | `8b85a9c` | 제외 | UI 개편; 전체 Pretendard font 도입은 후속 커밋에서 개선 |
| 2026-07-17 | `b8864d4` | P-실측 | ClickHouse Dashboard 집계, API 9.97~27.93배 이상 개선 |
| 2026-07-17 | `4b4849c` | 제외 | Overview 시각 조정 |
| 2026-07-16 | `53e13b0` | P-기대 | ECharts panel lazy loading |
| 2026-07-16 | `cfa5e2e` | 제외 | DNS 상관관계 화면 완성 |
| 2026-07-16 | `23bd34d` | P-확정 | DNS correlation Endpoint filter SQL pushdown |
| 2026-07-16 | `16ab0cb` | 제외 | DNS 경계 매칭·정확 비교, 주효과는 correctness |
| 2026-07-16 | `5efcbd5` | 제외 | DNS/IP 기능 최초 도입 |
| 2026-07-16 | `b8431e2` | P-확정/기대 | 12개 route lazy, PostgreSQL query index 3개 |
| 2026-07-16 | `ec07332` | 제외 | CI/배포 문서 정합성 |
| 2026-07-16 | `a8100e0` | 제외 | auto-deploy 안정화 |
| 2026-07-16 | `5ecad48` | 제외 | pipeline marker 제거 |
| 2026-07-16 | `80869a4` | 제외 | pipeline trigger test |
| 2026-07-16 | `0e8f4f5` | 제외 | production branch 자동 승격 |
| 2026-07-16 | `745f57b` | 제외 | Slack 운영 알림 규칙 |
| 2026-07-16 | `c8f26e4` | 제외 | backup/restore 상태 문서 |
| 2026-07-15 | `fa40be2` | 제외 | Portainer 복구/backup 절차 |
| 2026-07-15 | `8d90cc2` | 제외 | 배포 SHA 문서 |
| 2026-07-15 | `cd5528a` | 제외 | 배포 상태 문서 |
| 2026-07-15 | `d08a0b5` | 제외 | Alloy disk metadata mount 수정 |
| 2026-07-15 | `273fa11` | 제외 | 운영 배포 정합성 |
| 2026-07-15 | `23015d1` | 제외 | 한글화 |
| 2026-07-15 | `5b925ff` | 제외 | Portainer Agent Alloy mount 수정 |
| 2026-07-15 | `616f2f3` | 제외 | Grafana monitoring 추가; 관측성 개선이지 처리 성능 개선은 아님 |
| 2026-07-15 | `3141e08` | 제외 | Portainer 배포 환경 구성 |
| 2026-07-14 | `5054e01` | P-기대 | layout save 650ms debounce/latest queue, production mode define |
| 2026-07-14 | `1e91909` | P-기대 | Nginx auto worker와 Kafka tuning 가능화; 순수 throughput 수치는 없음 |
| 2026-07-14 | `398c935` | 제외 | Login/session 기능 보완 |
| 2026-07-14 | `292280c` | P-확정 | Endpoint scope PostgreSQL pushdown |
| 2026-07-13 | `d6b2c4a` | 기준선 | ClickHouse partition/LowCardinality/TTL, DB index, microbatch, polling 제어 |

## 11. 한 줄 요약

실측으로 가장 큰 성과는 Dashboard API의 **최대 27.93배 이상 가속과 94.81% payload 감소**이고, 구조적으로는 대량 데이터를 애플리케이션으로 끌어와 처리하던 경로를 DB 집계·pagination·streaming·bulk query로 바꿔 데이터 증가 시의 메모리, 네트워크, query round trip, 반복 직렬화 비용을 줄인 것이 핵심이다.
