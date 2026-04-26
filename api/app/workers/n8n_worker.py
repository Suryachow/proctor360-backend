import json
import asyncio
import logging
import httpx
from aiokafka import AIOKafkaConsumer
from app.core.config import settings

logger = logging.getLogger(__name__)

async def run_n8n_integration_worker():
    """
    Consumes violations from Kafka and pushes them to n8n for automated intervention logic.
    n8n will handle Slack alerts, email warnings, or third-party CRM updates.
    """
    logger.info("Starting n8n Integration Worker...")
    
    consumer = AIOKafkaConsumer(
        settings.kafka_violation_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="n8n-automation-brain",
        value_deserializer=lambda v: json.loads(v.decode('utf-8'))
    )
    
    await consumer.start()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            async for msg in consumer:
                event = msg.value
                logger.info(f"Processing event for n8n: {event.get('event_type')}")
                
                try:
                    # E. n8n (Automation Brain) - Webhook Trigger
                    response = await client.post(
                        settings.n8n_webhook_url,
                        json=event
                    )
                    if response.status_code >= 400:
                        logger.error(f"n8n webhook failed: {response.status_code}")
                except Exception as e:
                    logger.error(f"n8n connection error: {e}")
                    
    finally:
        await consumer.stop()

if __name__ == "__main__":
    asyncio.run(run_n8n_integration_worker())
