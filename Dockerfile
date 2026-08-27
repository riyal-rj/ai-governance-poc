FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system --gid 10001 finassist \
    && useradd --system --uid 10001 --gid finassist --home-dir /nonexistent finassist

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --requirement requirements.txt

COPY --chown=finassist:finassist src ./src

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "src.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
