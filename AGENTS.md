# Repository agent contract

Deze repository is kanaal-only.

## Doel

Publiek YouTube-kanaal -> `/videos` -> maximaal 1000 entries inspecteren -> alleen exacte `upload_date` in 2026 -> publieke captiontekst + maximaal 7 top-level comments per video -> gevalideerd corpus/ZIP.

## Harde grenzen

- geen directe video-, Short- of playlistinput;
- geen video/audio-download, FFmpeg of Whisper;
- geen cookies, login, browserprofielen, proxies, CAPTCHA- of PO-token-bypass;
- comments zijn `top`, maximaal 7 per video, top-level only, geen replies;
- video-acquisitie is begrensd tot maximaal 7 gelijktijdig actieve video's en batches van maximaal 7;
- comments zijn non-gating; captionstatus blijft zelfstandig zichtbaar;
- project-/Skillkennis wordt nooit automatisch gepromoveerd.

Na expliciete `access_blocked`-evidence start geen volgende video-batch met nieuwe YouTube-netwerkacquisitie.

Queue-acquisitie draait uitsluitend op GitHub-hosted `ubuntu-24.04`. Per-video metadata, captions en comments gebruiken eerst de begrensde accountloze caption-first InnerTube/timedtext-route en daarna alleen de gepinde yt-dlp fallback. Core `access_blocked`-evidence uit kanaaldiscovery, metadata of captions is terminaal en activeert geen andere machine, proxy, login of bypass. Een comment-only access block blijft non-gating en maakt het resultaat `partial`. Lokaal uitvoeren blijft alleen als handmatige parity/debugroute ondersteund.

Resolve en de GitHub-hosted runtime gebruiken dezelfde immutable trusted runtime-SHA. Geen acquisitieroute voert runtimecode vanaf de transportbranch uit.

Update tests, `toolkit-contract.json`, security/threat-model en doctor bij iedere scopewijziging. Run voor merge: Python compile, shell syntax, unittest-suite en repository doctor.

## Agent-capability- en impactbeleid

Voordat een agent repository- of externe state wijzigt:

- Classificeer de bedoelde actie als `read_only`, `safe_write` of `high_risk_write`.
- `read_only` mag inspecteren, zoeken, diffen, linten en testen zonder externe state te muteren.
- `safe_write` moet begrensd en omkeerbaar zijn, met target-preflight, stale-state/idempotency-bescherming waar relevant, exacte readback en rollback wanneer het target dit ondersteunt.
- `high_risk_write` omvat destructieve, productie-, deploy-, publicatie-, permission-, securitygevoelige of breed gescopeerde mutaties. Houd die achter expliciete owner/approval en sterkere verificatie.
- Toolbeschikbaarheid, een agentverzoek of groene CI verleent nooit vanzelf extra schrijfrechten.

Bouw vóór niet-triviale bronwijzigingen een begrensde impactcontext uit gewijzigde paden, directe imports/afhankelijkheden, relevante contracten/workflows en de tests die het gedrag bewijzen. Een gegenereerde graph/index is alleen commit-gebonden evidence/cache: geen projectwaarheid, duurzaam geheugen of tweede controller.

GitHub Trending en externe repositories zijn alleen discovery-signalen. Distilleer patronen en verifieer die daarna tegen het ownercontract, actuele primaire/officiële documentatie en lokale regressie-evidence. Kopieer geen code, prompts, assets of configuratie zonder compatibele gebruiksrechten en een expliciete repositoryreden.

