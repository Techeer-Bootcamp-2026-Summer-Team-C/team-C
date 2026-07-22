# EDR_C 시연 데이터 준비 Runbook

이 Runbook의 데이터와 수치는 시연을 위해 재현한 local/QA 데이터다. production 실측이나 실제 침해 기록으로 표현하지 않는다.

## 1. presentation profile

서비스를 먼저 실행한다.

```powershell
uv run python -m tools.local_demo start
```

삭제 범위와 예상 count를 확인한다. `--dry-run`은 DB를 변경하지 않는다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor now --dry-run
```

PostgreSQL과 ClickHouse의 local/QA 데이터를 초기화하고 `5 Endpoint / 14일 5,600 Event / 3 Alert / 2 Incident`를 생성한다. 최근 24시간은 400 Event, 최근 7일은 2,800 Event다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor now --confirm-reset
```

실제 Dashboard API로 count와 관계를 검증한다.

```powershell
uv run python -m tools.verify_presentation_demo --manifest runtime/demo/presentation-manifest.json
```

로그인은 `frontend-admin / frontend-admin-password`를 사용한다. manifest에는 실행 후 결정된 Endpoint·Alert·Incident ID와 시연 URL이 기록된다.

## 2. 시연 클릭 순서

1. manifest의 `urls.overview`를 열고 `LATEST_24H`에서 400 Event, 3 Alert, 2 open Incident를 확인한다.
2. 기간을 `LATEST_7D`로 바꿔 2,800 Event를 확인한 뒤 `LATEST_24H`로 돌아온다.
3. Highest-risk Endpoint `SOYEON-WIN`을 연다.
4. Endpoint 화면의 `최근 Event 열기`를 눌러 최근 24시간 85개 Timeline을 확인한다.
5. Minecraft shader 설치 파일 → Encoded PowerShell 2회 → 외부 통신 순서를 확인한다.
6. Overview 또는 Incident 목록에서 manifest의 `powershellIncidentId`에 해당하는 Incident를 연다.
7. `Attack Timeline`과 연결 Alert 표에서 같은 `PROC_POWERSHELL_ENCODED` Alert 2개를 확인한다.
8. 두 Alert의 원본 Event를 열어 같은 Endpoint와 같은 30분 window인지 확인한다.
9. 같은 Minecraft 사고 케이스를 구성하는 `suspicious-egress` Incident와 `NET_SUSPICIOUS_EGRESS` Alert가 시스템상 별도로 존재하는지 확인한다.

## 3. DNS correctness profile

이 profile도 destructive reset이므로 presentation profile과 동시에 유지되지 않는다. 시연 직전이 아니라 Screenshot·녹화 준비 시 별도로 실행한다.

```powershell
uv run python -m tools.seed_presentation_demo --profile dns-correctness --seed 20260721 --anchor now --dry-run
uv run python -m tools.seed_presentation_demo --profile dns-correctness --seed 20260721 --anchor now --confirm-reset
uv run python -m tools.verify_presentation_demo --manifest runtime/demo/dns-correctness-manifest.json
```

Intelligence에서 `yahoo.com`을 조회한다. `yahoo.com`, `mail.yahoo.com`, `api.yahoo.com`만 관찰 범위에 포함되고 `notyahoo.com`, `yahoo.com.evil.example`, `yahoo.co`는 제외돼야 한다.

## 4. 248,000 Event 성능 profile

시연 직전에는 실행하지 않는다. 먼저 계산만 확인한다.

```powershell
uv run python tools/seed_dashboard_long_range.py --days 31 --endpoints 100 --events-per-endpoint-day 80 --seed 20260715 --dry-run
```

출력의 `Events`가 `248,000`인지 확인한 뒤, 성능 측정용 local/QA 환경에서만 실행한다.

```powershell
uv run python tools/seed_dashboard_long_range.py --days 31 --endpoints 100 --events-per-endpoint-day 80 --seed 20260715 --confirm-reset
```

기존 long-range 도구는 먼저 작은 base fixture를 넣고 248,000개 생성 Event를 추가한다. 따라서 `Events added: 248,000`은 추가 생성량이며 DB 전체 row 수와 동일하다고 표현하지 않는다.

## 5. direct seed와 실제 Kafka Pipeline의 차이

기본 `direct-seed`는 시연 상태를 빠르고 결정적으로 복원한다. Event는 ClickHouse repository로, Alert·Incident는 현재 Rule loader와 Detection engine 및 PostgreSQL repository로 생성한다. Kafka 처리 증거로 사용하지 않는다.

Collector·Kafka·Worker가 모두 정상일 때만 실제 주입 모드를 사용한다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor now --emit-through-collector --wait-timeout-seconds 90 --confirm-reset
```

이 모드는 local 개발 CA로 profile별 mTLS Agent 인증서를 발급하고 Collector broker ACK 이후 ClickHouse·PostgreSQL의 최종 count를 polling한다. Collector의 accepted 응답 자체를 Detection 완료로 해석하지 않는다. manifest의 `ingestionMode`로 실행 경로를 확인한다.

## 6. 고정 anchor와 녹화 fallback

녹화에는 고정 RFC 3339 anchor를 사용해 Event 순서와 ID를 재현한다. 녹화 직후에는 같은 고정 anchor로 다시 seed하고 manifest URL이 재생되는지 확인한다.

```powershell
uv run python -m tools.seed_presentation_demo --profile presentation --seed 20260721 --anchor 2026-07-21T12:00:00Z --confirm-reset
```

### fallback 영상

- 최종본: `output/playwright/presentation-demo-final-1280x720.webm`
- 규격: WebM(VP8), 1280×720, 68.28초
- 포함 동선: Overview 400/3/2와 5 Endpoint → 최근 7일 2,800 → `SOYEON-WIN` → 최근 24시간 85 Event와 Minecraft Timeline → PowerShell Incident(Alert 2개) → 별도 Egress Incident
- 기존 3 Endpoint·64 Event 녹화본은 새 데이터 설계의 fallback으로 사용하지 않는다.
- 로그인 비밀번호 입력 장면, `.env`, 인증서 private key, production 화면은 포함하지 않는다.

단, 고정 anchor가 현재 시각 기준 24시간 밖이면 Overview의 `LATEST_24H`에는 보이지 않는다. 고정 녹화에서는 manifest의 CUSTOM 범위 URL을 사용하고, 라이브 시연 직전에는 `--anchor now`로 재생성한다.

fallback 영상은 Intro, presentation Dashboard 조사, DNS correctness를 별도 클립으로 준비한다. 로그인 비밀번호 입력 장면, `.env`, 인증서 private key, production 화면은 녹화하지 않는다.
