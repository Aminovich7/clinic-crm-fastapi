FROM python:3.14-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user. Nothing the app does needs root, and if the process
# is ever compromised this is the difference between an attacker inside one
# unprivileged account and an attacker owning the container.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /code
USER appuser

EXPOSE 8000

# No --reload here. The reloader watches the filesystem and holds a second
# process, neither of which belongs in a production image; it also silently
# restarts on any file change, which on a server is a way to lose in-flight
# requests rather than a feature. docker-compose.yml adds it back explicitly
# for local development, where the source tree is bind-mounted.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
