# Kyros MVP Dev Setup

## Prerequisites
- Docker + Docker Compose
- 8GB+ RAM available for containers

## 1. Clone and start
```bash
make up
```

## 2. Run migrations
In a new terminal:
```bash
make migrate
```

## 3. Open app
- Frontend: http://localhost:3000
- Backend: http://localhost:8000/docs

On first run with an empty database, open `/login` and create the first admin/brand from the UI bootstrap form.

## 4. Load your data
Use one of these paths:
- Upload CSVs through `/api/v1/ingestion/upload`
- Restore your PostgreSQL dump into `kyros_dev`

## Useful commands
- Run all jobs manually: `make jobs`
- Run backend tests: `make test`
