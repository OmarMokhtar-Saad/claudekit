---
name: api-design-patterns
description: "Use when designing or reviewing APIs - REST, GraphQL, gRPC conventions and best practices"
user-invocable: false
---

# API Design Patterns

## Core Principle

**APIs are contracts.** Once published, they are difficult to change without breaking consumers. Design for longevity, consistency, and clarity from the start.

---

## REST API Design

### Resource Naming

| Pattern | Example | Rule |
|---|---|---|
| Collection | `/users` | Plural nouns, never verbs |
| Item | `/users/{id}` | Singular resource by identifier |
| Nested | `/users/{id}/orders` | Express ownership relationships |
| Action | `/users/{id}/activate` | POST for non-CRUD operations |

### HTTP Methods

| Method | Purpose | Idempotent | Request Body |
|---|---|---|---|
| GET | Read resource(s) | Yes | No |
| POST | Create resource | No | Yes |
| PUT | Replace resource entirely | Yes | Yes |
| PATCH | Partial update | No | Yes |
| DELETE | Remove resource | Yes | No |

### Status Codes

| Code | Meaning | Use When |
|---|---|---|
| 200 | OK | Successful GET, PUT, PATCH |
| 201 | Created | Successful POST that creates a resource |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid input, validation failure |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Authenticated but not authorized |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Resource state conflict (duplicate, version mismatch) |
| 422 | Unprocessable Entity | Semantically invalid input |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Unhandled server failure |

---

## Versioning Strategies

| Strategy | Format | Pros | Cons |
|---|---|---|---|
| URL path | `/v1/users` | Explicit, easy to route | URL changes per version |
| Header | `Accept: application/vnd.api.v1+json` | Clean URLs | Less visible |
| Query param | `/users?version=1` | Easy to add | Pollutes query string |

**Recommendation:** Use URL path versioning for public APIs. Use header versioning for internal APIs where clients are controlled.

### Version Lifecycle

- **Active**: Current version, fully supported
- **Deprecated**: Still functional, migration deadline communicated
- **Sunset**: Removed, returns 410 Gone

---

## Pagination

### Cursor-Based (Recommended)

```
GET /users?after=cursor_abc&limit=20

Response:
{
  "data": [...],
  "pagination": {
    "next_cursor": "cursor_xyz",
    "has_more": true
  }
}
```

### Offset-Based

```
GET /users?offset=40&limit=20

Response:
{
  "data": [...],
  "pagination": {
    "total": 150,
    "offset": 40,
    "limit": 20
  }
}
```

| Method | Pros | Cons |
|---|---|---|
| Cursor-based | Stable under mutations, performant | Cannot jump to arbitrary page |
| Offset-based | Simple, supports page jumping | Unstable under inserts/deletes, slow at high offsets |

---

## Error Response Format

Standardize error responses across all endpoints:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "The request contains invalid fields",
    "details": [
      {
        "field": "email",
        "issue": "Invalid email format"
      }
    ],
    "request_id": "req_abc123"
  }
}
```

**Rules:**
- Always include a machine-readable error code
- Always include a human-readable message
- Include field-level details for validation errors
- Include a request ID for correlation with server logs
- NEVER expose stack traces, internal paths, or database details

---

## GraphQL Considerations

- Use queries for reads, mutations for writes
- Design schema around client needs, not database schema
- Implement query depth and complexity limits to prevent abuse
- Use DataLoader or equivalent for N+1 prevention
- Version via schema evolution (additive changes), not URL versioning

## gRPC Considerations

- Use Protocol Buffers for schema definition
- Design services around business capabilities, not CRUD
- Use streaming for large data transfers or real-time updates
- Implement proper deadline propagation across service calls
- Use status codes from the gRPC standard (OK, NOT_FOUND, INVALID_ARGUMENT, etc.)

---

## API Design Checklist

- [ ] Resources use plural nouns, not verbs
- [ ] HTTP methods match their intended semantics
- [ ] Status codes are specific and correct
- [ ] Error responses follow a consistent format
- [ ] Pagination is implemented for list endpoints
- [ ] Versioning strategy is documented and consistent
- [ ] Authentication and authorization are enforced
- [ ] Rate limiting is configured
- [ ] Request/response schemas are documented
- [ ] Breaking changes follow the deprecation lifecycle
