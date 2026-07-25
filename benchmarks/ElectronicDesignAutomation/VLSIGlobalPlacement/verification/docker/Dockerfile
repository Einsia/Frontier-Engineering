FROM python:3.11-slim

WORKDIR /workspace

COPY verification/evaluator.py /workspace/verification/evaluator.py
COPY verification/requirements.txt /workspace/verification/requirements.txt
COPY scripts/ /workspace/benchmarks/ElectronicDesignAutomation/VLSIGlobalPlacement/scripts/
COPY references/ /workspace/benchmarks/ElectronicDesignAutomation/VLSIGlobalPlacement/references/

ENV BENCHMARK_NAME=adaptec1
ENV FRONTIER_ENGINEERING_ROOT=/workspace

ENTRYPOINT ["python", "/workspace/verification/evaluator.py", "/workspace/benchmarks/ElectronicDesignAutomation/VLSIGlobalPlacement/scripts/init.py"]
