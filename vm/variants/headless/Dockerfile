# Inspekt Headless Docker Image
#
# A minimal Docker image for running Inspekt in headless mode.
# Includes Chrome and common fonts for consistent rendering.
#
# Build:
#   docker build -t inspekt-headless -f vm/variants/headless/Dockerfile .
#
# Usage:
#   docker run --rm inspekt-headless inspekt screenshot node \
#     --headless --url "https://example.com" --selector "h1" -o /output/shot.png
#
#   docker run --rm inspekt-headless inspekt a11y axe \
#     --headless --url "https://example.com" --json

FROM python:3.11-slim-bookworm

LABEL maintainer="Inspekt Team"
LABEL description="Inspekt CLI with headless Chrome for CI/CD"
LABEL version="1.0"

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Chrome dependencies and common fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chrome dependencies
    wget \
    gnupg \
    ca-certificates \
    # Font packages for consistent rendering
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-noto-cjk \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    # Additional libs Chrome needs
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome path for Inspekt
ENV INSPEKT_CHROME_PATH=/usr/bin/google-chrome-stable

# Create non-root user for security
RUN groupadd -r inspekt && useradd -r -g inspekt -d /home/inspekt -m inspekt

# Create output directory
RUN mkdir -p /output && chown inspekt:inspekt /output

# Install Inspekt
# Option 1: Install from PyPI (uncomment when published)
# RUN pip install --no-cache-dir inspekt

# Option 2: Install from local source (for development)
WORKDIR /app
COPY pyproject.toml ./
COPY inspekt/ ./inspekt/
RUN pip install --no-cache-dir -e .

# Switch to non-root user
USER inspekt

# Set working directory for output
WORKDIR /output

# Default command shows help
CMD ["inspekt", "--help"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD inspekt --version || exit 1
