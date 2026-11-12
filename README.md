# FactWise Care

FactWise Care is a local-first patient operations prototype for coordinating daily temperature tasks, doctor visits, discharge reviews, and bed occupancy. It uses synthetic demo data and deterministic workflow rules. It is not a clinical decision system.

## Run locally

Requirements: Python 3.12+ and Node.js 20+.

1. Copy `.env.example` to `.env` and set `SECRET_KEY` to a long random value. Keep `COOKIE_SECURE=false` for local HTTP.
2. In a terminal, install backend dependencies and start the API:

   ```powershell
   cd backend
   uv sync --extra dev
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload
   ```

3. In a second terminal, install and start the web app:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

4. Open the Vite URL printed in the terminal. The API is proxied to `http://127.0.0.1:8000`.

The backend creates and seeds the local SQLite database on first startup. Runtime data lives in `data/database/factwise.db` and is excluded from Git. Demo access for all three roles is available from the login screen. Development-only credentials are `admin`, `nurse`, or `doctor` with password `Demo123!`.

## Implemented workflows

- Role-enforced administrator, nurse, and doctor access.
- Synthetic registry, 74 beds, admission, and occupancy.
- Daily nurse temperature recording with duplicate and future-time checks.
- Nurse corrections preserve the original reading, require a reason, and are audited.
- Doctor visits with an urgent-care reason when today's temperature is missing.
- Doctor-recorded deceased outcomes close admissions and release beds.
- Deterministic three completed facility-local day discharge eligibility.
- Doctor review followed by administrator discharge and bed release.
- Operational dashboard, outcome benchmark display, and CSV export.
- Incomplete intake requests are retained in a human-review queue. Required admission details are collected before the patient is admitted.
- Empty or unsupported knowledge requests are retained for human review. AI is not configured or used, and cannot determine eligibility or change patient records.

The 38.0 °C fever threshold and `Asia/Kolkata` timezone are configurable placeholders, not approved clinical policy.

## Production build

```powershell
cd frontend
npm run build
cd ..\backend
uv run uvicorn app.main:app
```

FastAPI serves the built SPA when `frontend/dist` exists. The app expects one origin in deployment.

## Deployment

Use the included `Dockerfile` on a container host that supports a persistent volume. Mount the volume at `/data`, set `DATABASE_URL=sqlite:////data/factwise.db`, set a unique `SECRET_KEY`, and set `COOKIE_SECURE=true`. Configure the host health check to `/healthz`. The frontend and API are served from the same origin. Do not deploy SQLite on an ephemeral serverless filesystem.

No hosting account or volume-backed target is configured in this workspace, so a public demo URL has not been published. See [docs/demo-guide.md](docs/demo-guide.md) for role guidance and deployment notes.

## Safety and scope

This prototype is for synthetic demonstration only. It is not suitable for real patient data or clinical use. AI/document features are intentionally not configured; unsupported questions are flagged for human review rather than answered with invented evidence. Real deployment requires facility review of clinical rules, security/privacy controls, and regulatory requirements.
