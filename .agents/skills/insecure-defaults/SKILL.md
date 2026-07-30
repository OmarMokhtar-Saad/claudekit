---
name: insecure-defaults
description: Use when checking for insecure defaults — detects hardcoded credentials, fail-open patterns, and dangerous default values in configuration files and code.
user-invocable: false
allowed-tools: Read, Grep, Glob
---

# Insecure Defaults

## Core Principle

**Defaults must be secure. Convenience must never override safety.** If a developer deploys your code without changing a single configuration value, it must be secure by default. Every opt-out from security should be explicit and loud.

---

## Default Credential Patterns

### Hardcoded Credential Indicators

Search for these patterns across the entire codebase:

| Pattern | Example | Risk |
|---|---|---|
| Literal password assignment | `password = "admin123"` | Critical - credential in source |
| Default API key | `api_key = "test-key-12345"` | Critical - key in source control |
| Connection string with creds | `postgres://user:pass@host/db` | Critical - database access |
| Bearer token literal | `Authorization: Bearer sk-...` | Critical - token in source |
| Base64-encoded secrets | `dXNlcjpwYXNzd29yZA==` | High - obfuscated, not encrypted |
| Comment containing password | `// default password: changeme` | High - leaked in source |

### Search Patterns

Look for variable names and assignments matching:

```
password, passwd, pwd, secret, token, api_key, apikey, api-key,
access_key, private_key, auth_token, client_secret, conn_string,
connection_string, database_url, smtp_password, jwt_secret
```

Combined with value patterns:

```
= "...", = '...', : "...", : '...',
=> "...", := "..."
```

### False Positive Filtering

Exclude these from findings:
- Environment variable reads (`os.getenv`, `process.env`, `env::var`)
- Vault or secrets manager references
- Test fixtures in test directories with clearly fake values
- Schema definitions and type declarations
- Documentation examples that explicitly say "replace this"

---

## Fail-Open vs Fail-Closed Detection

### Fail-Open Anti-Patterns

| Pattern | What It Looks Like | Secure Alternative |
|---|---|---|
| Empty catch grants access | `catch(e) { return true; }` | `catch(e) { return false; }` |
| Default case permits | `default: allow()` in switch | `default: deny()` |
| Missing auth falls through | No `else` clause after auth check | Explicit deny in `else` |
| Error skips validation | Validation error caught, request proceeds | Reject request on validation failure |
| Timeout grants access | Auth service timeout results in access granted | Timeout results in access denied |
| Feature flag default | `featureFlag.get("mfa", false)` | `featureFlag.get("mfa", true)` for security features |

### Detection Checklist

- [ ] Every authentication check has an explicit denial path
- [ ] Every authorization check has an explicit denial path
- [ ] Exception handlers in security code default to deny
- [ ] Timeout conditions in security checks default to deny
- [ ] Switch statements on security decisions have a `default: deny` case
- [ ] Missing configuration values result in the most restrictive behavior

---

## Insecure TLS/SSL Defaults

| Setting | Insecure Default | Secure Default |
|---|---|---|
| TLS version | TLS 1.0, TLS 1.1, SSLv3 | TLS 1.2 minimum, prefer TLS 1.3 |
| Certificate verification | `verify: false`, `rejectUnauthorized: false` | Always verify certificates |
| Cipher suites | Include RC4, DES, 3DES, NULL | Only AEAD ciphers (AES-GCM, ChaCha20) |
| HSTS | Not set | `max-age=31536000; includeSubDomains` |
| Certificate pinning | Disabled | Pin known certificate hashes |
| OCSP stapling | Disabled | Enabled |

### Patterns to Search For

```
rejectUnauthorized: false
verify_ssl=False
InsecureSkipVerify: true
CURLOPT_SSL_VERIFYPEER, 0
ssl_verify: false
NODE_TLS_REJECT_UNAUTHORIZED=0
verify=False  # (in requests library calls)
```

---

## Permissive CORS Defaults

| Setting | Insecure | Secure |
|---|---|---|
| Origin | `*` or `Access-Control-Allow-Origin: *` | Explicit allowlist of trusted origins |
| Credentials | `Access-Control-Allow-Credentials: true` with `Origin: *` | Credentials only with specific origins |
| Methods | `Access-Control-Allow-Methods: *` | Only required methods (GET, POST) |
| Headers | `Access-Control-Allow-Headers: *` | Only required headers |
| Max age | Very long or missing | `Access-Control-Max-Age: 600` (10 min) |

