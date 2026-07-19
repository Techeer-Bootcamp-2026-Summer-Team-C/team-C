# 운영 데이터 백업·복구

## 0. 현재 스택 원클릭 백업

EC2에서 아래 명령을 실행하면 PostgreSQL custom dump, ClickHouse native backup, Kafka metadata snapshot과 SHA-256을 같은 시각의 디렉터리에 생성한다. 이어서 PostgreSQL과 ClickHouse를 고유한 임시 DB로 복원해 table 수를 확인하고 임시 DB를 삭제한다. 운영 DB에는 restore하지 않는다.

```bash
cd /home/ubuntu/team-C
EDR_BACKUP_S3_URI=s3://<운영-백업-버킷>/archives/ec2-backups \
  bash tools/backup_production_data.sh
```

기본 저장 위치는 `/home/ubuntu/backups/<UTC timestamp>`다. `EDR_BACKUP_S3_URI`를 생략하면 EC2에만 저장하고 경고한다. 컨테이너 이름이 기본 Portainer 이름과 다르면 `EDR_POSTGRES_CONTAINER`, `EDR_CLICKHOUSE_CONTAINER`, `EDR_KAFKA_CONTAINER`로 지정한다. 스크립트가 성공하면 `MANIFEST.txt`, `SHA256SUMS`, S3 업로드 사용 시 `S3_OBJECTS.txt`가 남는다.

## 1. 현재 백업 증적

2026-07-15 운영 데이터의 무중단 백업을 EC2에 생성했다.

- 경로: `/home/ubuntu/backups/20260715T142555`
- PostgreSQL custom dump: `postgres.dump` (`36K`)
- ClickHouse native backup: `clickhouse.zip` (`4K`)
- Kafka topic snapshot: `kafka-topics.txt` (`8K`)
- Kafka consumer group snapshot: `kafka-consumer-groups.txt` (`4K`)

SHA-256:

```text
6a7c55b05313a9c74ab0e9f308fd54aef7e9ffdbd4d6e5e99cf4f28ab749eada  postgres.dump
13a82e9e31c8eea6a3c7473008fa7d40522491fe2cb6b634200e795afc8c6e94  clickhouse.zip
4898d9b1e4201155c7319647d5356be39649ef11c58d194a1cbf509eb94790c1  kafka-consumer-groups.txt
b24632dc5aa02112ece712b4dbb51658ca18a9d5aa18b108e04fecd2e4e51057  kafka-topics.txt
```

비파괴 복구 훈련도 같은 날 완료했다. PostgreSQL은 임시 DB에서 public table 8개, ClickHouse는 임시 DB에서 table 2개를 확인한 뒤 두 임시 DB를 삭제했다. 운영 DB에는 복원하지 않았다.

같은 백업을 아래 S3 경로에 복제하고 로컬·S3 체크섬 검증을 완료했다. 총 5개 객체이며 크기는 `42.4 KiB`다.

- `s3://techeer-edr-storage-905418013218-ap-northeast-2-an/archives/ec2-backups/20260715T142555/`

버킷 수명 주기는 이미 활성화돼 있다. `archives/`는 생성 즉시(0일) Glacier Flexible Retrieval로 전환하며 만료하지 않고, `failures/`는 90일 후 만료한다. 두 규칙은 서로 다른 prefix에 적용되므로 이 운영 백업에는 90일 만료가 적용되지 않는다.

Kafka 파일은 메시지 데이터 백업이 아니라 토픽과 consumer 상태 스냅샷이다. 현재 Kafka는 단일 호스트 내부의 전송 계층이고, 영속 복구 원본은 PostgreSQL과 ClickHouse다. 이 규모에서는 broker 복제나 정지 volume snapshot을 추가하지 않고, Kafka 장애 시 영속 원본에서 재처리한다. 메시지 자체가 별도 복구 원본이 되어야 할 요구가 생길 때만 복제 구성을 다시 검토한다.

## 2. PostgreSQL 백업

```bash
docker exec edr-c-infra-postgres-1 sh -c \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > postgres.dump
```

복구는 운영 DB에 바로 덮어쓰지 않고 임시 DB에서 먼저 검증한다.

```bash
docker exec edr-c-infra-postgres-1 sh -c \
  'exec createdb -U "$POSTGRES_USER" edr_restore_test'
docker exec -i edr-c-infra-postgres-1 sh -c \
  'exec pg_restore -U "$POSTGRES_USER" -d edr_restore_test --exit-on-error' \
  < postgres.dump
docker exec edr-c-infra-postgres-1 sh -c \
  'exec dropdb -U "$POSTGRES_USER" edr_restore_test'
```

## 3. ClickHouse 백업

ClickHouse server가 쓸 수 있도록 백업 디렉터리 소유권을 먼저 맞춘다.

```bash
docker exec edr-c-infra-clickhouse-1 mkdir -p /var/lib/clickhouse/backups
docker exec edr-c-infra-clickhouse-1 \
  chown clickhouse:clickhouse /var/lib/clickhouse/backups
docker exec edr-c-infra-clickhouse-1 sh -c \
  'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$1"' \
  _ "BACKUP DATABASE edr TO File('edr-backup.zip')"
```

복구 훈련은 별도 DB 이름으로 수행하고 검증 후 삭제한다.

```bash
docker exec edr-c-infra-clickhouse-1 sh -c \
  'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$1"' \
  _ "RESTORE DATABASE edr AS edr_restore_test FROM File('edr-backup.zip')"
docker exec edr-c-infra-clickhouse-1 sh -c \
  'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$1"' \
  _ "DROP DATABASE edr_restore_test SYNC"
```

## 4. 삭제 전 원칙

- Portainer가 `Unused`로 표시하더라도 데이터 volume은 이름과 생성 시각만 보고 삭제하지 않는다.
- 현재 컨테이너 mount와 volume label을 매핑하고, 별도 저장소에 archive와 checksum을 만든 뒤 삭제한다.
- PostgreSQL·ClickHouse 복구 훈련이 끝나기 전에는 현재 운영 volume을 제거하지 않는다.
- 현재 Kafka volume은 별도 백업하지 않는다. 메시지 자체를 복구 원본으로 보존해야 하는 요구가 생기면 broker 복제 또는 정지 snapshot을 별도 설계한다.

## 5. 미사용 Docker volume 정리 증적

2026-07-15 현재 컨테이너 참조가 0개인 volume 14개를 하나의 archive로 만든 뒤 S3 업로드와 체크섬 검증을 완료하고 삭제했다.

- S3 경로: `s3://techeer-edr-storage-905418013218-ap-northeast-2-an/archives/docker-volumes/20260715T151036/`
- archive: `unused-docker-volumes.tar.gz` (`289.5 MiB`)
- 증적: `MANIFEST.txt`, `SHA256SUMS`
- 삭제 후 남은 volume: 사용 중인 6개
- 삭제 후 검증: Nginx health `ok`, backend readiness `{"status":"ready"}`

복원이 필요하면 archive 전체를 바로 Docker volume 경로에 덮어쓰지 않는다. `MANIFEST.txt`와 SHA-256을 먼저 검증하고, 필요한 volume 하나만 별도 임시 경로에 풀어 내용을 확인한 뒤 복원한다.
