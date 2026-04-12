.PHONY: dev dev-infra dev-backend test migrate lint

dev-infra:
	cd docker && docker compose up -d

dev-backend:
	uvicorn app.main:app --reload --port 8000

dev: dev-infra dev-backend

dev-worker:
	celery -A app.core.celery worker --loglevel=info

test:
	python -m pytest -v --tb=short

migrate:
	alembic upgrade head

migrate-gen:
	alembic revision --autogenerate -m "$(msg)"

lint:
	ruff check app/ tests/
	ruff format --check app/ tests/

format:
	ruff format app/ tests/
