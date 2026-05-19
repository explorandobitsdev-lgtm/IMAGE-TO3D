.PHONY: up down logs api worker web db rebuild

up:
	docker compose --env-file .env up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

api:
	docker compose logs -f api

worker:
	docker compose logs -f worker

web:
	docker compose logs -f web

db:
	docker compose exec postgres psql -U app -d platform

rebuild:
	docker compose build --no-cache
	docker compose up -d
