"""Explicit one-time download; never imported by ARIA's inference path."""
import argparse
import hashlib
from pathlib import Path
import urllib.request
import zipfile

MODEL_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_REVISION = "91cad51170dc346986eccefdc2dd33a9da36ead9"
MODEL_SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
RUNTIME_TAG = "b11126"
RUNTIME_SHA256 = "88b6648aa8a96c751a5279cff96ad79cb6070bc3ef2b4f77fc10ea4c29909d1c"


def download(url, path, digest):
    if path.exists():
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == digest:
                print(f"Verified cached {path.name}", flush=True)
                return
        raise ValueError(f"Existing file has the wrong checksum: {path}")
    temporary = path.with_suffix(path.suffix + ".partial")
    print(f"Downloading {path.name}", flush=True)
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    with temporary.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
            raise ValueError(f"Checksum mismatch: {temporary}")
    temporary.rename(path)
    print(f"Verified {path.name}: {path.stat().st_size} bytes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".aria-runtime"))
    args = parser.parse_args()
    root = args.directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = root / f"llama-{RUNTIME_TAG}-bin-win-cpu-x64.zip"
    download(f"https://github.com/ggml-org/llama.cpp/releases/download/{RUNTIME_TAG}/{archive.name}",
             archive, RUNTIME_SHA256)
    runtime = root / RUNTIME_TAG
    if not runtime.exists():
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if not (runtime / member.filename).resolve().is_relative_to(runtime):
                    raise ValueError("Invalid runtime archive path")
            bundle.extractall(runtime)
    download(f"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/{MODEL_REVISION}/{MODEL_NAME}",
             root / MODEL_NAME, MODEL_SHA256)
    print("Runtime:", next(runtime.rglob("llama-server.exe")))
    print("Model:", root / MODEL_NAME)


if __name__ == "__main__":
    main()
