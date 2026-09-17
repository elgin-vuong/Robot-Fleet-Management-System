import json
import os

from kafka import KafkaProducer

# Defaults to the local docker-compose Kafka (plaintext, single broker). In
# AWS, Terraform sets KAFKA_BOOTSTRAP_SERVERS to the MSK TLS bootstrap
# string and KAFKA_SECURITY_PROTOCOL to "SSL" — see
# infrastructure/terraform/modules/messaging and README "Kafka / event
# streaming". Only takes effect when enable_kafka = true; otherwise these
# workers aren't deployed to AWS at all.
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
TELEMETRY_TOPIC = "robot.telemetry"

_producer = None


def get_producer() -> KafkaProducer:
    global _producer

    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            security_protocol=KAFKA_SECURITY_PROTOCOL,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
        )

    return _producer
