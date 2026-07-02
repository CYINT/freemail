# FreeMail PWA Mobile Path

FreeMail private beta uses the browser/PWA webmail app as the supported mobile path.

## iPhone

1. Join the Dragonscale/VPN network that can resolve `freemail.kuzuryu.ai`.
2. Open Safari.
3. Go to `https://freemail.kuzuryu.ai`.
4. Sign in with FreeMail email/password and MFA.
5. Use Share, then Add to Home Screen.

The installed Home Screen app uses `apps/web/manifest.webmanifest`, iOS mobile web metadata in `apps/web/index.html`, and the service worker in `apps/web/sw.js`.

## Release Posture

The default release packet strategy is `pwa`. `scripts/release_packet_status.py` validates the `web-mobile-pwa` check and does not require Expo, EAS, TestFlight, Play Console, or native store-submission evidence.

Use `--mobile-strategy native` only when preparing a future native app-store release candidate.
