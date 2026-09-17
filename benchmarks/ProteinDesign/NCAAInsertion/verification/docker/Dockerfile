FROM rosettacommons/rosetta:serial
WORKDIR /workspace
RUN python3 -c "import pyrosetta; pyrosetta.init(silent=True); print('PyRosetta ready')"
CMD ["python3"]
