CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'user',
    credits         INTEGER      NOT NULL DEFAULT 5,
    stripe_customer_id VARCHAR(120),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE plans (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(50)  NOT NULL,
    stripe_price_id     VARCHAR(120),
    credits_per_cycle   INTEGER      NOT NULL,
    price_cents         INTEGER      NOT NULL,
    active              BOOLEAN      NOT NULL DEFAULT TRUE
);
INSERT INTO plans (name, credits_per_cycle, price_cents) VALUES
  ('free',  5,    0),
  ('pro',   200,  1900),
  ('team',  1000, 9900);

CREATE TABLE subscriptions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID REFERENCES users(id) ON DELETE CASCADE,
    plan_id                 INTEGER REFERENCES plans(id),
    stripe_subscription_id  VARCHAR(120),
    status                  VARCHAR(30) NOT NULL DEFAULT 'active',
    current_period_end      TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(40) NOT NULL,         -- image_to_3d | text_to_3d | heightmap | palmilha
    model           VARCHAR(40),                  -- triposr | instantmesh | shap_e | wonder3d | trimesh
    input           JSONB NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'queued',  -- queued|running|succeeded|failed
    progress        INTEGER     NOT NULL DEFAULT 0,
    error           TEXT,
    credits_cost    INTEGER     NOT NULL DEFAULT 1,
    worker_id       VARCHAR(120),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_jobs_user_created ON jobs(user_id, created_at DESC);
CREATE INDEX idx_jobs_status_active ON jobs(status) WHERE status IN ('queued','running');

CREATE TABLE assets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id      UUID REFERENCES jobs(id) ON DELETE CASCADE,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    kind        VARCHAR(20) NOT NULL,   -- mesh_obj | mesh_glb | mesh_stl | texture | preview
    storage_key VARCHAR(500) NOT NULL,
    bytes       BIGINT,
    meta        JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_assets_job ON assets(job_id);

CREATE TABLE marketplace_listings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id   UUID REFERENCES users(id) ON DELETE CASCADE,
    asset_id    UUID REFERENCES assets(id) ON DELETE CASCADE,
    title       VARCHAR(200) NOT NULL,
    description TEXT,
    price_cents INTEGER NOT NULL,
    license     VARCHAR(40) NOT NULL DEFAULT 'royalty-free',
    status      VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft|listed|sold|removed
    preview_url VARCHAR(500),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_listings_status ON marketplace_listings(status, created_at DESC);

CREATE TABLE purchases (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buyer_id               UUID REFERENCES users(id),
    listing_id             UUID REFERENCES marketplace_listings(id),
    price_cents_paid       INTEGER NOT NULL,
    stripe_payment_intent  VARCHAR(120),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE credit_transactions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    delta       INTEGER NOT NULL,
    reason      VARCHAR(100) NOT NULL,
    job_id      UUID REFERENCES jobs(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_credit_user ON credit_transactions(user_id, created_at DESC);
