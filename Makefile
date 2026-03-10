up:
	docker compose up --build

migrate:
	docker compose exec backend alembic upgrade head

load-pilot:
	@echo "Load pilot data using DB restore or ingestion APIs before testing."

test:
	docker compose exec backend pytest

jobs:
	docker compose exec backend python -m app.tasks.run_jobs
