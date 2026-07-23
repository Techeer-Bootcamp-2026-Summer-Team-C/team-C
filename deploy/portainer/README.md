# Portainer 배포 순서

이 디렉터리의 인프라·서비스·관측 Compose는 EC2의 Portainer Agent 환경에 배포한다. Mac mini의 Portainer Server는 `compose.portainer-server.yaml`을 `/Users/geonha/portainer/docker-compose.yml`로 동기화해 별도로 실행한다. Vercel 프론트엔드는 이 범위에서 관리하지 않는다. PostgreSQL, ClickHouse, Kafka는 `edr-c-infra`, 백엔드와 워커, Nginx는 `edr-c-service`로 분리한다.

운영 배포의 소스 오브 트루스는 다음 다섯 파일이다.

- `compose.infra.yaml`
- `compose.service.yaml`
- `compose.observability.yaml`
- `compose.portainer-agent.yaml`
- `compose.portainer-server.yaml`

Portainer에 입력할 변수 이름은 `env.infra.example`, `env.service.example`, `env.observability.example`을 참고한다. 예시 파일에는 비밀값을 넣지 않으며 실제 값은 Portainer 환경 변수로만 관리한다.

현재 저장소 변경을 GitHub에 올리기 전에는 아래 명령을 실행하지 않는다.

## 1. 기존 데이터 볼륨 확인

기존 EC2를 계속 사용한다면 새 PostgreSQL 볼륨을 먼저 만들면 안 된다. 현재 데이터가 들어 있는 볼륨 이름부터 확인한다.

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker inspect <현재-postgres-컨테이너명> --format '{{range .Mounts}}{{println .Name .Destination}}{{end}}'
docker inspect <현재-clickhouse-컨테이너명> --format '{{range .Mounts}}{{println .Name .Destination}}{{end}}'
docker inspect <현재-kafka-컨테이너명> --format '{{range .Mounts}}{{println .Name .Destination}}{{end}}'
```

출력된 실제 볼륨 이름을 각각 `POSTGRES_VOLUME_NAME`, `CLICKHOUSE_VOLUME_NAME`, `KAFKA_VOLUME_NAME`으로 사용한다. 기존 스택을 삭제하거나 볼륨을 새로 만들기 전에 데이터 백업을 먼저 완료한다.

완전히 새 EC2이고 기존 데이터가 없을 때만 다음처럼 새 볼륨을 만든다.

```bash
docker volume create edr-c-postgres-data
docker volume create edr-c-clickhouse-data
docker volume create edr-c-kafka-data
```

이 경우 Portainer 환경 변수의 볼륨 이름도 위 세 이름으로 설정한다.

## 2. 공유 네트워크와 TLS 디렉터리 준비

두 스택이 같은 데이터 서비스를 찾도록 외부 네트워크를 한 번만 만든다.

```bash
docker network inspect edr-c-data >/dev/null 2>&1 || docker network create edr-c-data
```

Nginx 인증서는 EC2의 고정 절대 경로에 둔다.

```bash
sudo install -d -m 700 /etc/edr-c/tls
sudo ls -la /etc/edr-c/tls
```

배포 전 다음 세 파일이 있어야 한다.

- `/etc/edr-c/tls/server.crt`
- `/etc/edr-c/tls/server.key`
- `/etc/edr-c/tls/agent-ca.crt`

Compose는 이 디렉터리가 없으면 자동 생성하지 않고 실패하도록 설정되어 있다. 잘못된 빈 디렉터리로 Nginx가 시작되는 것을 막기 위한 동작이다.

## 3. GitHub 이미지 빌드 확인

`main`에 변경이 반영되면 GitHub Actions의 `Build production images`가 두 이미지를 GHCR에 올린다.

- `ghcr.io/techeer-bootcamp-2026-summer-team-c/team-c-backend:<커밋-SHA>`
- `ghcr.io/techeer-bootcamp-2026-summer-team-c/team-c-nginx:<커밋-SHA>`

두 matrix job이 모두 성공한 뒤 전체 40자리 커밋 SHA를 복사한다. `latest`나 브랜치 이름은 사용하지 않는다.

이미지가 비공개라면 Portainer의 `Registries`에 `ghcr.io`를 등록한다. GitHub 사용자명과 `read:packages` 권한이 있는 토큰을 사용하고, EC2 환경에서 이 레지스트리를 사용할 수 있게 연결한다. 토큰은 Git이나 Compose 파일에 저장하지 않는다.

## 4. 인프라 스택 배포

Portainer에서 Git repository 방식으로 스택을 만들고 Compose path를 다음으로 지정한다.

```text
deploy/portainer/compose.infra.yaml
```

스택 이름은 `edr-c-infra`로 하고 다음 환경 변수를 입력한다.

```text
POSTGRES_DB=edr
POSTGRES_USER=<값>
POSTGRES_PASSWORD=<값>
CLICKHOUSE_DB=edr
CLICKHOUSE_USER=<값>
CLICKHOUSE_PASSWORD=<값>
POSTGRES_VOLUME_NAME=<1단계에서 확인한 실제 볼륨 이름>
CLICKHOUSE_VOLUME_NAME=<1단계에서 확인한 실제 볼륨 이름>
KAFKA_VOLUME_NAME=<1단계에서 확인한 실제 볼륨 이름>
```

배포 후 PostgreSQL, ClickHouse, Kafka 세 컨테이너가 모두 `healthy`가 될 때까지 기다린다. 이 스택에는 외부 공개 포트가 없다.

## 5. 서비스 스택 배포

두 번째 Git repository 스택의 Compose path는 다음과 같다.

```text
deploy/portainer/compose.service.yaml
```

스택 이름은 `edr-c-service`로 하고 다음 환경 변수를 입력한다.

```text
EDR_IMAGE_TAG=<3단계의 전체 40자리 커밋 SHA>
EDR_JWT_SECRET=<32자 이상의 임의 문자열>
EDR_POSTGRES_DSN=postgresql://<사용자>:<URL-인코딩한-비밀번호>@postgres:5432/<DB명>
EDR_CLICKHOUSE_DSN=http://<사용자>:<URL-인코딩한-비밀번호>@clickhouse:8123/<DB명>
EDR_AWS_REGION=ap-northeast-2
EDR_S3_BUCKET=<실제 S3 버킷 이름>
```

비밀번호에 `@`, `:`, `/`, `?`, `#`, `[`, `]` 같은 문자가 있으면 DSN 안의 비밀번호를 URL 인코딩해야 한다. EC2 인스턴스 역할로 S3에 접근하므로 AWS Access Key와 Secret Key는 입력하지 않는다.

