# Repository agent contract

Deze repository is kanaal-only.

## Doel

Publiek YouTube-kanaal -> `/videos` -> maximaal 1000 entries inspecteren -> alleen exacte `upload_date` in 2026 -> publieke captiontekst + maximaal 7 top-level comments per video -> gevalideerd corpus/ZIP.

## Harde grenzen

- geen directe video-, Short- of playlistinput;
- geen video/audio-download, FFmpeg of Whisper;
- geen cookies, login, browserprofielen, proxies, CAPTCHA- of PO-token-bypass;
- comments zijn `top`, maximaal 7 per video, top-level only, geen replies;
- comments zijn non-gating; captionstatus blijft zelfstandig zichtbaar;
- project-/Skillkennis wordt nooit automatisch gepromoveerd.

Queue-acquisitie probeert eerst GitHub-hosted `ubuntu-24.04`. Alleen expliciete `access_blocked`-evidence mag automatisch doorvallen naar `[self-hosted, linux, x64, webactueel-transcribe]`. Generieke fouten mogen die fallback niet activeren. Lokaal uitvoeren blijft ondersteund.

Resolve, hosted attempt en eventuele fallback gebruiken dezelfde immutable trusted runtime-SHA. Geen acquisitieroute voert runtimecode vanaf de transportbranch uit.

Update tests, `toolkit-contract.json`, security/threat-model en doctor bij iedere scopewijziging. Run voor merge: Python compile, shell syntax, unittest-suite en repository doctor.
