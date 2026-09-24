# Webactueel Transcriberen Runtime

> **Portfoliostatus:** Actief ondersteunend - Webactueel transcriptieruntime

**Rol:** publieke YouTube-kanaalcaptions en begrensde commentcontext verzamelen als evidence/discovery-input. Inhoudelijke acceptatie en promotie naar Skills/projectbronnen blijft buiten deze repository.

Deze repository heeft nu een publieke acquisitietaak:

**YouTube-kanaal -> `/videos` -> maximaal 1000 entries -> alleen uploadjaar 2026 -> publieke captiontekst + maximaal 7 top-level comments per video -> gevalideerd corpus + ZIP.**

De oude directe single-video/Short-ingang bestaat niet meer.

## Ondersteund

- `https://www.youtube.com/@handle`
- `https://www.youtube.com/@handle/videos`
- `https://www.youtube.com/channel/<id>`
- legacy `/c/` en `/user/` kanaalvormen
- optionele captiontaal via `language`; standaard `auto`
- maximaal 1000 entries van de `/videos`-tab
- maximaal 7 video's tegelijk actief; de runtime schuift door in begrensde batches van 7
- alleen video's met exacte `upload_date` in 2026
- een gekozen publieke captiontrack per video
- maximaal 7 YouTube-side `top` gesorteerde top-level comments per video
- manifest, voortgang, run-scoped cache-index, checksums en deterministische ZIP

Captionkeuze bij `language=auto`: Engels, daarna Nederlands, daarna de eerste andere bruikbare taal. Binnen dezelfde taal wint handmatige ondertiteling van automatisch gegenereerde ondertiteling. Automatisch vertaalde tracks worden uitgesloten.

## Niet ondersteund

- directe video-, Short- of playlistinput
- `/shorts`- of livestreamtab als aparte bron
- YouTube search, ranking of topicfilters
- comment replies
- likes/views/engagement als selectiemechanisme
- audio-extractie, FFmpeg of Whisper
- video- of audiodownload
- cookies, login, browserprofielen, proxies, PO-tokens of CAPTCHA-bypass

## Hybride uitvoering

De queue draait hosted-first:

1. de GitHub-hosted `resolve`-job valideert precies één append-only queue-request en legt de exacte vertrouwde `main`-SHA vast;
2. een GitHub-hosted `ubuntu-24.04` runner probeert de volledige kanaalacquisitie met precies die immutable SHA;
3. alleen wanneer het gevalideerde resultaat expliciete `access_blocked`-evidence bevat, start automatisch de dedicated fallback op `[self-hosted, linux, x64, webactueel-transcribe]`;
4. gewone code- of acquisitiefouten triggeren de self-hosted fallback niet stil.

`access_blocked` wordt niet alleen op kanaaldiscovery herkend, maar ook wanneer metadata, captions of comments aantoonbaar door YouTube anti-bot/rate limiting zijn geblokkeerd. Een gewone `partial` zonder zulke blokkade-evidence blijft het hosted resultaat.

De resolve-job, hosted poging en eventuele self-hosted fallback gebruiken allemaal dezelfde vastgelegde runtime-SHA en controleren de readback. Een wijziging op `main` tijdens de run kan daardoor niet stil andere runtimecode laten uitvoeren.

Na requestvalidatie wordt `runtime/Transcribe Public Source` op `pending` gezet. Een succesvolle hosted run publiceert direct het eindresultaat. Bij expliciete blokkade blijft de status pending totdat de self-hosted fallback eindigt. Als ook de fallback wordt geblokkeerd, blijft dat zichtbaar als `access_blocked`; de runtime omzeilt dit niet.

## Request

```json
{
  "enabled": true,
  "request_id": "brian-coords-2026",
  "url": "https://www.youtube.com/@BrianCoords",
  "language": "auto"
}
```

Andere requestvelden worden fail-closed geweigerd. Jaar, videolimiet en commentbeleid zijn bewust geen vrij instelbare requestvelden:

- `year = 2026`
- `max_videos = 1000`
- `comments_per_video = 7`
- `comment_sort = top`
- replies = uit
- `video_concurrency = 7` (vaste runtimepolicy, niet instelbaar via requests)

## Queue

Operationele requests worden append-only toegevoegd op branch `runtime-requests` als:

`requests/queue/<request_id>.json`

