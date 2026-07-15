# Portainer 백업과 복구

Mac mini의 Portainer Server는 `/Users/geonha/portainer/docker-compose.yml`과 Docker volume `portainer_data`를 사용한다. 저장소의 기준 Compose는 `deploy/portainer/compose.portainer-server.yaml`이다.

## 2026-07-15 검증 기록

- 업그레이드 전 버전: `2.39.3-alpine`
- 백업 위치: `/Users/geonha/portainer/backups/2026-07-15-before-2.39.5`
- 백업 파일: `portainer_data.tar.gz`, `docker-compose.yml`
- SHA-256: `b0bc03765937650a8a277a46b842a3f22b869f39e5a6138a13707dadb5447814`
- 압축 검증: `portainer.db`, 키, 인증서, Git stack checkout 포함 확인
- 복구 훈련: 별도 volume `portainer_data_restore_test_20260715`에 복원한 뒤 격리된 19443 포트에서 Portainer 2.39.3 API 응답 확인
- 정리: 복구 시험 컨테이너와 임시 volume 삭제, 운영 volume 보존

## 표준 백업

먼저 새 버전 이미지를 pull하고 백업 도구 이미지도 준비한다. Portainer를 중지하는 동안 EC2의 애플리케이션 컨테이너는 계속 실행된다.

```bash
cd /Users/geonha/portainer
mkdir -p backups/<timestamp>
cp docker-compose.yml backups/<timestamp>/docker-compose.yml
docker pull alpine:3.20
docker compose stop portainer
docker run --rm \
  -v portainer_data:/data:ro \
  -v "$PWD/backups/<timestamp>:/backup" \
  alpine:3.20 \
  tar -czf /backup/portainer_data.tar.gz -C / data
docker compose start portainer
shasum -a 256 backups/<timestamp>/portainer_data.tar.gz
tar -tzf backups/<timestamp>/portainer_data.tar.gz >/dev/null
```

백업 파일은 Mac mini 한 곳에만 두지 말고 암호화된 외부 저장소로 추가 복제한다. 백업 디렉터리와 압축파일에는 Portainer DB와 인증 자료가 포함되므로 공개 저장소나 채팅에 업로드하지 않는다.

## 비파괴 복구 훈련

운영 volume을 덮어쓰지 않고 새 임시 volume으로 복원한다.

```bash
docker volume create portainer_data_restore_test
docker run --rm \
  -v portainer_data_restore_test:/data \
  -v "$PWD/backups/<timestamp>:/backup:ro" \
  alpine:3.20 \
  tar -xzf /backup/portainer_data.tar.gz -C /
docker run -d \
  --name portainer-restore-test \
  -p 127.0.0.1:19443:9443 \
  -v portainer_data_restore_test:/data \
  portainer/portainer-ce:<backup-version>-alpine
curl --fail --insecure https://127.0.0.1:19443/api/status
docker rm -f portainer-restore-test
docker volume rm portainer_data_restore_test
```

API가 백업 시점 버전과 동일한 `Version`, 운영과 동일한 `InstanceID`를 반환해야 한다. 시험 컨테이너 로그에 `loading PortainerDB` 이후 fatal 또는 migration 오류가 없어야 한다.

## 실제 복구

실제 장애에서는 먼저 손상된 `portainer_data`를 별도 이름으로 보존한다. 검증한 백업을 새 volume에 복원하고, `compose.portainer-server.yaml`의 volume 이름을 복원 volume로 임시 변경해 기동한다. 로그인, endpoint 4 연결, 네 개 stack과 컨테이너 목록을 확인한 뒤에만 기존 손상 volume 정리를 승인한다.
