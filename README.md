# Finance App — Python Backend (Lite)

A serverless REST API for the personal finance management application, built with FastAPI and deployed as a container image on AWS Lambda. Sits behind API Gateway HTTP API (v2) with Cognito JWT authorization, and reads/writes to an Aurora Serverless v2 PostgreSQL database.

This is a **cost-optimized fork** of [`finance-mgmt-backend`](https://github.com/D3V-K/finance-mgmt-backend), rebuilt for single-digit real-world users rather than as a portfolio piece. The application code is unchanged; what's different is the AWS footprint — see [Cost & Architecture Tradeoffs](#cost--architecture-tradeoffs) for what changed and why.

---

## Table of Contents

- [Overview](#overview)
- [Cost & Architecture Tradeoffs](#cost--architecture-tradeoffs)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Authentication & Authorization](#authentication--authorization)
- [Database Layer](#database-layer)
- [API Reference](#api-reference)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Building and Deployment](#building-and-deployment)
- [CI/CD Pipeline](#cicd-pipeline)
- [Observability](#observability)

---

## Overview

The backend is a FastAPI application wrapped with Mangum to run as an AWS Lambda function. It is packaged as a Docker container image (rather than a zip artifact) to accommodate the combined size of FastAPI, SQLAlchemy, and psycopg2 binary dependencies.

```
API Gateway HTTP API (v2)
  └── Cognito JWT Authorizer (validates Bearer token)
        └── Lambda Function (FastAPI + Mangum, container image, no VPC)
              ├── Aurora Serverless v2 PostgreSQL (public endpoint, TLS-only, scale-to-zero)
              └── Secrets Manager (RDS-managed credential, read at cold-start)
```

---

## Cost & Architecture Tradeoffs

The production-grade version of this backend puts the Lambda function and Aurora cluster inside a private VPC, reachable only from each other, with a NAT Gateway so the Lambda can still call Secrets Manager and ECR. That's the right call for a real multi-tenant product. It's the wrong call for a single-digit-user personal project: **the NAT Gateway and the Aurora minimum-capacity floor are both flat monthly fees that don't scale down with traffic** — you pay them at 3am with zero requests just the same as you would serving real load.

| Cost driver | Production-grade version | This fork | Approx. monthly savings |
|---|---|---|---|
| NAT Gateway | ~$32 flat + ~$0.045/GB processed | Removed — Lambda isn't VPC-attached | ~$32-40 |
| Aurora compute floor | 0.5 ACU minimum, always on (~$40-45) | `MinCapacity: 0` — scales to zero, pays only for active ACU-hours | ~$35-45 (workload-dependent) |
| VPC endpoints | N/A (used NAT instead) | Not needed (no VPC) | — |
| **Estimated baseline (idle)** | **~$75-90/mo before any traffic** | **~$1-3/mo (storage + backups) plus a few cents of compute per active session** | **~90%** |

### What actually changed

- **Aurora Serverless v2 scales to zero.** `ServerlessV2ScalingConfiguration.MinCapacity` is `0` instead of `0.5`. The cluster pauses after a period of inactivity and resumes on the next connection — at the cost of a cold resume delay (see below). `MaxCapacity` defaults to 1 ACU (~2 GB RAM), which is more than enough headroom for a handful of users; the original's ceiling of 4 ACU was sized for load this project will never see.
- **The Lambda function isn't in a VPC at all.** It was only ever in one to reach Aurora privately and to route Secrets Manager/ECR calls through the NAT Gateway. Removing the VPC attachment removes the NAT dependency entirely, and Lambda cold starts are faster without ENI attachment overhead as a bonus.
- **Aurora is publicly accessible instead.** Since Lambda no longer has a private network path to reach it, the database needs a public endpoint. This is the real tradeoff: the DB port is technically internet-reachable. It's mitigated three ways — `rds.force_ssl` is enforced at the cluster parameter group (plaintext connections are rejected), the master password is RDS-managed via `ManageMasterUserPassword` (a long random value in Secrets Manager, never hand-set, easy to rotate), and the security group only opens 5432 (not the whole instance). This is a reasonable bar for a low-value personal finance dataset with single-digit users; it is **not** the bar to hold for a multi-tenant product handling other people's money — that's what the production-grade fork is for.
- **The Secrets Manager credential shape changed.** `ManageMasterUserPassword` gives you a secret containing only `{"username", "password"}` — RDS manages it, and AWS can auto-rotate it. Host, port, and database name aren't secrets, so they're passed as plain Lambda environment variables (`DB_HOST`, `DB_PORT`, `DB_NAME`) instead of being duplicated into the secret's JSON. `src/db.py` reads credentials from Secrets Manager and connection details from the environment, and always connects with `sslmode=require`.
- **No manually-provisioned infrastructure.** The production-grade version treats the VPC, NAT, and Aurora cluster as provisioned outside the SAM stack (by hand, or by a separate process) and passed in as parameters. This fork's `template.yaml` owns the Aurora cluster, subnet group, security group, and parameter group directly — `sam deploy` is the only step needed to stand up the whole thing from nothing but a VPC ID and two subnet IDs (the account's default VPC works fine).

### The cold-start tradeoff

Because Aurora can scale all the way to zero, the first request after a period of inactivity pays two cold starts back to back: the Lambda's own cold start (roughly 1-2s for this image size) plus Aurora resuming from paused (commonly 15-30s, per AWS). For a single-digit-user app where "first request of the day" is a normal pattern, this means an occasional slow request rather than a broken one — `LambdaTimeout` is left at 30s to give the resume room to finish, and this is the one place where "cost-optimized" and "always snappy" are directly in tension. If that resume latency becomes annoying in practice, the fix is a one-line change: bump `DbMaxCapacityAcu`'s floor by setting `MinCapacity: 0.5` instead of `0`, which brings back a small always-on cost (~$40-45/mo) in exchange for eliminating the pause entirely — a deliberate knob, not a rewrite.

### When to use which fork

- Use **this fork** for actually running the app for yourself or a handful of people, where minimizing AWS spend matters more than defense-in-depth network isolation.
- Use the [production-grade version](https://github.com/D3V-K/finance-mgmt-backend) as the reference architecture for a portfolio, for learning VPC/NAT/private-Aurora patterns, or as the starting point if this app ever needs to serve untrusted multi-tenant traffic.

---

## Architecture

### Lambda Container Image

The function is packaged as a Docker container image stored in Amazon ECR. This approach is chosen over a zip deployment for two reasons: the combined size of FastAPI, SQLAlchemy, and psycopg2-binary comfortably exceeds the 50 MB zip limit, and container images support up to 10 GB, giving full control over the runtime environment.

The Lambda handler entry point is the `Mangum` adapter in `src/main.py`. Mangum translates the API Gateway event format into a standard ASGI request that FastAPI can process, and translates the FastAPI response back into the format API Gateway expects.

### No VPC

The Lambda function does **not** join a VPC. It reaches Secrets Manager, ECR, and the Aurora cluster's public endpoint directly over the internet via AWS's managed networking — no NAT Gateway or VPC interface endpoint required. See [Cost & Architecture Tradeoffs](#cost--architecture-tradeoffs) for what this trades away.

### Aurora Serverless v2 (scale-to-zero)

The database is Aurora PostgreSQL Serverless v2 with `MinCapacity: 0`, so it pauses to zero ACUs (and zero compute cost) after a period of inactivity and resumes on the next connection, at the cost of a cold-start delay of roughly 15-30 seconds. `MaxCapacity` defaults to 1 ACU — sized for single-digit concurrent users, not for headroom.

A `NullPool` SQLAlchemy connection pool is used instead of the default pool. Lambda execution contexts are ephemeral and do not persist between invocations reliably, so a persistent connection pool would leak connections to Aurora. `NullPool` opens a fresh connection per request and closes it immediately after — the correct pattern for Lambda.

### Secrets Manager

RDS manages the master credential directly (`ManageMasterUserPassword: true`) — the resulting secret holds only `username` and `password`, and AWS can rotate it without any code changes. Host, port, and database name are passed as plain Lambda environment variables since they aren't sensitive. The Lambda function reads both once per cold start and caches the resulting database URL in module scope; warm invocations reuse it without another Secrets Manager call.

---

## Project Structure

```
backend/
├── src/
│   ├── main.py                  # FastAPI app, router registration, Mangum handler
│   ├── db.py                    # Engine + session setup, Secrets Manager retrieval
│   ├── dependencies.py          # Shared FastAPI dependencies (get_db, get_current_user)
│   │
│   ├── routers/
│   │   ├── transactions.py      # CRUD for transactions
│   │   ├── categories.py        # CRUD for categories + tree structure
│   │   └── reports.py           # Aggregation queries (monthly, by category, net worth)
│   │
│   ├── models/
│   │   ├── base.py              # SQLAlchemy declarative base
│   │   ├── user.py              # User model
│   │   ├── category.py          # Category model (self-referential for sub-categories)
│   │   └── transaction.py       # Transaction model
│   │
│   ├── schemas/
│   │   ├── transaction.py       # Pydantic request/response schemas for transactions
│   │   ├── category.py          # Pydantic schemas for categories
│   │   └── report.py            # Pydantic schemas for report responses
│   │
│   └── utils/
│       └── pagination.py        # Shared pagination helpers
│
├── alembic/
│   ├── env.py                   # Alembic environment config
│   ├── script.py.mako
│   └── versions/                # Individual migration files
│
├── tests/
│   ├── conftest.py              # Pytest fixtures (test DB, test client, auth mock)
│   ├── test_transactions.py
│   ├── test_categories.py
│   └── test_reports.py
│
├── Dockerfile                   # Lambda container image definition
├── .dockerignore                # Keeps venv/tests/secrets out of the build context
├── requirements.txt             # Production dependencies (installed into the image)
├── requirements.dev.txt         # Dev + test dependencies
├── alembic.ini                  # Alembic migration config
├── docker-compose.dev.yaml      # Local PostgreSQL for development
├── template.yaml                # AWS SAM template (Lambda + HTTP API + auth + Aurora)
├── samconfig.toml               # Saved sam build/deploy/local settings per env
└── env.local.example.json       # Template for sam local environment variables
```

---

## Tech Stack

| Concern | Library | Reason |
|---|---|---|
| Framework | FastAPI | Async, automatic OpenAPI docs, Pydantic integration |
| ASGI adapter | Mangum | Translates API Gateway events to ASGI for FastAPI |
| ORM | SQLAlchemy 2.0 | Declarative models, typed queries, migration support |
| Migrations | Alembic | Schema version control tied to SQLAlchemy models |
| DB driver | psycopg2-binary | PostgreSQL driver for SQLAlchemy |
| Validation | Pydantic v2 | Request/response schema validation, built into FastAPI |
| AWS SDK | boto3 | Secrets Manager access, any future AWS service calls |
| Testing | pytest + httpx | Async test client for FastAPI endpoints |
| Packaging | Docker + ECR | Container image deployment to Lambda |
| IaC | AWS SAM | Lambda, API Gateway, IAM, Aurora, and log group provisioning |

---

## Authentication & Authorization

The backend itself contains no authentication logic. JWT validation is offloaded entirely to API Gateway's native Cognito JWT Authorizer. When a request arrives, API Gateway validates the token signature, expiry, issuer, and audience against the configured Cognito User Pool before the Lambda function is ever invoked. An invalid or missing token returns a 401 directly from API Gateway — Lambda is never called.

Once inside the Lambda, the validated JWT claims are injected by API Gateway into the request context. The `get_current_user` dependency extracts the `sub` claim (the Cognito user ID) from the event context, looks up or creates the corresponding user record in the database, and returns it. Every router endpoint that needs user scoping declares this dependency.

```python
# dependencies.py
from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from .models.user import User
from .db import get_db

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    claims = request.state.aws_event["requestContext"]["authorizer"]["jwt"]["claims"]
    cognito_sub = claims.get("sub")
    if not cognito_sub:
        raise HTTPException(status_code=401, detail="Missing user identity")

    user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
    if not user:
        user = User(cognito_sub=cognito_sub)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
```

All data queries are scoped to the authenticated user's ID — there is no admin role or cross-user data access.

---

## Database Layer

### Connection Setup

The database URL is constructed once at module load time (cold start): credentials come from the RDS-managed Secrets Manager secret, host/port/dbname come from plain environment variables, and the connection is forced over TLS. SQLAlchemy uses `NullPool` to avoid connection leaks across Lambda invocations.

```python
# db.py
import os, boto3, json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

_db_url: str | None = None

def get_db_url() -> str:
    global _db_url
    if _db_url:
        return _db_url

    dev_db_url = os.getenv("DATABASE_URL")
    if dev_db_url:
        _db_url = dev_db_url
        return _db_url

    client = boto3.client("secretsmanager")
    secret = json.loads(
        client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    _db_url = (
        f"postgresql+psycopg2://{secret['username']}:{secret['password']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
        f"?sslmode=require"
    )
    return _db_url

engine = create_engine(get_db_url(), poolclass=NullPool)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Models

SQLAlchemy ORM models map directly to the Aurora schema. The `Category` model uses a self-referential foreign key to support nested sub-categories.

```python
# models/category.py
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .base import Base

class Category(Base):
    __tablename__ = "categories"

    id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id   = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name      = Column(String(100), nullable=False)
    type      = Column(String(10))          # 'income' or 'expense'
    color     = Column(String(7))           # hex color e.g. '#4A90E2'
    parent_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)

    children  = relationship("Category", backref="parent", remote_side=[id])
```

### Migrations

Database schema changes are managed with Alembic. Migrations run from a developer machine or a one-off Lambda invocation — they do not run automatically on deployment. Point `DATABASE_URL` at the Aurora cluster's public endpoint (see [Outputs](#deploying)) to run them from a laptop; no VPN or bastion is needed since the cluster is publicly reachable.

```bash
# Create a new migration after changing a model
alembic revision --autogenerate -m "add currency column to transactions"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1
```

---

## API Reference

All endpoints are prefixed with the stage path set by API Gateway (e.g. `/prod`). Every endpoint requires a valid Cognito JWT in the `Authorization: Bearer` header.

### Transactions

| Method | Path | Description |
|---|---|---|
| `GET` | `/transactions` | List transactions with optional `from`, `to`, `category_id` filters |
| `POST` | `/transactions` | Create a new transaction |
| `GET` | `/transactions/{id}` | Get a single transaction |
| `PUT` | `/transactions/{id}` | Update a transaction |
| `DELETE` | `/transactions/{id}` | Delete a transaction |

### Categories

| Method | Path | Description |
|---|---|---|
| `GET` | `/categories` | List all categories as a flat list |
| `GET` | `/categories/tree` | List categories as a nested tree structure |
| `POST` | `/categories` | Create a category (set `parent_id` for sub-categories) |
| `PUT` | `/categories/{id}` | Update a category |
| `DELETE` | `/categories/{id}` | Delete a category (cascades to transactions) |

### Reports

| Method | Path | Description |
|---|---|---|
| `GET` | `/reports/monthly` | Monthly income vs expense totals for a date range |
| `GET` | `/reports/by-category` | Spending breakdown by category for a date range |
| `GET` | `/reports/net-worth` | Cumulative net worth trend over time |

Full OpenAPI documentation is auto-generated by FastAPI and available at `/docs` when running locally.

---

## Environment Variables

The Lambda function reads the following environment variables at runtime. These are set in the SAM template and never committed to the repository.

```bash
DB_SECRET_ARN=arn:aws:secretsmanager:ap-northeast-1:123456789:secret:finance-lite/aurora-master-...
DB_HOST=finance-lite-dev-auroracluster-xxxxx.cluster-xxxxx.ap-northeast-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=financedb
COGNITO_USER_POOL_ID=ap-northeast-1_XXXXXXXXX
ENVIRONMENT=prod    # used to toggle debug logging
API_STAGE=prod      # stage prefix Mangum strips from incoming paths
```

`AWS_REGION` is set by the Lambda runtime itself and is reserved — it cannot be assigned in the template.

For local development, create a `.env` file at the project root and load it with `python-dotenv`. When running locally, set `DATABASE_URL` to point straight at a local PostgreSQL instance; `db.py` prefers it and never calls Secrets Manager. Leaving `DATABASE_URL` unset makes it fall back to `DB_SECRET_ARN` (plus `DB_HOST`/`DB_PORT`/`DB_NAME`), which requires real AWS credentials.

---

## Local Development

**Prerequisites**: Python 3.12+, Docker, AWS SAM CLI, a local PostgreSQL instance (or Docker)

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install all dependencies including dev tools
pip install -r requirements.txt -r requirements.dev.txt

# Run database migrations against a local PostgreSQL instance
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finance
alembic upgrade head

# Start the API locally with hot reload (bypasses Lambda/API Gateway)
uvicorn src.main:app --reload --port 8000
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

To test with the full Lambda + API Gateway emulation using SAM:

```bash
# Build the container image
sam build

# Start the local API Gateway emulator
sam local start-api --env-vars env.local.json
# → http://localhost:3000
```

`env.local.json` supplies environment variables to the local Lambda invocation and can point `DB_SECRET_ARN`/`DB_HOST`/`DB_PORT`/`DB_NAME` at a real deployed cluster or override `DATABASE_URL` for a local instance. Copy `env.local.example.json` to `env.local.json` to get started — it is gitignored, and `samconfig.toml` already points `sam local start-api` at it.

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing

# Run a specific test file
pytest tests/test_transactions.py -v
```

Tests use an in-memory SQLite database via a pytest fixture in `conftest.py` and mock the Cognito JWT claim injection so no real AWS resources are needed.

---

## Building and Deployment

`template.yaml` provisions the **entire** stack, including the database: the Lambda function (container image, no VPC), the HTTP API with its Cognito JWT authorizer, the Aurora Serverless v2 cluster with its subnet group, security group, and RDS-managed Secrets Manager credential, the execution role, log groups, and — in `prod` — an error alarm. Only the Cognito User Pool and a VPC to hang the DB subnet group off of (the account's default VPC is fine) are provisioned outside this stack.

### Stack parameters

| Parameter | Required | Default | Notes |
|---|---|---|---|
| `Environment` | no | `dev` | One of `dev`, `staging`, `prod`. Also the API Gateway stage name. |
| `CognitoUserPoolId` | **yes** | — | Builds the JWT issuer URL. |
| `CognitoUserPoolClientId` | **yes** | — | Validated as the JWT audience. |
| `VpcId` | **yes** | — | VPC for the Aurora subnet group. The default VPC works. |
| `PublicSubnetIds` | **yes** | — | At least two public subnets in different AZs. See command below. |
| `DbName` | no | `financedb` | |
| `DbMaxCapacityAcu` | no | `1` | Aurora Serverless v2 ceiling. `MinCapacity` is fixed at `0` (scale-to-zero) in the template. |
| `CorsAllowOrigins` | no | `*` | Set to the frontend origin in `prod`. |
| `LambdaMemorySize` | no | `512` | |
| `LambdaTimeout` | no | `30` | Capped by the HTTP API integration limit; also needs headroom for an Aurora cold resume. |
| `LogRetentionInDays` | no | `14` | Applies to both the function and access log groups. |

Find your default VPC's public subnet IDs:

```bash
VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query "Vpcs[0].VpcId" --output text)
aws ec2 describe-subnets \
  --filters Name=vpc-id,Values=$VPC_ID Name=default-for-az,Values=true \
  --query "Subnets[].SubnetId" --output text
```

### Deploying

```bash
# Build the container image (SAM reads the Dockerfile via the function's Metadata)
sam build

# Deploy to AWS (first time — guided setup, creates the managed ECR repository)
sam deploy --guided \
  --parameter-overrides \
    Environment=dev \
    CognitoUserPoolId=ap-northeast-1_XXXXXXXXX \
    CognitoUserPoolClientId=XXXXXXXXXXXXXXXXXXXXXXXXXX \
    VpcId=vpc-xxxxxxxx \
    PublicSubnetIds=subnet-aaa,subnet-bbb

# Subsequent deploys reuse the saved parameters in samconfig.toml
sam deploy                    # dev
sam deploy --config-env prod  # prod
```

`sam deploy` publishes the container image to ECR, updates the Lambda function, and applies any CloudFormation stack changes — including, on the very first deploy, standing up the Aurora cluster itself. Expect the first deploy to take several minutes longer than subsequent ones while Aurora provisions. `resolve_image_repos = true` in `samconfig.toml` means SAM creates and reuses a managed ECR repository — no ECR repository needs to be created by hand.

After deploying, the stack outputs `AuroraClusterEndpoint` and `DbSecretArn` — useful for pointing Alembic or a local client at the live database.

### Routing and the stage prefix

Three routes are registered against the HTTP API:

| Route | Authorizer |
|---|---|
| `GET /health` | none — public, for uptime checks and warming |
| `ANY /` | Cognito JWT |
| `ANY /{proxy+}` | Cognito JWT |

Because the stage is named after `Environment`, every request path arrives prefixed (e.g. `/dev/transactions`). The stack passes that prefix to the function as `API_STAGE`, and `main.py` hands it to Mangum as `api_gateway_base_path` so FastAPI routes match without carrying the stage name. Locally `API_STAGE` is unset, so nothing is stripped.

---

## CI/CD Pipeline

Backend deployment is automated via GitHub Actions on every push to `main`.

```yaml
# .github/workflows/deploy-backend.yml
name: Deploy backend

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip

      - run: pip install -r requirements.txt -r requirements.dev.txt

      - run: pytest --cov=src --cov-fail-under=80

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-northeast-1

      - uses: aws-actions/amazon-ecr-login@v2

      - uses: aws-actions/setup-sam@v2

      - name: Build and deploy with SAM
        run: |
          sam build
          sam deploy --config-env prod \
            --image-repository ${{ secrets.ECR_URI }} \
            --parameter-overrides \
              Environment=prod \
              CognitoUserPoolId=${{ secrets.COGNITO_USER_POOL_ID }} \
              CognitoUserPoolClientId=${{ secrets.COGNITO_CLIENT_ID }} \
              VpcId=${{ secrets.VPC_ID }} \
              PublicSubnetIds=${{ secrets.PUBLIC_SUBNET_IDS }}
```

Required repo secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ECR_URI`, `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `VPC_ID`, `PUBLIC_SUBNET_IDS`.

`sam build` builds the image from the `Dockerfile` declared in the function's `Metadata` and `sam deploy` pushes it to ECR — a separate `docker build`/`docker push` step is not needed, and there is no `ImageUri` parameter to override.

The `deploy` job only runs if the `test` job passes, enforcing a minimum 80% test coverage gate before any code reaches the Lambda function.

---

## Observability

All Lambda invocations automatically emit logs to CloudWatch Logs under the log group `/aws/lambda/<stack-name>-api`. Structured JSON logging is used so log entries can be queried and filtered in CloudWatch Insights.

```python
# Structured logging setup in main.py
import logging, json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        })

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(
    logging.DEBUG if os.environ.get("ENVIRONMENT") != "production" else logging.INFO
)
```

Useful CloudWatch Insights queries:

```sql
-- All errors in the last 24 hours
fields @timestamp, message
| filter level = "ERROR"
| sort @timestamp desc
| limit 50

-- Average Lambda duration by hour
stats avg(@duration) as avg_ms by bin(1h)
| sort bin(1h) desc
```

Lambda function metrics (invocation count, error rate, duration, throttles) are visible in the CloudWatch console under the function's monitoring tab without any additional configuration.

---

## Related

- [`finance-mgmt-backend`](https://github.com/D3V-K/finance-mgmt-backend) — the production-grade version this was forked from (private VPC, NAT Gateway, always-on Aurora floor)
- [`/frontend`](../frontend/README.md) — React + Vite frontend
