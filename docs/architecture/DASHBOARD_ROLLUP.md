# Dashboard Event Rollup 전략

## 1. 목표와 범위

Dashboard 첫 화면의 Event 집계를 매 요청마다 ClickHouse 원본에서 계산하지 않고 PostgreSQL의 1분 rollup에서 읽는다. 사용자가 Overview의 `Refresh`를 명시적으로 실행한 경우에만 같은 범위를 ClickHouse에서 실시간 집계한다.

이 rollup은 Event와 Alert를 하나의 DB에서 join하기 위한 복제본이 아니다. Event 집계 projection만 PostgreSQL에 저장하고 Alert·Incident는 기존 PostgreSQL 원본 테이블에서 별도로 집계한 뒤 API service에서 하나의 `DashboardSummaryDto`로 조합한다. Event 목록·상세·조사 근거는 계속 ClickHouse 또는 복원된 S3 Parquet에서 조회한다.

## 2. ClickHouse → PostgreSQL 동기화 방식 결정

2026-08-11 기준 공식 기능을 확인한 결과, 이 프로젝트에 바로 적용할 수 있는 ClickHouse outbound CDC source connector는 채택하지 않았다.

- [Debezium connector 목록](https://debezium.io/documentation/reference/stable/connectors/index.html)에는 PostgreSQL, MySQL, SQL Server 등 source connector가 있지만 ClickHouse source connector는 없다.
- [ClickHouse PostgreSQL integration](https://clickhouse.com/integrations/postgres)의 PostgreSQL table function/table engine은 ClickHouse가 PostgreSQL을 조회하거나 쓰기 위한 기능이다. 원본 Event ingest와 PostgreSQL 가용성을 결합하는 직접 write 경로로 사용하지 않는다.
- ClickHouse가 소개하는 [PostgreSQL과 ClickHouse 통합 구조](https://clickhouse.com/blog/postgres-clickhouse-oss)는 주로 PostgreSQL → ClickHouse CDC와 split writes를 다룬다.
- [`pg_clickhouse`](https://clickhouse.com/blog/introducing-pg_clickhouse)는 PostgreSQL에서 ClickHouse를 조회하는 FDW이며 ClickHouse → PostgreSQL 복제기가 아니다.

따라서 Python micro-batch worker를 동기화 경계로 사용한다. Kafka는 변경 알림과 재처리 순서를 제공하고, 집계의 source of truth는 ClickHouse다.

## 3. 데이터 흐름

```text
Event Storage Worker
├─ ClickHouse edr_events 저장
└─ Kafka telemetry.validated 발행
                 │
                 ▼
Dashboard Rollup Worker
├─ endpoint_id + occurred_at의 1분 bucket을 dirty set으로 병합
├─ ClickHouse에서 dirty bucket 전체를 다시 집계
├─ PostgreSQL rollup row를 transaction으로 교체
├─ PostgreSQL commit 이후 Kafka offset commit
└─ 잘못된 메시지는 Failure Sink에 격리한 뒤 해당 offset만 commit

Dashboard GET /dashboard/summary
├─ eventSource=ROLLUP (기본): PostgreSQL rollup 사용
└─ eventSource=LIVE (사용자 Refresh): ClickHouse 원본 집계 사용
```

`telemetry.validated` 메시지의 개별 값을 PostgreSQL count에 더하지 않는다. 메시지는 어느 bucket이 변경됐는지만 알려준다. Worker는 해당 `(endpoint_id, minute)`의 전체 결과를 ClickHouse에서 다시 계산한다.

## 4. PostgreSQL projection

### 4.1 `dashboard_event_rollups`

기본 키는 `(bucket_start_at, endpoint_id, event_type)`이다. 1분 단위 Event 수, 원본의 최종 `ingested_at`, rollup 갱신 시각을 저장한다.

### 4.2 `dashboard_event_dimension_rollups`

기본 키는 `(bucket_start_at, endpoint_id, dimension_name, dimension_value)`다. 프로세스, 원격 IP, 도메인, 파일 hash, DNS query, L7 protocol의 상위 후보를 저장한다.

ClickHouse에서 endpoint·1시간·dimension별 상위 50개만 projection해 PostgreSQL row 증가를 제한한다. `bucket_width_seconds=3600`으로 기존 1분 projection과 저장 경계를 구분하고 API는 요청 기간 전체를 다시 합산해 상위 10개를 반환한다. 따라서 total, event type, time series는 1분 `uniqExact(event_id)` 기반의 중복 제거 집계지만 top dimension은 bounded-candidate 근사치다.

### 4.3 `dashboard_rollup_state`

초기 backfill과 최근 갱신 범위, source freshness를 운영 확인용으로 기록한다. `covered_from`과 `covered_through`는 지금까지 관측한 가장 넓은 범위이므로 그 사이가 연속해서 준비됐다는 보장은 하지 않는다. 이 테이블 자체를 API readiness나 archive 삭제 가능 여부의 근거로 사용하지 않는다.

### 4.4 `dashboard_rollup_coverage`

전 범위 ClickHouse 재집계가 성공한 1분 bucket을 `(rollup_name, bucket_start_at)`으로 기록한다. API는 요청 범위를 분 경계로 확장한 뒤 필요한 minute 수와 coverage row 수가 정확히 같은지 확인한다. 중간 한 분이라도 빠지면 준비 완료로 간주하지 않는다.

Endpoint별 Kafka dirty-bucket 갱신은 특정 Endpoint만 다시 계산하므로 전역 coverage를 새로 만들지 않는다. 시작 backfill, 명시적 전체 범위 backfill, archive 직전 날짜 전체 재집계처럼 모든 Endpoint를 스캔한 작업만 coverage를 기록한다.

## 5. 동시성·멱등성

동일 Event가 재전달되거나 Worker가 commit 전에 중단되어도 count를 증가 연산하지 않으므로 중복 적재되지 않는다.

1. ClickHouse 집계는 `FINAL`과 `uniqExact(event_id)`를 사용해 동일 ID의 물리 중복/version을 하나로 계산한다.
2. 같은 Kafka partition의 여러 메시지는 가장 큰 offset만 보관하고 동일 bucket key는 set으로 합친다.
3. PostgreSQL의 transaction-scoped advisory lock은 ClickHouse 집계 시작부터 PostgreSQL 교체 commit까지 writer 전체를 직렬화한다. write 구간만 잠가 오래된 선행 조회가 최신 결과를 나중에 덮는 역전을 허용하지 않는다.
4. 대상 bucket의 기존 row를 삭제하고 새 전체 집계를 같은 transaction에서 삽입한다. 기본 키와 `ON CONFLICT DO UPDATE`도 중복 row를 차단한다.
5. 장기 실행 Worker connection은 autocommit mode에서 각 writer guard를 독립 transaction으로 확정한다. PostgreSQL commit이 성공한 뒤에만 Kafka offset을 commit한다. commit 전에 장애가 나면 같은 bucket을 다시 계산하며 결과는 동일하다.
6. Writer는 대상 UTC 날짜마다 shared advisory lock을 함께 잡는다. Archive의 partition 삭제 claim은 같은 날짜의 exclusive lock을 사용하므로 ClickHouse 조회와 partition drop이 교차하지 않는다.

전달 보장은 at-least-once이고 projection 결과는 멱등이다. ClickHouse 저장과 Kafka publish 사이의 기존 storage-worker 계약은 그대로 유지한다.

## 6. 초기 적재와 지속 동기화

- 시작 시 최근 31일 안에서 coverage가 없는 모든 연속 구간을 찾아 기본 1시간 chunk로 backfill한다. `EDR_DASHBOARD_ROLLUP_BACKFILL_CHUNK_HOURS`로 1~24시간 사이에서 조정할 수 있고, 각 chunk 사이에 bounded Kafka drain을 수행해 긴 backfill 중에도 consumer poll과 dirty-bucket 처리가 굶지 않게 한다. 상태 테이블의 마지막 시각만 보고 중간 hole을 건너뛰지 않는다.
- coverage 유무와 별개로 최근 기본 2분은 매 시작 시 다시 계산해 지연 도착 Event를 보정한다.
- Kafka dirty signal 유실과 수동 replay 지연을 보정하기 위해 기본 6시간마다 최근 24시간을 강제 재집계한다. `/operations/health`는 coverage뿐 아니라 ClickHouse 원본과 PostgreSQL projection의 `source_max_ingested_at` 차이도 확인한다.
- 이후 `telemetry.validated`를 `edr-dashboard-rollup-v1` consumer group으로 따라간다.
- dirty bucket은 기본 5초 또는 500개 중 먼저 충족되는 조건으로 flush한다.
- sparse dirty key는 endpoint별로 ClickHouse를 반복 조회하지 않고 같은 1시간 query window로 묶어 조회한다. PostgreSQL 기존 row 삭제도 key별 statement가 아니라 배열 기반 bulk delete로 처리한다.
- 검증 실패 메시지는 `DASHBOARD_ROLLUP/INVALID_MESSAGE` failure record로 저장한다. 그 전에 처리된 정상 offset을 먼저 flush한 뒤 poison offset을 commit하므로 재시작 crash loop와 정상 메시지 유실을 함께 막는다. Failure Sink 저장 자체가 실패하면 poison offset을 rewind하고 commit하지 않는다.
- `python -m tools.run_dashboard_rollup_worker --backfill-only --backfill-hours <N>`은 기존 상태와 관계없이 요청한 전체 기간을 강제로 재생성한다.

Rollup 도입 전에 ClickHouse에서 이미 삭제되어 S3에만 남아 있는 Event는 이 worker만으로 복원되지 않는다. 그 기간이 필요하면 S3 Parquet를 읽는 일회성 backfill 절차가 별도로 필요하다.

## 7. Archive 안전 장벽

Storage Lifecycle Worker는 검증된 UTC 날짜 partition을 ClickHouse에서 삭제하기 직전에 해당 하루를 rollup으로 다시 계산한다. Lifecycle connection도 repository transaction 단위로 commit하므로 rollup transaction이 실제 확정된 뒤에만 ClickHouse partition drop으로 진행한다. Rollup 갱신이 실패하면 partition을 유지한다.

Rollup 이후 늦은 Event가 들어오면 ingest guard가 기존 archive 검증을 무효화한다. Partition 삭제 claim은 동일 날짜 advisory lock 아래에서 archive checksum과 Event 수를 다시 확인하므로 갱신 이후 race가 발생해도 오래된 rollup을 남긴 채 partition을 삭제하지 않는다. 한 Endpoint의 partition 삭제가 확정된 날짜는 다른 신규 Endpoint도 HOT ingest를 시작할 수 없게 날짜 전체를 immutable하게 취급한다. 그렇지 않으면 새 Endpoint row가 이미 삭제된 ClickHouse 날짜 partition을 다시 만들 수 있다.

`is_delete` 또는 `partition_deleted_at`이 기록된 날짜는 rollup 관점의 frozen date다. Dirty refresh와 강제 range backfill은 날짜 shared lock 안에서 이 상태를 다시 확인하고 해당 날짜를 ClickHouse 원본만으로 재계산하지 않는다. 따라서 archive 뒤 남은 PostgreSQL rollup을 0건으로 덮거나 실제로 만들지 않은 coverage를 기록하지 않는다. 이미 S3에만 있는 과거 날짜는 S3 restore/backfill이 완료되기 전까지 `ROLLUP_NOT_READY`로 남는다.

## 8. 조회 계약

- `eventSource=ROLLUP`이 API 기본값이며 Overview 초기 로딩과 일반 재시도에 사용한다.
- 요청 범위의 minute coverage가 완전하지 않으면 값을 0으로 꾸미지 않고 retryable `503 ROLLUP_NOT_READY`를 반환한다.
- `eventSource=LIVE`는 사용자가 Overview의 `Refresh`를 실행했을 때만 사용한다. 성공 결과는 현재 query cache를 갱신한다.
- LIVE에만 Nginx IP별 `12 requests/minute, burst 3` 제한을 적용하고 초과 시 `429 RATE_LIMITED`를 반환한다. 애플리케이션은 로컬 semaphore와 PostgreSQL advisory slot을 함께 사용해 전체 replica 기준 기본 동시 실행 2개(`EDR_DASHBOARD_LIVE_MAX_CONCURRENCY`)로 제한하며 자리가 없으면 retryable 503을 반환한다. ClickHouse LIVE query에는 8초, 2 threads, 최대 5천만 read row 예산을 적용한다. ROLLUP 요청은 이 제한의 key에 포함되지 않는다.
- Frontend는 `ROLLUP_NOT_READY`를 일반 부분 실패와 구분하고 Retry를 사용자 요청 기반 LIVE 조회로 연결한다.
- LIVE 요청이 실패하면 기존 rollup 화면을 유지하고 stale/error 경고만 표시한다.
- 자동 ClickHouse Event polling과 Overview에서 사용하지 않던 별도 ingest summary 요청은 수행하지 않는다.
- Alert, Incident, Endpoint, storage 집계는 기존 PostgreSQL 경로를 사용한다. Event failure 집계는 아직 ClickHouse의 `event_failures`를 사용하므로 ROLLUP이 Dashboard의 모든 ClickHouse 접근을 제거하는 것은 아니다.

Activity Rollup bucket은 1분, top dimension bucket은 1시간 해상도다. 요청 시작·종료 시각이 경계와 맞지 않으면 activity는 최대 두 경계 minute, top dimension은 최대 두 경계 hour 범위의 근사치다. Event 목록과 상세의 `[from, to)` 계약은 원본 조회로 정확히 유지한다.

## 9. 운영 및 복구

- `/operations/health`에서 `Dashboard rollup coverage`, `Dashboard rollup worker`, group member 수와 lag를 확인한다. 최근 24시간에 coverage hole이 있으면 전체 상태가 degraded다.
- lag 증가 시 Worker를 재시작한다. offset replay는 동일 bucket 교체이므로 안전하다.
- projection 손상 또는 집계 로직 변경 시 필요한 기간을 `--backfill-only`로 다시 만든다.
- schema 변경 시 새 rollup version/group을 사용하고 전체 backfill 완료 후 API 읽기 경로를 전환한다.
- `dashboard_rollup_state.source_max_ingested_at`과 현재 시각의 차이는 freshness 지표지만 readiness나 삭제 안전 조건은 아니다.
- `dashboard_event_dimension_rollups`는 hour·endpoint·dimension별 상위 50개 후보를 보관한다. 기존 minute projection보다 이론상 row 상한을 60분의 1로 줄였지만 실제 retention과 Endpoint 수를 기준으로 PostgreSQL 용량을 계속 관찰해야 한다. API가 임의의 과거 31일 범위를 허용하므로 projection retention을 줄이려면 API 조회 가능 기간 또는 S3 기반 재생성 정책을 함께 결정한다.
- 현재 global writer advisory lock은 correctness를 우선해 모든 rollup write를 직렬화한다. 시간 window query 병합과 bulk delete로 한 번의 lock 점유 시간을 줄였지만, 처리량 목표를 넘으면 rollup version별/날짜별 lock 분할과 부하 시험이 다음 확장 단계다.

## 10. 실제 통합 검증

격리된 Docker Compose 프로젝트에서 다음 경로를 실제 PostgreSQL, ClickHouse, Kafka에 대해 검증했다.

- ClickHouse의 `FINAL + uniqExact(event_id)` 집계가 물리 중복 Event를 하나로 계산하고 UTC-aware bucket을 반환한다.
- ClickHouse 집계 결과를 PostgreSQL에 교체한 뒤 Event 추가와 재계산이 1 → 2로 갱신된다.
- 서로 다른 PostgreSQL connection이 같은 bucket을 동시에 교체해도 advisory lock으로 직렬화되며 두 결과가 합산되지 않는다.
- 먼저 시작한 ClickHouse 조회를 의도적으로 지연하고 두 번째 writer를 경쟁시켜도 조회와 교체가 함께 직렬화되어 최신 count가 최종값으로 남는다.
- Archive 삭제 확정 날짜에 신규 Endpoint ingest가 거절되고, frozen date에 대한 dirty/range refresh가 기존 rollup과 coverage를 훼손하지 않는다.
- 잘못된 Kafka 메시지가 Failure Sink에 저장되고, 선행 정상 offset flush 및 poison offset commit 순서가 유지되며, Failure Sink 장애 시 rewind된다.
- backfill이 설정된 시간 chunk로 나뉘고 chunk 사이 Kafka drain을 수행하며, sparse dirty bucket의 ClickHouse 조회가 시간 window 단위로 합쳐진다.
- Collector → `telemetry.raw` → Storage Worker → ClickHouse → `telemetry.validated` → Detection/Rollup Worker → PostgreSQL 전체 경로와 duplicate replay가 멱등이다.
- coverage가 없는 기본 Dashboard 요청은 `ROLLUP_NOT_READY`, backfill 뒤 ROLLUP 성공, 사용자 명시 LIVE 요청은 ClickHouse 원본 결과를 반환한다.
- 개발·운영 Nginx 설정은 임시 인증서를 사용한 `nginx -t`로 검증했다.
