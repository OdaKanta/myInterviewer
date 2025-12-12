# Use the latest Ubuntu LTS as base
FROM ubuntu:22.04

# 非対話モードに設定
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Tokyo \
    DEBIAN_FRONTEND=noninteractive \
    PYTHON_VERSION=3.11.5

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
    # タイムゾーン情報を設定
 && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
 && echo $TZ > /etc/timezone \
 && dpkg-reconfigure -f noninteractive tzdata \
 && rm -rf /var/lib/apt/lists/*

# Install system packages required for building Python and for audio/voice processing
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      wget curl build-essential make \
      libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
      libncurses5-dev libncursesw5-dev libffi-dev liblzma-dev tk-dev \
      libxml2-dev libxmlsec1-dev uuid-dev \
      portaudio19-dev libportaudio2 libasound2-dev ffmpeg \
      ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install Python 3.11.5 from source
RUN wget -q https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz \
 && tar -xf Python-${PYTHON_VERSION}.tar.xz \
 && cd Python-${PYTHON_VERSION} \
 && ./configure --enable-optimizations --with-ensurepip=install \
 && make -j"$(nproc)" \
 && make install \
 && cd .. \
 && rm -rf Python-${PYTHON_VERSION}* 


# Create symlink for python
RUN ln -fs /usr/local/bin/python3.11 /usr/local/bin/python \
 && ln -fs /usr/local/bin/pip3.11   /usr/local/bin/pip \
 && python --version && pip --version

# Set work directory to app root
WORKDIR /app

# Copy requirements.txt first for better caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .