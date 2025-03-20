# syntax=docker/dockerfile:1
FROM ubuntu@sha256:72297848456d5d37d1262630108ab308d3e9ec7ed1c3286a32fe09856619a782
COPY --from=ghcr.io/astral-sh/uv@sha256:cb641b1979723dc5ab87d61f079000009edc107d30ae7cbb6e7419fdac044e9f /uv /uvx /bin/

ADD . /app
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache \
    uv sync --frozen

CMD ["uv", "run", "bigmed", "serve"]
