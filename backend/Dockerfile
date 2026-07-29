FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.9 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . ./
RUN useradd --create-home --uid 10001 app && chown -R app:app /app

USER app
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
