"""FastAPI app: auth, jobs, billing, marketplace, admin, SSE."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal

import boto3
from botocore.client import Config
from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from db import Base, engine, get_db
from models import Asset, CreditTx, Job, Listing, User
from jobq import enqueue_job, get_redis

Base.metadata.create_all(bind=engine)

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
JWT_EXPIRES_MIN = int(os.environ.get("JWT_EXPIRES_MIN", "15"))
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PUBLIC = os.environ.get("S3_PUBLIC_ENDPOINT", os.environ["S3_ENDPOINT"])

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

app = FastAPI(title="3D-AI Platform", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


def make_token(user_id: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=JWT_EXPIRES_MIN)
    return jwt.encode({"sub": user_id, "exp": exp}, JWT_SECRET, algorithm=JWT_ALG)


def current_user(token: Annotated[str, Depends(oauth)], db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(401, "invalid token")
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(401, "user not found")
    return u


def require_admin(u: User = Depends(current_user)) -> User:
    if u.role != "admin":
        raise HTTPException(403, "admin only")
    return u


# ---------- Schemas ----------
class AuthIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    credits: int


class JobIn(BaseModel):
    type: Literal["image_to_3d", "text_to_3d", "heightmap", "palmilha"]
    model: str | None = None
    input: dict


class JobOut(BaseModel):
    id: str
    type: str
    model: str | None
    status: str
    progress: int
    error: str | None
    created_at: datetime
    assets: list[dict]


# ---------- Health ----------
@app.get("/health")
def health():
    return {"ok": True}


# ---------- Auth ----------
@app.post("/api/v1/auth/register", response_model=TokenOut)
def register(body: AuthIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(400, "email already registered")
    u = User(email=body.email, password_hash=pwd.hash(body.password))
    db.add(u)
    db.commit()
    db.refresh(u)
    return TokenOut(access_token=make_token(str(u.id)), user_id=str(u.id), credits=u.credits)


@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(body: AuthIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email).first()
    if not u or not pwd.verify(body.password, u.password_hash):
        raise HTTPException(401, "invalid credentials")
    return TokenOut(access_token=make_token(str(u.id)), user_id=str(u.id), credits=u.credits)


# ---------- Users ----------
@app.get("/api/v1/users/me")
def me(u: User = Depends(current_user)):
    return {"id": str(u.id), "email": u.email, "role": u.role, "credits": u.credits}


# ---------- Uploads ----------
@app.post("/api/v1/uploads/presign")
def presign(content_type: str = "image/png", u: User = Depends(current_user)):
    key = f"uploads/{u.id}/{uuid.uuid4().hex}"
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": S3_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )
    public = f"{S3_PUBLIC}/{S3_BUCKET}/{key}"
    return {"upload_url": url, "key": key, "public_url": public}


# ---------- Jobs ----------
def maybe_enhance_prompt(prompt: str) -> str:
    """LLM prompt enhancer (no-op se sem OPENAI_API_KEY)."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return prompt
    try:
        from openai import OpenAI

        cli = OpenAI(api_key=key)
        sys = (
            "Rewrite the user's prompt for 3D generation. Add visual "
            "vocabulary (style, material, lighting), remove ambiguity, "
            "keep concise English under 70 tokens."
        )
        r = cli.chat.completions.create(
            model=os.environ.get("PROMPT_ENHANCER_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": prompt}],
            temperature=0.4,
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return prompt


COSTS = {"image_to_3d": 5, "text_to_3d": 5, "heightmap": 1, "palmilha": 2}


@app.post("/api/v1/jobs", response_model=JobOut)
def create_job(body: JobIn, db: Session = Depends(get_db), u: User = Depends(current_user)):
    cost = COSTS.get(body.type, 1)
    if u.credits < cost:
        raise HTTPException(402, f"insufficient credits (need {cost}, have {u.credits})")

    inp = dict(body.input)
    if body.type == "text_to_3d" and "prompt" in inp:
        inp["prompt_enhanced"] = maybe_enhance_prompt(inp["prompt"])

    j = Job(user_id=u.id, type=body.type, model=body.model, input=inp, credits_cost=cost)
    db.add(j)
    u.credits -= cost
    db.add(CreditTx(user_id=u.id, delta=-cost, reason=f"job:{body.type}", job_id=j.id))
    db.commit()
    db.refresh(j)
    enqueue_job(str(j.id))
    return _job_dto(db, j)


