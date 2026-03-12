.PHONY: up down logs build test

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

# Backend only for now - there's no frontend test script yet, and no
# migrate target until Alembic/Postgres land in Phase 2.
test:
	cd taskflow && pytest
