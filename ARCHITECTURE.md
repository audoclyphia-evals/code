# System Architecture and Design Patterns

> A deep dive into the allocation service's domain-driven design, layered architecture, and the patterns that drive its command/event processing pipeline.

The allocation service implements an inventory management system built on Domain-Driven Design principles. It manages the allocation of order lines to product batches, handling the full lifecycle from batch creation through allocation and deallocation. The system employs a clean separation between domain logic, service layer orchestration, and infrastructure adapters, communicating internally through a message bus that dispatches both commands and domain events.

## Architecture

The system follows a **layered architecture** with clear boundaries between domain logic, application services, and infrastructure concerns. Each layer has a defined responsibility and communicates through well-established DDD patterns.

### Core Components

| Layer | Components | Responsibility |
|-------|-----------|----------------|
| **Domain** | `Product`, `Batch`, `OrderLine` | Core business rules for inventory allocation. `Product` serves as the aggregate root managing batch collections and allocation logic. |
| **Service Layer** | `MessageBus`, command/event handlers | Orchestrates use cases by dispatching commands to handlers, which coordinate domain objects and infrastructure through the Unit of Work. |
| **Adapters** | `SqlAlchemyRepository`, `SqlAlchemyUnitOfWork`, `EmailNotifications`, Redis publisher | Implements abstract interfaces for persistence, notifications, and external event publishing. |
| **Entrypoints** | Flask HTTP API, Redis event consumer | Receives external requests (HTTP and Redis pub/sub messages) and translates them into commands on the message bus. |

### Key Design Patterns

**Repository Pattern** — `AbstractRepository` defines a persistence interface; `SqlAlchemyRepository` provides the concrete implementation. This decouples domain logic from database specifics.

**Unit of Work** — `AbstractUnitOfWork` manages transaction boundaries and tracks new domain events generated during a business operation. `SqlAlchemyUnitOfWork` implements this with SQLAlchemy sessions.

**Message Bus** — The `MessageBus` dispatches both commands (synchronous, imperative operations) and events (reactive, side-effect triggers). Commands are handled by a single handler; events can trigger multiple downstream handlers.

**CQRS (Command Query Responsibility Segregation)** — The system maintains a separate `allocations_view` read model, updated via event handlers (`add_allocation_to_read_model` / `remove_allocation_from_read_model`), queried by the `allocations` view function.

```mermaid
flowchart TB
    %% Entry Points Tier
    subgraph Entry_Points [Entry Points]
        flask[Flask API]
        redis_consumer[Redis Event Consumer]
    end
    
    %% Service Layer Tier
    subgraph Service_Layer [Service Layer]
        bus[Message Bus]
        handlers[Command and Event Handlers]
        uow[Unit of Work]
    end
    
    %% Domain Tier
    subgraph Domain [Domain Layer]
        product[Product Aggregate]
        batch[Batch]
        orderline[OrderLine]
        commands[Commands]
        events[Events]
    end
    
    %% Infrastructure/Adapters Tier
    subgraph Adapters [Adapters Layer]
        orm[ORM]
        repo[Repository]
        redis_pub[Redis Publisher]
        notifications[Notifications]
    end
    
    %% External Services
    subgraph External [External Infrastructure]
        postgres[(PostgreSQL)]
        redis[(Redis)]
        mailhog[(MailHog)]
    end
    
    %% Relationships
    flask -->|HTTP| bus
    redis_consumer --> bus
    bus --> handlers
    handlers --> commands
    handlers --> events
    handlers --> uow
    uow --> repo
    repo --> orm
    orm --> postgres
    product --> batch
    batch --> orderline
    
    redis_pub --> redis
    handlers --> redis_pub
    notifications --> mailhog
    handlers --> notifications
    redis --> redis_consumer
```

### Data Flow

1. **HTTP requests** arrive at Flask endpoints, which deserialize input and dispatch commands to the message bus.
2. **Redis events** (e.g., `change_batch_quantity`) are consumed by the Redis event consumer and translated into commands.
3. The **message bus** routes commands to handlers, which open a Unit of Work, load aggregates via the repository, execute domain logic, and commit.
4. **Domain events** emitted during command handling (e.g., `Allocated`, `Deallocated`, `OutOfStock`) are collected by the Unit of Work and dispatched back through the message bus.
5. Event handlers perform **side effects**: publishing to external Redis channels, updating the read model, and sending email notifications.

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

### Domain Model

The domain is centered on three core types:

- **`Product`** — Aggregate root that owns a collection of `Batch` objects. All allocation and deallocation operations go through the product, which enforces invariants and emits domain events.
- **`Batch`** — Represents a replenishment batch with a reference, SKU, quantity, and optional ETA. Tracks allocated `OrderLine` sets and computes available quantity.
- **`OrderLine`** — Value object representing a customer order line (orderid, sku, qty).

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

