FROM ubuntu:latest
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ADD . /app
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache \
    uv sync --frozen

RUN uv run bigmed prepare-dataset data/medicine_dataset.csv data/kek.csv
CMD ["uv", "run", "bigmed", "dataset-to-cassandra", "data/kek.csv"]