### CORS Configuration Audit

- [ ] No wildcard origin (`*`) in production configurations
- [ ] Credentials flag is not combined with wildcard origin
- [ ] Allowed methods are restricted to what the API actually uses
- [ ] Preflight cache duration is reasonable (not indefinite)
- [ ] CORS configuration differs between development and production

---

## Debug Mode in Production

### Debug Indicators

| Framework | Debug Setting | Risk |
|---|---|---|
| Django | `DEBUG = True` | Stack traces, SQL queries exposed |
| Flask | `app.run(debug=True)` | Interactive debugger with code execution |
| Express | `NODE_ENV=development` | Verbose error responses |
| Rails | `config.consider_all_requests_local = true` | Detailed error pages |
| Spring | `spring.profiles.active=dev` | Development endpoints exposed |
| ASP.NET | `ASPNETCORE_ENVIRONMENT=Development` | Developer exception page |

### What Debug Mode Exposes

- Full stack traces with file paths and line numbers
- Database query details and connection information
- Environment variables and configuration values
- Internal service URLs and network topology
- Source code snippets around the error location
- Interactive debuggers (Flask/Werkzeug) allowing remote code execution

### Detection Checklist

- [ ] No debug flags set to `true` in production configuration
- [ ] Error responses in production return generic messages
- [ ] Development-only endpoints are not accessible in production
- [ ] Verbose logging is disabled in production configs
- [ ] Source maps are not deployed to production (for frontend apps)

---

## Default Port Exposure

| Service | Default Port | Risk If Exposed |
|---|---|---|
| Database (PostgreSQL) | 5432 | Direct database access |
| Database (MySQL) | 3306 | Direct database access |
| Database (MongoDB) | 27017 | Unauthenticated data access |
| Redis | 6379 | Unauthenticated cache/data access |
| Elasticsearch | 9200, 9300 | Data exposure, cluster manipulation |
| Docker daemon | 2375 (unencrypted) | Full host compromise |
| Kubernetes API | 6443, 8443 | Cluster control |
| Debug ports (Node) | 9229 | Remote code execution |
| Admin interfaces | 8080, 8443 | Administrative access |

### Network Exposure Checklist

- [ ] Database ports are not bound to `0.0.0.0`
- [ ] Cache services (Redis, Memcached) require authentication
- [ ] Management/admin ports are not exposed externally
- [ ] Debug/profiling ports are disabled in production
- [ ] Docker socket is not exposed without TLS

---

## Weak Algorithm Defaults

| Category | Weak | Strong |
|---|---|---|
| Hashing (passwords) | MD5, SHA1, SHA256 (unsalted) | bcrypt, argon2id, scrypt |
| Hashing (integrity) | MD5, SHA1 | SHA-256, SHA-3, BLAKE3 |
| Symmetric encryption | DES, 3DES, RC4, Blowfish | AES-256-GCM, ChaCha20-Poly1305 |
| Asymmetric encryption | RSA-1024 | RSA-2048+, Ed25519, ECDSA P-256+ |
| Key derivation | Raw SHA, single-pass | PBKDF2 (100k+ iterations), argon2 |
| Random generation | `Math.random()`, `rand()` | `crypto.randomBytes()`, `/dev/urandom` |
| JWT signing | `none`, `HS256` with weak secret | `RS256`, `ES256`, `EdDSA` |

### Algorithm Audit Checklist

- [ ] No use of MD5 or SHA1 for security purposes
- [ ] Password hashing uses a memory-hard algorithm (argon2id preferred)
- [ ] Encryption uses authenticated encryption (AEAD)
- [ ] RSA keys are at least 2048 bits
- [ ] JWT tokens are not using the `none` algorithm
- [ ] Random values for security purposes use cryptographic random generators

---

## Summary: Insecure Default Severity Ratings

| Category | Severity | Common Impact |
|---|---|---|
| Hardcoded credentials | Critical | Full system compromise |
| Fail-open auth patterns | Critical | Authentication bypass |
| Disabled TLS verification | High | Man-in-the-middle attacks |
| Debug mode in production | High | Information disclosure, RCE |
| Wildcard CORS | Medium | Cross-origin data theft |
| Weak cryptographic algorithms | Medium-High | Data exposure, forgery |
| Exposed default ports | Medium | Unauthorized service access |
