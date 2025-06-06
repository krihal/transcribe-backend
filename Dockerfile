FROM debian:bookworm-slim

# Install dependencies
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
		ca-certificates \
		curl \
		gcc \
		git \
		gnupg \
		libcurl4-openssl-dev \
		libssl-dev \
		make \
		pkg-config \
		python3 \
		python3-dev \
		python3-pip \
		python3-setuptools \
		python3-wheel \
		python3-venv \
		sudo \
		unzip \
		wget && \
	rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN rm -rf venv

# Install broker dependencies
RUN python3 -m venv venv && \
	. venv/bin/activate && \
	python3 -m pip install --upgrade pip && \
	pip install --no-cache-dir -r requirements.txt

# Run FastAPI
CMD ["/app/venv/bin/python3", "-m", "fastapi", "run", "app.py", "--port", "8000"]
