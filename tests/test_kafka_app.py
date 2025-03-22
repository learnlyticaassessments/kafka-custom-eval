import os
import time
import pytest
import json
from testcontainers.kafka import KafkaContainer
from kafka import KafkaProducer, KafkaConsumer
import importlib.util

def load_student_module():
    # Path to the student's assignment file in the evaluation folder.
    assignment_path = os.path.join("assignments", "kafka_app.py")
    spec = importlib.util.spec_from_file_location("kafka_app", assignment_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture(scope="module")
def student_module():
    return load_student_module()

@pytest.fixture(scope="module")
def kafka_bootstrap():
    # Spin up a Kafka container using Testcontainers
    with KafkaContainer() as kafka:
        # Allow some time for Kafka to be ready
        time.sleep(10)
        yield kafka.get_bootstrap_server()

def test_produce_consume(student_module, kafka_bootstrap):
    topic = "test-topic"
    messages = ["msg1", "msg2", "msg3"]
    kafka_config = {"bootstrap.servers": kafka_bootstrap}
    
    # Call student's produce function
    result = student_module.produce_messages(kafka_config, topic, messages)
    assert result is True, "produce_messages did not complete successfully."
    
    # Allow a few seconds for messages to propagate
    time.sleep(5)
    
    # Call student's consume function; expect to retrieve all messages
    consumed = student_module.consume_messages(kafka_config, topic, len(messages))
    assert len(consumed) == len(messages), "Number of consumed messages does not match produced."
    for msg in messages:
        assert msg in consumed, f"Message '{msg}' was not found in consumed messages."
