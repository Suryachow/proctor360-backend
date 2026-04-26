import json
import logging
from aiokafka import AIOKafkaProducer
from app.core.config import settings

logger = logging.getLogger(__name__)

class KafkaService:
    def __init__(self):
        self.producer = None
        self.bootstrap_servers = settings.kafka_bootstrap_servers

    async def start(self):
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            await self.producer.start()
            logger.info("Kafka Producer started successfully")
        except Exception as e:
            logger.error(f"Failed to start Kafka Producer: {e}")

    async def stop(self):
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka Producer stopped")

    async def send_violation(self, violation_data: dict):
        if not self.producer:
            logger.warning("Kafka Producer not initialized. Skipping event.")
            return

        try:
            await self.producer.send_and_wait(
                settings.kafka_violation_topic,
                value=violation_data
            )
            logger.info(f"Violation pushed to Kafka: {violation_data.get('event_type')}")
        except Exception as e:
            logger.error(f"Error sending violation to Kafka: {e}")

kafka_service = KafkaService()
