.PHONY: dev test lint migrate revision

dev:
	docker compose up --build

test:
	pytest

lint:
	ruff check app tests

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(message)"
