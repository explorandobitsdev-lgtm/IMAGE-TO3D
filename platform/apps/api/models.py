"""ORM models — mirroring infra/postgres/init.sql."""
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    credits = Column(Integer, nullable=False, default=5)
    stripe_customer_id = Column(String(120))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Plan(Base):
    __tablename__ = "plans"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    stripe_price_id = Column(String(120))
    credits_per_cycle = Column(Integer, nullable=False)
    price_cents = Column(Integer, nullable=False)
    active = Column(Boolean, default=True)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    type = Column(String(40), nullable=False)
    model = Column(String(40))
    input = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    progress = Column(Integer, nullable=False, default=0)
    error = Column(Text)
    credits_cost = Column(Integer, nullable=False, default=1)
    worker_id = Column(String(120))
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Asset(Base):
    __tablename__ = "assets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    kind = Column(String(20), nullable=False)
    storage_key = Column(String(500), nullable=False)
    bytes = Column(BigInteger)
    meta = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Listing(Base):
    __tablename__ = "marketplace_listings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"))
    title = Column(String(200), nullable=False)
    description = Column(Text)
    price_cents = Column(Integer, nullable=False)
    license = Column(String(40), default="royalty-free")
    status = Column(String(20), default="draft")
    preview_url = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class CreditTx(Base):
    __tablename__ = "credit_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    delta = Column(Integer, nullable=False)
    reason = Column(String(100), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
