from fastapi import FastAPI

from .settings import get_settings


settings = get_settings()

app = FastAPI(
    title="FreeMail API",
    version=settings.release_version,
    description="Admin and runtime API for the AGPL FreeMail mail platform.",
)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "freemail",
        "hostname": settings.hostname,
        "vpnOnly": settings.vpn_only,
        "release": {
            "version": settings.release_version,
            "commit": settings.release_commit,
        },
        "components": {
            "adminApi": "ready",
            "mailCore": "candidate-spike",
            "webmail": "scaffolded",
            "mobile": "planned",
        },
    }


@app.get("/api/v1/product")
def product() -> dict[str, object]:
    return {
        "name": settings.app_name,
        "license": "AGPL-3.0-or-later",
        "scope": [
            "mail-core",
            "admin-api",
            "webmail",
            "mobile-client",
            "deliverability-controls",
            "backup-restore",
        ],
    }


@app.get("/api/v1/deployment")
def deployment() -> dict[str, object]:
    return {
        "hostname": settings.hostname,
        "exposure": "vpn-only",
        "publicInternet": False,
        "requiredBoundary": "Dragonscale/VPN clients only",
    }
