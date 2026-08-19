# Webactueel Transcriberen Runtime

Controlled runtime voor Project Transcriberen. De repository verzamelt bronbewijs; `webactueel-workflow` beslist pas daarna wat betrouwbare, actuele en herbruikbare kennis is.

## Harde grenzen

- Publieke YouTube: metadata + precies één gekozen publieke captiontrack + optionele publieke comments. **Nooit audio/video-download.**
- Geen cookies, login, CAPTCHA-, DRM-, betaalmuur- of leeftijdscontrole-bypass.
- YouTube wordt alleen uitgevoerd wanneer `youtube_access_basis` al buiten deze runtime is beoordeeld als `prior-written-permission` of `applicable-law-reviewed`.
- `source_context.source_set_version` moet exact `2.0.0-audit-hardening` zijn.
- In een publieke GitHub-repository moet `public_request_acknowledged=true` zijn en zijn raw transcript/comment-artifacts verboden. Voor inhoudelijke analyse met raw broninhoud is een private/lokale of private-caller runtime nodig.

## Invocation

De runtime ondersteunt vier uitvoerroutes met hetzelfde requestcontract:

1. `workflow_dispatch` voor handmatige/debug-runs;
2. een immutable JSON-request op branch `runtime-requests` onder `requests/queue/<request_id>.json` voor automatische Chat/connector-routing;
3. `workflow_call` voor gecontroleerde repo-to-repo workflows;
4. lokale/private uitvoering voor contentanalyse die raw transcript/commenttekst nodig heeft.

Requestbestanden voor de queue zijn append-only: de bestandsnaam moet gelijk zijn aan `request_id`, een run accepteert precies één nieuw JSON-bestand en live requeststate wordt nooit naar `main` gemerged. De runtime blijft een evidence-adapter; `webactueel-workflow` houdt workflow- en kenniseigenaarschap.

## YouTube-scopes

`video`, `short`, `search`, `playlist`, `channel_videos`, `channel_shorts`, `channel_streams`, `channel_all`.

`channel_all` combineert videos, Shorts en streams, interleavet de tabs en dedupliceert video-ID's. Ranking (`relevance`, `views`, `likes`, `comments`, `newest`, `random`) geldt alleen binnen de werkelijk opgehaalde kandidaatset. `random` gebruikt `request_id` als reproduceerbare seed.

## Captions

Bij `language=auto`: Engels -> Nederlands -> eerste andere echte track. Binnen dezelfde taal wint manual van automatic. Auto-vertalingen worden uitgesloten.

Captionextractie probeert eerst de normale anonieme yt-dlp-route. Als die route geen bruikbare caption levert, volgen begrensde accountloze client-fallbacks (`tv`, `mweb`, `web_safari`, `web_embedded`). Er worden geen cookies, accounts, proxies of handmatige PO-tokens toegevoegd. Een echte upstream access-/anti-botblokkade blijft `access_blocked`.

De genormaliseerde transcripttekst is schoon; bij toegestane inhoudspersistentie wordt daarnaast `transcript-cues.json` bewaard zodat een inzicht terug te voeren blijft op het bronmoment.

## Comments

`include_comments=true` haalt comments op met `comment_sort=top|new`. Standaard is `include_replies=false`: bounded commentwerk beperkt zowel totaal als parents en vraagt nul replies op. Replies vereisen expliciete opt-in.

`raise_incomplete_data=1` maakt een onvolledige YouTube-commentresponse een echte fout. Daardoor wordt gedeeltelijke commentextractie niet als succesvol afgerond opgeslagen. Tijdelijke netwerk-/5xx-fouten krijgen begrensde retries; 429/rate-limitfouten krijgen langere cooldowns. Tussen geselecteerde zware YouTube-items gebruikt de runtime 5-10 seconden jitter.

Directe author-ID/naam/URL worden niet opgeslagen. Voor persistence worden duidelijke e-mailadressen, URLs, handles en telefoonnummers in tekst geredigeerd. Dit is dataminimalisatie, geen garantie op volledige anonimisering.

