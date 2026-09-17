# Security

De runtime accepteert uitsluitend een publieke YouTube-kanaal-URL en verwerkt de `/videos`-tab. Directe video’s, Shorts en playlists zijn geen invoercontract.

Harde grenzen: geen cookies/login/browserprofielen/proxies, geen CAPTCHA- of PO-token-bypass, geen media-download, geen FFmpeg/Whisper. Alle yt-dlp-videoroutes gebruiken `--skip-download` en `--no-cookies`.

Per run worden maximaal 1000 kanaalvideo’s geïnspecteerd. Alleen video’s met exact uploadjaar 2026 komen in het corpus. Per gematchte video worden maximaal 7 top-level comments op `top`-sortering gevraagd; replies worden niet opgeslagen. Commentfalen is non-gating en wordt apart gerapporteerd.

Acquisitie draait uitsluitend op de dedicated Linux x64 runner `webactueel-transcribe` of lokaal via `scripts/run_local.sh`. De transportbranch levert nooit uitvoerbare code aan de self-hosted host.
