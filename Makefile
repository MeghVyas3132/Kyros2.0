up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python -m scripts.seed_data

init: migrate seed
	@echo "✅ Database migrated and seeded. Login at http://localhost:3000 with admin@kyros.ai / kyros123"

start: up
	@echo "Waiting for services to start..."
	sleep 8
	docker compose exec backend alembic upgrade head
	docker compose exec backend python -m scripts.seed_data
	@echo "✅ Ready! Open http://localhost:3000"

load-pilot:
	@echo "Load pilot data using DB restore or ingestion APIs before testing."

test:
	docker compose exec backend pytest

jobs:
	docker compose exec backend python -m app.tasks.run_jobs
