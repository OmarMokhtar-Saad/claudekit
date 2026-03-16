---
name: clean-architecture
description: "Use when reviewing or implementing code changes - enforces layer boundaries and dependency rules"
user-invocable: false
---

# Clean Architecture

## Core Principle

**Dependencies point inward. Inner layers know nothing about outer layers.** This creates systems that are testable, maintainable, and adaptable to change.

---

## The Layer Model

```
+--------------------------------------------------+
|  OUTER: Infrastructure / Frameworks / UI          |
|  (databases, web frameworks, file systems, APIs)  |
|                                                    |
|  +--------------------------------------------+  |
|  |  MIDDLE: Application / Use Cases            |  |
|  |  (orchestration, business workflows)        |  |
|  |                                              |  |
|  |  +--------------------------------------+  |  |
|  |  |  INNER: Domain / Business Logic      |  |  |
|  |  |  (entities, value objects, rules)     |  |  |
|  |  +--------------------------------------+  |  |
|  |                                              |  |
|  +--------------------------------------------+  |
|                                                    |
+--------------------------------------------------+
```

### Layer 1: Domain (Innermost)

**Contains:**
- Business entities and value objects
- Business rules and validation logic
- Domain interfaces (ports)
- Domain events

**Depends on:** Nothing external. Only standard language libraries.

**Example concepts:**
- A `User` entity with validation rules for email format
- An `OrderStatus` enum with valid state transitions
- A `MoneyAmount` value object that prevents negative values

### Layer 2: Application / Use Cases (Middle)

**Contains:**
- Use case implementations (application services)
- Input/output port definitions
- Application-level validation
- Orchestration of domain objects

**Depends on:** Domain layer only.

**Example concepts:**
- A `PlaceOrder` use case that coordinates validation, inventory check, payment
- A `UserRegistration` service that handles the signup workflow
- Input DTOs and output DTOs for use case boundaries

### Layer 3: Infrastructure (Outermost)

**Contains:**
- Database implementations (repositories)
- Web controllers and API handlers
- External service clients
- File system access
- Framework configuration
- UI components

**Depends on:** Application and Domain layers.

**Example concepts:**
- A `DatabaseUserRepository` implementing the `UserRepository` port
- A REST controller that calls the `PlaceOrder` use case
- An email service adapter implementing the `NotificationPort`

---

## Forbidden Dependencies

| From | To | Allowed? |
|---|---|---|
| Domain | Application | **NO** |
| Domain | Infrastructure | **NO** |
| Application | Infrastructure | **NO** |
| Infrastructure | Application | Yes |
| Infrastructure | Domain | Yes |
| Application | Domain | Yes |
| Same layer | Same layer | Yes (with caution) |

### How to Detect Violations

Look for these patterns:

**Domain importing infrastructure:**
```
# VIOLATION: Domain layer importing a database library
from database_orm import Session  # in a domain file
```

**Domain depending on application:**
```
# VIOLATION: Entity depending on use case
from app.use_cases import PlaceOrder  # in an entity file
```

**Application importing infrastructure:**
```
# VIOLATION: Use case importing HTTP framework
from web_framework import Request  # in a use case file
```

---

## The Dependency Inversion Principle

When an inner layer needs something from an outer layer, use dependency inversion:

1. **Define an interface (port) in the inner layer**
2. **Implement it in the outer layer**
3. **Inject the implementation at startup**

```
# Domain layer defines the port
class UserRepository:
    def find_by_id(self, user_id: str) -> User | None:
        raise NotImplementedError

    def save(self, user: User) -> User:
        raise NotImplementedError

# Infrastructure layer implements it
class PostgresUserRepository(UserRepository):
    def find_by_id(self, user_id: str) -> User | None:
        # database-specific implementation
        ...

# Application layer uses the port, not the implementation
class GetUserProfile:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def execute(self, user_id: str) -> UserProfile:
        user = self.user_repo.find_by_id(user_id)
        ...
```

---

## Layer Responsibilities

### Domain Layer Rules

- **MUST** contain all business rules
- **MUST** be testable without any external dependencies
- **MUST NOT** know about persistence, UI, or frameworks
- **MUST NOT** import anything from outer layers
- **SHOULD** use value objects for validated data
- **SHOULD** define ports (interfaces) for external dependencies

### Application Layer Rules

- **MUST** orchestrate domain objects to fulfill use cases
- **MUST** define DTOs for input and output at the boundary
- **MUST NOT** contain business rules (delegate to domain)
- **MUST NOT** know about specific infrastructure implementations
- **SHOULD** handle transaction boundaries
- **SHOULD** handle authorization checks

### Infrastructure Layer Rules

- **MUST** implement ports defined by inner layers
- **MUST** handle all framework-specific concerns
- **MUST** convert between external formats and domain objects
- **MUST NOT** contain business logic
- **SHOULD** be replaceable without affecting inner layers

---

## Validation Checklist

When reviewing or implementing changes, verify:

### Structure
- [ ] Each layer has its own directory/module/package
- [ ] No circular dependencies between layers
- [ ] Dependency direction is always inward

### Domain Layer
- [ ] No imports from application or infrastructure
- [ ] Business rules are in entities, not services
- [ ] Value objects validate their own constraints
- [ ] Ports are defined as interfaces in this layer

### Application Layer
- [ ] Use cases have single responsibility
- [ ] No direct infrastructure access (uses ports)
- [ ] DTOs exist at boundaries (no domain objects leaked)
- [ ] No framework-specific annotations or decorators

### Infrastructure Layer
- [ ] Implements ports from inner layers
- [ ] Converts between external and domain representations
- [ ] No business logic hiding in controllers or repositories
- [ ] Framework coupling is isolated here

---

## Common Violations and Fixes

| Violation | Fix |
|---|---|
| Business logic in controller | Move to domain entity or use case |
| Database queries in use case | Create repository port, implement in infrastructure |
| Domain entity knows about JSON | Create DTO in application layer for serialization |
| Use case returns database entity | Map to output DTO at application boundary |
| Framework annotations in domain | Remove and use configuration in infrastructure |
| Validation in controller only | Add domain validation in entity/value object |
