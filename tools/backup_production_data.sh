#!/usr/bin/env bash
set -euo pipefail

backup_root="${EDR_BACKUP_ROOT:-/home/ubuntu/backups}"
backup_s3_uri="${EDR_BACKUP_S3_URI:-}"
postgres_container="${EDR_POSTGRES_CONTAINER:-edr-c-infra-postgres-1}"
clickhouse_container="${EDR_CLICKHOUSE_CONTAINER:-edr-c-infra-clickhouse-1}"
kafka_container="${EDR_KAFKA_CONTAINER:-edr-c-infra-kafka-1}"
clickhouse_database="${EDR_CLICKHOUSE_DATABASE:-edr}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
timestamp_slug="$(printf '%s' "${timestamp}" | tr '[:upper:]' '[:lower:]')"
backup_directory="${backup_root%/}/${timestamp}"
postgres_restore_database="edr_restore_${timestamp_slug}"
clickhouse_restore_database="edr_restore_${timestamp_slug}"
clickhouse_backup_file="edr-backup-${timestamp}.zip"

cleanup() {
  docker exec "${postgres_container}" sh -c \
    'exec dropdb --if-exists -U "$POSTGRES_USER" "$1"' _ "${postgres_restore_database}" >/dev/null 2>&1 || true
  docker exec "${clickhouse_container}" sh -c \
    'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$1"' \
    _ "DROP DATABASE IF EXISTS ${clickhouse_restore_database} SYNC" >/dev/null 2>&1 || true
  docker exec "${clickhouse_container}" \
    rm -f "/var/lib/clickhouse/backups/${clickhouse_backup_file}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for command in docker sha256sum; do
  command -v "${command}" >/dev/null || {
    echo "required command is unavailable: ${command}" >&2
    exit 1
  }
done

for container in "${postgres_container}" "${clickhouse_container}" "${kafka_container}"; do
  if [[ "$(docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null)" != "true" ]]; then
    echo "required container is not running: ${container}" >&2
    exit 1
  fi
done

mkdir -p "${backup_directory}"

docker exec "${postgres_container}" sh -c \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "${backup_directory}/postgres.dump"

docker exec "${clickhouse_container}" mkdir -p /var/lib/clickhouse/backups
docker exec "${clickhouse_container}" chown clickhouse:clickhouse /var/lib/clickhouse/backups
docker exec "${clickhouse_container}" sh -c \
  'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$1"' \
  _ "BACKUP DATABASE ${clickhouse_database} TO File('${clickhouse_backup_file}')"
docker cp \
  "${clickhouse_container}:/var/lib/clickhouse/backups/${clickhouse_backup_file}" \
  "${backup_directory}/clickhouse.zip"

docker exec "${kafka_container}" /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server kafka:29092 --describe \
  > "${backup_directory}/kafka-topics.txt"
docker exec "${kafka_container}" /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:29092 --all-groups --describe \
  > "${backup_directory}/kafka-consumer-groups.txt"

docker exec "${postgres_container}" sh -c \
  'exec createdb -U "$POSTGRES_USER" "$1"' _ "${postgres_restore_database}"
docker exec -i "${postgres_container}" sh -c \
  'exec pg_restore -U "$POSTGRES_USER" -d "$1" --exit-on-error' _ "${postgres_restore_database}" \
  < "${backup_directory}/postgres.dump"
postgres_table_count="$(
  docker exec "${postgres_container}" sh -c \
    'exec psql -U "$POSTGRES_USER" -d "$1" -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema = '\''public'\''"' \
    _ "${postgres_restore_database}"
)"

docker exec "${clickhouse_container}" sh -c \
  'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$1"' \
  _ "RESTORE DATABASE ${clickhouse_database} AS ${clickhouse_restore_database} FROM File('${clickhouse_backup_file}')"
clickhouse_table_count="$(
  docker exec "${clickhouse_container}" sh -c \
    'exec clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$1"' \
    _ "SELECT count() FROM system.tables WHERE database = '${clickhouse_restore_database}'"
)"

if [[ "${postgres_table_count}" -le 0 || "${clickhouse_table_count}" -le 0 ]]; then
  echo "restore verification returned an empty database" >&2
  exit 1
fi

(
  cd "${backup_directory}"
  sha256sum postgres.dump clickhouse.zip kafka-topics.txt kafka-consumer-groups.txt > SHA256SUMS
  sha256sum --check SHA256SUMS
  {
    echo "created_at_utc=${timestamp}"
    echo "postgres_public_tables=${postgres_table_count}"
    echo "clickhouse_tables=${clickhouse_table_count}"
    du -h postgres.dump clickhouse.zip kafka-topics.txt kafka-consumer-groups.txt
  } > MANIFEST.txt
)

if [[ -n "${backup_s3_uri}" ]]; then
  command -v aws >/dev/null || {
    echo "EDR_BACKUP_S3_URI is set but aws CLI is unavailable" >&2
    exit 1
  }
  destination="${backup_s3_uri%/}/${timestamp}/"
  aws s3 cp "${backup_directory}" "${destination}" --recursive --only-show-errors
  aws s3 ls "${destination}" > "${backup_directory}/S3_OBJECTS.txt"
  echo "backup uploaded to ${destination}"
else
  echo "EDR_BACKUP_S3_URI is unset; backup remains only at ${backup_directory}" >&2
fi

echo "backup and non-destructive restore verification succeeded: ${backup_directory}"
