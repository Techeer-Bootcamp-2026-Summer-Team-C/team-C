from dataclasses import dataclass

import backend.kafka as kafka_module
from backend.kafka import PARTITIONS_PER_TOPIC, RAW_TOPIC, VALIDATED_TOPIC, ensure_topics


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


def test_ensure_topics_does_not_reduce_existing_partition_count(monkeypatch) -> None:
    admin = FakeAdmin({RAW_TOPIC: TopicMetadata(4), VALIDATED_TOPIC: TopicMetadata(PARTITIONS_PER_TOPIC)})
    monkeypatch.setattr(kafka_module, "AdminClient", lambda _config: admin)

    ensure_topics("kafka:9092")

    assert admin.created_topics == []
    assert admin.created_partitions == []
