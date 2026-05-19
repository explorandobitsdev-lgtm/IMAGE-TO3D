"""Worker GPU: consome jobs do Redis e roda os pipelines."""
import json
import os
import socket
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

import boto3
import redis
from botocore.client import Config
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pipelines import dispatch  # noqa: E402

REDIS_URL = os.environ["REDIS_URL"]
S3_BUCKET = os.environ["S3_BUCKET"]
WORKER_ID = f"worker-{socket.gethostname()}-{os.getpid()}"

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
db = create_engine(
    f"postgresql+psycopg://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ['POSTGRES_HOST']}:5432/{os.environ['POSTGRES_DB']}",
    pool_pre_ping=True,
)
s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


def publish(job_id, **payload):
    r.publish(f"jobs:{job_id}:events", json.dumps(payload))


def upload(local_path, key):
    s3.upload_file(local_path, S3_BUCKET, key)
    return os.path.getsize(local_path)


def process(job_id: str):
    print(f"[{WORKER_ID}] picking job {job_id}")
    with db.begin() as c:
        row = c.execute(
            text("SELECT id, user_id, type, model, input FROM jobs WHERE id = :id"),
            {"id": job_id},
        ).first()
        if not row:
            print(f"  job {job_id} not found")
            return
        c.execute(
            text(
                "UPDATE jobs SET status='running', worker_id=:w, started_at=NOW() "
                "WHERE id=:id"
            ),
            {"id": job_id, "w": WORKER_ID},
        )

    job_type = row.type
    model = row.model
    inp = row.input

    def on_progress(pct, msg=""):
        with db.begin() as c:
            c.execute(text("UPDATE jobs SET progress=:p WHERE id=:id"), {"id": job_id, "p": pct})
        publish(job_id, progress=pct, message=msg)

    try:
        publish(job_id, progress=0, message="started")
        with tempfile.TemporaryDirectory() as tmp:
            outputs = dispatch(
                job_type=job_type,
                model=model,
                input=inp,
                workdir=Path(tmp),
                on_progress=on_progress,
                s3=s3,
                bucket=S3_BUCKET,
            )

            with db.begin() as c:
                for kind, local_path, meta in outputs:
                    key = f"jobs/{job_id}/{Path(local_path).name}"
                    bytes_ = upload(local_path, key)
                    c.execute(
                        text(
                            "INSERT INTO assets (job_id, user_id, kind, storage_key, bytes, meta) "
                            "VALUES (:j, :u, :k, :s, :b, :m)"
                        ),
                        {
                            "j": job_id,
                            "u": str(row.user_id),
                            "k": kind,
                            "s": key,
                            "b": bytes_,
                            "m": json.dumps(meta or {}),
                        },
                    )
                c.execute(
                    text(
                        "UPDATE jobs SET status='succeeded', progress=100, finished_at=NOW() "
                        "WHERE id=:id"
                    ),
                    {"id": job_id},
                )

        publish(job_id, progress=100, message="done", done=True, ok=True)
        print(f"  job {job_id} succeeded")

    except Exception as e:
        traceback.print_exc()
        with db.begin() as c:
            c.execute(
                text(
                    "UPDATE jobs SET status='failed', error=:err, finished_at=NOW() WHERE id=:id"
                ),
                {"id": job_id, "err": str(e)[:1000]},
            )
        publish(job_id, done=True, ok=False, error=str(e))


def main():
    print(f"[{WORKER_ID}] online — model={os.environ.get('WORKER_MODEL')} device={os.environ.get('WORKER_DEVICE')}")
    queues = ["jobs:queue:high", "jobs:queue"]
    while True:
        res = r.brpop(queues, timeout=10)
        if not res:
            continue
        _, job_id = res
        try:
            process(job_id)
        except Exception:
            traceback.print_exc()
            time.sleep(1)


if __name__ == "__main__":
    main()
