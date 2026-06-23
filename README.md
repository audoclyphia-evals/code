# Allocation System

![PyPI](https://img.shields.io/pypi/v/code.svg?logo=pypi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![Python](https://img.shields.io/badge/python-3.9-blue.svg?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/flask-2.x-000000.svg?logo=flask&logoColor=white)

A domain-driven inventory allocation service built with Python, Flask, and PostgreSQL.

This application manages the allocation of order lines to product batches, following clean architecture principles. It provides a REST API for creating batches, allocating inventory, and querying allocation status, backed by an event-driven service layer with Redis pub/sub integration for inter-service communication.

## Project Overview

The Allocation System is an example application demonstrating a Python-based architecture for inventory management. The system assigns incoming customer order lines to the most appropriate product batch based on availability and batch date, ensuring earliest-available-first allocation.

The architecture employs several key patterns:
- **Domain-Driven Design** — Clean separation between domain models (`Product`, `Batch`, `OrderLine`), application service layer, and infrastructure adapters.
- **Command and Event Architecture** — Commands (`Allocate`, `CreateBatch`, `ChangeBatchQuantity`, `Deallocate`) drive state changes; domain events (`Allocated`, `Deallocated`, `OutOfStock`) trigger side effects through the message bus.
- **Unit of Work and Repository Patterns** — Transaction management via `AbstractUnitOfWork` and product persistence via `AbstractRepository` interface.
- **Flask REST API & Redis Event Integration** — HTTP endpoints for core operations, with Redis for publishing domain events and consuming external commands.
- **Read Model & Notifications** — An `allocations_view` table for efficient lookups and an abstracted notification system for events like out-of-stock.

The following sections detail the system's structure, requirements, and usage.

## Features

The codebase is organized as follows:
- **Domain Layer** (`src/allocation/domain/`) — Core models (`Product`, `Batch`, `OrderLine`), command objects (`Allocate`, `CreateBatch`, `ChangeBatchQuantity`, `Deallocate`), and domain events (`Allocated`, `Deallocated`, `OutOfStock`).
- **Service Layer** (`src/allocation/service_layer/`) — Command and event handlers, the `MessageBus` dispatcher, and the Unit of Work abstraction (`AbstractUnitOfWork`, `SqlAlchemyUnitOfWork`) for transaction management.
- **Adapters** (`src/allocation/adapters/`) — Concrete implementations for persistence (`SqlAlchemyRepository`), ORM mapping, email notifications (`EmailNotifications`), and Redis event publishing.
- **Entrypoints** (`src/allocation/entrypoints/`) — Flask HTTP API (`flask_app.py`) exposing batch, allocation, and deallocation endpoints, and a Redis pub/sub consumer (`redis_eventconsumer.py`) for handling external events.
- **Views** (`src/allocation/views.py`) — Read-model queries for allocation lookups by order ID.

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

## Quickstart

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

This section provides detailed examples for interacting with the system.

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

Request fields are validated by type. Missing or incorrectly typed fields return a `400` error with a descriptive message. When a batch includes an `eta`, it is treated as an incoming shipment. Batches without an `eta` are considered available immediately. During allocation, earlier-dated batches are preferred.

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

### Deallocating Order Lines

The `POST /deallocate` endpoint removes a previously allocated order line from its batch, freeing the stock. If the deallocated order line was previously displaced from another batch (e.g., due to a batch quantity reduction), it is automatically reallocated to the best available batch:

```python
r = requests.post(f"{url}/deallocate", json={
    "orderid": "order-123",
    "sku": "SKU-123",
    "qty": 15,
})
print(r.status_code)  # 202 on success, 400 on error
```

Errors returned as `400`:
- `InvalidSku` — the SKU does not exist in the system.
- `InvalidDeallocation` — no batch has an allocation matching the specified order line.

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

# Deallocate
bus.handle(commands.Deallocate("order-001", "SKU-A", 10))
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

## API Reference

The following is a summary of the HTTP API endpoints. For a detailed OpenAPI specification, refer to `api_documentation.yaml`.

| Method | Endpoint | Description | Success Code | Error Codes |
|---|---|---|---|---|
| `POST` | `/add_batch` | Creates a new batch. | `201 Created` | `400` (Invalid input) |
| `POST` | `/allocate` | Allocates an order line to the best batch. | `202 Accepted` | `400` (`InvalidSku`, `OutOfStock`) |
| `POST` | `/deallocate` | Deallocates a specific order line from a batch. | `202 Accepted` | `400` (`InvalidSku`, `InvalidDeallocation`) |
| `GET` | `/allocations/<orderid>` | Retrieves all batch allocations for an order. | `200 OK` | `404` (Not Found) |

## Additional Documentation

For more detailed information, see the following documentation:

- [System Architecture and Design Patterns](ARCHITECTURE.md) - Explains the overall architecture of the Allocation System, focusing on key patterns like Domain-Driven Design, repository, unit of work, and event-driven architecture, which are central to understanding this example application. Helps developers grasp the system structure and component interactions.
- [Development and Testing Guidelines](CONTRIBUTING.md) - Provides guidelines for setting up the development environment, contributing to the codebase, and running tests (unit, integration, e2e). Since the repository includes extensive test files and Docker configuration, this helps newcomers understand how to develop and test locally.