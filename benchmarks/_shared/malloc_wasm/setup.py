"""Install the pinned Linux x86-64 compiler and Wasmtime C API.

From the repository root:
    python benchmarks/_shared/malloc_wasm/setup.py --install

Without --install this command only checks local dependencies. Set
FRONTIER_MALLOC_TOOLCHAIN or pass --root to use a different installation root.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request


WASI_DIRECTORY = "wasi-sdk-34.0-x86_64-linux"
WASMTIME_DIRECTORY = "wasmtime-v48.0.2-x86_64-linux-c-api"
ASSETS = (
    (
        WASI_DIRECTORY,
        "https://github.com/WebAssembly/wasi-sdk/releases/download/"
        "wasi-sdk-34/wasi-sdk-34.0-x86_64-linux.tar.gz",
        "b761e3a0721dbae9c09a0059e5fdb2bf917d1b4a8a7b430fb3b5aafb0984b2c4",
    ),
    (
        WASMTIME_DIRECTORY,
        "https://github.com/bytecodealliance/wasmtime/releases/download/"
        "v48.0.2/wasmtime-v48.0.2-x86_64-linux-c-api.tar.xz",
        "d9a2b5dfaf688035f288a7ae81a4b96c3acdd3e849262c2ab577b61908c3f9f9",
    ),
)


@dataclass(frozen=True)
class Toolchain:
    root: Path
    clang: Path
    wasmtime: Path


def _root(root: str | Path | None = None) -> Path:
    value = root or os.environ.get("FRONTIER_MALLOC_TOOLCHAIN")
    return Path(value).expanduser().resolve() if value else (
        Path.home() / ".cache/frontier-eval/malloc-wasm"
    ).resolve()


def resolve(root: str | Path | None = None) -> Toolchain:
    """Return installed tool paths without network access."""
    root = _root(root)
    result = Toolchain(root, root / WASI_DIRECTORY / "bin/clang",
                       root / WASMTIME_DIRECTORY)
    required = (
        result.clang,
        result.clang.parent / "wasm-ld",
        result.wasmtime / "include/wasmtime.h",
        result.wasmtime / "include/wasm.h",
        result.wasmtime / "lib/libwasmtime.so",
    )
    if not all(path.is_file() for path in required) or not os.access(result.clang, os.X_OK):
        raise FileNotFoundError(
            f"Malloc Wasm dependencies are incomplete at {root}. "
            "Run python benchmarks/_shared/malloc_wasm/setup.py --install "
            f"--root {root}"
        )
    return result


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _check_download_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "github.com", "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    } or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Toolchain download must use an official HTTPS release asset")


class _ReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, destination: Path, expected: str) -> None:
    if destination.is_file() and _digest(destination) == expected:
        return
    _check_download_url(url)
    opener = urllib.request.build_opener(_ReleaseRedirect())
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            request = urllib.request.Request(url, headers={"User-Agent": "Frontier-Malloc-Setup"})
            with opener.open(request, timeout=120) as response:
                _check_download_url(response.url)
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > 1024 * 1024 * 1024:
                        raise ValueError("Toolchain archive exceeds the download size limit")
                    output.write(block)
        if _digest(temporary) != expected:
            raise ValueError(f"SHA-256 mismatch for {destination.name}")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _extract(archive: Path, destination: Path, directory: str) -> None:
    """Extract regular files first, then contained relative symbolic links."""
    destination = destination.resolve()
    with tarfile.open(archive) as source:
        members = source.getmembers()
        names: set[str] = set()
        total = 0
        for member in members:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or not name.parts
                    or name.parts[0] != directory or str(name) in names):
                raise ValueError(f"Unsafe archive path: {member.name}")
            names.add(str(name))
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError(f"Unsupported archive entry: {member.name}")
            if member.issym():
                target = PurePosixPath(member.linkname)
                resolved = (destination / name.parent / target).resolve()
                if target.is_absolute() or not resolved.is_relative_to(destination / directory):
                    raise ValueError(f"Unsafe archive link: {member.name}")
            total += member.size
            if total > 2 * 1024 * 1024 * 1024:
                raise ValueError("Unpacked toolchain exceeds the size limit")

        for member in members:
            if member.issym():
                continue
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as input_file, target.open("xb") as output:
                    shutil.copyfileobj(input_file, output)
                target.chmod(member.mode & 0o777)

        for member in members:
            if not member.issym():
                continue
            target = destination / member.name
            if any(parent.is_symlink() for parent in target.parents):
                raise ValueError(f"Archive link traverses another link: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(member.linkname)
        for member in members:
            if member.issym() and not (destination / member.name).resolve().is_relative_to(
                destination / directory
            ):
                raise ValueError(f"Archive link escapes extraction directory: {member.name}")


def install(root: str | Path | None = None) -> Toolchain:
    """Explicitly download and install hash-verified release assets."""
    root = _root(root)
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("The pinned Malloc toolchain supports Linux x86-64")
    root.mkdir(parents=True, exist_ok=True)
    import fcntl

    with (root / ".install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return resolve(root)
        except FileNotFoundError:
            pass
        downloads = root / "downloads"
        downloads.mkdir(exist_ok=True)
        for directory, url, expected in ASSETS:
            target = root / directory
            if target.exists():
                continue
            archive = downloads / url.rsplit("/", 1)[1]
            _download(url, archive, expected)
            with tempfile.TemporaryDirectory(prefix=".extract-", dir=root) as stage:
                _extract(archive, Path(stage), directory)
                os.replace(Path(stage) / directory, target)
        return resolve(root)


def compile_command(source: str | Path, output: str | Path, handout: str | Path,
                    toolchain: Toolchain | None = None) -> list[str]:
    """Build a memory64 module with only the host-controlled memlib imports."""
    toolchain = toolchain or resolve()
    support = Path(__file__).resolve().parent
    return [
        str(toolchain.clang), "--no-default-config", "--target=wasm64-unknown-unknown",
        "-O2", "-nostdlib", "-nostdinc", "-ffreestanding", "-fno-builtin", "-mbulk-memory",
        "-I" + str(support / "include"), "-I" + str(Path(handout).resolve()),
        str(Path(source).resolve()), str(support / "guest.c"),
        "-Wl,--no-entry", "-Wl,--export=mm_init", "-Wl,--export=mm_malloc",
        "-Wl,--export=mm_free", "-Wl,--export=mm_realloc", "-Wl,--export=__heap_base",
        "-Wl,--export-memory", "-Wl,--initial-memory=25165824", "-Wl,--max-memory=25165824",
        "-Wl,-z,stack-size=1048576", "-Wl,--allow-undefined-file=" + str(support / "allowed_imports.txt"),
        "-o", str(Path(output).resolve()),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Download the pinned dependencies")
    parser.add_argument("--root", type=Path, help="Override FRONTIER_MALLOC_TOOLCHAIN")
    args = parser.parse_args()
    paths = install(args.root) if args.install else resolve(args.root)
    print(f"clang: {paths.clang}\nwasmtime: {paths.wasmtime}")


if __name__ == "__main__":
    main()
