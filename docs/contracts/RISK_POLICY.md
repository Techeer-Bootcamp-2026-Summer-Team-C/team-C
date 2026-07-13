# EDR Risk 및 전역 상태 정책

## 1. 문서 목적

이 문서는 `API_SPEC.md`의 `EndpointRiskDto`, `EndpointRiskSummaryDto`, `EdrStateDto`를 계산하는 Backend 정책 V1을 정의한다. FastAPI/Pydantic DTO가 외부 응답 계약이고 이 문서는 계산 입력, 중복 제거, 가중치, 반올림, 상태 구간과 reason code 발생 조건의 단일 기준이다.

Endpoint Risk와 전역 EDR 상태는 Dashboard API가 계산한다. 프론트는 반환된 score, level, status와 reason code를 표시할 뿐 Alert/Event 목록을 다시 집계하거나 상태를 판정하지 않는다.

## 2. 공통 규칙

- 계산 대상 row는 모두 `is_delete=false`다.
- 계산 기준 시각 `calculatedAt`은 요청 처리 시작 시각의 UTC RFC3339 `Z` timestamp다.
- 한 응답 안의 모든 Endpoint Risk와 전역 EDR 상태는 같은 `calculatedAt`을 사용한다.
- Endpoint Risk와 전역 EDR 상태는 현재 운영 snapshot이며 Dashboard의 `timePreset`, `from`, `to`와 무관하다.
- 모든 score는 0~100 범위다.
- 모든 중간 계산은 decimal로 수행하고 마지막 score 변환은 `ROUND_HALF_UP`을 사용한다. Python의 기본 bankers rounding을 사용하지 않는다.
- count가 없으면 `0`, list가 없으면 `[]`, 대상 Endpoint가 없을 때 최고점은 `null`이다.
- 정책 V1은 시간 감쇠를 사용하지 않는다.
- 정책 V1은 새 저장 테이블, materialized view, 별도 Risk Worker를 만들지 않는다.

## 3. Endpoint Risk

### 3.1 입력

Endpoint별로 다음 값을 사용한다.

- Alert status가 `OPEN` 또는 `IN_PROGRESS`인 활성 Alert
- 활성 Alert의 `riskScore`
- status가 `OPEN`인 Incident
- Alert의 `ruleCode`, `ruleVersion`, `detectedAt`, `alertId`
- Incident의 `incidentId`, `title`

`activeAlertCount`는 중복 제거 전 활성 Alert 전체 개수다. `openIncidentCount`는 OPEN Incident 전체 개수다. `highestAlertRiskScore`는 중복 제거 전 활성 Alert 전체의 최고 `riskScore`이며 활성 Alert가 없으면 `null`이다.

### 3.2 동일 Rule Alert 중복 처리

점수 계산에서는 동일 `(ruleCode, ruleVersion)` Alert를 한 그룹으로 묶고 대표 Alert 하나만 사용한다.

대표 Alert 선택 순서:

1. `riskScore`가 높은 Alert
2. 동점이면 `detectedAt`이 최신인 Alert
3. 다시 동점이면 `alertId`가 큰 Alert

대표 Alert를 `riskScore` 내림차순으로 정렬하고 동점이면 `detectedAt` 내림차순, `alertId` 내림차순으로 정렬한다. 상위 3개를 `A1`, `A2`, `A3`으로 사용한다.

### 3.3 Alert contribution

각 contribution은 개별적으로 `ROUND_HALF_UP`하여 integer score point로 만든다.

```text
A1 contribution = roundHalfUp(A1.riskScore)
A2 contribution = roundHalfUp(A2.riskScore * 0.25)
A3 contribution = roundHalfUp(A3.riskScore * 0.10)
```

대표 Alert가 해당 순번까지 없으면 contribution은 `0`이다.

### 3.4 Incident contribution

OPEN Incident는 정렬 후 상위 2개만 점수에 반영한다.

정렬 순서:

1. severity: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`
2. `lastDetectedAt` 내림차순
3. `incidentId` 내림차순

```text
Incident 1 contribution = 10
Incident 2 contribution = 10
```

OPEN Incident가 2개를 초과해도 incident contribution 최대값은 20이다. 전체 개수는 `openIncidentCount`에 그대로 반환한다.

### 3.5 최종 Endpoint score

```text
rawScore =
    A1 contribution
  + A2 contribution
  + A3 contribution
  + Incident 1 contribution
  + Incident 2 contribution

score = min(rawScore, 100)
```

입력 factor는 위 계산 순서대로 누적한다. 누적값이 100을 넘으면 마지막 factor의 `contribution`을 100까지 남은 점수로 줄이고 이후 factor는 반환하지 않는다. 따라서 `riskFactors[].contribution` 합계는 항상 최종 `score`와 같다.

활성 Alert와 OPEN Incident가 모두 없으면:

```text
score = 0
level = LOW
activeAlertCount = 0
openIncidentCount = 0
highestAlertRiskScore = null
riskFactors = []
```

### 3.6 Risk level

| score | RiskLevel |
| ---: | --- |
| 0~24 | `LOW` |
| 25~49 | `MEDIUM` |
| 50~79 | `HIGH` |
| 80~100 | `CRITICAL` |

### 3.7 Risk factor 생성

Alert factor:

```text
code = ALERT_PRIMARY / ALERT_SECONDARY / ALERT_TERTIARY
sourceType = ALERT
sourceId = 대표 alertId
title = Alert title
description = ruleCode, ruleVersion과 적용 가중치를 설명하는 고정 형식 문자열
contribution = 최종 score에 실제 반영된 integer point
```

Incident factor:

```text
code = OPEN_INCIDENT
sourceType = INCIDENT
sourceId = incidentId
title = Incident title
description = OPEN correlation Incident가 추가한 점수를 설명하는 고정 형식 문자열
contribution = 최종 score에 실제 반영된 integer point
```

Factor는 최대 5개이며 contribution이 `0`인 factor는 반환하지 않는다. Event raw payload, command line 전체, packet metadata 원문, private key와 secret은 factor에 포함하지 않는다.

### 3.8 RETIRED Endpoint

RETIRED Endpoint도 활성 Alert 또는 OPEN Incident가 있으면 Endpoint Risk를 계산한다. 다만 RETIRED Endpoint는 Collection Health의 OFFLINE, STALE, ingest 지연 대상에서 제외한다.

## 4. Endpoint Risk summary

`EndpointRiskSummaryDto`는 현재 `is_delete=false` Endpoint 전체의 `EndpointRiskDto`를 기준으로 계산한다.

- `highestScore`: 최고 Endpoint score, Endpoint가 없으면 `null`
- `highRiskEndpointCount`: level이 정확히 `HIGH`인 Endpoint 수
- `criticalRiskEndpointCount`: level이 정확히 `CRITICAL`인 Endpoint 수
- `byLevel`: 실제 존재하는 level별 count, enum 순서 `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `calculatedAt`: 개별 Endpoint Risk와 동일한 기준 시각

`HIGH`와 `CRITICAL` count는 서로 중복하지 않는다.

## 5. Threat Level

### 5.1 입력

- `highestEndpointRiskScore`: Endpoint가 없으면 계산 입력에서 `0`
- `highRiskEndpointCount`: level이 정확히 HIGH인 수
- `criticalRiskEndpointCount`: level이 정확히 CRITICAL인 수
- `openIncidentCount`: 현재 OPEN Incident 전체 수
- `criticalOpenAlertCount`: 현재 `OPEN/IN_PROGRESS`이면서 severity가 CRITICAL인 Alert 전체 수

### 5.2 점수 공식

