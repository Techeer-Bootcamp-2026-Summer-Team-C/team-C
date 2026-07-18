# 운영 배포 현황

이 문서는 2026-07-15~16 KST 점검에서 확인한 스냅샷과 운영 절차를 기록한다. 실제 현재 상태는 Portainer의 컨테이너 이미지 태그와 라이브 health check를 다시 확인해야 한다.

## 결론

운영 배포의 기준은 Vercel이 아니라 EC2의 Portainer Agent 환경이다. Mac mini의 Portainer Server가 EC2 Agent를 관리하고, 애플리케이션은 GHCR에 빌드된 커밋 SHA 고정 이미지를 사용한다. Vercel은 다른 계정에서 관리되고 있어 이번 점검과 변경 범위에서 제외했다.

최종 점검 시점 운영 서비스는 이미지 빌드 커밋 `273fa115f5dacfa2efaf6bcf34cdb5ca64e37ec5`의 backend와 Nginx를 사용한다. 운영 Compose의 마지막 변경은 `d08a0b538b8d1e466bd62b450e8a03335e32e895`이며, 이 커밋은 이미지 빌드 대상 경로를 바꾸지 않아 별도 서비스 이미지를 만들지 않았다. 이 문서만 바꾸는 후속 커밋도 런타임 재배포 대상이 아니다. backend와 Nginx는 `healthy`, PostgreSQL·ClickHouse·Kafka는 `healthy`, 두 worker와 Alloy, Portainer Agent는 `running`, 일회성 `app-init`은 정상 종료 상태인 `Exited (0)`이다. 워킹트리의 미커밋 변경은 운영 이미지에 포함되지 않는다.

## 배포 소스 오브 트루스

| 역할 | Portainer 스택 | Compose 파일 |
|---|---|---|
| 데이터 인프라 | `edr-c-infra` | `deploy/portainer/compose.infra.yaml` |
| API·worker·Nginx | `edr-c-service` | `deploy/portainer/compose.service.yaml` |
| Grafana Cloud 수집 | `edr-c-observability` | `deploy/portainer/compose.observability.yaml` |
| 원격 관리 Agent | EC2 `portainer-agent` | `deploy/portainer/compose.portainer-agent.yaml` |
| 관리 서버 | Mac mini `portainer` | `deploy/portainer/compose.portainer-server.yaml` |

단일 호스트 개발·데모 Compose나 Vercel 설정은 운영 Portainer 배포의 기준이 아니다. 환경 변수 이름은 `deploy/portainer/env.*.example`을 참고하고, 실제 비밀값은 Portainer에만 저장한다.

## 2026-07-15 적용 결과

