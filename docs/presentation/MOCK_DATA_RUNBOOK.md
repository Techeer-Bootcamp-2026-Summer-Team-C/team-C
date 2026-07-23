# EDR_C 시연 데이터 준비 Runbook

이 Runbook의 데이터와 수치는 시연을 위해 재현한 local/QA 데이터다. production 실측이나 실제 침해 기록으로 표현하지 않는다.

모든 destructive 명령은 `--confirm-reset`을 요구하고 `EDR_ENV=local|qa`, 허용된 demo database 이름,
local host를 함께 검증한다. 원격 QA database가 필요하면 `EDR_ENV=qa`와
`EDR_SEED_ALLOWED_QA_HOSTS=qa-db.example.internal,qa-clickhouse.example.internal`처럼 정확한 hostname
allowlist를 명시한다. 이름에 `qa` 또는 `test`가 포함됐다는 이유만으로 원격 host를 허용하지 않는다.

## 1. presentation profile

서비스를 먼저 실행한다.

```powershell
uv run python -m tools.local_demo start
```

삭제 범위와 예상 count를 확인한다. `--dry-run`은 DB를 변경하지 않는다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor now --dry-run
```

PostgreSQL과 ClickHouse의 local/QA 데이터를 초기화하고 `5 Endpoint / 14일 5,600 Event / 3 Alert / 1 Incident`를 생성한다. 최근 24시간은 400 Event, 최근 7일은 2,800 Event다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor now --confirm-reset
```

실제 Dashboard API로 count와 관계를 검증한다.

```powershell
uv run python -m tools.verify_presentation_demo --manifest runtime/demo/presentation-manifest.json
```

로그인은 `frontend-admin / frontend-admin-password`를 사용한다. manifest에는 실행 후 결정된 Endpoint·Alert·Incident ID와 시연 URL이 기록된다.

### 배포된 멘토 전용 사이트

이 절차는 기존 PostgreSQL·ClickHouse 내용을 전부 삭제한다. 서비스가 멘토 시연 전용이고 전체 초기화가 승인된 경우에만 사용한다. 기존 데이터 보존이나 live rollback을 성공 조건으로 약속하지 않으며, 실패 시 복구 방식은 동일한 seed와 anchor를 사용한 결정적 재주입이다. 기존 production guard를 `EDR_ENV=qa`로 속여 우회하지 않는다.

#### 1. 배포와 runtime을 고정한다

초기화 기능이 포함된 Backend image SHA가 배포됐는지 먼저 확인한다. 이후 초기화가 끝날 때까지 stack을 다시 배포하거나 환경 변수를 바꾸지 않는다.

실제 Agent가 모두 중지됐고 자동 재시작되지 않는지 확인한다. Nginx를 다시 열기 전에도 같은 상태를 재확인해야 한다. 실제 Agent가 별도 경로로 Collector에 직접 접근할 수 있다면 그 경로도 먼저 차단한다.

Backend Console에서 production opt-in과 이 배포만 가리키는 고유 target ID를 설정한다. 아래 ID는 이 멘토 전용 배포에서만 사용하며, 다른 배포를 초기화할 때 재사용하지 않는다.

