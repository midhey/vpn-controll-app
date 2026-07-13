SHELL := /bin/bash
REAL_SETUP_ENV := AGENT_MODE=http SETUP_RUNNER=deploy_script SETUP_AGENT_LISTEN=0.0.0.0:8090

.DEFAULT_GOAL := help

.PHONY: help install start start-backend start-frontend

help:
	@printf '%s\n' \
		'make start           Запустить backend и frontend' \
		'make start-backend   Запустить только backend' \
		'make start-frontend  Запустить только frontend' \
		'make install         Установить зависимости'

install:
	cd backend && uv sync --group dev
	cd frontend && npm install

start-backend:
	cd backend && env $(REAL_SETUP_ENV) uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

start-frontend:
	cd frontend && npm run dev

start:
	@command -v uv >/dev/null || { echo 'Ошибка: команда uv не найдена.' >&2; exit 1; }
	@command -v npm >/dev/null || { echo 'Ошибка: команда npm не найдена.' >&2; exit 1; }
	@set -e; \
	backend_pid=''; \
	frontend_pid=''; \
	cleanup() { \
		status=$$?; \
		trap - EXIT INT TERM; \
		for pid in "$$backend_pid" "$$frontend_pid"; do \
			if [[ -n "$$pid" ]] && kill -0 "$$pid" 2>/dev/null; then \
				kill "$$pid" 2>/dev/null || true; \
			fi; \
		done; \
		for pid in "$$backend_pid" "$$frontend_pid"; do \
			[[ -z "$$pid" ]] || wait "$$pid" 2>/dev/null || true; \
		done; \
		exit "$$status"; \
	}; \
	trap cleanup EXIT INT TERM; \
	printf '%s\n' \
		'Backend: http://localhost:8000/api/docs' \
		'Frontend: http://localhost:5173' \
		'Для остановки нажмите Ctrl+C.'; \
	( cd backend && exec env $(REAL_SETUP_ENV) uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 ) & \
	backend_pid=$$!; \
	( cd frontend && exec npm run dev ) & \
	frontend_pid=$$!; \
	while kill -0 "$$backend_pid" 2>/dev/null && kill -0 "$$frontend_pid" 2>/dev/null; do \
		sleep 1; \
	done; \
	status=0; \
	if ! kill -0 "$$backend_pid" 2>/dev/null; then \
		wait "$$backend_pid" || status=$$?; \
	else \
		wait "$$frontend_pid" || status=$$?; \
	fi; \
	exit "$$status"
