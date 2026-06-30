# VPN-Only Deployment

FreeMail must not be exposed directly to the public internet during the current implementation phase.

## Hostname

Local/private hostname:

```text
freemail.kuzuryu.ai
```

## Required Boundary

- DNS should route `freemail.kuzuryu.ai` to the private Dragonscale/VPN target.
- Docker service ports must bind to `127.0.0.1` on the host.
- A local bridge or reverse proxy may expose HTTPS to VPN clients only.
- No WAN port-forwarding should be added for FreeMail until a later release gate explicitly changes that posture.

## Default Ports

| Surface | Default host port | Exposure |
| --- | ---: | --- |
| Admin API | `18090` | loopback |
| Web shell | `18091` | loopback |
| SMTP candidate | `2525` | loopback |
| Implicit-TLS submission candidate | `2465` | loopback |
| Implicit-TLS IMAP candidate | `2993` | loopback |
| JMAP/management candidate | `18092` | loopback |
| HTTPS candidate | `18443` | loopback |

## Verification

```powershell
docker compose config --quiet
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:18090/health/
```

Before routing `freemail.kuzuryu.ai`, verify the private bridge maps only VPN clients to the loopback service.