```bash
export EDR_PRODUCTION_DEMO_RESET_MODE=FULL_RESET_DEDICATED_MENTOR_DEMO
export EDR_DEMO_RESET_TARGET_ID=mentor-demo-team-c-prod-20260723
export EDR_DASHBOARD_BASE_URL=https://tukproject.dev
export DEMO_ANCHOR="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

fingerprint에는 다음 runtime context가 포함된다. Portainer stack과 Backend Console의 값이 정확히 같은지 확인한다. 기본값이 아닌 값을 운영 중이라면 기본값으로 덮어쓰지 말고 실제 배포 값을 유지한다.

| 환경 변수 | 이 배포의 예상값 |
| --- | --- |
| `EDR_KAFKA_BOOTSTRAP_SERVERS` | `kafka:29092` |
| `EDR_KAFKA_RAW_TOPIC` | `telemetry.raw` |
| `EDR_KAFKA_VALIDATED_TOPIC` | `telemetry.validated` |
| `EDR_EVENT_STORAGE_CONSUMER_GROUP` | `edr-event-storage-v1` |
| `EDR_DETECTION_CONSUMER_GROUP` | `edr-detection-v1` |
| `EDR_S3_BUCKET` | Portainer stack에 설정된 기존 private bucket의 정확한 이름 |

빈 값이나 문서 placeholder를 사용하면 초기화가 거부된다. 다음 명령은 값을 출력하지 않고 여섯 항목이 모두 설정됐는지만 확인한다.

```bash
: "${EDR_KAFKA_BOOTSTRAP_SERVERS:?missing EDR_KAFKA_BOOTSTRAP_SERVERS}"
: "${EDR_KAFKA_RAW_TOPIC:?missing EDR_KAFKA_RAW_TOPIC}"
: "${EDR_KAFKA_VALIDATED_TOPIC:?missing EDR_KAFKA_VALIDATED_TOPIC}"
: "${EDR_EVENT_STORAGE_CONSUMER_GROUP:?missing EDR_EVENT_STORAGE_CONSUMER_GROUP}"
: "${EDR_DETECTION_CONSUMER_GROUP:?missing EDR_DETECTION_CONSUMER_GROUP}"
: "${EDR_S3_BUCKET:?missing EDR_S3_BUCKET}"
```

DB DSN이나 비밀번호는 확인을 위해 출력하거나 채팅에 붙여 넣지 않는다.

#### 2. 유입을 막고 consumer를 비운다

Portainer에서 다음 순서를 지킨다.

1. HTTP 8080과 mTLS 8443 유입을 함께 막기 위해 Nginx를 가장 먼저 중지한다.
2. `storage-lifecycle-worker`를 즉시 중지한다.
3. `event-storage-worker`와 `detection-worker`는 아직 실행한 채 남은 메시지를 처리하게 한다.
4. Kafka Console에서 두 consumer group의 모든 partition `LAG`가 0인지 확인한다.

```bash
/opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:29092 \
  --group edr-event-storage-v1 \
  --describe

/opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:29092 \
  --group edr-detection-v1 \
  --describe
```

5. lag가 0인 상태에서 Worker log에 새 처리 작업이 들어오지 않는지 확인한다.
6. `event-storage-worker`, `detection-worker` 순으로 중지한다.
7. Backend는 외부에서 접근할 수 없는 상태로 두고 Console 실행에만 사용한다.

#### 3. dry-run 후 같은 target을 초기화한다

Backend Console에서 대상 fingerprint와 count를 확인한다. 이 명령은 DB를 변경하지 않는다.

```bash
python -m tools.seed_presentation_demo \
  --profile presentation \
  --seed 20260721 \
  --anchor "$DEMO_ANCHOR" \
  --production-demo-reset \
  --output-manifest /tmp/edr-c-demo/presentation-manifest.json \
  --dry-run
```

직전 출력의 `target fingerprint`를 그대로 넣어 실행한다. fingerprint, 두 확인문과 `--confirm-reset` 중 하나라도 다르면 DB 연결 전에 거부된다.

```bash
read -r -p "Dry-run target fingerprint: " DEMO_TARGET_FINGERPRINT

python -m tools.seed_presentation_demo \
  --profile presentation \
  --seed 20260721 \
  --anchor "$DEMO_ANCHOR" \
  --production-demo-reset \
  --output-manifest /tmp/edr-c-demo/presentation-manifest.json \
  --confirm-reset \
  --confirm-production-demo-reset FULL_RESET_DEDICATED_MENTOR_DEMO \
  --confirm-runtime-stopped INGRESS_AND_WORKERS_STOPPED \
  --target-fingerprint "$DEMO_TARGET_FINGERPRINT"
