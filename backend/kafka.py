from dataclasses import dataclass
from typing import Protocol

from confluent_kafka import Consumer, KafkaError, Message, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewPartitions, NewTopic

RAW_TOPIC = "telemetry.raw"
VALIDATED_TOPIC = "telemetry.validated"
TOPICS = (RAW_TOPIC, VALIDATED_TOPIC)
PARTITIONS_PER_TOPIC = 3
REPLICATION_FACTOR = 1


@dataclass(frozen=True, slots=True)
class ConsumedMessage:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes
    headers: list[tuple[str, bytes | None]]
    native: Message | None = None


class ProducerPort(Protocol):
    def publish(
        self,
        topic: str,
        *,
        key: str,
        value: bytes,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> bool: ...

    def check(self) -> None: ...


class ConsumerPort(Protocol):
    def consume_one(self, timeout: float = 1.0) -> ConsumedMessage | None: ...

    def commit(self, message: ConsumedMessage) -> None: ...

    def pause(self, message: ConsumedMessage) -> None: ...


class KafkaProducer:
    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = Producer({"bootstrap.servers": bootstrap_servers, "enable.idempotence": True})

    def publish(
        self,
        topic: str,
        *,
        key: str,
        value: bytes,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> bool:
        if topic not in TOPICS:
            raise ValueError(f"unsupported Kafka topic: {topic}")
        delivery_error: list[object] = []
        delivered: list[bool] = []

        def callback(error: object, _message: Message) -> None:
            if error is not None:
                delivery_error.append(error)
            else:
                delivered.append(True)

        self._producer.produce(topic, key=key.encode(), value=value, headers=headers, callback=callback)
        self._producer.flush(10)
        return bool(delivered) and not delivery_error

    def check(self) -> None:
        self._producer.list_topics(timeout=5)


class KafkaConsumer:
    def __init__(self, bootstrap_servers: str, *, group_id: str, topic: str) -> None:
        if topic not in TOPICS:
            raise ValueError(f"unsupported Kafka topic: {topic}")
        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        self._consumer.subscribe([topic])

    def consume_one(self, timeout: float = 1.0) -> ConsumedMessage | None:
        message = self._consumer.poll(timeout)
        if message is None:
            return None
        if message.error():
            if message.error().code() == KafkaError._PARTITION_EOF:
                return None
            raise RuntimeError(str(message.error()))
        value = message.value()
        if value is None:
            raise RuntimeError("Kafka message has no value")
        return ConsumedMessage(
            topic=message.topic(),
            partition=message.partition(),
            offset=message.offset(),
            key=message.key(),
            value=value,
            headers=message.headers() or [],
            native=message,
        )

    def commit(self, message: ConsumedMessage) -> None:
        if message.native is None:
            raise ValueError("native Kafka message is required")
        self._consumer.commit(message=message.native, asynchronous=False)

    def pause(self, message: ConsumedMessage) -> None:
        if message.native is None:
            return
        self._consumer.pause([TopicPartition(message.topic, message.partition)])

    def close(self) -> None:
        self._consumer.close()


def ensure_topics(bootstrap_servers: str) -> None:
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata = admin.list_topics(timeout=10)
    missing = [topic for topic in TOPICS if topic not in metadata.topics]
    if missing:
        futures = admin.create_topics(
            [
                NewTopic(
                    topic,
                    num_partitions=PARTITIONS_PER_TOPIC,
                    replication_factor=REPLICATION_FACTOR,
                )
                for topic in missing
            ]
        )
        for future in futures.values():
            future.result(10)

    under_partitioned = [
        topic
        for topic in TOPICS
        if topic in metadata.topics and len(metadata.topics[topic].partitions) < PARTITIONS_PER_TOPIC
    ]
    if under_partitioned:
        futures = admin.create_partitions(
            [NewPartitions(topic, new_total_count=PARTITIONS_PER_TOPIC) for topic in under_partitioned]
        )
        for future in futures.values():
            future.result(10)
