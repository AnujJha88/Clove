# Clove Kernel Docker Image
# Usage: docker run -v /tmp:/tmp clove

FROM ubuntu:22.04 AS builder

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY CMakeLists.txt ./
COPY src/ src/

RUN mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc)

# Runtime
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    libssl3 \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/build/clove_kernel /usr/local/bin/clove_kernel
COPY agents/python_sdk/ /tmp/clove_sdk/
RUN pip3 install --no-cache-dir /tmp/clove_sdk/ && rm -rf /tmp/clove_sdk/

ENV CLOVE_SOCKET=/tmp/clove.sock

# Without --privileged, sandboxing won't work, so default to --no-sandbox
# For full sandboxing: docker run --privileged clove clove_kernel
CMD ["clove_kernel", "--no-sandbox"]