```

초기화 또는 검증이 중간에 실패하면 Nginx와 세 Worker를 중지한 상태로 유지한다. 환경 변수, `20260721` seed, `DEMO_ANCHOR`, dry-run에서 확인한 fingerprint를 바꾸지 말고 같은 명령을 다시 실행한다. 이 재주입은 승인된 wipe 이후의 시연 상태를 다시 만드는 절차이며, 삭제 전 live 데이터로 되돌리는 rollback 절차가 아니다.

#### 4. 사용자가 정한 ADMIN을 만든다

Production demo reset은 고정 `frontend-admin`·`frontend-viewer` 계정을 만들지 않는다. 완료 후 사용자가 정한 ADMIN ID로 계정을 별도 생성하고 비밀번호를 두 번 입력한다. 운영 ADMIN 비밀번호는 최소 16자다.

```bash
read -r -p "Mentor login ID: " MENTOR_LOGIN_ID

python -m tools.create_admin \
  --login-id "$MENTOR_LOGIN_ID" \
  --name "Mentor Evaluator"
```

비밀번호는 Backend Console의 대화형 prompt에 직접 입력한다. 비밀번호를 명령 인자, 환경 변수, manifest, 로그 또는 채팅에 붙여 넣지 않는다. 생성 결과의 `user_id`는 발표 후 제거 절차에 필요하므로 비밀이 아닌 운영 기록에 보관한다.

계정 생성 후 Backend Console에서 API 결과를 검증한다. 이 명령에서도 비밀번호는 prompt에 직접 입력한다.

```bash
python -m tools.verify_presentation_demo \
  --manifest /tmp/edr-c-demo/presentation-manifest.json \
  --api-base-url http://127.0.0.1:8000 \
  --login-id "$MENTOR_LOGIN_ID" \
  --prompt-password
```

#### 5. 멘토 사이트만 다시 연다

검증이 끝나면 실제 Agent가 여전히 중지됐고 다시 연결되지 않을 상태인지 재확인한다. 그다음 `event-storage-worker`, `detection-worker`를 시작하고 Nginx를 마지막에 시작한다.

`storage-lifecycle-worker`는 seed의 고정 Endpoint와 archive key에 영향을 줄 수 있으므로 멘토 시연이 끝날 때까지 계속 중지한다. 공개 `/nginx-health`, `/health/ready`, 사용자 지정 ADMIN 로그인과 주요 시연 화면을 각각 확인한다.

#### 6. 발표 직후 임시 ADMIN을 제거한다

Backend Console에서 생성 시 출력된 정확한 `user_id`와 사용자가 정한 login ID를 넣는다. 먼저 대상을 조회하고, 비활성화한 다음 soft-delete한다. 초기화 후 이 계정이 유일한 ACTIVE ADMIN이므로 비활성화 명령에는 마지막 ADMIN 제거 확인문이 필요하다.

```bash
read -r -p "Created ADMIN user_id: " MENTOR_USER_ID
read -r -p "Mentor login ID: " MENTOR_LOGIN_ID

python -m tools.manage_admin inspect \
  --user-id "$MENTOR_USER_ID"

python -m tools.manage_admin disable \
  --user-id "$MENTOR_USER_ID" \
  --confirm-login-id "$MENTOR_LOGIN_ID" \
  --confirm-environment production \
  --operator demo-owner \
  --reason "mentor-demo-ended" \
  --confirm-last-admin-removal ALLOW_NO_ACTIVE_ADMIN

python -m tools.manage_admin soft-delete \
  --user-id "$MENTOR_USER_ID" \
  --confirm-login-id "$MENTOR_LOGIN_ID" \
  --confirm-environment production \
  --operator demo-owner \
  --reason "mentor-demo-ended"
