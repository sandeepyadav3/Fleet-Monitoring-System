import json
import logging
import os
import time
from datetime import datetime, timezone

import pika
import redis
from pymongo import MongoClient
from pymongo.errors import PyMongoError

RABBITMQ_URL = os.environ.get(
    "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
)
QUEUE_NAME = os.environ.get("QUEUE_NAME", "fleet-telemetry")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = os.environ.get("MONGO_DB", "fleet_db")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "telemetry_logs")
RETRY_DELAY_SECONDS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("fleet-worker")


def connect_redis() -> redis.Redis:
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    client.ping()
    logger.info("Connected to Redis at %s:%s", REDIS_HOST, REDIS_PORT)
    return client


def connect_mongo() -> tuple[MongoClient, object]:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    collection = client[MONGO_DB][MONGO_COLLECTION]
    logger.info("Connected to MongoDB %s.%s", MONGO_DB, MONGO_COLLECTION)
    return client, collection


def process_message(channel, method, _properties, body, redis_client, collection) -> None:
    delivery_tag = method.delivery_tag

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.exception("Dropping message with invalid JSON")
        channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
        return

    vehicle_id = payload.get("vehicle_id")
    if not vehicle_id:
        logger.error("Dropping message missing vehicle_id: %s", payload)
        channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
        return

    try:
        redis_key = f"vehicle:{vehicle_id}"
        redis_client.set(redis_key, json.dumps(payload))

        document = dict(payload)
        document["server_timestamp"] = datetime.now(timezone.utc)
        collection.insert_one(document)
    except (redis.RedisError, PyMongoError, OSError):
        logger.exception(
            "Failed to persist telemetry for %s; message will be requeued",
            vehicle_id,
        )
        channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
        return
    except Exception:
        logger.exception(
            "Unexpected error processing %s; message will be requeued",
            vehicle_id,
        )
        channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
        return

    channel.basic_ack(delivery_tag=delivery_tag)
    logger.info("Processed telemetry for %s", vehicle_id)


def consume() -> None:
    redis_client = None
    mongo_client = None

    while True:
        try:
            if redis_client is None:
                redis_client = connect_redis()
            else:
                redis_client.ping()

            if mongo_client is None:
                mongo_client, collection = connect_mongo()
            else:
                mongo_client.admin.command("ping")
                collection = mongo_client[MONGO_DB][MONGO_COLLECTION]

            parameters = pika.URLParameters(RABBITMQ_URL)
            parameters.heartbeat = 60
            parameters.blocked_connection_timeout = 30
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=lambda ch, method, properties, body: process_message(
                    ch, method, properties, body, redis_client, collection
                ),
                auto_ack=False,
            )

            logger.info("Consuming queue %s", QUEUE_NAME)
            channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Shutting down worker")
            try:
                if "channel" in locals() and channel.is_open:
                    channel.stop_consuming()
                if "connection" in locals() and connection.is_open:
                    connection.close()
            except Exception:
                logger.exception("Error while closing RabbitMQ connection")
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning(
                "RabbitMQ connection failed; retrying in %ss",
                RETRY_DELAY_SECONDS,
            )
            time.sleep(RETRY_DELAY_SECONDS)
        except (redis.RedisError, PyMongoError, OSError):
            logger.exception(
                "Database connection failed; retrying in %ss",
                RETRY_DELAY_SECONDS,
            )
            redis_client = None
            if mongo_client is not None:
                mongo_client.close()
                mongo_client = None
            time.sleep(RETRY_DELAY_SECONDS)
        except Exception:
            logger.exception(
                "Worker crashed; retrying in %ss",
                RETRY_DELAY_SECONDS,
            )
            time.sleep(RETRY_DELAY_SECONDS)

    if mongo_client is not None:
        mongo_client.close()


if __name__ == "__main__":
    consume()
