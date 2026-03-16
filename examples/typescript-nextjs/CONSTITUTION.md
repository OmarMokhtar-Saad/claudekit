# Next.js Example Constitution

**Version**: 1.0
**Status**: ACTIVE

## Article I: Architecture

Components → Domain → Data. No direct UI→Data imports. Server components by default.

## Article II: Code Quality

- Strict TypeScript (no `any`)
- ESLint + Prettier enforced
- Named exports preferred

## Article III: Testing

- 80% coverage on new code
- Test command: `npm test`
- Use Testing Library for component tests
- Use MSW for API mocking

## Article IV: Security

- No hardcoded secrets (use env vars)
- Input validation with Zod
- XSS prevention (React handles most)
- CSRF protection on API routes

## Article V: Operations

- All plans require ops.json
- Max 5 operations per config
- Protected files: package.json, tsconfig.json, *.md

## Article VI: Review

- Plan approval: 90/100
- Quality verification: 80/100
- Max 3 iterations before escalation