```

마지막으로 같은 `inspect` 명령을 다시 실행해 `status`가 `DISABLED`, `isDelete`가 `true`인지 확인한다. 이후 Nginx를 중지하고, 일반 운영으로 되돌릴 계획이 확정되기 전에는 `storage-lifecycle-worker`를 임의로 재시작하지 않는다.

## 2. 시연 클릭 순서

1. manifest의 `urls.overview`를 열고 `LATEST_24H`에서 400 Event, 3 Alert, 1 open Incident를 확인한다.
2. 기간을 `LATEST_7D`로 바꿔 2,800 Event를 확인한 뒤 `LATEST_24H`로 돌아온다.
3. Highest-risk Endpoint `SOYEON-WIN`을 연다.
4. Endpoint 화면의 `최근 Event 열기`를 눌러 최근 24시간 85개 Timeline을 확인한다.
5. Minecraft shader 설치 파일 → Encoded PowerShell 2회 → 외부 통신 순서를 확인한다.
6. Overview 또는 Incident 목록에서 manifest의 `chainIncidentId`에 해당하는 Incident를 연다.
7. `Attack Timeline`과 연결 Alert 표에서 `PROC_POWERSHELL_ENCODED` Alert 2개와 `NET_SUSPICIOUS_EGRESS` Alert 1개를 확인한다.
8. 세 Alert의 원본 Event를 열어 같은 Endpoint와 같은 30분 window인지 확인한다.
9. TLS Event의 `tlsSni=update-cache.test`와 Incident의 `powershell-tls-egress-chain` correlation key를 확인한다.

## 3. DNS correctness profile

이 profile도 destructive reset이므로 presentation profile과 동시에 유지되지 않는다. 시연 직전이 아니라 Screenshot·녹화 준비 시 별도로 실행한다.

```powershell
uv run python -m tools.seed_presentation_demo --profile dns-correctness --seed 20260721 --anchor now --dry-run
uv run python -m tools.seed_presentation_demo --profile dns-correctness --seed 20260721 --anchor now --confirm-reset
uv run python -m tools.verify_presentation_demo --manifest runtime/demo/dns-correctness-manifest.json
```

Intelligence에서 `yahoo.com`을 조회한다. `yahoo.com`, `mail.yahoo.com`, `api.yahoo.com`만 관찰 범위에 포함되고 `notyahoo.com`, `yahoo.com.evil.example`, `yahoo.co`는 제외돼야 한다.

## 4. direct seed와 실제 Kafka Pipeline의 차이

기본 `direct-seed`는 시연 상태를 빠르고 결정적으로 복원한다. Event는 ClickHouse repository로, Alert·Incident는 현재 Rule loader와 Detection engine 및 PostgreSQL repository로 생성한다. Kafka 처리 증거로 사용하지 않는다.

Collector·Kafka·Worker가 모두 정상일 때만 실제 주입 모드를 사용한다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor now --emit-through-collector --wait-timeout-seconds 90 --confirm-reset
```

이 모드는 local 개발 CA로 profile별 mTLS Agent 인증서를 발급하고 Collector broker ACK 이후 ClickHouse·PostgreSQL의 최종 count를 polling한다. Collector의 accepted 응답 자체를 Detection 완료로 해석하지 않는다. manifest의 `ingestionMode`로 실행 경로를 확인한다.

## 5. 고정 anchor와 녹화 fallback

녹화에는 고정 RFC 3339 anchor를 사용해 Event 순서와 ID를 재현한다. 녹화 직후에는 같은 고정 anchor로 다시 seed하고 manifest URL이 재생되는지 확인한다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor 2026-07-21T12:00:00Z --confirm-reset
```

### fallback 영상

- 최종본: `output/playwright/presentation-demo-final-1280x720.webm`
- 규격: WebM(VP8), 1280×720, 68.28초
- 포함 동선: Overview 400/3/1과 5 Endpoint → 최근 7일 2,800 → `SOYEON-WIN` → 최근 24시간 85 Event와 Minecraft Timeline → PowerShell/TLS Incident(Alert 3개)
- 기존 3 Endpoint·64 Event 녹화본은 새 데이터 설계의 fallback으로 사용하지 않는다.
- 로그인 비밀번호 입력 장면, `.env`, 인증서 private key, production 화면은 포함하지 않는다.

단, 고정 anchor가 현재 시각 기준 24시간 밖이면 Overview의 `LATEST_24H`에는 보이지 않는다. 고정 녹화에서는 manifest의 CUSTOM 범위 URL을 사용하고, 라이브 시연 직전에는 `--anchor now`로 재생성한다.

fallback 영상은 Intro, presentation Dashboard 조사, DNS correctness를 별도 클립으로 준비한다. 로그인 비밀번호 입력 장면, `.env`, 인증서 private key, production 화면은 녹화하지 않는다.
