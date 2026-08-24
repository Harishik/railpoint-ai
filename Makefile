.PHONY: install data calibrate train test lint api web up clean

install:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -e ".[dev,ml]"
	npm --prefix frontend install

calibrate:  ## Validate the simulator against the real Sehwa traces
	.venv/bin/railpoint calibrate

data:       ## Generate the fleet and stratified datasets
	.venv/bin/railpoint build-data

train:      ## Train, calibrate, evaluate, export
	.venv/bin/railpoint train

test:
	.venv/bin/python -m pytest tests/ -q

lint:
	.venv/bin/ruff check ml backend tests scripts
	cd frontend && npx tsc --noEmit

api:
	.venv/bin/uvicorn backend.app.main:app --port 8000 --reload

web:
	npm --prefix frontend run dev

up:
	docker compose up --build

clean:
	rm -rf data/synthetic/* data/processed/* experiments/artifacts/*
