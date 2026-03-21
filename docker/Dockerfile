# Multi-stage Dockerfile for Youtu-Agent
# Supports both GitHub clone and local copy methods
# Usage:
#   GitHub mode: docker build --build-arg BUILD_MODE=github .
#   Local mode:  docker build --build-arg BUILD_MODE=local .

# 1. Use an official Python base image
FROM python:3.12

# 2. Install git (needed for GitHub mode)
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# 3. Set the working directory
WORKDIR /youtu-agent

# 4. Define build argument for build mode
ARG BUILD_MODE=local

# 5. Copy or clone source code based on build mode
RUN if [ "$BUILD_MODE" = "github" ]; then \
        echo "Building from GitHub repository..."; \
        git clone --branch v0.1.1 --depth 1 https://github.com/TencentCloudADP/youtu-agent.git .; \
    else \
        echo "Building from local files..."; \
    fi

# Copy local files only in local mode
COPY . /tmp/local-src/
RUN if [ "$BUILD_MODE" = "local" ]; then \
        echo "Copying local source files..."; \
        cp -r /tmp/local-src/* . 2>/dev/null || true; \
        cp -r /tmp/local-src/.[^.]* . 2>/dev/null || true; \
    else \
        echo "Using GitHub source with local UI patches..."; \
        cp -f /tmp/local-src/utu/ui/webui_chatbot.py ./utu/ui/webui_chatbot.py 2>/dev/null || true; \
        cp -f /tmp/local-src/examples/svg_generator/main_web.py ./examples/svg_generator/main_web.py 2>/dev/null || true; \
    fi && \
    rm -rf /tmp/local-src

# 6. Install the 'uv' build tool globally
RUN pip install uv

# 7. Synchronize the Python environment and dependencies
RUN uv sync

# 8. Add the virtual environment's bin directory to PATH
ENV PATH="/youtu-agent/.venv/bin:$PATH"

# 9. Install the frontend UI package
RUN uv pip install https://github.com/TencentCloudADP/youtu-agent/releases/download/frontend/v0.2.0/utu_agent_ui-0.2.0-py3-none-any.whl

# 10. Expose the web UI port
EXPOSE 8848

# 11. Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8848/ || exit 1

# 12. Set the default command based on build mode
# GitHub mode: Use WebUIChatbot (examples/svg_generator/main_web.py)
# Local mode: Use WebUIAgents with agent switching support (demo/main_web_agents.py)
RUN if [ "$BUILD_MODE" = "github" ]; then \
        echo '#!/bin/bash' > /start.sh && \
        echo 'python examples/svg_generator/main_web.py' >> /start.sh; \
    else \
        echo '#!/bin/bash' > /start.sh && \
        echo 'python demo/main_web_agents.py --config examples/svg_generator.yaml' >> /start.sh; \
    fi && \
    chmod +x /start.sh

CMD ["/start.sh"]
