# Development and Testing Guidelines

Development environment setup, testing strategies, and contribution guidelines for the allocation system example application.

This document provides practical guidance for setting up a local development environment, running the test suite across all testing levels (unit, integration, and end-to-end), and contributing to the project. It covers infrastructure requirements, available tooling, test conventions, and the expected workflow for developers working with this codebase.

## Development

### Prerequisites

The application requires the following infrastructure services, defined in `docker-compose.yml`:

| Service | Purpose | Host Port |
|---|---|---|
| PostgreSQL | Primary database | `54321` |
| Redis | Event pub/sub messaging | `63791` |
| MailHog | Email testing (SMTP) | `11025` (SMTP), `18025` (Web UI) |
| API | Flask web server | `5005` |

### Environment Setup

**Option 1: Docker Compose (recommended)**

Start all infrastructure services and the application:

```bash
docker-compose up
```

This launches the API server on `http://localhost:5005` and the Redis event consumer. The PostgreSQL database, Redis, and MailHog services are started as dependencies.

**Option 2: Local Development**

1. Install Python dependencies:

```bash
pip install -r requirements.txt
pip install -e src
```

2. Set the following environment variables to configure service connections:

| Variable | Purpose | Default (from `config.py`) |
|---|---|---|
| `DB_HOST` | PostgreSQL hostname | `localhost` |
| `DB_PASSWORD` | PostgreSQL password | Required |
| `API_HOST` | API server hostname | `localhost` |
| `REDIS_HOST` | Redis hostname | `localhost` |
| `EMAIL_HOST` | MailHog hostname | `localhost` |

3. Run the Flask application:

```bash
FLASK_APP=allocation/entrypoints/flask_app.py flask run --host=0.0.0.0 --port=80
```

4. Run the Redis event consumer in a separate process:

```bash
python src/allocation/entrypoints/redis_eventconsumer.py
```

### Key Dependencies

**Runtime:**
- `sqlalchemy<2` — ORM and database access
- `flask` — Web framework for HTTP entrypoints
- `psycopg2-binary` — PostgreSQL adapter
- `redis` — Redis client for event publishing and consumption

**Development/Testing:**
- `pytest` — Test runner
- `pytest-icdiff` — Improved diff output for test failures
- `mypy` — Static type checking
- `pylint` — Code linting
- `requests` — HTTP client for API tests
- `tenacity` — Retry logic for test infrastructure setup

### Code Quality

Run type checking and linting with:

```bash
mypy src/allocation
pylint src/allocation
```

## Testing

The test suite is organized into three levels under the `tests/` directory, each serving a distinct purpose.

### Test Structure

```
tests/
├── unit/                  # Fast, isolated domain logic tests
│   ├── test_batches.py    # Batch domain model unit tests
│   ├── test_handlers.py   # Command handler unit tests with fakes
│   └── test_product.py    # Product domain model unit tests
├── integration/           # Tests with real infrastructure
│   ├── test_email.py      # Email notification integration tests
│   ├── test_repository.py # Repository persistence tests
│   ├── test_uow.py        # Unit of work transaction tests
│   └── test_views.py      # View query integration tests
├── e2e/                   # Full system tests via HTTP/Redis
│   ├── test_api.py        # API endpoint end-to-end tests
│   └── test_external_events.py  # Redis event consumer tests
├── conftest.py            # Shared fixtures and infrastructure setup
└── random_refs.py         # Random test data generators
```

### Unit Tests

Unit tests verify domain logic in isolation, using fake implementations for all external dependencies. They are fast and require no running infrastructure.

```bash
# Run all unit tests
pytest tests/unit/

# Run a specific test class
pytest tests/unit/test_handlers.py::TestAllocate
```

Key scenarios covered include order line allocation, batch creation, batch quantity changes, deallocation, error handling for invalid SKUs, unit of work commit behavior, and out-of-stock notifications.

### Integration Tests

Integration tests verify component interactions with real infrastructure (PostgreSQL, SQLite, Redis). The `conftest.py` module provides fixtures for database setup, ORM mapper initialization, and infrastructure readiness checks.

```bash
# Run integration tests
pytest tests/integration/
```

These tests use the `sqlite_bus` fixture to bootstrap a message bus backed by SQLite, and include helpers that wait for external services to become available before executing. Integration tests cover repository persistence, unit of work transactions, email notifications, and view queries including allocation view and deallocation behavior.

### End-to-End Tests