De bestandsnaam moet exact gelijk zijn aan `request_id`. De transportcommit mag precies een nieuw requestbestand toevoegen. Geen acquisitierunner voert code vanaf de transportbranch uit.

## Snelheid en backpressure

De video-acquisitie is I/O-gebonden en wordt daarom parallel uitgevoerd met maximaal 7 workers. Een batch bevat nooit meer dan 7 video's. Metadata, captions en comments van verschillende video's mogen parallel lopen; binnen één video blijft de volgorde gecontroleerd. `progress.json` wordt duurzaam per batch bijgewerkt in plaats van na iedere tussenstap. De eind-ZIP gebruikt een snellere deflate-instelling om onnodige CPU-wachttijd te beperken.

Bij expliciete `access_blocked`-evidence (zoals HTTP 403/429 of anti-botmelding) wordt geen volgende batch gestart met nieuwe YouTube-netwerkacquisitie. De maximaal 7 reeds actieve workers mogen hun begrensde werk afronden. Dit is backpressure, geen bypass.

## Cache en hervatten

Op de dedicated self-hosted/local host worden gevalideerde captions gecachet op `video_id + requested_language`. De transcript-SHA en lengte worden voor hergebruik gecontroleerd; corrupte cachedata wordt verwijderd en opnieuw opgehaald. GitHub-hosted runners zijn ephemeral en delen deze persistente cache niet.

Comments worden niet persistent als waarheid gecachet. Iedere nieuwe kanaalrun mag daardoor opnieuw de actuele YouTube-side topselectie proberen op te halen.

De SQLite-database blijft hoststate en wordt nooit naar `main` gecommit. `processed-index.json` is expliciet `current_run`: alleen de videos uit de huidige corpusrun worden geexporteerd. Oude cachehistorie van andere kanalen of eerdere runs komt niet in de ZIP terecht.

## Output en volledigheid

Per gematchte 2026-video:

- `videos/<video_id>/metadata.json`
- `videos/<video_id>/transcript.txt` alleen wanneer captions bestaan
- `videos/<video_id>/comments.json` met maximaal 7 top-level comments

Per run:

- `results/result.json`
- `results/manifest.json`
- `results/progress.json`
- `results/processed-index.json`
- `results/channel-corpus.zip`
- `results/SHA256SUMS.txt`

Een video zonder captions blijft zichtbaar als `skipped_no_captions`; dat is geen acquisitiefout. Metadata die niet kan worden opgehaald of geen `upload_date` bevat wordt daarentegen als `unresolved` vastgelegd, omdat lidmaatschap van 2026 dan niet bewezen kan worden. Captionfouten en niet-beschikbare comments blijven per video zichtbaar. Een run met zulke onvolledigheden krijgt `status=partial`, niet `ok`.

Comments blijven non-gating voor een geldig transcript: een commentfout verwijdert of degradeert de caption niet. Het totale corpus wordt wel als gedeeltelijk gemarkeerd zolang gevraagde commentcontext ontbreekt.

Voor no-replies gebruikt de runtime yt-dlp `max_comments=7,7,0,0,1`; `max-depth=1` sluit replies expliciet uit. De runtime filtert replies daarna nogmaals bij readback.

## Toolchain

De runtime gebruikt exact gepinde, SHA-256-gecontroleerde binaries:

- yt-dlp nightly `2026.09.16.232951`
- Deno `2.9.7`

`scripts/install_tools.sh` accepteert alleen de exacte versie of downloadt de vastgelegde release en controleert SHA-256 voor installatie. yt-dlp draait altijd via de lokale wrapper met Deno expliciet als JS-runtime.

## Lokaal uitvoeren

Vereisten: Linux x86_64 of WSL2/Ubuntu, Python 3.12+, `curl` en GNU `sha256sum`.

```bash
bash scripts/run_local.sh requests/transcribe.json
```

De lokale route gebruikt dezelfde resolver, toolbootstrap, channel runtime, cache en resultaatvalidator als de remote routes.

## Kennisgrens

Transcripts en comments zijn evidence/discovery-input. Deze repo promoot niets automatisch naar project-, Skill-, Memory- of bronwaarheid. Dat blijft eigendom van de Webactueel-workflow en de juiste vakskill.

## Licentie

Deze repository bevat momenteel geen open-sourcelicentie. Hergebruik, distributie of afgeleide werken zijn niet toegestaan zonder expliciete toestemming van de rechthebbende.
