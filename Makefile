.PHONY: up down clean populate setup

setup:
	@test -f .env || cp .env.example .env
	@echo "Archivo .env inicializado."

up: setup
	docker compose up -d

down:
	docker compose down

clean:
	docker compose down -v

populate:
	python3 -m venv .venv
	./.venv/bin/pip install -r requirements.txt
	./.venv/bin/python scripts/ETL.py