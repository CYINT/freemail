import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mail_store_backup import DEFAULT_DOCKER_IMAGE, DEFAULT_VOLUME, run_mail_store_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive the FreeMail Stalwart mail-store Docker volume.")
    parser.add_argument("--volume", default=DEFAULT_VOLUME, help="Docker volume to archive.")
    parser.add_argument("--output", required=True, help="Output .tar.gz path.")
    parser.add_argument("--image", default=DEFAULT_DOCKER_IMAGE, help="Helper container image.")
    args = parser.parse_args()

    run_mail_store_backup(volume=args.volume, output=Path(args.output), image=args.image)
    return 0


if __name__ == "__main__":
    sys.exit(main())
