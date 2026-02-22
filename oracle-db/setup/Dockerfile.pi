ARG NODE_VERSION=22
FROM node:${NODE_VERSION}-slim

ARG PI_VERSION=latest

# System tools pi commonly needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Install pi
RUN npm install -g @mariozechner/pi-coding-agent@${PI_VERSION}

WORKDIR /workspace

ENTRYPOINT ["pi"]
