# PrintLoop: API + UI (web/dist served by FastAPI) + headless OrcaSlicer and BambuStudio, one container.
# Build: docker build -t printloop .   Run: see deploy/compose.yaml.

ARG ORCA_VERSION=2.4.2
ARG BAMBU_TAG=v02.08.02.61
ARG BAMBU_ASSET=BambuStudio_ubuntu24.04-v02.08.02.61-20260820225108.AppImage

FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# The AppImages are extracted (no FUSE inside containers) and run through their AppRun.
FROM ubuntu:24.04 AS slicers
ARG ORCA_VERSION BAMBU_TAG BAMBU_ASSET
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/s
RUN curl -fsSL -o orca.AppImage \
      "https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v${ORCA_VERSION}/OrcaSlicer_Linux_AppImage_Ubuntu2404_V${ORCA_VERSION}.AppImage" \
 && chmod +x orca.AppImage && ./orca.AppImage --appimage-extract >/dev/null && mv squashfs-root /opt/OrcaSlicer \
 && curl -fsSL -o bambu.AppImage "https://github.com/bambulab/BambuStudio/releases/download/${BAMBU_TAG}/${BAMBU_ASSET}" \
 && chmod +x bambu.AppImage && ./bambu.AppImage --appimage-extract >/dev/null && mv squashfs-root /opt/BambuStudio \
 && rm -f *.AppImage

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8
# Runtime libraries the slicers link against even when run headless with --slice.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl python3 \
      libgtk-3-0t64 libwebkit2gtk-4.1-0 libgl1 libegl1 libglu1-mesa libosmesa6 libgstreamer1.0-0 \
      libgstreamer-plugins-base1.0-0 libsecret-1-0 libsoup-3.0-0 libfontconfig1 libdbus-1-3 libsm6 libice6 libmspack0t64 locales \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
COPY --from=slicers /opt/OrcaSlicer /opt/OrcaSlicer
COPY --from=slicers /opt/BambuStudio /opt/BambuStudio
RUN ln -s /opt/OrcaSlicer/AppRun /usr/local/bin/orca-slicer && ln -s /opt/BambuStudio/AppRun /usr/local/bin/bambu-studio

RUN useradd --create-home --uid 10001 printloop && mkdir -p /data/runs /data/replay && chown -R printloop /data
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project --no-dev
COPY src/ src/
COPY examples/ examples/
COPY --from=web /web/dist web/dist
RUN uv sync --locked --no-dev && chown -R printloop /app

USER printloop
ENV PATH=/app/.venv/bin:$PATH PRINTLOOP_RUNS_DIR=/data/runs MODE1_REPLAY_DIR=/data/replay
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://localhost:8788/api/health >/dev/null || exit 1
CMD ["uvicorn", "printloop.api:app", "--host", "0.0.0.0", "--port", "8788", "--proxy-headers", "--forwarded-allow-ips", "*"]
