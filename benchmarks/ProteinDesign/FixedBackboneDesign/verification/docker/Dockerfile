FROM rosettacommons/rosetta:serial

# Set working directory
WORKDIR /workspace

# Verify PyRosetta is available
RUN python3 -c "import pyrosetta; pyrosetta.init(silent=True); print('PyRosetta ready: ' + pyrosetta.__version__)"

# Default command
CMD ["python3"]
