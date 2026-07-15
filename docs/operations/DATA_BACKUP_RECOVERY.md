# 운영 데이터 백업·복구

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

이 백업은 운영 EC2의 같은 디스크에 있으므로 호스트 장애에 대한 백업으로는 충분하지 않다. S3 같은 별도 저장소로 복제하고 보존 기간을 적용해야 한다.

Kafka 파일은 메시지 데이터 백업이 아니라 토픽과 consumer 상태 스냅샷이다. 단일 broker의 메시지 데이터를 일관되게 보존하려면 broker 중지 후 volume snapshot을 만들거나 별도 broker/object storage로 복제하는 설계가 필요하다.

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
- Kafka volume snapshot은 broker 중지 또는 복제 구성을 별도 승인한 뒤 수행한다.
