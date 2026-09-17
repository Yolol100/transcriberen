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

## Waarom self-hosted

GitHub-hosted cloud-IP's kunnen door YouTube worden geblokkeerd. Daarom valideert de GitHub-hosted `resolve`-job alleen het append-only queue-request; echte YouTube-acquisitie draait op:

`[self-hosted, linux, x64, webactueel-transcribe]`

De resolve-job legt eerst de exacte vertrouwde `main`-commit vast. De self-hosted runtime checkt vervolgens precies die SHA uit en verifieert de readback voordat acquisitie start. Een wijziging op `main` tussen resolve en runtime kan daardoor niet stil een andere runtime laten uitvoeren.

Na requestvalidatie wordt `pending` gepubliceerd. De self-hosted job vervangt dit na uitvoering door het echte resultaat. Als YouTube ook de normale verbinding van de dedicated host blokkeert, blijft dat zichtbaar als `access_blocked`; de runtime omzeilt dit niet.

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

## Queue

Operationele requests worden append-only toegevoegd op branch `runtime-requests` als:

`requests/queue/<request_id>.json`

De bestandsnaam moet exact gelijk zijn aan `request_id`. De transportcommit mag precies een nieuw requestbestand toevoegen. De self-hosted runner voert nooit code vanaf de transportbranch uit.

## Cache en hervatten

Gevalideerde captions worden op de trusted execution host gecachet op `video_id + requested_language`. De transcript-SHA en lengte worden voor hergebruik gecontroleerd; corrupte cachedata wordt verwijderd en opnieuw opgehaald.

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

De lokale route gebruikt dezelfde resolver, toolbootstrap, channel runtime, cache en resultaatvalidator als de self-hosted route.

## Kennisgrens

Transcripts en comments zijn evidence/discovery-input. Deze repo promoot niets automatisch naar project-, Skill-, Memory- of bronwaarheid. Dat blijft eigendom van de Webactueel-workflow en de juiste vakskill.

## Licentie

Deze repository bevat momenteel geen open-sourcelicentie. Hergebruik, distributie of afgeleide werken zijn niet toegestaan zonder expliciete toestemming van de rechthebbende.
