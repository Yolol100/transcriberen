# Webactueel Transcriberen Runtime

> **Portfoliostatus:** Actief ondersteunend · Webactueel transcriptieruntime

**Rol in het platform:** deze runtime levert één begrensde transcriptietaak aan de Webactueel-workflow. Requests gebruiken de eigen append-only `runtime-requests`-queue; [Orchestrator](https://github.com/Yolol100/Orchestrator) maakt hiervoor geen nieuwe runtimebranch en inhoudelijke acceptatie blijft bij de owning workflow.

Deze repository heeft één taak:

**publieke YouTube-video of Short -> één echte ondertiteltrack -> platte transcripttekst.**

Als een video of Short geen ondertiteling heeft, is dat geen fout. De run eindigt met `skipped_no_captions` en maakt geen `transcript.txt`.

## Ondersteund

- `https://www.youtube.com/watch?v=<id>`
- `https://www.youtube.com/shorts/<id>`
- `https://youtu.be/<id>`
- optionele taal via `language`; standaard `auto`
- één geselecteerde captiontrack
- lokale of dedicated self-hosted uitvoering via een normale directe internetverbinding

Captionkeuze bij `language=auto`: Engels, daarna Nederlands, daarna de eerste andere beschikbare echte taal. Binnen dezelfde taal wint handmatige ondertiteling van automatisch gegenereerde ondertiteling. Bij een expliciete taalcode, bijvoorbeeld `en-US`, wordt eerst die exacte code gezocht; pas daarna wordt naar dezelfde taalfamilie teruggevallen. Automatisch vertaalde tracks worden uitgesloten.

## Niet ondersteund

De runtime doet bewust niet aan comments, kanaal- of playlistverzameling, YouTube search, ranking, topicfilters, likes/views/engagement, knowledge handoffs, artikelen, feeds, sitemaps, audio-extractie, FFmpeg, Whisper of video/audio-download.

Ook worden geen cookies, login, browserprofielen, proxies, PO-tokens of CAPTCHA-bypasses gebruikt.

## Waarom self-hosted

GitHub-hosted cloud-IP's kunnen van YouTube `Sign in to confirm you're not a bot` krijgen. Dat is geen captionlogica die betrouwbaar kan worden weggeprogrammeerd. Daarom valideert de GitHub-hosted `resolve`-job alleen het immutable queue-request; de daadwerkelijke YouTube-captionextractie draait op de dedicated runner:

`[self-hosted, linux, x64, webactueel-transcribe]`

Na succesvolle requestvalidatie publiceert de hosted job direct een `pending` commitstatus. Daardoor blijft zichtbaar dat een request correct is geaccepteerd, ook wanneer de self-hosted runner offline is of nog in de wachtrij staat. De self-hosted job vervangt die status na uitvoering door `success`, `failure` of `error`.

De runner gebruikt de normale netwerkverbinding van die host. Als YouTube ook daar toegang blokkeert, wordt dat eerlijk als `access_blocked` gerapporteerd. Warnings van yt-dlp worden niet onderdrukt, zodat een anti-botmelding niet stil als `skipped_no_captions` kan worden geïnterpreteerd.

## Request

```json
{
  "enabled": true,
  "request_id": "example-video-001",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "language": "auto"
}
```

Alle andere requestvelden worden geweigerd. Daarmee kan oude comments/search/ranking-configuratie niet stil terugkomen.

## Queue

Operationele requests worden append-only toegevoegd op branch `runtime-requests` als:

`requests/queue/<request_id>.json`

De bestandsnaam moet exact gelijk zijn aan `request_id`. De queuecommit mag precies één nieuw requestbestand toevoegen en niets anders. De self-hosted runner voert nooit code vanaf de transportbranch uit; hij checkt uitsluitend `Yolol100/transcriberen@main` uit.

## Snelle herkenning en cache

Succesvolle transcripties worden op de trusted execution host persistent bijgehouden in een lokale SQLite-index. De sleutel is `video_id + requested_language`.

Bij iedere nieuwe request gebeurt eerst een cachecontrole:

- bestaat dezelfde video + taal al met een gevalideerd succesvol transcript, dan wordt dat transcript direct hergebruikt en wordt YouTube niet opnieuw bevraagd;
- klopt de opgeslagen transcript-SHA of lengte niet meer, dan wordt de corrupte cache-entry verwijderd en vindt een normale nieuwe acquisitie plaats;
- de persistente database blijft hoststate en wordt nooit naar `main` gecommit.

Standaard staat de database in:

`~/.local/share/webactueel-transcribe/history.sqlite3`

Via `TRANSCRIBE_STATE_DIR` kan een andere state-directory worden gekozen.

Iedere run exporteert daarnaast `results/processed-index.json`. Die bevat onder meer:

- `unique_videos` — aantal unieke video-ID's;
- `processed_entries` — aantal unieke video/taal-combinaties;
- `captions_done` — aantal entries met een succesvol transcript;
- `status_counts` — aantallen per runtime-status;
- `items` — alle bekende video-ID's met status, taal, captionmetadata, hashes en verwerkingstijdstippen.

Transcripttekst zelf staat niet in `processed-index.json`.

## Output

Iedere run maakt:

- `results/result.json`
- `results/processed-index.json`
- `results/SHA256SUMS.txt`
- `results/transcript.txt` alleen bij status `ok`

`result.json` bevat bij de cache-route ook `cache_hit: true`; bij een verse acquisitie wordt `cache_hit: false` vastgelegd.

Mogelijke statussen:

- `ok` — ondertiteling opgehaald of uit de gevalideerde lokale cache hergebruikt en genormaliseerd;
- `skipped_no_captions` — bron heeft aantoonbaar geen bruikbare captiontrack; bewust overgeslagen;
- `access_blocked` — YouTube blokkeert de acquisitieverbinding;
- `error` — andere extractie- of validatiefout.

Ruwe yt-dlp-metadata wordt niet opgeslagen. Media wordt nooit gedownload. Resultaten leggen de werkelijk gebruikte yt-dlp- en Deno-versies vast; de validator weigert toolversiedrift.

## Toolchain

De capability is gepind op:

- yt-dlp nightly `2026.08.20.234504`;
- Deno `2.9.5`.

`scripts/install_tools.sh` accepteert een reeds aanwezige exact passende binary. Als die ontbreekt of een andere versie heeft, haalt het script uitsluitend de gepinde GitHub-release op en controleert de vastgelegde SHA-256 vóór installatie. yt-dlp wordt daarna altijd via een lokale wrapper gestart met Deno expliciet als `--js-runtimes` runtime.

## Lokaal uitvoeren

Vereisten: Linux x86_64 of WSL2/Ubuntu, Python 3.12+, `curl` en GNU `sha256sum`. yt-dlp en Deno hoeven niet vooraf geïnstalleerd te zijn; de bootstrap regelt de exact gepinde versies wanneer nodig.

```bash
bash scripts/run_local.sh requests/transcribe.json
```

De lokale route gebruikt dezelfde resolver, toolbootstrap, cachecontrole, captionruntime, history-export en resultaatvalidator als de self-hosted GitHub Actions-route. Na afloop worden ook `cache_hit`, `captions_done` en `processed_entries` getoond.

Zie `docs/SELF-HOSTED-RUNNER.md` voor de dedicated runner.

## Licentie

Deze repository bevat momenteel geen open-sourcelicentie. Hergebruik, distributie of afgeleide werken zijn niet toegestaan zonder expliciete toestemming van de rechthebbende.
