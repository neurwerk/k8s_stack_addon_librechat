"""Opt-in session check and single synthetic chat using copied browser request headers."""

import argparse
import urllib.error
from pathlib import Path

from chat_smoke import chat
from fixtures import IMAGE_EXPECTED_TEXT, IMAGE_PATH
from image_upload import upload_image
from session import Session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument("--endpoint")
    parser.add_argument("--model")
    parser.add_argument("--save-title")
    parser.add_argument("--image", action="store_true", help="Use the bundled OCR image")
    parser.add_argument("--refresh", action="store_true", help="May rotate session credentials")
    args = parser.parse_args()
    if bool(args.endpoint) != bool(args.model):
        parser.error("Supply both --endpoint and --model")
    if args.save_title and (not args.model or len(args.save_title) > 120):
        parser.error("--save-title requires a model and at most 120 characters")
    if args.image and not args.model:
        parser.error("Image tests require --endpoint and --model")
    try:
        session = Session(args.origin, args.request_file)
        session.authenticate(refresh=args.refresh)
        print("PASS authenticated LibreChat session")
        if args.model:
            attachment = (
                upload_image(
                    session.opener,
                    session.origin,
                    session.headers,
                    args.endpoint,
                    args.model,
                    IMAGE_PATH,
                )
                if args.image
                else None
            )
            chat(
                session.opener,
                session.origin,
                session.headers,
                args.endpoint,
                args.model,
                attachment=attachment,
                expected_text=IMAGE_EXPECTED_TEXT if args.image else None,
                save_title=args.save_title,
            )
        return 0
    except urllib.error.HTTPError as exc:
        print(f"FAIL live check: HTTP {exc.code}; response withheld")
        exc.close()
    except (OSError, ValueError, TypeError, KeyError):
        print("FAIL live check: invalid input, response, or connection; details withheld")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
