FROM python:3.14-slim-trixie

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ccache \
    curl \
    fish \
    git \
    patchelf \
    sudo \
    wget \
    && rm -rf /var/lib/apt/lists/*

ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid "$USER_GID" "$USERNAME" \
    && useradd --uid "$USER_UID" --gid "$USER_GID" --create-home --shell /usr/bin/fish "$USERNAME" \
    && printf '%s ALL=(root) NOPASSWD:ALL\n' "$USERNAME" > "/etc/sudoers.d/$USERNAME" \
    && chmod 0440 "/etc/sudoers.d/$USERNAME"

RUN pip install --no-cache-dir uv

USER $USERNAME
WORKDIR /workspace