def _job_dto(db, j: Job) -> JobOut:
    assets = db.query(Asset).filter(Asset.job_id == j.id).all()
    return JobOut(
        id=str(j.id),
        type=j.type,
        model=j.model,
        status=j.status,
        progress=j.progress,
        error=j.error,
        created_at=j.created_at,
        assets=[
            {
                "id": str(a.id),
                "kind": a.kind,
                "url": f"{S3_PUBLIC}/{S3_BUCKET}/{a.storage_key}",
                "bytes": a.bytes,
                "meta": a.meta,
            }
            for a in assets
        ],
    )


@app.get("/api/v1/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db), u: User = Depends(current_user)):
    j = db.query(Job).filter(Job.id == job_id, Job.user_id == u.id).first()
    if not j:
        raise HTTPException(404)
    return _job_dto(db, j)


@app.get("/api/v1/jobs")
def list_jobs(db: Session = Depends(get_db), u: User = Depends(current_user), limit: int = 50):
    rows = (
        db.query(Job)
        .filter(Job.user_id == u.id)
        .order_by(Job.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [_job_dto(db, j) for j in rows]


@app.get("/api/v1/jobs/{job_id}/stream")
async def stream_job(job_id: str, u: User = Depends(current_user)):
    r = get_redis()
    pubsub = r.pubsub()
    pubsub.subscribe(f"jobs:{job_id}:events")

    async def event_gen():
        try:
            while True:
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    yield {"data": msg["data"]}
                    payload = json.loads(msg["data"])
                    if payload.get("done"):
                        break
                await asyncio.sleep(0.1)
        finally:
            pubsub.unsubscribe()
            pubsub.close()

    return EventSourceResponse(event_gen())


# ---------- Marketplace ----------
@app.get("/api/v1/marketplace/listings")
def listings(db: Session = Depends(get_db), limit: int = 50):
    rows = (
        db.query(Listing)
        .filter(Listing.status == "listed")
        .order_by(Listing.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": str(r.id),
            "title": r.title,
            "description": r.description,
            "price_cents": r.price_cents,
            "license": r.license,
            "preview_url": r.preview_url,
        }
        for r in rows
    ]


@app.post("/api/v1/marketplace/listings")
def create_listing(
    asset_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    price_cents: int = Form(...),
    license: str = Form("royalty-free"),
    db: Session = Depends(get_db),
    u: User = Depends(current_user),
):
    a = db.query(Asset).filter(Asset.id == asset_id, Asset.user_id == u.id).first()
    if not a:
        raise HTTPException(404, "asset not found")
    listing = Listing(
        seller_id=u.id,
        asset_id=a.id,
        title=title,
        description=description,
        price_cents=price_cents,
        license=license,
        status="listed",
        preview_url=f"{S3_PUBLIC}/{S3_BUCKET}/{a.storage_key}",
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return {"id": str(listing.id), "status": listing.status}


# ---------- Billing (Stripe stub) ----------
@app.post("/api/v1/billing/checkout")
def billing_checkout(plan: str = Form(...), u: User = Depends(current_user)):
    if not os.environ.get("STRIPE_SECRET_KEY"):
        raise HTTPException(503, "Stripe não configurado")
    import stripe

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": plan, "quantity": 1}],
        client_reference_id=str(u.id),
        success_url="http://localhost:3000/billing/success",
        cancel_url="http://localhost:3000/billing/cancel",
    )
    return {"url": session.url}


@app.post("/api/v1/billing/webhook")
async def stripe_webhook(req: Request, db: Session = Depends(get_db)):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "webhook secret not set")
    import stripe

    payload = await req.body()
    sig = req.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        raise HTTPException(400, f"invalid: {e}")

    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        user_id = sess.get("client_reference_id")
        u = db.query(User).filter(User.id == user_id).first()
        if u:
            u.credits += 200  # TODO: ler do plan
            db.add(CreditTx(user_id=u.id, delta=200, reason="stripe:checkout"))
            db.commit()
    return {"received": True}


# ---------- Admin ----------
@app.get("/api/v1/admin/jobs")
def admin_jobs(db: Session = Depends(get_db), _: User = Depends(require_admin), limit: int = 200):
    rows = db.query(Job).order_by(Job.created_at.desc()).limit(min(limit, 1000)).all()
    return [_job_dto(db, j) for j in rows]


@app.get("/api/v1/admin/users")
def admin_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = db.query(User).order_by(User.created_at.desc()).limit(500).all()
    return [
        {"id": str(r.id), "email": r.email, "role": r.role, "credits": r.credits, "created_at": r.created_at}
        for r in rows
    ]
