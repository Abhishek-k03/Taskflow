.PHONY: up down logs build test migrate scale

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

# Backend only for now - there's no frontend test script yet.
test:
	cd taskflow && pytest

# Run once against a fresh `make up` - persistence works with no schema
# applied too (best-effort dual-write), it just has nothing to write into.
migrate:
	docker compose run --rm api alembic upgrade head

# Workers are the scaling unit - api and scheduler stay at one replica
# (the scheduler must, until the leader lock lands).
scale:
	docker compose up -d --scale worker=3
