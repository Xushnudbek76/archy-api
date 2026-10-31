FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 archy \
    && useradd --uid 10001 --gid archy --no-create-home archy \
    && mkdir -p /var/lib/archy/media /var/lib/archy/mail \
    && chown -R archy:archy /var/lib/archy
COPY --chown=archy:archy app ./app
COPY --chown=archy:archy scripts ./scripts
COPY --chown=archy:archy migrations ./migrations
COPY --chown=archy:archy alembic.ini ./
USER archy
EXPOSE 3007
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3007/v1/health/ready', timeout=8)"
CMD ["python", "-m", "uvicorn", "app.main:build_app", "--factory", "--host", "0.0.0.0", "--port", "3007", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
