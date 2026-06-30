from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Thread
from typing import Iterator


VIEWPORTS = {
    "desktop": {"width": 1365, "height": 900},
    "tablet": {"width": 820, "height": 1100},
    "mobile": {"width": 390, "height": 844},
}


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Run browser screenshot QA for the FreeMail webmail shell.")
    parser.add_argument("--output-dir", default=".freemail-qa/web-screenshots")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    web_root = root / "apps" / "web"
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import expect, sync_playwright
    except ImportError:
        print("Install dev dependencies and browsers first: python -m pip install -r requirements-dev.txt", file=sys.stderr)
        return 1

    failures = []
    with _static_server(web_root) as base_url:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    for name, viewport in VIEWPORTS.items():
                        failures.extend(_check_viewport(browser, expect, base_url, output_dir, name, viewport))
                finally:
                    browser.close()
        except PlaywrightError as exc:
            print(f"Browser QA failed to start: {exc}", file=sys.stderr)
            print("If Chromium is missing, run: python -m playwright install chromium", file=sys.stderr)
            return 1

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print(f"browser web QA passed; screenshots written to {output_dir}")
    return 0


def _check_viewport(browser, expect, base_url: str, output_dir: Path, name: str, viewport: dict[str, int]) -> list[str]:
    page = browser.new_page(viewport=viewport)
    screenshot_path = output_dir / f"webmail-{name}.png"
    failures = []
    try:
        page.goto(base_url, wait_until="networkidle")
        expect(page).to_have_title("FreeMail Webmail")
        for selector in [
            ".app-shell",
            ".sidebar",
            "#mailbox-login",
            "#message-list",
            "#message-reader",
            "#compose-form",
            "#reply-action",
            "#forward-action",
            "#archive-action",
        ]:
            expect(page.locator(selector)).to_be_visible()
        metrics = page.evaluate(
            """() => ({
                windowWidth: window.innerWidth,
                documentWidth: document.documentElement.scrollWidth,
                bodyWidth: document.body.scrollWidth,
                shellHeight: document.querySelector('.app-shell')?.getBoundingClientRect().height || 0,
                composeTop: document.querySelector('#compose-form')?.getBoundingClientRect().top || 0,
                readerTop: document.querySelector('#message-reader')?.getBoundingClientRect().top || 0
            })"""
        )
        if max(metrics["documentWidth"], metrics["bodyWidth"]) > metrics["windowWidth"] + 1:
            failures.append(
                f"{name}: horizontal overflow "
                f"{max(metrics['documentWidth'], metrics['bodyWidth'])}>{metrics['windowWidth']}"
            )
        if metrics["shellHeight"] < viewport["height"]:
            failures.append(f"{name}: app shell does not fill viewport height")
        if metrics["composeTop"] <= metrics["readerTop"]:
            failures.append(f"{name}: compose panel is not positioned after the reader header")
        overlap_count = page.evaluate(
            """() => Array.from(document.querySelectorAll('.folder-nav a')).filter((link) => {
                const label = link.querySelector('span:first-child')?.getBoundingClientRect();
                const count = link.querySelector('span:last-child')?.getBoundingClientRect();
                return label && count && label.right + 8 > count.left;
            }).length"""
        )
        if overlap_count:
            failures.append(f"{name}: folder navigation labels overlap counts")
        page.screenshot(path=screenshot_path, full_page=True)
        if screenshot_path.stat().st_size < 10_000:
            failures.append(f"{name}: screenshot appears too small to be a rendered page")
    finally:
        page.close()
    return failures


@contextmanager
def _static_server(directory: Path) -> Iterator[str]:
    handler = partial(QuietStaticHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
