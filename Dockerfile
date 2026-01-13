# ios-media-toolkit Docker image
# Works with both CPU (x265) and GPU (nvenc) - use --gpus all for NVIDIA
#
# Build: docker build -t imt .
# Run CPU: docker run -v /media:/media imt process /media/album -o /media/out --profile balanced
# Run GPU: docker run --gpus all -v /media:/media imt process /media/album -o /media/out --profile nvenc_4k
#
# NVENC requirements:
# - NVIDIA driver 550+ (for FFmpeg 7.x / nvenc SDK 12.2)
# - nvidia-container-toolkit installed on host
# - Run with: --gpus all

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

LABEL maintainer="ios-media-toolkit"
LABEL description="iPhone media processing with Dolby Vision preservation"

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Enable NVIDIA video encoding capabilities (required for NVENC)
# See: https://forums.developer.nvidia.com/t/cannot-load-libnvidia-encode-so-1/117652
ENV NVIDIA_DRIVER_CAPABILITIES=compute,video,utility

# Versions - update these as needed
ENV DOVI_TOOL_VERSION=2.3.1

# Install base dependencies (no Python - uv will manage it)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    xz-utils \
    libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

# Install ffmpeg (BtbN build with nvenc + x265 support)
# Using master build for latest codecs; versioned builds also available (e.g., ffmpeg-n7.1-latest-linux64-gpl-7.1.tar.xz)
RUN curl -fsSL "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz" \
    -o /tmp/ffmpeg.tar.xz \
    && tar -xf /tmp/ffmpeg.tar.xz -C /tmp \
    && mv /tmp/ffmpeg-master-latest-linux64-gpl/bin/* /usr/local/bin/ \
    && rm -rf /tmp/ffmpeg*

# Install dovi_tool
RUN curl -fsSL "https://github.com/quietvoid/dovi_tool/releases/download/${DOVI_TOOL_VERSION}/dovi_tool-${DOVI_TOOL_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
    -o /tmp/dovi_tool.tar.gz \
    && tar -xzf /tmp/dovi_tool.tar.gz -C /usr/local/bin/ \
    && chmod +x /usr/local/bin/dovi_tool \
    && rm /tmp/dovi_tool.tar.gz

# Compile mp4muxer from Dolby Labs dlb_mp4base
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    g++ \
    && git clone --depth 1 https://github.com/DolbyLaboratories/dlb_mp4base.git /tmp/dlb_mp4base \
    && make -C /tmp/dlb_mp4base/make/mp4muxer/linux_amd64 \
    && mv /tmp/dlb_mp4base/make/mp4muxer/linux_amd64/mp4muxer_release /usr/local/bin/mp4muxer \
    && chmod +x /usr/local/bin/mp4muxer \
    && rm -rf /tmp/dlb_mp4base \
    && apt-get purge -y git make g++ && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Install uv and Python 3.14
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
RUN uv python install 3.14

# Install ios-media-toolkit
# Option 1: From PyPI (when published)
# RUN uv pip install ios-media-toolkit

# Option 2: From local source (for testing)
COPY . /app
WORKDIR /app
RUN uv sync --no-dev

# Verify installations
RUN ffmpeg -version | head -1 \
    && dovi_tool --version \
    && mp4muxer --version 2>&1 | head -1 \
    && exiftool -ver \
    && uv run imt --version

# Default working directory for media
WORKDIR /media

# Run imt from the app directory where venv is
ENTRYPOINT ["uv", "run", "--project", "/app", "imt"]
CMD ["--help"]
