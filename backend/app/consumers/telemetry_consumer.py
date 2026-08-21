import json

from kafka import KafkaConsumer

from backend.app.database import SessionLocal
from backend.app.kafka import KAFKA_BOOTSTRAP_SERVERS, TELEMETRY_TOPIC
from backend.app.models.robot import Robot  # noqa: F401 - registers the `robots` table for Telemetry's FK
from backend.app.models.telemetry import Telemetry

CONSUMER_GROUP = "telemetry-writer"


def _save(event: dict):
    db = SessionLocal()
    try:
        db.add(
            Telemetry(
                robot_id=event["id"],
                battery=event["battery"],
                temperature=event["temperature"],
                x=event["x"],
                y=event["y"],
            )
        )
        db.commit()
    finally:
        db.close()


def main():
    consumer = KafkaConsumer(
        TELEMETRY_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
    )

    print(f"Listening for telemetry on '{TELEMETRY_TOPIC}'...")

    try:
        for message in consumer:
            _save(message.value)
            print(f"Persisted telemetry for {message.value['id']}")
    except KeyboardInterrupt:
        print("Telemetry consumer stopped.")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
