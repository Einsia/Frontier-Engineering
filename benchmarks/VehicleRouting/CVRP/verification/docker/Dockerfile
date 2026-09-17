FROM python:3.11-slim

WORKDIR /workspace

# The evaluator, reference solver and baseline use only the Python standard
# library. The unified runtime mounts the benchmark sandbox into the
# container, so no benchmark files are baked into the image (this keeps
# reference.json and the reference solver out of the container image).

ENV PYTHONUNBUFFERED=1

CMD ["python"]
