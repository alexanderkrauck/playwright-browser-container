FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99
ENV RESOLUTION=1920x1080

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Display server
    xvfb \
    x11vnc \
    # VNC and web access
    websockify \
    novnc \
    # Basic utilities
    wget \
    ca-certificates \
    # Node.js for Playwright MCP
    curl \
    # Process management
    supervisor \
    # Window management utilities
    xdotool \
    wmctrl \
    # Python for our MCP server
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright MCP globally
RUN npm install -g @playwright/mcp@latest

# Create necessary directories
RUN mkdir -p /data/chrome-profile \
    && mkdir -p /var/log/supervisor \
    && mkdir -p /usr/share/novnc

# Install Playwright browsers 
RUN npx playwright install --with-deps chrome

# Install Python MCP dependencies
COPY mcp-server/requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --ignore-installed typing_extensions -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt


# Copy configuration files
COPY config/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY config/browser-viewer.html /usr/share/novnc/browser-viewer.html
COPY scripts/entrypoint.sh /entrypoint.sh

# Make entrypoint executable
RUN chmod +x /entrypoint.sh

# Expose ports
EXPOSE 6080 8931

# Volume for persistent data
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]