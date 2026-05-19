"""Redis-backed job queue + progress pub/sub."""
import json
import os

import redis

_redis = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

QUEUE_KEY = "jobs:queue"
QUEUE_HIGH = "jobs:queue:high"


def get_redis():
    return _redis


def enqueue_job(job_id: str, priority: str = "normal"):
    key = QUEUE_HIGH if priority == "high" else QUEUE_KEY
    _redis.lpush(key, job_id)


def publish_progress(job_id: str, progress: int, message: str = ""):
    _redis.publish(
        f"jobs:{job_id}:events",
        json.dumps({"progress": progress, "message": message}),
    )


def publish_done(job_id: str, ok: bool, error: str | None = None):
    _redis.publish(
        f"jobs:{job_id}:events",
        json.dumps({"done": True, "ok": ok, "error": error}),
    )
