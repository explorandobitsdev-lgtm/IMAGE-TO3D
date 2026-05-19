# Plataforma 3D-AI — Arquitetura

SaaS de geração 3D (text-to-3D, image-to-3D, palmilha) inspirado em
Meshy AI / Tripo3D. Microserviços containerizados, fila de jobs Redis,
workers GPU, frontend Next.js com viewer Three.js.

## 1. Visão geral

```
                                    ┌──────────────────┐
                                    │  Stripe / OAuth  │
                                    └────────┬─────────┘
                                             │
   ┌─────────────────┐  HTTPS    ┌───────────▼──────────┐  pg  ┌──────────────┐
   │  Next.js (web)  │ ─────────►│  FastAPI (api)       │─────►│ PostgreSQL   │
   │  Three.js R3F   │ ◄─────────│  auth, jobs, billing │      │  users/jobs  │
   └─────┬───────────┘  JSON     └────┬─────────────┬───┘      └──────────────┘
         │                            │             │
         │ assets via                 │ enqueue     │ pub/sub status
         │ presigned URL              ▼             ▼
         │                       ┌──────────┐  ┌──────────┐
         └──────────────────────►│   S3 /   │  │  Redis   │◄─┐
                                 │  MinIO   │  │  queue   │  │
                                 └────┬─────┘  └────┬─────┘  │
                                      │ get/put     │ pop    │ progress
                                      │             ▼        │
                                      │     ┌───────────────┐│
                                      └────►│  Worker GPU   ││
                                            │  PyTorch+CUDA ├┘
                                            │  TripoSR /    │
                                            │  InstantMesh  │
                                            │  + heightmap  │
                                            └───────────────┘
```

## 2. Componentes

| Serviço | Tech | Função |
|---|---|---|
| **web** | Next.js 14 (App Router) + TypeScript + @react-three/fiber | Landing, dashboard, upload, viewer 3D, marketplace |
| **api** | FastAPI + SQLAlchemy + Pydantic | REST: auth (JWT), jobs CRUD, billing, marketplace, admin |
| **worker-gpu** | Python + PyTorch + CUDA | Inferência: image-to-3D (TripoSR/InstantMesh), text-to-3D (Shap-E/Point-E), palmilha (CPU) |
| **postgres** | Postgres 16 | Persistência transacional |
| **redis** | Redis 7 | Fila de jobs (RQ-like), pub/sub de progresso, cache de sessão |
| **minio** | MinIO (S3-compatible) | Storage de uploads e assets gerados. Em produção: S3/R2/GCS |
| **nginx** | Nginx (opcional, prod) | TLS, reverse proxy, rate limit |

## 3. Folder structure

```
platform/
├── ARCHITECTURE.md
├── docker-compose.yml
├── .env.example
├── infra/
│   └── postgres/init.sql
├── apps/
│   ├── api/                 # FastAPI
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py          # rotas: auth, jobs, billing, admin, marketplace
│   │   ├── db.py            # SQLAlchemy session
│   │   ├── models.py        # ORM models
│   │   └── queue.py         # Redis enqueue/pop
│   ├── worker/              # Python GPU worker
│   │   ├── Dockerfile       # nvidia/cuda base
│   │   ├── requirements.txt
│   │   ├── worker.py        # consumidor de fila
│   │   └── pipelines/
│   │       ├── triposr.py   # image-to-3D
│   │       ├── heightmap.py # relevo (reusa src do repo)
│   │       └── palmilha.py  # palmilha (reusa src do repo)
│   └── web/                 # Next.js + Three.js
│       ├── Dockerfile
│       ├── package.json
│       ├── next.config.mjs
│       ├── tsconfig.json
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── globals.css
│       │   ├── page.tsx           # landing cinematográfica
│       │   └── create/page.tsx    # form image-to-3D / text-to-3D / palmilha
│       └── components/
│           └── Viewer.tsx         # R3F + OrbitControls + OBJLoader
└── docs/
    └── api.openapi.yaml    # contrato REST (gerado pelo FastAPI também em /docs)
```

## 4. Database schema (Postgres)

Definido em `infra/postgres/init.sql`. Tabelas principais:

