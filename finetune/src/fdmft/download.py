"""Resumable download of the sources into data/raw/<source>/.

- Kaggle: public endpoint `/api/v1/datasets/download/<ref>` (no credentials needed for public datasets), the zip
  is downloaded with HTTP Range resume, then extracted into `files/`.
- Roboflow: needs ROBOFLOW_API_KEY. The non-augmented version with the most images is chosen and the licence
  declared by the API is recorded in `download.json`.
- Hugging Face: `snapshot_download` of the dataset repo.

A completed source has `download.json`; running the command again skips it.
"""
from __future__ import annotations

import json
import shutil
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import requests

from fdmft.config import ROBOFLOW_API_KEY
from fdmft.sources import Source, registry

CHUNK = 1 << 20
UA = {"User-Agent": "printloop-finetune/0.1 (dataset download)"}


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def fetch(url: str, dest: Path, retries: int = 8) -> Path:
    """Downloads `url` into `dest`, resuming from `dest.part` if it exists."""
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        have = part.stat().st_size if part.exists() else 0
        headers = dict(UA, Range=f"bytes={have}-") if have else dict(UA)
        try:
            with requests.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) as r:
                if r.status_code == 416:            # already complete
                    break
                r.raise_for_status()
                if have and r.status_code != 206:   # the server ignores Range: start again
                    have = 0
                total = int(r.headers.get("Content-Length", 0)) + have
                mode = "ab" if have else "wb"
                last = time.monotonic()
                with part.open(mode) as fh:
                    for chunk in r.iter_content(CHUNK):
                        fh.write(chunk)
                        have += len(chunk)
                        if time.monotonic() - last > 30:
                            log(f"  {dest.name}: {have / 1e6:,.0f} / {total / 1e6:,.0f} MB")
                            last = time.monotonic()
            break
        except (requests.RequestException, OSError) as exc:
            wait = min(300, 10 * 2 ** (attempt - 1))
            log(f"  error ({exc}); retry {attempt}/{retries} in {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"download failed: {url}")
    part.rename(dest)
    return dest


def extract(archive: Path, target: Path) -> None:
    tmp = target.with_name(target.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(tmp)
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)


def _finish(src: Source, info: dict) -> None:
    info |= {"source": src.id, "ref": src.ref, "kind": src.kind, "downloaded_at": datetime.now(UTC).isoformat()}
    info.setdefault("license", src.license)
    (src.raw_dir / "download.json").write_text(json.dumps(info, indent=2))


def download_kaggle(src: Source, keep_archive: bool) -> None:
    meta = requests.get(f"https://www.kaggle.com/api/v1/datasets/view/{src.ref}", headers=UA, timeout=60).json()
    archive = src.raw_dir / "archive.zip"
    if not archive.exists():
        fetch(f"https://www.kaggle.com/api/v1/datasets/download/{src.ref}", archive)
    log(f"  extracting {archive.stat().st_size / 1e6:,.0f} MB")
    extract(archive, src.files_dir)
    if not keep_archive:
        archive.unlink()
    _finish(src, {"version": meta.get("currentVersionNumber"), "license_declared": meta.get("licenseName"),
                  "bytes": meta.get("totalBytes")})


ROBOFLOW_LICENSES = {"cc by 4.0": "CC-BY-4.0", "mit": "MIT", "public domain": "CC0-1.0", "cc0 1.0": "CC0-1.0",
                     "apache 2.0": "Apache-2.0", "odbl v1.0": "ODbL-1.0", "cc by-nc 4.0": "CC-BY-NC-4.0"}


def _roboflow_version(project: dict) -> dict:
    """Non-augmented version with the most images (augmentation multiplies near-identical copies)."""
    versions = project.get("versions") or []
    if not versions:
        raise RuntimeError("Roboflow project without published versions")

    def has_aug(v: dict) -> bool:
        return bool(v.get("augmentation")) and v.get("augmentation") not in ({}, [], "None")

    clean = [v for v in versions if not has_aug(v)]
    pool = clean or versions
    return max(pool, key=lambda v: v.get("images", 0))


def download_roboflow(src: Source, keep_archive: bool) -> None:
    if not ROBOFLOW_API_KEY:
        raise RuntimeError("ROBOFLOW_API_KEY missing (.env): free key from app.roboflow.com/settings/api")
    ws, proj = src.ref.split("/")
    base = f"https://api.roboflow.com/{ws}/{proj}"
    info = requests.get(base, params={"api_key": ROBOFLOW_API_KEY}, timeout=60).json()
    project = info.get("project", {})
    version = _roboflow_version(info)
    vnum = str(version["id"]).split("/")[-1]
    fmt = src.export_format
    log(f"  version {vnum}: {version.get('images')} images, augmentation={version.get('augmentation') or 'no'}")
    link = None
    for _ in range(60):                        # the export may have to be generated: poll
        exp = requests.get(f"{base}/{vnum}/{fmt}", params={"api_key": ROBOFLOW_API_KEY}, timeout=120).json()
        link = exp.get("export", {}).get("link")
        if link:
            break
        time.sleep(10)
    if not link:
        raise RuntimeError(f"Roboflow export not available: {exp}")
    archive = src.raw_dir / "archive.zip"
    if not archive.exists():
        fetch(link, archive)
    extract(archive, src.files_dir)
    if not keep_archive:
        archive.unlink()
    lic_raw = str(project.get("license", "")).strip()
    lic = ROBOFLOW_LICENSES.get(lic_raw.lower(), lic_raw or "unknown")
    if lic != src.license:
        log(f"  WARNING: licence declared by the API '{lic_raw}' differs from the registry '{src.license}'")
    _finish(src, {"version": vnum, "images": version.get("images"), "classes": project.get("classes"),
                  "license": lic, "license_declared": lic_raw, "augmentation": version.get("augmentation"),
                  "format": fmt})


def download_hf(src: Source, keep_archive: bool) -> None:
    from huggingface_hub import snapshot_download

    path = snapshot_download(src.ref, repo_type="dataset", local_dir=src.files_dir)
    _finish(src, {"local_dir": str(path)})


DOWNLOADERS = {"kaggle": download_kaggle, "roboflow": download_roboflow, "huggingface": download_hf}


def download(source_ids: list[str] | None, keep_archive: bool = False, force: bool = False) -> int:
    srcs = registry()
    ids = source_ids or list(srcs)
    failed = 0
    for sid in ids:
        src = srcs[sid]
        done = src.raw_dir / "download.json"
        if done.exists() and not force:
            log(f"{sid}: already downloaded")
            continue
        src.raw_dir.mkdir(parents=True, exist_ok=True)
        log(f"{sid}: downloading ({src.kind} {src.ref})")
        try:
            DOWNLOADERS[src.kind](src, keep_archive)
            log(f"{sid}: done")
        except Exception as exc:  # noqa: BLE001 - a failing source must not block the others
            failed += 1
            log(f"{sid}: FAILED: {exc}")
    return failed