```text
highestRiskContribution = highestEndpointRiskScore * 0.70
highEndpointContribution = min(highRiskEndpointCount * 3, 15)
criticalEndpointContribution = min(criticalRiskEndpointCount * 10, 20)
openIncidentContribution = min(openIncidentCount * 3, 15)
criticalAlertContribution = min(criticalOpenAlertCount * 5, 20)

threatRawScore =
    highestRiskContribution
  + highEndpointContribution
  + criticalEndpointContribution
  + openIncidentContribution
  + criticalAlertContribution

threatLevel.score = roundHalfUp(min(threatRawScore, 100))
```

### 5.3 Threat status

| score | status |
| ---: | --- |
| 0~24 | `GREEN` |
| 25~59 | `YELLOW` |
| 60~100 | `RED` |

### 5.4 Threat reason code

| 조건 | reason code |
| --- | --- |
| 최고 Endpoint Risk level이 `MEDIUM` | `MEDIUM_ENDPOINT_RISK` |
| `highRiskEndpointCount > 0` | `HIGH_ENDPOINT_RISK` |
| `criticalRiskEndpointCount > 0` | `CRITICAL_ENDPOINT_RISK` |
| `openIncidentCount > 0` | `OPEN_INCIDENT` |
| `criticalOpenAlertCount > 0` | `CRITICAL_ALERT` |

reason code는 조건이 참일 때 한 번만 포함한다. 최고 Endpoint Risk가 LOW이고 나머지 조건도 없으면 `reasonCodes: []`다.

## 6. Collection Health

Collection Health는 UI time filter를 사용하지 않는다. Failure 입력만 내부 고정 window인 최근 15분 `[calculatedAt-15m, calculatedAt)`을 사용한다.

### 6.1 Endpoint 상태 contribution

RETIRED가 아닌 Endpoint만 사용한다.

```text
staleCount = isStale=true인 Endpoint 수
offlineNonStaleCount = status=OFFLINE AND isStale=false인 Endpoint 수

staleContribution = min(staleCount * 35, 70)
offlineContribution = min(offlineNonStaleCount * 20, 40)
```

STALE Endpoint는 OFFLINE contribution에 중복 포함하지 않는다.

### 6.2 Sensor contribution

현재 Endpoint별 `sensorHealth` snapshot을 사용한다. 동일 Endpoint와 sensor 조합은 한 번만 센다. RETIRED Endpoint sensor는 제외한다.

```text
degradedContribution = min(degradedSensorCount * 10, 20)
unavailableContribution = min(unavailableSensorCount * 25, 50)
```

### 6.3 Ingest 지연 contribution

non-retired Endpoint가 없으면 ingest 지연 contribution은 `0`이다.

non-retired Endpoint가 하나 이상이고 `latestIngestedAt=null`이면 contribution은 `40`이다. 그 외에는 `calculatedAt - latestIngestedAt`을 사용한다.

| 지연 | contribution |
| --- | ---: |
| 2분 이하 | 0 |
| 2분 초과~5분 | 10 |
| 5분 초과~15분 | 25 |
| 15분 초과 | 40 |

정확히 2분, 5분, 15분은 낮은 구간에 포함한다.

### 6.4 Failure contribution

ClickHouse `event_failures`에서 `failure_id`별 최신 row를 선택하고 최근 15분의 현재 상태를 센다.

```text
failedContribution = min(FAILED count * 5, 20)
reprocessFailedContribution = min(REPROCESS_FAILED count * 10, 20)
```

`REPROCESSED`는 collection penalty에 포함하지 않는다.

### 6.5 Storage contribution

PostgreSQL `ingest_metadata`의 현재 `RESTORE_FAILED` S3 bucket 수를 사용한다.

```text
storageContribution = min(RESTORE_FAILED bucket count * 20, 40)
```

`EXPIRED`는 정상적인 재복원 필요 상태이므로 storage failure penalty에 포함하지 않는다.

### 6.6 최종 Collection Health score

