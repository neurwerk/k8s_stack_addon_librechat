"""Bounded multipart uploads through LibreChat's ordinary application routes."""

import json
import urllib.request
import uuid


def upload_file(
    opener, origin, headers, endpoint, model, *, filename, mime, data, dimensions=None
) -> dict:
    if not data or len(data) > 1048576:
        raise ValueError("Live fixture uploads are limited to 1 MiB")
    boundary = "live-" + uuid.uuid4().hex
    fields = {
        "endpoint": endpoint,
        "endpointType": "custom",
        "model": model,
        "file_id": str(uuid.uuid4()),
        "message_file": "true",
    }
    if dimensions is not None:
        fields.update(width=str(dimensions[0]), height=str(dimensions[1]))
    parts = [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
        ).encode()
        for key, value in fields.items()
    ]
    if any(character in filename + mime for character in '\r\n"'):
        raise ValueError("Invalid fixture upload metadata")
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        origin + ("/api/files/images" if dimensions is not None else "/api/files"),
        data=b"".join(parts),
        headers={
            **headers,
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Accept": "application/json",
        },
    )
    with opener.open(request, timeout=90) as response:
        if response.headers.get_content_type() != "application/json":
            raise ValueError("Expected JSON upload response")
        body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("Oversized upload response")
        result = json.loads(body)
    if not isinstance(result, dict) or not isinstance(result.get("file_id"), str):
        raise ValueError("Upload did not return a file ID")
    if (
        not result["file_id"]
        or not isinstance(result.get("filepath"), str)
        or not result["filepath"]
    ):
        raise ValueError("Upload did not return a file path")
    return result
