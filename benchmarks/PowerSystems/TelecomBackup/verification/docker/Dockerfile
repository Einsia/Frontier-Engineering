FROM python:3.11-slim

WORKDIR /workspace

# The evaluator, simulator, reference solver and baseline use only the Python
# standard library. The unified runtime mounts the benchmark sandbox into the
# container, so no benchmark files are baked into the image. The candidate may
# read `verification/simulator.py` (it is part of the scoring objective and is
# allowed by the constraints), but no instance data is baked in.

ENV PYTHONUNBUFFERED=1

CMD ["python"]
