# syntax=docker/dockerfile:1
FROM ubuntu:latest
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ADD . /app
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache \
    uv sync --frozen

CMD ["uv", "run", "bigmed", "serve"]
