from dataclasses import dataclass

import backend.kafka as kafka_module
from backend.kafka import (
    DETECTION_CONSUMER_GROUP,
    EVENT_STORAGE_CONSUMER_GROUP,
    PARTITIONS_PER_TOPIC,
    RAW_TOPIC,
    REPLICATION_FACTOR,
    VALIDATED_TOPIC,
    ensure_topics,
)


class CompletedFuture:
    def result(self, timeout: int) -> None:
        assert timeout == 10


@dataclass
class TopicMetadata:
    partition_count: int

    @property
    def partitions(self) -> dict[int, object]:
        return {index: object() for index in range(self.partition_count)}


@dataclass
class ClusterMetadata:
    topics: dict[str, TopicMetadata]


class FakeAdmin:
    def __init__(self, topics: dict[str, TopicMetadata]) -> None:
        self.metadata = ClusterMetadata(topics)
        self.created_topics = []
        self.created_partitions = []

    def list_topics(self, timeout: int) -> ClusterMetadata:
        assert timeout == 10
        return self.metadata

    def create_topics(self, topics):
        self.created_topics.extend(topics)
        return {topic.topic: CompletedFuture() for topic in topics}

    def create_partitions(self, partitions):
        self.created_partitions.extend(partitions)
        return {partition.topic: CompletedFuture() for partition in partitions}


def test_default_topic_partition_replication_and_consumer_group_contract() -> None:
    assert RAW_TOPIC == "telemetry.raw"
    assert VALIDATED_TOPIC == "telemetry.validated"
    assert PARTITIONS_PER_TOPIC == 2
    assert REPLICATION_FACTOR == 1
    assert EVENT_STORAGE_CONSUMER_GROUP == "edr-event-storage-v1"
    assert DETECTION_CONSUMER_GROUP == "edr-detection-v1"


def test_ensure_topics_creates_new_topics_with_two_partitions(monkeypatch) -> None:
    admin = FakeAdmin({})
    monkeypatch.setattr(kafka_module, "AdminClient", lambda _config: admin)

    ensure_topics("kafka:9092")

    assert [(topic.topic, topic.num_partitions, topic.replication_factor) for topic in admin.created_topics] == [
        (RAW_TOPIC, 2, 1),
        (VALIDATED_TOPIC, 2, 1),
    ]
    assert admin.created_partitions == []


def test_ensure_topics_creates_missing_and_expands_existing(monkeypatch) -> None:
    admin = FakeAdmin({RAW_TOPIC: TopicMetadata(1)})
    monkeypatch.setattr(kafka_module, "AdminClient", lambda _config: admin)

    ensure_topics("kafka:9092")

    assert [(topic.topic, topic.num_partitions, topic.replication_factor) for topic in admin.created_topics] == [
        (VALIDATED_TOPIC, PARTITIONS_PER_TOPIC, 1)
    ]
    assert [(item.topic, item.new_total_count) for item in admin.created_partitions] == [
        (RAW_TOPIC, PARTITIONS_PER_TOPIC)
    ]


def test_ensure_topics_keeps_existing_two_partitions(monkeypatch) -> None:
    admin = FakeAdmin({RAW_TOPIC: TopicMetadata(2), VALIDATED_TOPIC: TopicMetadata(2)})
    monkeypatch.setattr(kafka_module, "AdminClient", lambda _config: admin)

    ensure_topics("kafka:9092")

    assert admin.created_topics == []
    assert admin.created_partitions == []


def test_ensure_topics_does_not_reduce_existing_partition_count(monkeypatch) -> None:
    admin = FakeAdmin({RAW_TOPIC: TopicMetadata(3), VALIDATED_TOPIC: TopicMetadata(4)})
    monkeypatch.setattr(kafka_module, "AdminClient", lambda _config: admin)

    ensure_topics("kafka:9092")

    assert admin.created_topics == []
    assert admin.created_partitions == []


def test_ensure_topics_uses_configured_names_counts_and_replication(monkeypatch) -> None:
    admin = FakeAdmin({})
    monkeypatch.setattr(kafka_module, "AdminClient", lambda _config: admin)

    ensure_topics(
        "kafka:9092",
        topics=("custom.raw", "custom.validated"),
        partitions_per_topic=4,
        replication_factor=2,
    )

    assert [(topic.topic, topic.num_partitions, topic.replication_factor) for topic in admin.created_topics] == [
        ("custom.raw", 4, 2),
        ("custom.validated", 4, 2),
    ]
