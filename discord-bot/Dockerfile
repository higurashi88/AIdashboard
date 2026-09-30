FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv \
    && useradd --create-home --shell /usr/sbin/nologin bot

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY bot ./bot
# 通知のカーソル（state.json）の置き場所。compose で名前付きボリュームを重ねる。
RUN mkdir -p /data && chown bot:bot /data

USER bot

CMD ["python", "-m", "bot"]
