FROM ghcr.io/astral-sh/uv:python3.12-alpine

RUN apk add --no-cache openjdk21-jre-headless gcompat tmux

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV XDG_DATA_HOME=/data

COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-install-project --no-dev

COPY . /app
RUN uv sync --frozen --no-dev

RUN mkdir -p /data && chmod 777 /data

ENV PATH="/app/.venv/bin:$PATH"
ENV LODESTONE_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

CMD ["tmux", "new-session", "-s", "main", "python -m lodestone --tui"]
