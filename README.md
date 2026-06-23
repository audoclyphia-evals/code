# Allocation System

![PyPI](https://img.shields.io/pypi/v/code.svg?logo=pypi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![Python](https://img.shields.io/badge/python-3.9-blue.svg?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/flask-2.x-000000.svg?logo=flask&logoColor=white)

A domain-driven inventory allocation service built with Python, Flask, and PostgreSQL.

This application manages the allocation of order lines to product batches, following clean architecture principles. It provides a REST API for creating batches, allocating inventory, and querying allocation status, backed by an event-driven service layer with Redis pub/sub integration for inter-service communication.

## Overview

The Allocation System is an example application demonstrating a Python-based architecture for inventory management. The system assigns incoming customer order lines to the most appropriate product batch based on availability and batch date, ensuring earliest-available-first allocation.

### Core Components

- **Domain Layer** (`src/allocation/domain/`) — Core models (`Product`, `Batch`, `OrderLine`), command objects (`Allocate`, `CreateBatch`, `ChangeBatchQuantity`), and domain events (`Allocated`, `Deallocated`, `OutOfStock`).
- **Service Layer** (`src/allocation/service_layer/`) — Command and event handlers, the `MessageBus` dispatcher, and the Unit of Work abstraction (`AbstractUnitOfWork`, `SqlAlchemyUnitOfWork`) for transaction management.
- **Adapters** (`src/allocation/adapters/`) — Concrete implementations for persistence (`SqlAlchemyRepository`), ORM mapping, email notifications (`EmailNotifications`), and Redis event publishing.
- **Entrypoints** (`src/allocation/entrypoints/`) — Flask HTTP API (`flask_app.py`) exposing batch and allocation endpoints, and a Redis pub/sub consumer (`redis_eventconsumer.py`) for handling external events.
- **Views** (`src/allocation/views.py`) — Read-model queries for allocation lookups by order ID.

## Features

- **Domain-Driven Design** — Clean separation between domain models (`Product`, `Batch`, `OrderLine`), application service layer, and infrastructure adapters.
- **Command and Event Architecture** — Commands (`Allocate`, `CreateBatch`, `ChangeBatchQuantity`) drive state changes; domain events (`Allocated`, `Deallocated`, `OutOfStock`) trigger side effects through the message bus.
- **Unit of Work Pattern** — Transaction management via `AbstractUnitOfWork` with a concrete `SqlAlchemyUnitOfWork` implementation, supporting automatic commit and rollback.
- **Repository Pattern** — `AbstractRepository` interface with `SqlAlchemyRepository` for product persistence, including lookup by SKU or batch reference.
- **Flask REST API** — HTTP endpoints for adding batches, allocating order lines, and retrieving allocation views.
- **Redis Event Publishing** — Domain events published to Redis channels (e.g., `line_allocated`) for external consumers.
- **Redis Event Consumption** — Dedicated consumer subscribes to external events (e.g., `change_batch_quantity`) and dispatches corresponding commands.
- **Email Notifications** — Abstracted notification system with SMTP-based `EmailNotifications` implementation, triggered on out-of-stock events.
- **Read Model** — `allocations_view` table maintained by event handlers for efficient allocation lookups without querying domain models.
- **Docker Compose Setup** — Preconfigured services for PostgreSQL, Redis, MailHog, and the application API.

## Requirements

- Python 3.9 or higher
- PostgreSQL 9.6 or higher
- Redis
- Docker and Docker Compose (for containerized deployment)

### Python Dependencies

**Application:**
- `sqlalchemy` (<2)
- `flask`
- `psycopg2-binary`
- `redis`

**Development/Testing:**
- `pytest`
- `pytest-icdiff`
- `mypy`
- `pylint`
- `requests`
- `tenacity`

## Installation

### Using Docker Compose (Recommended)

The fastest way to run the full system including PostgreSQL, Redis, MailHog, and the API:

```bash
git clone <repository-url>
cd code

docker-compose up -d
```

This starts the following services:

| Service | Description | External Port |
|---|---|---|
| `api` | Flask REST API | `5005` |
| `redis_pubsub` | Redis event consumer | — |
| `postgres` | PostgreSQL database | `54321` |
| `redis` | Redis message broker | `63791` |
| `mailhog` | MailHog (email testing UI) | `18025` |

### Local Development Setup

```bash
git clone <repository-url>
cd code

pip install -r requirements.txt
pip install -e src
```

## Quick Start

With the Docker Compose stack running on `localhost:5005`:

```bash
# 1. Create a batch of 100 units
curl -X POST http://localhost:5005/add_batch \
  -H "Content-Type: application/json" \
  -d '{"ref": "batch-001", "sku": "PRODUCT-A", "qty": 100, "eta": null}'

# 2. Allocate 10 units to an order
curl -X POST http://localhost:5005/allocate \
  -H "Content-Type: application/json" \
  -d '{"orderid": "order-001", "sku": "PRODUCT-A", "qty": 10}'

# 3. Check allocations for the order
curl http://localhost:5005/allocations/order-001
```

**Expected response** for step 3:
```json
[
  {"sku": "PRODUCT-A", "batchref": "batch-001"}
]
```

## Usage

### Adding Batches

Batches represent incoming stock. The `POST /add_batch` endpoint accepts a batch reference, SKU, quantity, and optional ETA date:

```python
import requests

url = "http://localhost:5005"

requests.post(f"{url}/add_batch", json={
    "ref": "batch-001",
    "sku": "SKU-123",
    "qty": 200,
    "eta": "2024-03-15",  # null for in-stock items
})
# Response: 201 Created
```

When a batch includes an `eta`, it is treated as an incoming shipment. Batches without an `eta` are considered available immediately. During allocation, earlier-dated batches are preferred.

### Allocating Order Lines

The `POST /allocate` endpoint assigns an order line to the best available batch:

```python
r = requests.post(f"{url}/allocate", json={
    "orderid": "order-123",
    "sku": "SKU-123",
    "qty": 15,
})
print(r.status_code)  # 202 on success, 400 if SKU is invalid
```

If no batch has sufficient stock, the system triggers an `OutOfStock` event, which sends an email notification to `stock@made.com`.

### Querying Allocations

The `GET /allocations/<orderid>` endpoint returns the batch allocation for a given order:

```python
r = requests.get(f"{url}/allocations/order-123")
print(r.json())
# [{"sku": "SKU-123", "batchref": "batch-001"}]
```

Returns `404` if no allocations exist for the order ID.

### Programmatic Usage via Bootstrap

The `bootstrap` module wires together dependencies for programmatic access:

```python
from allocation import bootstrap
from allocation.domain import commands

bus = bootstrap.bootstrap()

# Create a batch
bus.handle(commands.CreateBatch("batch-001", "SKU-A", 100, None))

# Allocate
bus.handle(commands.Allocate("order-001", "SKU-A", 10))
```

The `bootstrap()` function returns a `MessageBus` instance that accepts commands and events. Dependencies such as the Unit of Work, notification backend, and event publisher can be overridden via `inject_dependencies`.

### Running Tests

The test suite is organized into three tiers:

```bash
# Unit tests (fast, no external dependencies)
pytest tests/unit/

# Integration tests (require PostgreSQL, Redis)
pytest tests/integration/

# End-to-end tests (require running Docker Compose stack)
pytest tests/e2e/
```

Unit tests use in-memory fakes (`FakeRepository`, `FakeUnitOfWork`, `FakeNotifications`) defined in `tests/unit/test_handlers.py`. Integration and end-to-end tests exercise the full stack with real infrastructure services.