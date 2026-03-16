# Next.js Example

A TypeScript Next.js project with ClaudeKit multi-agent workflows pre-configured.

## Technology Stack

- **Language**: TypeScript 5.x
- **Framework**: Next.js 15 (App Router)
- **Build System**: npm
- **Test Framework**: Vitest + Testing Library

## Development Commands

```bash
# Install
npm install

# Dev server
npm run dev

# Build
npm run build

# Test
npm test

# Lint
npm run lint

# Coverage
npm run test -- --coverage

# Type check
npx tsc --noEmit
```

## Project Structure

```
src/
├── app/              # Next.js App Router pages
│   ├── layout.tsx
│   ├── page.tsx
│   └── api/          # API routes
├── components/       # React components
│   ├── ui/           # Generic UI components
│   └── features/     # Feature-specific components
├── lib/              # Shared utilities
│   ├── api.ts        # API client
│   └── utils.ts      # Helper functions
├── domain/           # Business logic
│   ├── models.ts     # Type definitions
│   └── services.ts   # Business logic
└── data/             # Data access
    └── repositories.ts
tests/
├── components/       # Component tests
├── domain/           # Business logic tests
└── setup.ts          # Test configuration
```

## Coverage Targets

- New code: 80%
- Overall: 70%
- Critical paths: 90%

## Architecture

```
Components (UI) → Domain (business logic) → Data (API/DB)
```

**Rules**:
- Components never import from Data layer directly
- Domain layer has no React dependencies
- Server components for data fetching, client components for interactivity

## ClaudeKit Commands

| Command | Purpose |
|---------|---------|
| `/plan <task>` | Create implementation plan with ops.json |
| `/review` | Validate plan (90% threshold) |
| `/implement` | Execute approved plan |
| `/verify` | Run quality checks (80% threshold) |
| `/debug <issue>` | Diagnose bugs (read-only) |

## Operations Config

Scripts: `.claude/operations/scripts/`