E2E tests exercise the full system through the HTTP API and Redis pub/sub. They use the API client helpers in `tests/e2e/api_client.py` and the Redis client in `tests/e2e/redis_client.py`.

```bash
# Run end-to-end tests
pytest tests/e2e/
```

Prerequisites: All Docker Compose services must be running.

### Running the Full Suite

```bash
# Run all tests (unit + integration)
pytest

# Run with verbose output
pytest -v

# Run a specific test by name
pytest -k test_happy_path_returns_202_and_batch_is_allocated
```

### Writing New Tests

- **Unit tests**: Place in `tests/unit/`. Use fake implementations for all external dependencies. Follow existing patterns in `test_handlers.py` for command handler tests.
- **Integration tests**: Place in `tests/integration/`. Use the session factories and fixtures from `conftest.py` to set up database connections.
- **E2E tests**: Place in `tests/e2e/`. Use `api_client` functions for HTTP interactions and `redis_client` for event-based assertions.

Random test data (order IDs, SKUs, batch references) can be generated using the helpers in `tests/random_refs.py`.

## Contributing

### Workflow

1. Fork the repository and create a feature branch.
2. Make changes following existing code patterns and conventions.
3. Add or update tests for any new functionality.
4. Ensure all test levels pass before submitting.
5. Submit a pull request with a clear description of the changes.

### Code Conventions

- Domain logic lives in `src/allocation/domain/` — keep it free of infrastructure concerns.
- Service layer handlers in `src/allocation/service_layer/handlers.py` orchestrate domain operations.
- Adapters in `src/allocation/adapters/` implement external integrations (database, notifications, Redis).
- Entry points in `src/allocation/entrypoints/` define HTTP and event consumers.
- Tests should use the established fake pattern (`FakeRepository`, `FakeUnitOfWork`) for unit-level isolation.

### Reporting Issues

Report bugs and feature requests via the project's issue tracker. Include reproduction steps, expected behavior, and actual behavior when reporting defects.

## System Overview

The allocation system follows a layered architecture with domain models, service layer handlers, adapters, and entrypoints. For a detailed explanation of the architecture, design patterns (Domain-Driven Design, Unit of Work, Repository, Message Bus), and component interactions, see [System Architecture and Design Patterns](ARCHITECTURE.md).

```mermaid
flowchart TB
    %% Entry Points Tier
    subgraph Entry_Points [Entry Points]
        %% source: cluster_1: entrypoints/flask_app.py with routes /add_batch, /allocate, /deallocate, /allocations/<orderid>
        flask[Flask API]
        %% source: entrypoints/redis_eventconsumer.py
        redis_consumer[Redis Event Consumer]
    end

    %% Service Layer Tier
    subgraph Service_Layer [Service Layer]
        %% source: service_layer/messagebus.py
        bus[Message Bus]
        %% source: service_layer/handlers.py with COMMAND_HANDLERS and EVENT_HANDLERS dicts
        handlers[Command and Event Handlers]
        %% source: service_layer/unit_of_work.py (AbstractUnitOfWork and SqlAlchemyUnitOfWork)
        uow[Unit of Work]
    end

    %% Domain Tier
    subgraph Domain [Domain Layer]
        %% source: domain/model.py Product class
        product[Product Aggregate]
        %% source: domain/model.py Batch class
        batch[Batch]
        %% source: domain/model.py OrderLine dataclass
        orderline[OrderLine]
        %% source: domain/commands.py (Allocate, Deallocate, CreateBatch, ChangeBatchQuantit)
        commands[Commands]
        %% source: domain/events.py (Allocated, Deallocated, OutOfStock)
        events[Events]
    end

    %% Infrastructure/Adapters Tier
    subgraph Adapters [Adapters Layer]
        %% source: adapters/orm.py
        orm[ORM]
        %% source: adapters/repository.py (AbstractRepository, SqlAlchemyRepository)
        repo[Repository]
        %% source: adapters/redis_eventpublisher.py
        redis_pub[Redis Publisher]
        %% source: adapters/notifications.py (AbstractNotifications)
        notifications[Notifications]
        %% source: service_layer/handlers.py functions add_allocation_to_read_model, remove_allocation_from_read_model
        read_model[Read Model]
    end

    %% External Services
    subgraph External [External Infrastructure]
        %% source: docker-compose.yml service postgres
        postgres[(PostgreSQL)]
        %% source: docker-compose.yml service redis
        redis[(Redis)]
        %% source: docker-compose.yml service mailhog, abstracted to Email Service
        email_service[(Email Service)]
    end

    %% Relationships
    flask -->|HTTP| bus
    redis_consumer --> bus
    bus --> handlers
    handlers --> commands
    %% New relationship: events also trigger handlers
    events -.-> handlers
    handlers --> events
    handlers --> uow
    uow --> repo
    repo --> orm
    orm --> postgres
    product --> batch
    batch --> orderline

    redis_pub -->|Publish| redis
    handlers --> redis_pub
    notifications --> email_service
    handlers --> notifications
    redis -->|Consume| redis_consumer

    %% New relationships from context
    handlers --> read_model
    flask -->|Query| read_model
```