- 운영 Compose 마지막 변경: `d08a0b538b8d1e466bd62b450e8a03335e32e895`
- GitHub Actions `Build production images`: `273fa115f5dacfa2efaf6bcf34cdb5ca64e37ec5`의 backend와 Nginx 이미지 빌드 성공
- 서비스 스택의 `EDR_IMAGE_TAG`: 위 이미지 빌드 SHA로 갱신 후 pull/redeploy 성공
- 세 Git 기반 스택의 repository reference: 모두 `refs/heads/main` (2026-07-16 `edr-c-service`만 `refs/heads/production` + polling으로 전환, 아래 절 참조)
- 관측 스택: Docker 로그 필터 결과를 실제 Loki source에 연결하고 `/run/udev/data`를 읽기 전용으로 마운트한 최신 Compose로 재배포
- Alloy: `running`, remote-write WAL 재생과 Kafka exporter 갱신 확인, `/run/udev/data` 오류 없음
- HTTP 검증: `/nginx-health` 200 `ok`, `/health/ready` 200 `ready`
- OpenAPI 검증: 25개 path, locale·dashboard layout·process tree 계약 포함
- 컨테이너: 30개에서 운영에 필요한 10개로 정리
- 이미지: 25개에서 실행 중인 7개 이미지로 정리하고 이전 `f13e554...` backend/Nginx 이미지 삭제
- 스택: 7개에서 운영 3개와 Portainer Agent 스택만 남겨 4개로 정리
- 네트워크: 연결이 없던 demo/local 네트워크 3개를 제거해 Docker 기본 3개와 운영 네트워크 3개만 유지
- 데이터 볼륨: 미사용 14개를 S3에 archive한 뒤 삭제하고, 사용 중인 6개만 유지
- Portainer Server: `2.39.3-alpine`에서 `2.39.5-alpine`으로 업그레이드하고 DB migration 성공 확인
- Portainer HTTPS: 9443 활성화 후 Tailscale Serve의 tailnet 전용 HTTPS 주소에서 200 응답 확인
- Portainer 백업: 업그레이드 전 `portainer_data` 압축, SHA-256 검증, 별도 volume 실제 복원 훈련 성공
- Portainer Agent: UI 직접 교체 실패 후 기존 Compose로 복구하고, 이미지를 먼저 pull하는 절차로 `2.39.5-alpine` 전환 및 endpoint `Up` 확인
- 운영 데이터 백업: `/home/ubuntu/backups/20260715T142555`에 PostgreSQL dump, ClickHouse native backup, Kafka 토픽·consumer 스냅샷과 SHA-256 생성
- 데이터 복구 훈련: 임시 DB에서 PostgreSQL public table 8개와 ClickHouse table 2개를 확인하고 임시 DB 삭제 완료
- 이미지 후속 정리: 새 Agent 검증 후 미사용 `portainer/agent:2.39.3-alpine` 제거, 실행 이미지 7개만 유지
- 관측 재검증: Alloy 최신 100줄에서 `level=error` 0건, Kafka exporter 메타데이터 갱신 지속 확인
- 외부 백업: PostgreSQL·ClickHouse·Kafka 메타데이터 백업 5개 객체(`42.4 KiB`)를 `archives/ec2-backups/20260715T142555/`에 업로드하고 SHA-256 검증 완료
- volume archive: 미사용 volume 14개를 `archives/docker-volumes/20260715T151036/unused-docker-volumes.tar.gz`(`289.5 MiB`)로 보관하고 체크섬 검증 후 삭제
- S3 수명 주기: 기존 `archives/` 0일 Glacier Flexible Retrieval 전환과 `failures/` 90일 만료 규칙 확인, 중복 규칙은 만들지 않음
- SSM Session Manager: EC2 역할에 `AmazonSSMManagedInstanceCore` 연결, Snap Agent `3.3.4793.0` 활성화, 인스턴스 `i-04b0a5ebb3c054f9a` 온라인 확인
- Grafana Cloud 실측: 수집 대상 4개 모두 `up=1`, readiness `probe_success=1`, 루트 디스크 사용률 약 `36.64%`; 현재 consumer lag 값은 `0`
- Grafana Cloud 알림: Slack contact point `Grafana`에 아래 3개 규칙을 연결하고 `Team C Production` 폴더의 `team-c-production-1m` 평가 그룹에 저장
  - `Backend readiness failed`: `probe_success < 1`, 1분 지속
  - `Root disk usage high`: 루트 파일시스템 사용률 `> 85%`, 5분 지속
  - `Kafka consumer lag high`: `sum(kafka_consumergroup_lag) or vector(0) > 100`, 5분 지속
- Grafana Cloud 알림 검증: readiness와 디스크 규칙은 실제 평가 `Normal`, Kafka lag는 현재 값 `0`과 미리보기 `Normal`, 세 규칙 모두 저장 성공 확인

삭제한 범위는 중단된 `edr-c-demo-*`, 생성만 되고 실행되지 않던 `edr-c-local-*`, Alloy/Grafana Cloud로 대체된 `edr-monitoring-*` 컨테이너와 그 뒤 미사용 상태가 된 이미지다. 운영 데이터 볼륨과 현재 이미지, Portainer Agent는 보존했다.

볼륨 이름만으로 사용 여부를 판단하면 안 된다. 현재 인프라는 이전 스택에서 생성된 `edr-c-demo-*` 또는 `edr-c-local_*` 이름의 일부 외부 볼륨을 실제 운영 데이터 볼륨으로 재사용한다. Portainer에서 `Unused` 표시가 없거나 현재 컨테이너에 연결된 볼륨은 이름이 오래돼 보여도 삭제하지 않는다.

