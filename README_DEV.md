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

## 3. Load pilot data
```bash
make load-pilot
```

Use one of these real-data paths:
- Restore your PostgreSQL dump into `kyros_dev`
- Upload pilot CSVs through `/api/v1/ingestion/upload`

## 4. Open app
- Frontend: http://localhost:3000
- Backend: http://localhost:8000/docs

## Authentication
Use real pilot user credentials present in your loaded dataset.

## Useful commands
- Run all jobs manually: `make jobs`
- Run backend tests: `make test`
