.DEFAULT_GOAL := run

.PHONY: run rund services stop clean gen load setup teardown

# Runs all services in detached mode.
run:
	ln -sfn .env.local .env
	docker compose --env-file .env.local up -d --build --wait --wait-timeout 120

# Runs all services without detached mode (for debugging).
rund:
	ln -sfn .env.local .env
	docker compose --env-file .env.local up --build

# Shows all service statuses.
services:
	docker compose --env-file .env.local ps

# Stops all running services.
stop:
	docker compose --env-file .env.local down

# Cleans up all resources including volumes.
clean:
	python3 -m app.cli teardown
	docker compose --env-file .env.local down

gen:
	python3 -m app.cli gen

load:
	python3 -m app.cli load

setup:
	python3 -m app.cli setup

teardown:
	python3 -m app.cli teardown
