# syntax=docker/dockerfile:1
#
# One image, one port: the API serves the built dashboard itself.
#
#   docker compose up        ->  http://localhost:8000
#
# Ships the trained network and its calibration, so a clone serves the real
# model. It does NOT contain the private Sehwa extract; nothing at runtime needs
# it — only the real-data acceptance test and the simulator calibration gate do.

FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
# node_modules is excluded by .dockerignore. Without that, this COPY overwrote
# the Linux install above with the host's (e.g. macOS) native binaries, and
# `npm run build` broke inside the image.
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS api
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY ml/ ml/
COPY backend/ backend/
# CPU-only torch first. Left to resolve from PyPI, Linux gets the CUDA build —
# several GB of GPU libraries for a model that runs on CPU in milliseconds.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1" \
 && pip install -e ".[ml,api]"
# The trained weights, the calibration artefact, and the measured results the
# Model page reads — the page was empty in this image before, because results
# were never copied in. After the install, so a retrain rebuilds one layer
# instead of reinstalling torch.
COPY experiments/artifacts/ experiments/artifacts/
COPY experiments/results/ experiments/results/
COPY --from=web /app/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
