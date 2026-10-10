FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[web]' && useradd --create-home rmink
USER rmink
ENV RMINK_MAX_UPLOAD_MB=25 RMINK_MAX_PAGES=40 RMINK_CONCURRENCY=2
EXPOSE 8765
CMD ["rmink", "web", "--host", "0.0.0.0", "--port", "8765", "--no-open"]
