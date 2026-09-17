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

YouTube-acquisitie draait alleen lokaal of op `[self-hosted, linux, x64, webactueel-transcribe]`. GitHub-hosted jobs valideren alleen de append-only requestqueue.

Update tests, `toolkit-contract.json`, security/threat-model en doctor bij iedere scopewijziging. Run vóór merge: Python compile, shell syntax, unittest-suite en repository doctor.
