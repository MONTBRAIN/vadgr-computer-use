FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for AT-SPI2, X11 tooling, vision fallback (headless OpenCV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    xdotool \
    scrot \
    xvfb \
    python3-gi \
    gir1.2-atspi-2.0 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY computer_use/ ./computer_use/

RUN pip install .

EXPOSE 8000

ENTRYPOINT ["vadgr-cua"]
CMD ["--transport", "sse", "--port", "8000"]