## 2026-07-16 자동 배포 전환

- `edr-c-service` 스택을 `refs/heads/production` + GitOps polling(5분, re-pull)으로 전환. 이 스택은 더 이상 `EDR_IMAGE_TAG`를 수동으로 바꾸지 않는다.
- `main` push → GitHub Actions가 backend·Nginx 이미지를 커밋 SHA로 빌드 → `promote` job이 `compose.service.yaml`의 이미지 태그를 그 SHA로 고정해 `production` 브랜치에 기록 → Portainer polling이 감지해 자동 재배포. (실측 검증 완료)
- `promote`는 `main` push에서만 실행된다(`workflow_dispatch`로 임의 브랜치를 승격할 수 없음).
- 나머지 스택(`edr-c-infra`, `edr-c-observability`)은 계속 `refs/heads/main` 기준이며 수동 절차를 따른다.
- 비밀값(JWT·DSN 등)은 여전히 Portainer 스택 환경 변수에만 저장하고, `production` 브랜치에는 이미지 SHA만 기록한다.
- 전제: EC2 endpoint의 `allowBindMountsForRegularUsers`를 활성화해야 Nginx TLS bind mount 배포가 막히지 않는다.

## 표준 업데이트 절차

`edr-c-service`는 자동 배포된다(위 "2026-07-16 자동 배포 전환" 참조): `main`에 push하면 이미지 빌드 → `production` 브랜치 SHA 고정 → Portainer polling(5분)으로 자동 재배포된다. 수동 조작이 필요 없다. 인프라·관측 스택은 여전히 `refs/heads/main` 기준 수동 절차를 따른다.

배포 후 확인:

1. `app-init=Exited (0)`, backend/Nginx=`healthy`, worker 2개=`running`을 확인한다.
2. 저장소 checkout이 있는 관리 PC에서 Mac mini를 경유해 공개 경로와 API 계약을 확인한다.

```powershell
powershell -File tools/verify_production_deployment.ps1 `
  -BaseUrl http://<EC2-Tailscale-IP>:8080 `
  -SshHost macmini
```

3. 새 배포가 안정적인 것을 확인한 뒤에만 이전 SHA 이미지 중 Portainer가 `Unused`로 표시하는 항목을 제거한다.

### 수동 재배포·롤백 (예외 시에만)

자동 배포가 막혔거나 이전 버전으로 되돌려야 할 때만 수동 개입한다. 이전 이미지 SHA는 GHCR에 남아 있으므로, 되돌릴 커밋을 `main`에 반영해 재빌드하거나(권장) admin이 Portainer에서 해당 SHA 이미지로 임시 재배포한다. `production` 브랜치의 compose는 이미지 SHA가 고정돼 있어 `EDR_IMAGE_TAG` 수동 변경은 더 이상 사용하지 않는다.

## 남은 운영 과제

### 우선순위 높음

- PostgreSQL·ClickHouse 백업은 중요한 데이터 변경 또는 배포 전후에 갱신하고, 정기 자동화는 데이터 규모와 운영 빈도가 커질 때 적용한다.

### 다음 정리

- archive된 volume이 실제로 필요할 때만 개별 복원 훈련을 한다. 현재 운영 volume 6개는 유지한다.
- PR 테스트·린트 CI는 저장소 workflow로 관리한다. `main` 보호 규칙에서 이 CI를 required check로 지정하는 운영 설정은 별도로 확인한다. Portainer webhook과 GitHub Environment 승인은 현재 규모에서는 추가하지 않고 polling 기반 자동 배포를 유지한다.
- Grafana Cloud 체험/과금 상태가 끝나기 전에 계속 사용할지 또는 대체할지 결정한다.
- Vercel은 실제 소유 계정에서 프로젝트·도메인·환경 변수·배포 이력을 별도로 점검한다. 현재 Portainer 운영과 섞어 관리하지 않는다.
