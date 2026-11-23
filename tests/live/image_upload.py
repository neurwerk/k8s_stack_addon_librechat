"""Upload one small PNG through LibreChat; never log file metadata or content."""

import struct
from pathlib import Path

from file_upload import upload_file


def upload_image(
    opener, origin: str, headers: dict[str, str], endpoint: str, model: str, path: Path
) -> dict:
    if path.stat().st_size > 1048576:
        raise ValueError("Image smoke test is limited to 1 MiB")
    data = path.read_bytes()
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Image smoke test requires a PNG")
    if data[8:16] != b"\x00\x00\x00\rIHDR":
        raise ValueError("Missing PNG dimensions")
    width, height = struct.unpack(">II", data[16:24])
    if not (0 < width <= 8192 and 0 < height <= 8192):
        raise ValueError("Image dimensions exceed the smoke-test limit")
    result = upload_file(
        opener,
        origin,
        headers,
        endpoint,
        model,
        filename="control.png",
        mime="image/png",
        data=data,
        dimensions=(width, height),
    )
    print("PASS PNG uploaded; metadata withheld", flush=True)
    return result
