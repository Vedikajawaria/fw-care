FROM node:22-alpine AS frontend
WORKDIR /workspace/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /workspace/backend
COPY backend/ ./
RUN pip install --no-cache-dir .
COPY --from=frontend /workspace/frontend/dist /workspace/frontend/dist
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/factwise.db
ENV COOKIE_SECURE=true
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