### Domain Model

```mermaid
classDiagram
    direction TB
    namespace domain {
        class Product {
            - sku: str
            - batches: List~Batch~
            - version_number: int
            + allocate(line: OrderLine): str
            + change_batch_quantity(ref: str, qty: int)
            + deallocate(line: OrderLine)
        }
        class Batch {
            - ref: str
            - sku: str
            - qty: int
            - eta: Optional~date~
            + allocate(line: OrderLine)
            + deallocate(line: OrderLine)
            + can_deallocate(line: OrderLine): bool
            + deallocate_one() -> OrderLine
            + allocated_quantity: int
            + available_quantity: int
            + can_allocate(line: OrderLine) -> bool
        }
        class OrderLine {
            - orderid: str
            - sku: str
            - qty: int
        }
    }
    namespace commands {
        class Command {
            <<Abstract>>
        }
        class Allocate {
            <<Command>>
            - orderid: str
            - sku: str
            - qty: int
        }
        class Deallocate {
            <<Command>>
            - orderid: str
            - sku: str
            - qty: int
        }
        class CreateBatch {
            <<Command>>
            - ref: str
            - sku: str
            - qty: int
            - eta: Optional~date~
        }
        class ChangeBatchQuantity {
            <<Command>>
            - ref: str
            - qty: int
        }
    }
    namespace events {
        class Event {
            <<Abstract>>
        }
        class Allocated {
            <<Event>>
            - orderid: str
            - sku: str
            - batchref: str
        }
        class Deallocated {
            <<Event>>
            - orderid: str
            - sku: str
            - qty: int
        }
        class OutOfStock {
            <<Event>>
            - sku: str
        }
    }
    Product "1" *-- "0..*" Batch : contains
    Batch "1" *-- "0..*" OrderLine : allocates
    Product --> OrderLine : uses
    Allocate ..|> Command
    Deallocate ..|> Command
    CreateBatch ..|> Command
    ChangeBatchQuantity ..|> Command
    Allocated ..|> Event
    Deallocated ..|> Event
    OutOfStock ..|> Event
    Product ..> Allocated : emits
    Product ..> Deallocated : emits
    Allocate ..> Product : triggers
    Deallocate ..> Product : triggers
    CreateBatch ..> Product : triggers
    ChangeBatchQuantity ..> Product : triggers
```

### Key Flows

```mermaid
sequenceDiagram
    autonumber
    participant Client as "HTTP Client"
    participant Flask as "Flask App (allocate_endpoint)"
    participant MBus as "Message Bus (messagebus.py)"
    participant Handler as "Allocate Handler (handlers.py)"
    participant UoW as "Unit of Work (unit_of_work.py)"
    participant Repo as "Repository (repository.py)"
    participant Product as "Product (model.py)"

    %% Flow traced from scope_function_body: flask_app.py allocate_endpoint
    Client->>Flask: POST /allocate (orderid, sku, qty)
    activate Flask
    Flask->>Flask: _get_json_field(data, "orderid", str)
    Flask->>Flask: _get_json_field(data, "sku", str)
    Flask->>Flask: _get_json_field(data, "qty", int)
    note right of Flask: Creates Allocate command
    Flask->>MBus: bus.handle(commands.Allocate(orderid, sku, qty))

    MBus->>Handler: allocate(cmd, uow)
    activate Handler
    note over Handler: Creates OrderLine(cmd.orderid, cmd.sku, cmd.qty)
    Handler->>UoW: with uow:
    activate UoW
    Handler->>UoW: uow.products.get(sku=line.sku)
    UoW->>Repo: repository.get(sku)
    activate Repo
    Repo-->>UoW: product (or None)
    deactivate Repo
    UoW-->>Handler: product

    alt product is None
        Handler-->>Flask: raise InvalidSku
    else product found
        Handler->>Product: product.allocate(line)
        activate Product
        note over Product: Finds suitable batch and allocates
        Product-->>Handler: batchref (string)
        deactivate Product

        Handler->>UoW: uow.commit()
        note right of UoW: Flushes changes to database
        UoW-->>Handler: committed
        deactivate UoW
    end

    Handler-->>MBus: returns (batchref or exception)
    deactivate Handler
    MBus-->>Flask: returns to bus.handle()
    deactivate Flask

    alt Success (batchref returned)
        Flask-->>Client: 202 OK
    else InvalidSku Exception
        Flask-->>Client: 400 Bad Request
    end

    %% Context sources:
    %% Flask: src/allocation/entrypoints/flask_app.py - allocate_endpoint
    %% MBus: src/allocation/service_layer/messagebus.py - MessageBus
    %% Handler: src/allocation/service_layer/handlers.py - allocate
    %% UoW: src/allocation/service_layer/unit_of_work.py - AbstractUnitOfWork
    %% Repo: src/allocation/adapters/repository.py - AbstractRepository
    %% Product: src/allocation/domain/model.py - Product.allocate
```

