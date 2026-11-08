"""Download selected UTA-RLDD subjects from official ZIPs via HTTP byte ranges.

Only ALERT (0) and DROWSY (10) are selected. No archive is downloaded in full.
Downloaded videos and the catalog stay in ignored local directories.
"""

import argparse
from contextlib import ExitStack
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import time
import zipfile
import zlib

import requests

SOURCE = "https://sites.google.com/view/utarldd/home"
# Public file IDs from the author's Drive folder; no account/token needed.
ARCHIVES = {
    "Fold1_part1.zip": "16x8afSOwfbdGAjUbfRFvwGj1ie8Lf5Do",
    "Fold1_part2.zip": "1qPoJ06jeznytP_BGJ25hxdQy7eYTTjyk",
    "Fold2_part1.zip": "12uVMVLv_kRXzQb4QDdru9RK3G9hzfpPQ",
    "Fold2_part2.zip": "1nYGUpqE3x5ZeRLgDeMlUN4K_ccPjM2pe",
    "Fold3_part1.zip": "1-JhE5TfkNyr4UbQk6PSkkpI7z-SChkWS",
    "Fold3_part2.zip": "1LZU5KfJkFMj2pIkGwb3RjHDazoUfxSYQ",
    "Fold4_part1.zip": "1IYKdrjvawf90bG_cfeoWA4rZSymllFbD",
    "Fold4_part2.zip": "1zJlASBwABBgVSULQLiia0R_Eqar8_B3D",
    "Fold5_part1.zip": "16w30wEgcAbaUr4gx9o4sl_2TbIunD5yA",
    "Fold5_part2.zip": "1loOQE1-hoNM5dIOjXHI2Ss5NjjoPZcX6",
}
GIB = 1024 ** 3
CHUNK = 8 * 1024 * 1024


class DatasetQuotaError(ValueError):
    """The public source is temporarily refusing downloads."""


class RangeReader(io.RawIOBase):
    """Seekable remote file with strict range validation and bounded reads."""

    def __init__(self, file_id, session=None, url=None):
        super().__init__()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
            raise ValueError("Invalid public Drive file ID")
        self.session = session or requests.Session()
        self.owns_session = session is None
        self.url = url or f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
        self.position = 0
        self.size = None
        self.transferred = 0
        self._range(0, 0)

    def _range(self, start, end):
        last_error = None
        for attempt in range(3):
            try:
                with self.session.get(self.url, headers={"Range": f"bytes={start}-{end}",
                                                        "Accept-Encoding": "identity"},
                                      stream=True, timeout=(10, 45)) as response:
                    if response.status_code != 206:
                        if "text/html" in response.headers.get("Content-Type", ""):
                            preview = next(response.iter_content(4096), b"").decode("utf-8", errors="replace")
                            if "quota exceeded" in preview.lower():
                                raise DatasetQuotaError("Google Drive: Quota exceeded. Download stopped; "
                                    "no full archive was fetched. Try again when the source permits "
                                    "downloads, or use --local-zip with an existing official archive.")
                        raise ValueError(f"Expected HTTP 206, got {response.status_code}. "
                                         "Drive may require browser access or have a quota limit; "
                                         "refusing to read a whole archive.")
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if not match:
                        raise ValueError("Missing/invalid Content-Range")
                    got_start, got_end, total = map(int, match.groups())
                    if (got_start != start or got_end != end or total <= end
                            or (self.size is not None and self.size != total)):
                        raise ValueError("Unexpected range or changed archive size")
                    self.size = total
                    chunks, received = [], 0
                    for block in response.iter_content(1024 * 1024):
                        received += len(block)
                        if received > end - start + 1:
                            raise ValueError("Response exceeded requested byte range")
                        chunks.append(block)
                    if received != end - start + 1:
                        raise requests.ConnectionError("Incomplete byte range")
                    self.transferred += received
                    return b"".join(chunks)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(attempt + 1)
        raise last_error

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        position = offset if whence == io.SEEK_SET else (
            self.position + offset if whence == io.SEEK_CUR else self.size + offset)
        if whence not in (io.SEEK_SET, io.SEEK_CUR, io.SEEK_END) or position < 0:
            raise ValueError("Invalid seek")
        self.position = position
        return position

    def read(self, size=-1):
        if size is None or size < 0:
            size = self.size - self.position
        size = min(size, self.size - self.position)
        if size <= 0:
            return b""
        # zipfile only needs the central directory and bounded video chunks.
        if size > 16 * 1024 * 1024:
            raise ValueError("Unbounded remote read refused")
        data = self._range(self.position, self.position + size - 1)
        self.position += size
        return data

    def close(self):
        if not self.closed and self.owns_session:
            self.session.close()
        super().close()