```text
collectionRawScore =
    staleContribution
  + offlineContribution
  + degradedContribution
  + unavailableContribution
  + ingestDelayContribution
  + failedContribution
  + reprocessFailedContribution
  + storageContribution

collectionHealth.score = roundHalfUp(min(collectionRawScore, 100))
```

### 6.7 Collection Health status

| score | status |
| ---: | --- |
| 0~19 | `GREEN` |
| 20~49 | `YELLOW` |
| 50~100 | `RED` |

### 6.8 Collection reason code

| 조건 | reason code |
| --- | --- |
| `offlineNonStaleCount > 0` | `OFFLINE_ENDPOINT` |
| `staleCount > 0` | `STALE_ENDPOINT` |
| `degradedSensorCount > 0` | `DEGRADED_SENSOR` |
| `unavailableSensorCount > 0` | `UNAVAILABLE_SENSOR` |
| ingest 지연 contribution `> 0` | `INGEST_DELAYED` |
| `FAILED count > 0` 또는 `REPROCESS_FAILED count > 0` | `INGEST_FAILURE` |
| `RESTORE_FAILED bucket count > 0` | `STORAGE_FAILURE` |

## 7. 최종 EDR 상태 결합

```text
edrState.score = max(threatLevel.score, collectionHealth.score)

status priority:
RED > YELLOW > GREEN

edrState.status = threatLevel.status와 collectionHealth.status 중 더 높은 우선순위
```

`edrState.reasonCodes`는 두 축의 reason code 합집합이다. 중복을 제거하고 `API_SPEC.md`의 `EdrStateReasonCode` enum 선언 순서로 정렬한다. 원인이 없으면 `[]`다.

`highestEndpointRiskScore`, `highRiskEndpointCount`, `criticalRiskEndpointCount`는 같은 snapshot의 Endpoint Risk summary 값을 그대로 사용한다.

## 8. 검증 예시

### 8.1 Endpoint Risk

대표 Alert riskScore가 70, 60, 40이고 OPEN Incident가 1개인 경우:

```text
A1 = 70
A2 = roundHalfUp(60 * 0.25) = 15
A3 = roundHalfUp(40 * 0.10) = 4
Incident = 10
score = 99
level = CRITICAL
```

### 8.2 Clamp와 factor 합계

대표 Alert riskScore가 90, 80이고 OPEN Incident가 1개인 경우:

```text
A1 = 90
A2 = 20
raw running total = 110

A2 effective contribution = 10
score = 100
이후 Incident factor는 반환하지 않음
```

### 8.3 EDR 상태

Threat score가 64, Collection Health score가 35이면:

```text
edrState.score = 64
edrState.status = RED
```

## 9. 필수 테스트 경계

- 활성 데이터가 전혀 없는 Endpoint는 score 0, LOW, 빈 factor다.
- 동일 Rule Alert 중 대표 Alert가 결정적으로 선택된다.
- A2/A3 가중치와 ROUND_HALF_UP 결과가 고정된다.
- factor contribution 합계가 score와 같다.
- score 24/25/49/50/79/80/100 경계가 정확하다.
- RETIRED Endpoint risk는 계산되지만 Collection Health에서는 제외된다.
- STALE Endpoint가 OFFLINE contribution에 중복 포함되지 않는다.
- ingest 지연 2/5/15분 경계가 정확하다.
- non-retired Endpoint가 없을 때 `latestIngestedAt=null`은 penalty가 아니다.
- Failure는 최근 15분과 `failure_id`별 최신 row만 사용한다.
- 최종 EDR 상태는 두 축 중 더 나쁜 status와 더 높은 score를 사용한다.

## 10. 변경 관리

공식이나 임계값을 변경할 때는 이 문서를 먼저 갱신하고 Backend 단위 테스트와 API contract fixture를 함께 변경한다. 정책 변경만으로 새 REST API, 새 enum literal, 새 저장 테이블을 추가하지 않는다. API 응답 shape 변경이 필요한 경우에만 `API_SPEC.md`를 별도로 변경한다.
