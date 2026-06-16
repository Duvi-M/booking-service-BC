from taskiq_redis import ListQueueBroker

from app.config import get_settings

settings = get_settings()

broker = ListQueueBroker(settings.background_broker_url)
