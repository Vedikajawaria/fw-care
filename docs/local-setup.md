# Local setup

## Requirements

- Python 3.12 or later
- `uv`
- Node.js 20 or later and npm

## Start the application

From the project root, copy `.env.example` to `.env` and replace `SECRET_KEY`.

Backend, from `backend`:

```powershell
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Frontend, from `frontend`:

```powershell
npm install
npm run dev
```

The frontend development server proxies API requests to port 8000. FastAPI initializes and seeds the database on first start. The `data` directory is located at the project root.

## Demo accounts

Development-only accounts:

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `Demo123!` |
| Nurse | `nurse` | `Demo123!` |
| Doctor | `doctor` | `Demo123!` |

Seeded patient data is synthetic. Do not use these credentials or the prototype with real patient information.

## Persistence and backup

The SQLite database is `data/database/factwise.db`. Stop the backend before copying this file for a consistent local backup. Restore by replacing the file while the backend is stopped. Uploaded documents are not implemented.
