from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import boto3
import clickhouse_connect
import psycopg

from .archive_service import BotoRestoreObjectClient
from .event_service import RestoredEventReader
from .kafka import KafkaProducer, ensure_topics
from .rule_loader import LoadedRule, RuleLoader
from .settings import Settings


class RuntimeServices:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        bootstrap_servers = settings.kafka_bootstrap_servers
        ensure_topics(bootstrap_servers)
        self.producer = KafkaProducer(bootstrap_servers)
        self.clickhouse = clickhouse_connect.get_client(
            dsn=settings.clickhouse_dsn.get_secret_value(),
            autogenerate_session_id=False,
        )
        self.s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            region_name="us-east-1",
        )
        self.restored_events = RestoredEventReader(
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key_id.get_secret_value(),
            secret_key=settings.s3_secret_access_key.get_secret_value(),
            bucket=settings.s3_bucket,
        )
        self.restore_client = BotoRestoreObjectClient(self.s3, bucket=settings.s3_bucket)
        self.rules = self._load_rules()

    @contextmanager
    def postgres(self) -> Iterator[Any]:
        with psycopg.connect(self.settings.postgres_dsn.get_secret_value()) as connection:
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