```mermaid
sequenceDiagram
    autonumber
    participant Flask as "Flask Endpoint"
    participant Bus as "Message Bus"
    participant Handler as "Deallocate Handler"
    participant UoW as "Unit of Work"
    participant Product as "Product"
    participant Batch as "Batch"

    Flask->>Bus: handle(DeallocateCommand)
    Bus->>Handler: deallocate(cmd, uow)
    Handler->>UoW: products.get(sku)
    UoW-->>Handler: product
    
    alt product is None
        Handler-->>Bus: raise InvalidSku
    else product exists
        Handler->>Product: deallocate(orderline)
        
        Product->>Batch: can_deallocate(line)
        Batch-->>Product: bool
        
        alt can deallocate
            Product->>Batch: deallocate(line)
            Batch-->>Product: None
            Product->>Product: version_number += 1
            Product->>Product: events.append(Deallocated)
            Product-->>Handler: None
            Handler->>UoW: commit()
            UoW-->>Handler: None
        else cannot deallocate
            Product-->>Handler: ValueError
            Handler-->>Bus: raise InvalidDeallocation
        end
    end
    
    Bus-->>Flask: OK
```

```mermaid
sequenceDiagram
    %% source: Cluster_1 (Flask API endpoints)
    actor User as "HTTP Client"
    %% source: src/allocation/entrypoints/flask_app.py#add_batch endpoint
    participant FlaskEndpoint as "add_batch Flask Route"
    %% source: src/allocation/service_layer/messagebus.py#MessageBus
    participant MessageBus as "MessageBus"
    %% source: src/allocation/service_layer/handlers.py#add_batch handler
    participant Handler as "add_batch Handler"
    %% source: src/allocation/service_layer/unit_of_work.py#AbstractUnitOfWork
    participant UoW as "Unit of Work"
    %% source: src/allocation/adapters/repository.py#AbstractRepository
    participant Repository as "Product Repository"
    %% source: src/allocation/domain/model.py#Product class
    participant Product as "Product"

    User->>FlaskEndpoint: POST /add_batch (ref, sku, qty, eta)
    Note right of FlaskEndpoint: Validate JSON fields
    FlaskEndpoint->>MessageBus: handle(CreateBatch command)
    MessageBus->>Handler: add_batch(cmd, uow)
    
    %% source: Unit of Work context manager pattern
    Handler->>UoW: Enter context
    UoW->>Repository: Get product by SKU
    Repository-->>UoW: Return product or None
    
    alt Product exists
        %% source: Product.add_batch method
        UoW->>Product: add_batch(ref, sku, qty, eta)
        Product-->>UoW: Batch added to product
    else Product doesn't exist
        %% source: Product.__init__ constructor - creates new product
        UoW->>Product: Create new Product(sku)
        Product-->>UoW: New product instance created
    end
    
    UoW->>UoW: Commit transaction
    Note right of UoW: Persist to database
    UoW-->>Handler: Context exit
    
    Handler-->>MessageBus: Return
    
    %% source: Event handling loop in MessageBus
    loop Process domain events
        MessageBus->>MessageBus: Dispatch any published events
    end
    
    MessageBus-->>FlaskEndpoint: Return
    
    FlaskEndpoint-->>User: 201 Created
```