---
name: refactoring-patterns
description: "Use when refactoring code - catalog of proven patterns with effort estimates"
user-invocable: false
---

# Refactoring Patterns

## Core Principle

**Refactoring changes structure without changing behavior.** Every refactoring step must keep the test suite green. If you cannot run tests between steps, the steps are too large.

---

## Pattern Catalog

### 1. Layer Boundary Fixes

**Problem:** Business logic has leaked into controllers, UI code, or infrastructure layers.

**Symptoms:**
- Controllers/handlers contain validation logic
- Database queries mixed with business rules
- UI components making direct API calls with business logic

**Steps:**
1. Identify the misplaced logic
2. Create appropriate domain service or entity method
3. Move the logic to the domain layer
4. Update the outer layer to delegate to the domain
5. Verify behavior is unchanged

**Effort:** Medium (2-4 hours per boundary fix)

**Risk:** Low if tests exist for the current behavior

---

### 2. God Class Extraction

**Problem:** A single class/module has too many responsibilities.

**Symptoms:**
- Class has 500+ lines
- Class has 10+ public methods in unrelated areas
- Changes to one feature frequently require modifying this class
- Hard to name the class without using "Manager", "Handler", "Utils"

**Steps:**
1. List all responsibilities of the god class
2. Group related methods into cohesive clusters
3. Create new classes for each cluster
4. Move methods to their new homes one at a time
5. Update the god class to delegate to new classes
6. Eventually remove the god class or reduce it to a facade

**Effort:** High (4-8 hours depending on size)

**Risk:** Medium - ensure callers are updated

**Example transformation:**
```
BEFORE:
  OrderManager
    - createOrder()
    - validateOrder()
    - calculateTotal()
    - applyDiscount()
    - sendConfirmationEmail()
    - generateInvoice()
    - updateInventory()

AFTER:
  OrderService          -> createOrder()
  OrderValidator        -> validateOrder()
  PricingCalculator     -> calculateTotal(), applyDiscount()
  NotificationService   -> sendConfirmationEmail()
  InvoiceGenerator      -> generateInvoice()
  InventoryService      -> updateInventory()
```

---

### 3. Circular Dependency Breaks

**Problem:** Module A depends on Module B, which depends on Module A.

**Symptoms:**
- Import errors or initialization order issues
- Difficulty testing modules in isolation
- Changes ripple unpredictably between modules

**Resolution strategies:**

**Strategy A: Extract Interface**
1. Identify the dependency direction that should be inverted
2. Create an interface in the depended-upon module
3. Have the depending module implement or use the interface
4. Break the direct import

**Strategy B: Extract Shared Module**
1. Identify the shared concepts causing the cycle
2. Create a new module for those shared concepts
3. Have both original modules depend on the new one
4. Remove the direct dependency between the originals

**Strategy C: Merge Modules**
1. If the modules are tightly coupled, they may belong together
2. Merge into a single module
3. Consider if the merged module needs splitting differently

**Effort:** Medium (2-4 hours)

**Risk:** Medium - may affect module boundaries project-wide

---

### 4. State Management Cleanup

**Problem:** State is scattered, duplicated, or mutated unpredictably.

**Symptoms:**
- Same data stored in multiple places
- Bugs where state gets "out of sync"
- Difficult to determine the current state at any point
- Global mutable state accessed from many locations

**Steps:**
1. Map all state locations (globals, singletons, instance vars)
2. Identify the single source of truth for each piece of state
3. Remove duplicate state storage
4. Create clear state transitions (state machine if appropriate)
5. Add validation at state boundaries

**Effort:** High (4-12 hours depending on scope)

**Risk:** High - state bugs are subtle and may not be caught by simple tests

---

### 5. Long Method Extraction

**Problem:** A method is too long to understand at a glance.

**Symptoms:**
- Method exceeds 30 lines
- Multiple levels of nesting
- Comments separating "sections" within the method
- Variables only used in one section

**Steps:**
1. Identify logical sections within the method
2. Extract each section into a well-named private method
3. The original method becomes a high-level orchestration
4. Verify behavior unchanged after each extraction

**Effort:** Low (30-60 minutes)

**Risk:** Very Low - straightforward mechanical transformation

---

### 6. Conditional to Polymorphism

**Problem:** Long if/else or switch chains that grow with each new case.

**Symptoms:**
- Switch statements duplicated in multiple places
- Adding a new case requires touching multiple files
- Conditions based on type codes or enum values

**Steps:**
1. Identify the condition being switched on
2. Create an interface/base class for the behavior
3. Create an implementation for each case
4. Replace conditionals with polymorphic dispatch
5. Use a factory or registry to select the implementation

**Effort:** Medium (2-4 hours)

**Risk:** Low-Medium - well-understood transformation

---

### 7. Primitive Obsession to Value Objects

**Problem:** Using raw primitives (strings, integers) for domain concepts.

**Symptoms:**
- Validation logic repeated wherever the value is used
- Easy to mix up parameters of the same type
- No central place for format rules

**Steps:**
1. Identify the domain concept (email, money, phone number, etc.)
2. Create a value object class with validation in the constructor
3. Replace raw primitives with the value object throughout
4. Move format/validation logic into the value object

**Effort:** Low-Medium (1-3 hours)

**Risk:** Low - adds type safety

---

## Effort Estimation Guide

| Pattern | Typical Effort | Risk | Prerequisites |
|---|---|---|---|
| Layer Boundary Fix | 2-4 hours | Low | Tests exist |
| God Class Extraction | 4-8 hours | Medium | Clear responsibility groups |
| Circular Dependency Break | 2-4 hours | Medium | Understand the cycle |
| State Management Cleanup | 4-12 hours | High | Full state map |
| Long Method Extraction | 30-60 min | Very Low | None |
| Conditional to Polymorphism | 2-4 hours | Low-Medium | Clear case structure |
| Primitive to Value Object | 1-3 hours | Low | None |

---

## Refactoring Safety Rules

1. **Test before refactoring** - Ensure tests exist for current behavior
2. **Small steps** - Each step should be independently verifiable
3. **One refactoring at a time** - Do not combine multiple patterns in one step
4. **Run tests after every step** - Catch regressions immediately
5. **Commit after each step** - Create rollback points
6. **No behavior changes** - If you need to change behavior, that is a separate task
