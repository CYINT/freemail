import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freemail_api.mail_store_backup import (
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_VOLUME,
    MailStoreBackupError,
    run_mail_store_restore,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a FreeMail Stalwart mail-store Docker volume archive.")
    parser.add_argument("--volume", default=DEFAULT_VOLUME, help="Target Docker volume.")
    parser.add_argument("--input", required=True, help="Input .tar.gz path.")
    parser.add_argument("--image", default=DEFAULT_DOCKER_IMAGE, help="Helper container image.")
    parser.add_argument("--force", action="store_true", help="Clear and replace the target Docker volume contents.")
    args = parser.parse_args()

    try:
        run_mail_store_restore(volume=args.volume, backup=Path(args.input), image=args.image, force=args.force)
    except (MailStoreBackupError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
