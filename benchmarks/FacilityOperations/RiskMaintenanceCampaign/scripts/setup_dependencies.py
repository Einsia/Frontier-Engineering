#!/usr/bin/env python3
"""Install exact third-party baseline sources from the audited offline archive."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def install(root=ROOT):
    manifest = json.loads((root / "references/dependencies.json").read_text())
    blob = (root / manifest["archive"]).read_bytes()
    if hashlib.sha256(blob).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("Dependency archive checksum mismatch")
    expected = {entry["path"]: entry for entry in manifest["files"]}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(expected) or {m.name for m in members} != set(expected):
            raise ValueError("Dependency archive member mismatch")
        verified = []
        for member in members:
            relative = Path(member.name)
            if not member.isfile() or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe dependency member")
            path = root / relative
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Dependency path escapes task directory")
            data = archive.extractfile(member).read()
            if hashlib.sha256(data).hexdigest() != expected[member.name]["sha256"]:
                raise ValueError("Dependency file checksum mismatch: " + member.name)
            verified.append((path, data))
        # Validate every member before writing any file. Never execute archive contents.
        for path, data in verified:
            if path.is_file() and path.read_bytes() == data:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            try:
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    return len(expected)


if __name__ == "__main__":
    print("Verified and installed %d offline dependency files." % install())
