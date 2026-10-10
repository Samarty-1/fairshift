FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]"
RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["fairshift", "serve", "--host", "0.0.0.0", "--port", "8000"]
