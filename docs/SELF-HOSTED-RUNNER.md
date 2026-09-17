# Dedicated self-hosted runner

De runtime gebruikt `runtime-requests` als append-only transportbranch. GitHub-hosted valideert alleen het request; kanaalacquisitie draait op `[self-hosted, linux, x64, webactueel-transcribe]`.

Hostvereisten: dedicated Linux x64, normale outbound HTTPS, Python 3.12+, `curl` en GNU `sha256sum`. De toolchain blijft exact gepind via `scripts/install_tools.sh`. Geen cookies, accounts, proxies of browserprofielen.

Een request bevat alleen kanaal-URL plus optionele captiontaal:
```json
{
  "enabled": true,
  "request_id": "brian-coords-2026",
  "url": "https://www.youtube.com/@BrianCoords",
  "language": "auto"
}
```

De runtime normaliseert naar `/videos`, inspecteert maximaal 1000 entries en neemt alleen exacte uploaddata uit 2026 mee. Per gematchte video worden maximaal 7 top-level comments op `top`-sortering opgehaald; comments zijn non-gating.

De self-hosted job checkt uitsluitend `main` uit. Als YouTube de normale verbinding blokkeert, blijft dat `access_blocked`; er is geen cookies/proxy/CAPTCHA-bypassfallback.
