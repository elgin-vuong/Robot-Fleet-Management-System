from kafka import KafkaConsumer

from backend.app.consumers.telemetry_consumer import _save
from backend.app.database import SessionLocal
from backend.app.kafka import KAFKA_BOOTSTRAP_SERVERS, TELEMETRY_TOPIC, get_producer
from backend.app.models.telemetry import Telemetry


def _clear_telemetry(robot_id):
    db = SessionLocal()
    try:
        db.query(Telemetry).filter(Telemetry.robot_id == robot_id).delete()
        db.commit()
    finally:
        db.close()


def test_publish_telemetry_lands_on_topic():
    consumer = KafkaConsumer(
        TELEMETRY_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=None,
        value_deserializer=lambda v: v,
        auto_offset_reset="latest",
        consumer_timeout_ms=5000,
    )
    
    consumer.poll(timeout_ms=1000)

    producer = get_producer()
    payload = {
        "id": "R001",
        "battery": 42.0,
        "temperature": 55.5,
        "x": 1.0,
        "y": -2.0,
    }
    producer.send(TELEMETRY_TOPIC, key="R001", value=payload)
    producer.flush()

    try:
        message = next(iter(consumer))
    except StopIteration:
        message = None
    finally:
        consumer.close()

    assert message is not None
    assert message.key == b"R001"


def test_consumer_save_persists_telemetry_event():
    _clear_telemetry("R002")

    event = {
        "id": "R002",
        "battery": 77.5,
        "temperature": 41.2,
        "x": 3.0,
        "y": 4.0,
    }

    _save(event)

    db = SessionLocal()
    try:
        rows = db.query(Telemetry).filter(Telemetry.robot_id == "R002").all()
    finally:
        db.close()

    assert len(rows) == 1
    assert rows[0].battery == 77.5
    assert rows[0].temperature == 41.2


def test_consumer_save_multiple_events_appends_rows():
    _clear_telemetry("R003")

    _save({"id": "R003", "battery": 90.0, "temperature": 36.0, "x": 0.0, "y": 0.0})
    _save({"id": "R003", "battery": 89.5, "temperature": 36.5, "x": 0.5, "y": 0.5})

    db = SessionLocal()
    try:
        rows = db.query(Telemetry).filter(Telemetry.robot_id == "R003").all()
    finally:
        db.close()

    assert len(rows) == 2
