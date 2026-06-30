from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
from typing import Iterator
from urllib.parse import urlparse


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
                    failures.extend(_check_admin_console(browser, expect, base_url, output_dir))
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
            "#star-action",
            "#unstar-action",
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


def _check_admin_console(browser, expect, base_url: str, output_dir: Path) -> list[str]:
    page = browser.new_page(viewport=VIEWPORTS["desktop"])
    screenshot_path = output_dir / "webmail-admin-console.png"
    status_updates: list[dict[str, str]] = []
    failures = []

    def api_response(route):
        request = route.request
        parsed = urlparse(request.url)
        if request.method == "GET" and parsed.path == "/api/v1/admin/domains":
            return _fulfill_json(route, [{"id": 1, "name": "example.com", "status": "active"}])
        if request.method == "GET" and parsed.path == "/api/v1/admin/users":
            return _fulfill_json(route, [{"id": 2, "email": "user@example.com", "displayName": "User", "isAdmin": False, "status": "invited"}])
        if request.method == "GET" and parsed.path == "/api/v1/admin/mailboxes":
            return _fulfill_json(route, [{"id": 3, "address": "user@example.com", "userId": 2, "status": "active"}])
        if request.method == "GET" and parsed.path == "/api/v1/admin/aliases":
            return _fulfill_json(route, [{"id": 4, "source": "info@example.com", "destination": "user@example.com", "status": "active"}])
        if request.method == "GET" and parsed.path == "/api/v1/admin/dkim-keys":
            return _fulfill_json(
                route,
                [{"id": 5, "domainId": 1, "selector": "default", "dnsName": "default._domainkey.example.com", "status": "active"}],
            )
        if request.method == "GET" and parsed.path == "/api/v1/admin/audit-log":
            return _fulfill_json(route, [{"id": 6, "actor": "admin-api", "action": "domain.create", "targetType": "domain", "targetId": 1, "createdAt": "2026-06-30T00:00:00Z"}])
        if request.method == "GET" and parsed.path == "/api/v1/admin/domains/1/dns":
            return _fulfill_json(
                route,
                {
                    "domain": "example.com",
                    "records": [
                        {"type": "MX", "name": "example.com", "value": "10 freemail.kuzuryu.ai", "ttl": 3600, "purpose": "Inbound mail"},
                        {"type": "TXT", "name": "example.com", "value": "v=spf1 mx -all", "ttl": 3600, "purpose": "SPF"},
                    ],
                },
            )
        if request.method == "PATCH" and parsed.path == "/api/v1/admin/domains/1/status":
            status_updates.append(json.loads(request.post_data or "{}"))
            return _fulfill_json(route, {"id": 1, "name": "example.com", "status": "suspended"})
        return route.fulfill(status=404, body="{}")

    try:
        page.route("**/api/v1/admin/**", api_response)
        page.goto(base_url, wait_until="networkidle")
        page.locator("#admin-api-base-url").fill(base_url.rstrip("/"))
        page.locator("#admin-token").fill("test-admin-token")
        page.locator("#bootstrap-token").fill("test-bootstrap-token")
        page.locator("#admin-auth button[type='submit']").click()
        expect(page.locator("#admin-status")).to_contain_text("Admin session saved")
        page.locator("#admin-refresh-action").click()
        expect(page.get_by_role("heading", name="Domains (1)")).to_be_visible()
        expect(page.get_by_role("button", name="DNS")).to_be_visible()
        expect(page.get_by_role("button", name="Suspend").first).to_be_visible()
        page.get_by_role("button", name="DNS").click()
        expect(page.locator("#admin-results")).to_contain_text("DNS guidance for example.com")
        expect(page.locator("#admin-results")).to_contain_text("v=spf1 mx -all")
        page.locator("#admin-refresh-action").click()
        expect(page.get_by_role("heading", name="Domains (1)")).to_be_visible()
        page.get_by_role("button", name="Suspend").first.click()
        expect(page.locator("#admin-status")).to_contain_text("Status updated")
        if status_updates != [{"status": "suspended"}]:
            failures.append(f"admin console did not submit expected status update: {status_updates}")
        page.screenshot(path=screenshot_path, full_page=True)
        if screenshot_path.stat().st_size < 10_000:
            failures.append("admin console screenshot appears too small to be a rendered page")
    finally:
        page.close()
    return failures


def _fulfill_json(route, payload: object):
    return route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(payload),
    )


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