> 운영 `edr-c-service`는 현재 `refs/heads/production` 브랜치 + polling으로 자동 배포된다(7절 참조). production 브랜치의 compose는 이미지 SHA가 고정돼 있어 `EDR_IMAGE_TAG`는 CI가 자동으로 채운다. 이 스택을 재구성할 때는 repository reference를 `refs/heads/production`으로 두고 `EDR_IMAGE_TAG` 없이 나머지 비밀 변수만 입력한다.

필요할 때만 다음 포트를 기본값에서 바꾼다.

```text
NGINX_HTTP_HOST_PORT=8080
NGINX_MTLS_HOST_PORT=8443
```

`app-init`은 데이터 서비스 연결을 제한된 횟수만 재시도한 뒤 마이그레이션과 Kafka 토픽 준비를 수행한다. 정상 완료되면 `Exited (0)` 상태가 되는 것이 맞다. 그 다음 backend와 worker가 시작되고, backend가 healthy가 된 뒤 Nginx가 시작된다.

## 6. 배포 확인

아래 최소 체크리스트를 순서대로 확인한다.

1. GitHub Actions의 `Build production images`에서 `validate`, backend/Nginx build, `promote`가 모두 성공했는지 확인한다.
2. `production` 브랜치의 `compose.service.yaml`에 고정된 backend/Nginx 이미지 SHA가 성공한 `Build production images` 실행의 source commit SHA와 같은지 확인한다. 프런트엔드 전용 `main` 커밋은 이 워크플로를 실행하지 않으므로 최신 `main` SHA와 직접 비교하지 않는다.
3. Portainer에서 `app-init=Exited (0)`, backend/Nginx와 아래 worker 3개가 모두 `healthy`이고 재시작을 반복하지 않는지 확인한다.
   - `event-storage-worker`
   - `detection-worker`
   - `storage-lifecycle-worker`

Worker healthcheck는 단순 PID가 아니라 처리 loop heartbeat를 확인한다. Kafka worker는 15초, Storage Lifecycle Worker는 75초 넘게 heartbeat가 갱신되지 않으면 `unhealthy`가 된다.