def video_entries(name, file_id, archive, local_zip=None):
    videos = []
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename.replace("\\", "/"))
        if (entry.is_dir() or path.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv"}
                or not path.parent.name.isdigit() or path.stem not in {"0", "10"}):
            continue
        video = {"archive": name, "file_id": file_id, "member": entry.filename,
                 "subject_id": path.parent.name, "label": path.stem,
                 "extension": path.suffix.lower(), "bytes": entry.file_size,
                 "compressed_bytes": entry.compress_size, "crc32": entry.CRC}
        if local_zip is not None:
            video["local_zip"] = str(local_zip)
        videos.append(video)
    return videos


def list_archives(archives=None):
    videos = []
    for name, file_id in (archives or ARCHIVES).items():
        with RangeReader(file_id) as reader, zipfile.ZipFile(reader) as archive:
            entries = video_entries(name, file_id, archive)
            videos.extend(entries)
            print(f"Catalog {name}: {len(entries)} target videos; archive={reader.size / GIB:.2f} GiB; "
                  f"metadata_read={reader.transferred} bytes", flush=True)
    if not videos:
        raise ValueError("No supported subject/label filenames in official ZIPs; inspect layout")
    return {"source": SOURCE, "videos": videos, "created_at_unix": time.time()}


def list_local_archives(paths):
    videos = []
    for path in paths:
        path = Path(path).resolve()
        with zipfile.ZipFile(path) as archive:
            videos.extend(video_entries(path.name, None, archive, local_zip=path))
    if not videos:
        raise ValueError("No supported UTA-RLDD videos in local archives")
    return {"source": SOURCE, "videos": videos, "created_at_unix": time.time(),
            "input": "Local copies of UTA-RLDD ZIPs; no network used"}


def select_videos(catalog, subjects=None, count=5):
    pairs = {}
    for video in catalog["videos"]:
        key = (video["subject_id"], video["label"])
        if key in pairs:
            previous = pairs[key]
            if previous["crc32"] != video["crc32"] or previous["bytes"] != video["bytes"]:
                raise ValueError(f"Conflicting duplicate subject/label: {key}")
        else:
            pairs[key] = video
    complete = sorted({s for s, _ in pairs if (s, "0") in pairs and (s, "10") in pairs},
                      key=lambda s: (int(s), s))
    if count < 1:
        raise ValueError("Subject count must be positive")
    selected = list(dict.fromkeys(subjects)) if subjects else complete[:count]
    if not selected or any(s not in complete for s in selected) or (not subjects and len(selected) != count):
        raise ValueError("Not enough complete subjects, or selected folder IDs are missing")
    return [pairs[(subject, label)] for subject in selected for label in ("0", "10")]


def valid_existing(path, video):
    if not path.is_file() or path.stat().st_size != video["bytes"]:
        return False
    checksum = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(CHUNK), b""):
            checksum = zlib.crc32(block, checksum)
    return checksum == video["crc32"]


