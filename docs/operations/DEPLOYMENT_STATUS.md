# 운영 배포 현황

이 문서는 2026-07-15 KST 점검에서 확인한 스냅샷과 운영 절차를 기록한다. 실제 현재 상태는 Portainer의 컨테이너 이미지 태그와 라이브 health check를 다시 확인해야 한다.

## 결론

운영 배포의 기준은 Vercel이 아니라 EC2의 Portainer Agent 환경이다. Mac mini의 Portainer Server가 EC2 Agent를 관리하고, 애플리케이션은 GHCR에 빌드된 커밋 SHA 고정 이미지를 사용한다. Vercel은 다른 계정에서 관리되고 있어 이번 점검과 변경 범위에서 제외했다.

최종 점검 시점 운영 서비스는 이미지 빌드 커밋 `273fa115f5dacfa2efaf6bcf34cdb5ca64e37ec5`의 backend와 Nginx를 사용한다. 운영 Compose와 문서의 최신 `main`은 `d08a0b538b8d1e466bd62b450e8a03335e32e895`이며, 이 커밋은 이미지 빌드 대상 경로를 바꾸지 않아 별도 서비스 이미지를 만들지 않았다. backend와 Nginx는 `healthy`, PostgreSQL·ClickHouse·Kafka는 `healthy`, 두 worker와 Alloy, Portainer Agent는 `running`, 일회성 `app-init`은 정상 종료 상태인 `Exited (0)`이다. 워킹트리의 미커밋 변경은 운영 이미지에 포함되지 않는다.

## 배포 소스 오브 트루스

| 역할 | Portainer 스택 | Compose 파일 |
|---|---|---|
| 데이터 인프라 | `edr-c-infra` | `deploy/portainer/compose.infra.yaml` |
| API·worker·Nginx | `edr-c-service` | `deploy/portainer/compose.service.yaml` |
| Grafana Cloud 수집 | `edr-c-observability` | `deploy/portainer/compose.observability.yaml` |
| 원격 관리 Agent | `portainer` | EC2에서 별도 관리 |

단일 호스트 개발·데모 Compose나 Vercel 설정은 운영 Portainer 배포의 기준이 아니다. 환경 변수 이름은 `deploy/portainer/env.*.example`을 참고하고, 실제 비밀값은 Portainer에만 저장한다.

## 2026-07-15 적용 결과

- 최종 Git `main`과 `origin/main`: `d08a0b538b8d1e466bd62b450e8a03335e32e895`
- GitHub Actions `Build production images`: `273fa115f5dacfa2efaf6bcf34cdb5ca64e37ec5`의 backend와 Nginx 이미지 빌드 성공
- 서비스 스택의 `EDR_IMAGE_TAG`: 위 이미지 빌드 SHA로 갱신 후 pull/redeploy 성공
- 세 Git 기반 스택의 repository reference: 모두 `refs/heads/main`
- 관측 스택: Docker 로그 필터 결과를 실제 Loki source에 연결하고 `/run/udev/data`를 읽기 전용으로 마운트한 최신 Compose로 재배포
- Alloy: `running`, remote-write WAL 재생과 Kafka exporter 갱신 확인, `/run/udev/data` 오류 없음
- HTTP 검증: `/nginx-health` 200 `ok`, `/health/ready` 200 `ready`
- OpenAPI 검증: 25개 path, locale·dashboard layout·process tree 계약 포함
- 컨테이너: 30개에서 운영에 필요한 10개로 정리
- 이미지: 25개에서 실행 중인 7개 이미지로 정리하고 이전 `f13e554...` backend/Nginx 이미지 삭제
- 스택: 7개에서 운영 3개와 Portainer Agent 스택만 남겨 4개로 정리
- 네트워크: 연결이 없던 demo/local 네트워크 3개를 제거해 Docker 기본 3개와 운영 네트워크 3개만 유지
- 데이터 볼륨: 20개(사용 중 6개, 미사용 표시 14개), 백업 전에는 삭제하지 않음

삭제한 범위는 중단된 `edr-c-demo-*`, 생성만 되고 실행되지 않던 `edr-c-local-*`, Alloy/Grafana Cloud로 대체된 `edr-monitoring-*` 컨테이너와 그 뒤 미사용 상태가 된 이미지다. 운영 데이터 볼륨과 현재 이미지, Portainer Agent는 보존했다.

볼륨 이름만으로 사용 여부를 판단하면 안 된다. 현재 인프라는 이전 스택에서 생성된 `edr-c-demo-*` 또는 `edr-c-local_*` 이름의 일부 외부 볼륨을 실제 운영 데이터 볼륨으로 재사용한다. Portainer에서 `Unused` 표시가 없거나 현재 컨테이너에 연결된 볼륨은 이름이 오래돼 보여도 삭제하지 않는다.

## 표준 업데이트 절차

1. `main`의 GitHub Actions 이미지 빌드가 성공했는지 확인한다.
2. 전체 40자리 커밋 SHA를 `edr-c-service`의 `EDR_IMAGE_TAG`에 입력한다.
3. `Pull latest image`를 켜고 서비스 스택만 재배포한다.
4. `app-init=Exited (0)`, backend/Nginx=`healthy`, worker 2개=`running`을 확인한다.
5. 저장소 checkout이 있는 관리 PC에서 Mac mini를 경유해 공개 경로와 API 계약을 확인한다.

```powershell
powershell -File tools/verify_production_deployment.ps1 `
  -BaseUrl http://<EC2-Tailscale-IP>:8080 `
  -SshHost macmini
```

6. 새 배포가 안정적인 것을 확인한 뒤에만 이전 SHA 이미지 중 Portainer가 `Unused`로 표시하는 항목을 제거한다.

## 남은 운영 과제

### 우선순위 높음

- PostgreSQL·ClickHouse·Kafka 정기 백업과 실제 복구 훈련을 자동화한다.
- Portainer Server의 HTTP 9000 접근을 9443 HTTPS 또는 Tailscale HTTPS로 전환한다.
- Portainer 2.39.3 LTS를 현재 제공되는 패치 버전으로 올리기 전에 설정과 데이터 백업을 만든다.
- Grafana Cloud에서 컨테이너 단위 cAdvisor 지표가 충분히 수집되는지 다시 확인하고, readiness 실패·consumer lag·디스크 부족 알림을 코드나 런북으로 고정한다.

### 다음 정리

- 현재 볼륨을 스택별로 매핑하고, 백업이 확인된 익명·고아 볼륨만 별도 승인 후 제거한다.
- 수동 SHA 승격 절차가 안정화되면 Portainer webhook과 GitHub Environment 승인 기반 자동 배포를 검토한다.
- Grafana Cloud 체험/과금 상태가 끝나기 전에 계속 사용할지 또는 대체할지 결정한다.
- Vercel은 실제 소유 계정에서 프로젝트·도메인·환경 변수·배포 이력을 별도로 점검한다. 현재 Portainer 운영과 섞어 관리하지 않는다.