EC2에서는 Nginx health를 확인한다.

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
curl --fail http://127.0.0.1:8080/nginx-health
```

4. 저장소 checkout이 있는 관리 PC에서 Mac mini를 경유해 Nginx, 애플리케이션 readiness, OpenAPI의 핵심 계약을 확인한다.

```powershell
powershell -File tools/verify_production_deployment.ps1 `
  -BaseUrl http://<EC2-Tailscale-IP>:8080 `
  -SshHost macmini
```

EC2에 저장소 checkout과 PowerShell이 실제로 설치된 경우에만 `-SshHost` 없이 `http://127.0.0.1:8080`을 사용한다. Portainer Git 스택을 사용한다고 해서 저장소 파일이 Agent 호스트에 존재한다고 가정하면 안 된다.

5. Frontend 변경이 포함됐다면 GitHub 커밋의 Vercel 상태가 `success`인지 확인하고, `https://tukproject.dev/login`에서 로그인 후 Overview API 데이터가 표시되는지 확인한다. 모든 확인이 끝난 뒤에만 이전 이미지를 정리한다.

## 7. 이후 서비스 업데이트

일반 서비스 배포에서는 인프라 스택을 건드리지 않는다.

`edr-c-service`는 2026-07-16부터 자동 배포된다: `main` push → GitHub Actions 이미지 빌드 → `promote` job이 `production` 브랜치에 이미지 SHA 고정 → Portainer가 `production`을 5분마다 polling해 자동 re-pull·재배포. 수동으로 `EDR_IMAGE_TAG`를 바꿀 필요가 없다.

배포 후 `/nginx-health`, `/health/ready`와 컨테이너 로그로 확인한다. 롤백이 필요하면 이전 이미지 SHA가 GHCR에 남아 있으므로 Portainer에서 해당 SHA로 재배포하면 된다.

운영 Nginx는 `/docs`, `/redoc`, `/openapi.json`을 외부에 공개하지 않고 404를 반환한다. OpenAPI artifact 생성과 Swagger 검증은 개발 환경에서 FastAPI에 직접 접근해 수행한다. `/health/*`는 운영 readiness 확인을 위해 계속 프록시한다.

외부 볼륨은 스택 수명주기와 분리되어 있어 스택을 다시 배포해도 자동 삭제되지 않는다. 그래도 기존 스택을 처음 전환하는 날에는 별도 백업 없이 삭제 작업을 진행하지 않는다.

## 이전 오류와 차단 방식

- 원격 BuildKit HTTP/2 오류: Portainer Compose에서 `build`, `context`, `dockerfile`을 사용하지 않고 GHCR 이미지의 커밋 SHA만 사용한다.
- `EDR_NGINX_CERT_DIR` 누락 오류: 환경 변수 대신 `/etc/edr-c/tls` 고정 절대 경로를 사용한다.
- `undefined volume -` 오류: Nginx 인증서 마운트를 Compose long syntax로 명시하고 모든 named volume을 최상위 `volumes`에 정의한다.
- 원격 Agent의 Git 상대 경로 bind 오류: Portainer 서버의 `/data/compose/...` 경로는 EC2에 존재하지 않으므로 repository 파일을 `configs.file`이나 bind mount로 전달하지 않는다. Alloy 설정은 Compose에 포함하고 컨테이너 내부에서 파일로 만든다.
- Alloy node exporter의 `/run/udev/data` 오류: 호스트의 udev 데이터 디렉터리를 같은 경로에 읽기 전용으로 mount하고 `create_host_path: false`로 잘못된 빈 디렉터리 생성을 막는다.

## 8. Grafana Cloud 연동

인프라와 서비스가 안정화된 뒤 세 번째 Git repository 스택을 만든다.

```text
deploy/portainer/compose.observability.yaml
```

스택 이름은 `edr-c-observability`로 하고 Grafana Cloud의 Metrics와 Logs 전송 정보를 입력한다.

```text
GRAFANA_CLOUD_METRICS_URL=<Prometheus remote_write URL>
GRAFANA_CLOUD_METRICS_USER=<Metrics username 또는 instance ID>
GRAFANA_CLOUD_LOGS_URL=<Loki push URL>
GRAFANA_CLOUD_LOGS_USER=<Logs username 또는 instance ID>
GRAFANA_CLOUD_TOKEN=<metrics:write와 logs:write 권한을 가진 access policy token>
```