Met `comment_selection=knowledge` maakt de runtime alleen **review-kandidaten**. Signalen zijn onder andere creator, pinned, creator-favorited, likes en overlap met `knowledge_context.goal/keywords`. `comment-review.json` markeert tekst expliciet als untrusted. `knowledge-handoff.json` geeft een generieke overdracht naar de gekozen `target_owner`; in publieke runs bevat die geen raw transcript/commenttekst. De inhoudelijke Skill/projecteigenaar moet semantic review, currentness, deduplicatie en conflictcheck uitvoeren vóór promotie.

## Recovery en checkpoints

YouTube-itemwerk heeft harde proces-timeouts via `scripts/runtime.py`. Captions en comments worden onafhankelijk verwerkt: een captionfout blokkeert comments niet en omgekeerd. Mislukte onderdelen komen in `results/retry-queue.json` met bron-ID/URL en componentstatus zodat een controller of vervolgrun gericht kan herstellen in plaats van bewijs stil als compleet te behandelen.

## Werkbudget

Veilige standaardgrenzen:

- `max_items <= 250` zonder unbounded opt-in;
- `scan_limit <= 1000` zonder unbounded opt-in;
- `max_comments <= 1000` per item zonder unbounded opt-in;
- maximaal 20.000 commentrecords binnen één bounded request;
- harde maxima blijven gelden, ook bij `allow_unbounded=true`;
- `max_comments=all` kan alleen voor maximaal vijf geselecteerde items en blijft best effort.

## Web/article/feed/sitemap

De directe HTTP-route valideert publieke IP-adressen, blokkeert credentials/secrets in URLs, bindt request-time DNS aan vooraf gecontroleerde publieke adressen, valideert redirects, volgt RFC-9309 robotssemantiek, respecteert `Retry-After`, gebruikt hostpacing en een 10 MB responslimiet. Een onbetrouwbare robots-response bij 5xx/netwerkfout blokkeert conservatief.

## Geautoriseerde niet-YouTube audio

Whisper fallback is alleen beschikbaar wanneer `allow_audio_fallback=true`, `audio_access_authorized=true` en een concrete rechtenbasis aanwezig is. De route heeft duur-, bestandsgrootte- en proces-timeouts. FFmpeg/Whisper worden alleen voor die route geïnstalleerd.

## Resultaat en provenance

De runtime levert `results/result.json` en, voor YouTube, `youtube-index.json` plus itemmetadata, `retry-queue.json` en bij knowledge-commentselectie `knowledge-handoff.json`. Bij toegestane private/lokale contentpersistence kunnen transcript/cue/comment/review-sidecars bestaan.

`result.json` bevat requesthash, repository, runtime-head SHA, workflow ref, run ID/attempt, event en visibility. De workflow maakt `results/SHA256SUMS.txt` en attesteert dat checksumreceipt via GitHub/Sigstore. De validator controleert contract, privacy, hashes, tellingen en de no-media-grens.

## Security/CI

- Actions en tooldownloads zijn op immutable SHA's gepind.
- Python productie-installatie gebruikt een volledig gehashte wheel-lock.
- PR's krijgen GitHub Dependency Review; de lock krijgt daarnaast pip-audit.
- CodeQL scant Python en Actions.
- `SECURITY.md` en `THREAT-MODEL.md` beschrijven de trust boundaries.

Een groene runtime is nog geen projectwaarheid. Alleen `webactueel-workflow` mag bewijs na inhoudelijke review gecontroleerd promoveren.

## Repository governance

Generieke runtimecode en contracten staan op `main`. Handmatige runs gebruiken `workflow_dispatch`; geautomatiseerde Chat/connector-requests gebruiken uitsluitend de operationele branch `runtime-requests`; repo-to-repo gebruik mag via `workflow_call`. Live requeststate en target-specifieke source-sets worden niet naar `main` gemerged. Required branch controls are documented in `.github/REPOSITORY-GOVERNANCE.md`.
