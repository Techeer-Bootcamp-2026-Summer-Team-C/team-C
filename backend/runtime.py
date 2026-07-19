from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import boto3
import clickhouse_connect
import psycopg
from botocore.config import Config

from .archive_service import BotoRestoreObjectClient
from .event_service import RestoredEventReader
from .kafka import KafkaProducer
from .rule_loader import LoadedRule, RuleLoader
from .settings import Settings


class RuntimeServices:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        bootstrap_servers = settings.kafka_bootstrap_servers
        self.raw_topic = settings.kafka_raw_topic
        self.validated_topic = settings.kafka_validated_topic
        self.producer = KafkaProducer(bootstrap_servers, allowed_topics=settings.kafka_topics)
        self.clickhouse = clickhouse_connect.get_client(
            dsn=settings.clickhouse_dsn.get_secret_value(),
            autogenerate_session_id=False,
            connect_timeout=5,
            send_receive_timeout=10,
        )
        self.s3 = create_s3_client(settings)
        self.restored_events = RestoredEventReader(
            region=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url,
            access_key=_secret_value(settings.s3_access_key_id),
            secret_key=_secret_value(settings.s3_secret_access_key),
            bucket=settings.s3_bucket,
        )
        self.restore_client = BotoRestoreObjectClient(self.s3, bucket=settings.s3_bucket)
        self.rules = self._load_rules()

    @contextmanager
    def postgres(self) -> Iterator[Any]:
        with psycopg.connect(
            self.settings.postgres_dsn.get_secret_value(),
            connect_timeout=5,
        ) as connection:
            yield connection

    def check_ready(self) -> None:
        self.producer.check()
        with self.postgres() as connection:
            connection.execute("SELECT 1").fetchone()
        self.clickhouse.command("SELECT 1")
        self.s3.head_bucket(Bucket=self.settings.s3_bucket)
        self._load_rules()

    @staticmethod
    def _load_rules() -> list[LoadedRule]:
        root = Path(__file__).parents[1]
        loader = RuleLoader(
            schema_path=root / "schemas" / "rule-v1.schema.json",
            mapping_path=root / "mappings" / "mitre_attack.yaml",
        )
        return loader.load_directory(root / "rules")


def create_s3_client(settings: Settings) -> Any:
    options: dict[str, Any] = {
        "config": Config(
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
        )
    }
    if settings.aws_region is not None:
        options["region_name"] = settings.aws_region
    if settings.s3_endpoint_url is not None:
        options["endpoint_url"] = settings.s3_endpoint_url
    access_key = _secret_value(settings.s3_access_key_id)
    secret_key = _secret_value(settings.s3_secret_access_key)
    if access_key is not None and secret_key is not None:
        options["aws_access_key_id"] = access_key
        options["aws_secret_access_key"] = secret_key
    return boto3.client("s3", **options)


def _secret_value(value: Any) -> str | None:
    return value.get_secret_value() if value is not None else None