- **users**: `id, email, password_hash, role, credits, stripe_customer_id`
- **plans**: `id, name, stripe_price_id, credits_per_cycle, price_cents`
- **subscriptions**: `id, user_id, plan_id, stripe_subscription_id, status, current_period_end`
- **jobs**: `id, user_id, type, model, input(jsonb), status, progress, error, credits_cost, started_at, finished_at`
- **assets**: `id, job_id, user_id, kind, storage_key, bytes, meta(jsonb)`
- **marketplace_listings**: `id, seller_id, asset_id, title, description, price_cents, license, status`
- **purchases**: `id, buyer_id, listing_id, price_cents_paid, stripe_payment_intent`
- **credit_transactions**: `id, user_id, delta, reason, job_id`

Índices críticos:
- `jobs(user_id, created_at DESC)` — listagem do usuário
- `jobs(status) WHERE status IN ('queued','running')` — worker pickup
- `assets(job_id)` — junção rápida no detalhe do job

## 5. REST API

Base: `/api/v1`. Auth: `Authorization: Bearer <jwt>` (15min) + refresh cookie.

| Método | Rota | Descrição |
|---|---|---|
| POST | `/auth/register` | cria user, retorna JWT |
| POST | `/auth/login` | retorna JWT |
| POST | `/auth/refresh` | rotaciona JWT |
| GET  | `/users/me` | perfil + créditos |
| POST | `/uploads/presign` | URL presigned (PUT) pro MinIO/S3 |
| POST | `/jobs` | enfileira job: `{type, model, input}`. Deduz créditos. |
| GET  | `/jobs/{id}` | status, progresso, assets |
| GET  | `/jobs` | lista paginada do usuário |
| GET  | `/jobs/{id}/stream` | SSE de progresso em tempo real |
| GET  | `/assets/{id}/url` | URL temporária pra download |
| GET  | `/marketplace/listings` | listagem pública filtrável |
| POST | `/marketplace/listings` | publicar asset próprio |
| POST | `/marketplace/listings/{id}/purchase` | comprar (Stripe Checkout) |
| POST | `/billing/checkout` | criar Stripe Checkout session |
| POST | `/billing/webhook` | webhook Stripe (subs + purchases) |
| GET  | `/admin/jobs` | (role=admin) todos os jobs |
| GET  | `/admin/users` | (role=admin) métricas |

OpenAPI gerado automaticamente em `GET /docs` (FastAPI Swagger UI).

## 6. Pipeline de geração

```
POST /jobs           → 1. valida créditos
                       2. INSERT jobs (status=queued)
                       3. LPUSH redis "jobs:queue" job_id
                       4. retorna job_id

Worker loop:
                       1. BRPOP "jobs:queue"
                       2. UPDATE jobs SET status='running', worker_id=…, started_at=NOW()
                       3. PUBLISH "jobs:{id}:progress" 0
                       4. roda pipeline (image-to-3D / text-to-3D / heightmap / palmilha)
                          a. publica progresso (10, 30, 60, 90)
                          b. PBR opcional: gera UV unwrap + texture (xatlas + diffusion)
                          c. exporta OBJ + GLB + STL
                          d. upload pro MinIO/S3
                       5. INSERT assets (uma linha por arquivo)
                       6. UPDATE jobs SET status='succeeded', finished_at=NOW()
                       7. PUBLISH "jobs:{id}:done"

API SSE stream:
                       SUBSCRIBE "jobs:{id}:progress", "jobs:{id}:done"
                       → manda eventos pro browser
```

### Modelos open source integrados

| Modelo | Tipo | Licença | VRAM mín. | Repo |
|---|---|---|---|---|
| **TripoSR** | image→3D, single view | MIT | 8 GB | stabilityai/TripoSR |
| **InstantMesh** | image→3D, alta qualidade | Apache-2 | 16 GB | TencentARC/InstantMesh |
| **Zero123-XL** | novel view synthesis | MIT (research) | 12 GB | cvlab-columbia/zero123 |
| **Wonder3D** | multi-view + mesh recon | AGPL | 24 GB | xxlong0/Wonder3D |
| **Stable Fast 3D** | image→3D rápido | StabilityAI Community | 12 GB | stabilityai/stable-fast-3d (uso comercial restrito — verificar antes) |
| **Shap-E** | text→3D | MIT | 8 GB | openai/shap-e |

Skeleton entrega **TripoSR** ligado e funcional. Os outros ficam como
stubs em `apps/worker/pipelines/` prontos pra implementar.

### Prompt enhancement (text-to-3D)