### Domain Events

Domain events represent state changes that external consumers react to:

| Event | Trigger | Downstream Effects |
|-------|---------|-------------------|
| `Allocated` | Successful allocation of an order line | Publish to Redis `line_allocated` channel; insert into read model |
| `Deallocated` | Order line removed from a batch | Attempt reallocation to another batch; remove from read model |
| `OutOfStock` | Allocation fails due to insufficient stock | Send out-of-stock email notification |

### Deallocation and Batch Quantity Changes

When a batch quantity is reduced via the `ChangeBatchQuantity` command, the domain may need to deallocate previously allocated order lines. These deallocated lines are then automatically reallocated to other available batches. If no batch can be found with a matching allocation, an `InvalidDeallocation` exception is raised, which the Flask endpoint translates into a `400 Bad Request` response.

Both `Batch` and `Product` expose `deallocate()` and `can_deallocate()` methods that enforce the invariant that only lines present in a batch's allocation set can be removed.

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

### Batch Addition Flow

New batches are added through the `CreateBatch` command. If the product does not yet exist, a new `Product` aggregate is created. The handler appends the batch to the product's collection and commits.

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

### Infrastructure Integration

- **PostgreSQL** — Primary data store for products, batches, allocations, and the read model.
- **Redis** — Used for pub/sub messaging: publishing `line_allocated` events and consuming `change_batch_quantity` commands from external systems.
- **MailHog** — SMTP mock for out-of-stock email notifications during development and testing.

## Project Structure

```
src/
├── allocation/
│   ├── domain/                  # Core domain model and events
│   │   ├── model.py             # Product, Batch, OrderLine aggregates
│   │   ├── events.py            # Allocated, Deallocated, OutOfStock events
│   │   └── commands.py          # Allocate, Deallocate, CreateBatch, ChangeBatchQuantity commands
│   ├── service_layer/           # Application service orchestration
│   │   ├── handlers.py          # Command and event handler functions
│   │   ├── messagebus.py        # MessageBus dispatching commands and events
│   │   └── unit_of_work.py      # Abstract and SQLAlchemy unit of work implementations
│   ├── adapters/                # Infrastructure implementations
│   │   ├── orm.py               # SQLAlchemy table definitions and mapper setup
│   │   ├── repository.py        # Abstract and SQLAlchemy repository implementations
│   │   ├── notifications.py     # Abstract and email notification implementations
│   │   └── redis_eventpublisher.py  # Redis pub/sub event publisher
│   ├── entrypoints/             # External interface adapters
│   │   ├── flask_app.py         # Flask HTTP API with route definitions
│   │   └── redis_eventconsumer.py  # Redis pub/sub consumer for external events
│   ├── bootstrap.py             # Application bootstrapping and dependency injection
│   ├── config.py                # Environment-based configuration for all services
│   └── views.py                 # Read model query functions
tests/
├── unit/                        # Domain and handler unit tests
│   ├── test_batches.py          # Batch domain model tests
│   ├── test_product.py          # Product aggregate tests
│   └── test_handlers.py         # Command handler tests with fake dependencies
├── integration/                 # Integration tests against real infrastructure
│   ├── test_repository.py       # Repository persistence tests
│   ├── test_uow.py              # Unit of work transaction tests
│   ├── test_views.py            # Read model view tests
│   └── test_email.py            # Email notification integration tests
├── e2e/                         # End-to-end API and event tests
│   ├── api_client.py            # HTTP client helpers for API testing
│   ├── redis_client.py          # Redis pub/sub client helpers
│   ├── test_api.py              # Full API allocation flow tests
│   └── test_external_events.py  # Redis event consumption tests
├── conftest.py                  # Shared test fixtures (DB, API, Redis setup)
└── random_refs.py               # Random test data generators
├── docker-compose.yml           # Service orchestration (API, Redis consumer, Postgres, Redis, MailHog)
├── Dockerfile                   # Python 3.9 application image
└── requirements.txt             # Project dependencies
```

### Key Directories

- **`domain/`** — Pure domain logic with no infrastructure dependencies. Contains the aggregate root (`Product`), value objects (`Batch`, `OrderLine`), commands, and events.
- **`service_layer/`** — Orchestrates domain operations through the message bus. Handlers coordinate between the repository, unit of work, and external services.
- **`adapters/`** — Implements abstract interfaces defined by the service layer. Swappable for testing or alternative infrastructure.
- **`entrypoints/`** — Translates external protocols (HTTP, Redis pub/sub) into internal commands.
- **`tests/`** — Three-tier testing strategy: unit tests with fakes, integration tests against real databases, and end-to-end tests against the running API.