"""Bundled inputs and assertions, independent of the working directory."""

from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "docling"
IMAGE_PATH = DATA / "ocr" / "sources" / "rotated_90_dense_text.png"
IMAGE_EXPECTED_TEXT = "ZQXPHOENIX 7742"