Antes de mandar pro modelo, passar o prompt do usuário por um LLM
(OpenAI, Claude ou um modelo local via Ollama) com um system prompt do
estilo:

> "Reescreva este prompt para geração 3D: adicione vocabulário visual
> (estilo, material, iluminação), remova ambiguidade, mantenha conciso
> em inglês, < 70 tokens."

Implementado em `apps/api` no endpoint `POST /jobs` quando `type=text_to_3d`,
gravando o prompt original e o expandido no `jobs.input.prompt` /
`jobs.input.prompt_enhanced`.

## 7. Marketplace

- **Listagem**: usuário publica um asset gerado. Sistema cria thumbnail
  (render do GLB com Three.js headless via Puppeteer ou rendering server-side).
- **Compra**: Stripe Payment Intent. Após confirmação via webhook, gera
  asset duplicado para o comprador (ou só dá acesso temporário ao
  storage_key original via signed URL).
- **Royalties**: comissão da plataforma (ex. 20%) abatida via Stripe Connect.
- **Licenças**: enum `cc-by | cc0 | royalty-free | exclusive`. Ao comprar
  como `exclusive`, listagem é retirada e marcada `sold`.
- **Anti-fraude**: detectar duplicatas via hash perceptual do thumbnail
  (pHash) antes de aceitar listagem.

## 8. Escalabilidade & deploy

**Local (skeleton):** docker-compose, 1 worker GPU.

**Produção:**
- Web/API atrás de Nginx ou Cloudflare. Múltiplas réplicas (stateless).
- Workers GPU em pool autoescalável:
  - Bare-metal com NVIDIA (A10G, L4, A100) gerenciado por Kubernetes (NVIDIA GPU Operator).
  - Ou serverless GPU: Runpod, Modal, Replicate, Banana — chamados via webhook por um worker-proxy.
- Fila Redis com priorização: jobs pagos plano premium vão pra `jobs:queue:high`.
- Storage: S3 (us-east) + CloudFront pra distribuição global de assets.
- Postgres: RDS Multi-AZ ou Supabase. Connections via PgBouncer.
- Observabilidade: Prometheus + Grafana (métricas), Sentry (erros), Loki (logs).
- Rate limiting: por API key + por user no Redis.

**GPU worker design:**
- Worker carrega modelos uma vez no boot. Modelo trocável via env `MODEL=triposr|instantmesh|...`.
- Concorrência: 1 job por worker (modelos saturam VRAM). Horizontal scale.
- Health check: `/healthz` retorna `cuda.is_available()` + VRAM livre.
- Graceful shutdown: termina job em andamento antes de morrer (SIGTERM hook).

## 9. Custos estimados (produção pequena, 1k usuários ativos/mês)

| Item | Custo/mês |
|---|---|
| GPU (1× L4 24h Runpod, 50% util) | ~US$ 180 |
| Postgres managed (Supabase Pro) | US$ 25 |
| Redis (Upstash) | US$ 10 |
| S3 + CloudFront (100 GB egress) | US$ 20 |
| Stripe (2.9% + $0.30 por tx) | varia |
| Domínio + e-mail (Resend) | US$ 5 |
| **Total infra** | **~US$ 240/mês** |

## 10. Roadmap de implementação

1. **Skeleton (hoje, entregue):** auth + jobs + 1 modelo + viewer.
2. **Stripe + créditos** (1 semana): planos, checkout, webhook, gating.
3. **Mais modelos** (2 semanas): InstantMesh, Shap-E, Wonder3D.
4. **PBR textures** (1 semana): UV unwrap (xatlas) + diffusion de textura.
5. **Marketplace MVP** (2 semanas): listagem + compra + Stripe Connect.
6. **Admin dashboard** (1 semana): métricas, ban, refund.
7. **Otimizações** (contínuo): cache, CDN, queue priorization, autoscale.

## 11. O que NÃO está pronto

- Stripe — endpoints existem como stubs; precisam de chaves reais + webhook secret.
- Modelos pesados (InstantMesh, Wonder3D) — só TripoSR está fiado no worker.
- Frontend marketplace — backend listado mas UI apenas em "create" + "viewer".
- Autenticação OAuth (Google/GitHub) — só email/senha. OAuth = +Authlib.
- E-mail transacional — usar Resend ou SES.
- Testes (unit + e2e) — TODO.
- Migrations versionadas (Alembic) — schema só em `init.sql` agora.
- Rate limiting — TODO (slowapi + Redis).
