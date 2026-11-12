# Architecture

FactWise Care is a same-origin modular monolith:

- React and TypeScript provide the role-specific operations screens.
- FastAPI owns authentication, validation, authorization, workflow rules, and the JSON API.
- SQLAlchemy persists records in SQLite with foreign keys, WAL, and partial unique indexes.
- Alembic tracks the initial database schema.
- Local runtime data is kept outside the frontend and excluded from Git.

Patient admission and discharge are service-side operations; the frontend never writes directly to the database. Session cookies are signed, `HttpOnly`, and `SameSite=Lax`. State-changing API calls require the session CSRF token.

## Review-first request handling

Incomplete intake is persisted as `needs_review` and can be completed by an administrator before admission. Knowledge requests are persisted for human review. No generative model is invoked in this build. The eligibility service is deterministic and independent of AI.

## Deliberate limitations

Document parsing, hybrid retrieval, Gemini generation, user management, and production-grade authentication are not enabled. The demo accounts and local secret defaults are for development only.
