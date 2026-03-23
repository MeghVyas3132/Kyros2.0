.PHONY: up down migrate load-pilot test jobs logs shell-backend shell-db

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	docker compose exec backend alembic upgrade head

load-pilot:
	docker compose exec backend python scripts/seed_data.py

test:
	docker compose exec backend pytest -v --tb=short

jobs:
	docker compose exec backend celery -A app.tasks.celery_app worker --beat -l info

logs:
	docker compose logs -f backend celery_worker

shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec postgres psql -U kyros -d kyros_dev