토큰은 Git이나 Compose 파일에 저장하지 않고 Portainer 환경 변수로만 입력한다. Alloy는 외부 포트를 공개하지 않으며 `edr-c-data` 네트워크에서 Kafka와 backend readiness를 확인한다.

Portainer 서버와 Agent가 서로 다른 호스트이므로 repository의 상대 경로 파일을 EC2에 직접 mount하지 않는다. `compose.observability.yaml`은 Alloy 설정을 환경 변수로 전달하고 컨테이너 내부의 `/tmp/config.alloy`에 기록한 뒤 Alloy를 시작한다.

Docker 로그 discovery는 먼저 `edr-c-infra`, `edr-c-service`, `edr-c-observability` 프로젝트만 남긴 뒤 그 결과를 Loki source에 전달한다. 필터 규칙만 별도로 넘기지 말고 `discovery.relabel.docker_logs.output`을 사용해야 구형 demo와 monitoring 컨테이너 로그가 섞이지 않는다.

수집 범위는 다음과 같다.

- EC2 호스트 CPU, 메모리, 디스크, 네트워크 메트릭
- Docker 컨테이너 메트릭
- Kafka 브로커와 consumer group 메트릭
- backend readiness blackbox 메트릭
- `edr-c-infra`, `edr-c-service`, `edr-c-observability` 컨테이너 로그

Alloy가 Docker 컨테이너 메트릭과 로그를 읽기 위해 Docker socket을 읽기 전용으로 마운트한다. Docker socket 자체는 강한 권한을 제공하므로 이 스택의 관리 권한은 Portainer 관리자에게만 둔다.

Grafana Cloud에서 메트릭과 로그 유입을 확인하기 전에는 기존 `edr-monitoring` 스택을 제거하지 않는다. 2026-07-15에 Cloud 수집을 검증한 뒤 기존 로컬 Grafana와 Prometheus 컨테이너 및 미사용 이미지를 제거했다.

이미지 정리는 새 SHA 배포 검증 이후에만 수행한다. Portainer가 `Unused`로 표시한 이미지에 한해 삭제하고, 실행 중인 컨테이너의 이미지와 데이터 볼륨은 함께 삭제하지 않는다. 볼륨 정리는 백업과 스택별 매핑을 확인한 별도 작업으로 처리한다.

Vercel은 계속 Portainer 관리 범위 밖에 둔다.

## 9. Mac mini Portainer Server

Portainer Server는 `2.39.5-alpine`으로 고정하고 영속 volume `portainer_data`를 재사용한다. 컨테이너의 9443은 Mac mini loopback에만 바인딩하고 Tailscale Serve가 이를 tailnet 전용 HTTPS로 전달한다. 외부에 9000 HTTP를 계속 공개하지 않는다.

```bash
cp deploy/portainer/compose.portainer-server.yaml /Users/geonha/portainer/docker-compose.yml
cd /Users/geonha/portainer
docker compose up -d
tailscale serve --bg --yes https+insecure://localhost:9443
tailscale serve status
```

서버와 EC2의 표준 Agent는 같은 패치 버전을 사용한다. Server 또는 Agent를 올리기 전에는 `docs/operations/PORTAINER_BACKUP_RECOVERY.md`의 백업과 비파괴 복구 훈련을 먼저 수행한다.

## 10. EC2 Portainer Agent

Agent를 Portainer의 컨테이너 Duplicate/Edit 화면에서 직접 교체하지 않는다. 저장소의 `compose.portainer-agent.yaml`을 EC2의 `/home/ubuntu/portainer/docker-compose.yml`에 동기화한 뒤 SSH에서 Compose로 갱신한다. 새 이미지를 먼저 pull한 뒤 Compose를 갱신하면 pull 또는 검증 실패가 기존 Agent를 먼저 제거하지 않는다.

```bash
cd /home/ubuntu/portainer
docker compose pull portainer-agent
docker compose up -d --no-deps portainer-agent
docker compose ps
docker compose logs --tail 100 portainer-agent
```

Agent의 9001 포트는 EC2 보안 그룹에서 인터넷에 공개하지 않고 Mac mini와 EC2가 속한 tailnet 경로로만 접근한다. Server의 environment 주소도 EC2 Tailscale IP의 9001을 사용한다.