def download(catalog, root, subjects=None, count=5, max_gib=8.0):
    if not math.isfinite(max_gib) or max_gib <= 0:
        raise ValueError("Download budget must be finite and positive")
    selected = select_videos(catalog, subjects, count)
    total = sum(v["bytes"] for v in selected)
    print(f"Selected people: {list(dict.fromkeys(v['subject_id'] for v in selected))}; "
          f"{len(selected)} videos; total={total / GIB:.2f} GiB", flush=True)
    if total > max_gib * GIB:
        raise ValueError(f"Subset exceeds --max-gib {max_gib}; no videos downloaded")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < total + 10 * GIB:
        raise ValueError("Insufficient disk space with a 10 GiB reserve")
    downloaded = []
    with ExitStack() as stack:
        archives = {}
        for video in selected:
            # Never extract an untrusted member path: choose a safe local name.
            subject = video["subject_id"]
            if (not subject.isdigit() or video["label"] not in {"0", "10"}
                    or video["extension"] not in {".mp4", ".mov", ".avi", ".mkv"}):
                raise ValueError("Unsafe catalog subject/label")
            destination = (root / subject / f"{video['label']}{video['extension']}").resolve()
            if not destination.is_relative_to(root):
                raise ValueError("Destination escapes dataset directory")
            if valid_existing(destination, video):
                print(f"Verified existing {subject}/{destination.name}; skipping", flush=True)
                downloaded.append(video)
                continue
            if destination.exists():
                raise ValueError(f"Existing file has different size/CRC: {destination}; refusing overwrite")
            archive_key = video.get("local_zip") or video["file_id"]
            if archive_key not in archives:
                if video.get("local_zip"):
                    archives[archive_key] = stack.enter_context(zipfile.ZipFile(video["local_zip"]))
                else:
                    reader = stack.enter_context(RangeReader(video["file_id"]))
                    archives[archive_key] = stack.enter_context(zipfile.ZipFile(reader))
            archive = archives[archive_key]
            info = archive.getinfo(video["member"])
            if info.file_size != video["bytes"] or info.CRC != video["crc32"]:
                raise ValueError("Remote ZIP differs from the catalog; refresh it")
            destination.parent.mkdir(parents=True, exist_ok=True)
            partial = destination.with_suffix(destination.suffix + ".part")
            if partial.is_symlink():
                raise ValueError("Refusing to write a symlink as a partial download")
            received, checksum, last_log = 0, 0, time.monotonic()
            print(f"Downloading {subject}/{destination.name}: {info.file_size / GIB:.2f} GiB", flush=True)
            # ZipExtFile also validates CRC on completion; we verify explicitly.
            with archive.open(info) as source, partial.open("wb") as target:
                while block := source.read(CHUNK):
                    received += len(block)
                    if received > info.file_size:
                        raise ValueError("Video exceeds catalog size")
                    checksum = zlib.crc32(block, checksum)
                    target.write(block)
                    if time.monotonic() - last_log >= 10:
                        print(f"  {subject}/{destination.name}: {received / info.file_size:.0%}", flush=True)
                        last_log = time.monotonic()
            if received != info.file_size or checksum != info.CRC:
                raise ValueError("Downloaded video failed size/CRC verification")
            partial.replace(destination)
            downloaded.append(video)
            print(f"Verified {subject}/{destination.name}", flush=True)
    (root / "download-manifest.json").write_text(json.dumps({"source": SOURCE,
        "selection": "explicit IDs" if subjects else "first complete numeric subject IDs (pilot)",
        "videos": downloaded}, indent=2), encoding="utf-8")
    return downloaded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--local-zip", type=Path, action="append", help="Existing official ZIP; repeat for multiple archives")
    parser.add_argument("--root", type=Path, default=Path("datasets/UTA-RLDD"))
    parser.add_argument("--subjects", nargs="+")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--max-gib", type=float, default=8.0)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--refresh-catalog", action="store_true")
    args = parser.parse_args()
    if args.catalog is None:
        args.catalog = Path("ml-data/uta-local-catalog.json" if args.local_zip else "ml-data/uta-catalog.json")
    try:
        if args.local_zip:
            catalog = list_local_archives(args.local_zip)
            args.catalog.parent.mkdir(parents=True, exist_ok=True)
            args.catalog.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
        elif args.catalog.exists() and not args.refresh_catalog:
            catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        else:
            catalog = list_archives()
            args.catalog.parent.mkdir(parents=True, exist_ok=True)
            args.catalog.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
        selection = select_videos(catalog, args.subjects, args.count)
        print(f"Plan: {len(selection)} videos, {sum(v['bytes'] for v in selection) / GIB:.2f} GiB", flush=True)
        if not args.catalog_only:
            download(catalog, args.root, args.subjects, args.count, args.max_gib)
    except (ValueError, OSError, KeyError, requests.RequestException, zipfile.BadZipFile) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
