FROM python:3.12.14-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends g++ libboost-program-options-dev default-jre-headless bubblewrap && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.2.6
WORKDIR /repo
COPY . /repo
RUN python benchmarks/FacilityOperations/RiskMaintenanceCampaign/scripts/setup_dependencies.py
