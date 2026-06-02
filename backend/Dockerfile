FROM python:3.12-slim-bullseye AS builder

RUN pip install --upgrade -i https://mirrors.aliyun.com/pypi/simple poetry==2.1.1

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app
COPY pyproject.toml poetry.lock /app/
RUN --mount=type=cache,target=$POETRY_CACHE_DIR \
    poetry install --no-interaction --no-ansi --no-root --without=dev

FROM python:3.12-slim-bullseye AS runtime

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src:/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY src /app/src
COPY prompts /app/prompts
COPY scripts /app/scripts
COPY migrations /app/migrations
COPY config*.yaml alembic.ini /app/

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
