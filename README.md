# Webactueel Transcriberen Runtime

Accountloze controlled-runtime voor `project-transcriberen`. De repository is de uitvoeringscapability; `webactueel-workflow` blijft domeinowner en bepaalt bronselectie, gebruiksrechten, kwaliteit, promotie en bronwrites.

## Doel

De runtime verzamelt en normaliseert toegestane broninhoud zonder nieuw account, API-key, OAuth, MCP/MQTT-server of externe transcriptdienst:

- publieke losse video-/mediabronnen en beschikbare ondertitels/metadata via `yt-dlp`;
- publieke YouTube-kanalen en playlists, inclusief kanaal-tabs `videos`, `shorts` en `streams`;
- **publieke YouTube uitsluitend via captions en metadata; nooit audio/video-download**;
- audio-normalisatie via `ffmpeg`/`ffprobe` en lokale speech-to-text via `whisper.cpp` alleen voor expliciet geautoriseerde niet-YouTube-audio;
- artikelen en pagina's via Trafilatura;
- RSS/Atom- en sitemap-linkdiscovery met de lokale Python/Trafilatura-laag;
- SHA-256, toolversies, fetchmoment en transformatieprovenance in ieder resultaat.

## Harde grenzen

- Alleen expliciete publieke `http://`/`https://` bronnen; private, loopback, link-local en credentialed URLs worden geweigerd.
- Geen cookies, login, credentials, DRM-bypass, betaalmuur-bypass, CAPTCHA-/age-control-bypass, proxy-fallback of private netwerkdoelen.
- Publieke YouTube-bronnen zijn captions/metadata-only. Een losse video zonder bereikbare captions faalt gecontroleerd; in een kanaal/playlist wordt echte captionafwezigheid `no_usable_captions`, terwijl een bot-/loginchallenge of technische toegangsblokkade apart als `caption_access_error` wordt geregistreerd.
- YouTube kan gedeelde cloud-IP's een bot-/loginchallenge geven voordat captions bereikbaar zijn. De repo omzeilt die niet en claimt dan geen transcript.
- `allow_audio_fallback=true` vereist óók `audio_access_authorized=true` én een concrete `rights_basis` die de audio-toegang/transcriptie dekt.
- Geen broninhoud automatisch promoveren tot projectwaarheid of rechtstreeks naar een Skill schrijven.
- `reuse_allowed` en `rights_basis` zijn expliciete requestvelden. `content.md` wordt alleen bewaard wanneer hergebruik is toegestaan én daadwerkelijk captions zijn verzameld.
- Een transcript is een transformatie van bronmateriaal en kan fouten bevatten; bron- en transformatieprovenance blijft daarom onderdeel van het resultaat.

## YouTube-collecties

Een kanaalroot (`/@handle`, `/channel/...`, `/c/...`, `/user/...`) wordt onderzocht via `/videos`, `/shorts` en `/streams`. Video-ID's worden gededupliceerd. Een playlist (`?list=...`) wordt als één collectie verwerkt.

- `max_items=0`: volledige gevonden collectie tot de harde veiligheidslimiet van 10.000 video's;
- `max_items=1..5000`: begrensde scan;
- iedere gevonden video wordt afzonderlijk op publiek bereikbare handmatige/automatische captions gecontroleerd;
- `no_usable_captions`: de captionroute draaide, maar leverde geen bruikbare track;
- `caption_access_error`: YouTube/tooling kon captionbeschikbaarheid niet betrouwbaar bepalen, bijvoorbeeld door een bot-/loginchallenge;
- `processing_error`: onverwachte lokale verwerkingsfout;
- geen van deze foutstatussen activeert audio-download of Whisper voor publieke YouTube.

Zie `docs/youtube-collections.md` voor de live geteste grenzen en de handmatige GitHub-runner availability probe.

## Toolchain

- `yt-dlp` 2026.07.04, officiële immutable releasebinary; SHA-256 wordt vóór gebruik gecontroleerd.
- Deno 2.9.5 als gepinde lokale EJS-runtime voor yt-dlp; release-asset en SHA-256 zijn vastgezet.
- De officiële yt-dlp-binary bevat de benodigde EJS-scripts; remote EJS-componentdownloads zijn niet ingeschakeld.
- FFmpeg/ffprobe uit de GitHub-hosted Ubuntu runtime; de werkelijk gebruikte versie wordt in het resultaat vastgelegd.
- `whisper.cpp` v1.9.2 plus gepind `base` model alleen voor geautoriseerde niet-YouTube-audiofallback.
- Trafilatura 2.1.0 voor artikeltekst en webcontentextractie.

`bgutil-ytdlp-pot-provider` en `youtube-transcript-api` zijn bewust geen vaste dependencies. De lokale bgutil/Deno-provider is live getest maar hief de GitHub-hosted YouTube-botchallenge niet op; transcript-API-routes lossen dezelfde cloud-IP-afhankelijkheid niet betrouwbaar op zonder infrastructuur die buiten de repo-eisen valt.

## Request

De normale Chat-/GitHub-route schrijft `requests/transcribe.json`. Een geldig request bevat onder meer:

```json
{
  "enabled": true,
  "request_id": "transcribe-voorbeeld-001",
  "owner": "webactueel-workflow",
  "project_id": "project-transcriberen",
  "url": "https://www.youtube.com/@OpenAI",
  "mode": "auto",
  "language": "nl",
  "max_items": 0,
  "allow_audio_fallback": false,
  "audio_access_authorized": false,
  "reuse_allowed": false,
  "rights_basis": "analysis-only",
  "source_context": {
    "project_id": "project-transcriberen",
    "source_set_version": "set-at-execution"
  }
}
```

Ondersteunde `mode`-waarden: `auto`, `media`, `article`, `feed`, `sitemap`.

## Uitvoer en bron-/Skill-update

De workflow uploadt `transcription-result-<request_id>` met minimaal `result.json` en toolversies. YouTube-collecties leveren daarnaast `source-register.json` en `knowledge-handoff.json`; `content.md` bestaat alleen wanneer `reuse_allowed=true` én minimaal één captiontrack succesvol is verzameld.

De repository muteert geen projectbron of Skill zelfstandig. `knowledge-handoff.json` is reviewmateriaal, geen direct uitvoerbaar updateplan. Webactueel-workflow accepteert alleen onderbouwde inzichten, dedupliceert/parafraseert ze, routeert ieder geaccepteerd inzicht naar precies één canonieke eigenaar en past een write alleen toe via de bestaande gecontroleerde write-route met actuele readback/hash, backup, validatie en rollback.

## Bewijsniveau

Repo-uitvoer is maximaal `controlled_runtime`. De runtime bewijst wat met de geregistreerde toolchain vanaf de actuele runner kon worden verwerkt. Hij bewijst niet dat captions vanaf ieder netwerk altijd bereikbaar zijn, dat transcriptie semantisch foutloos is, dat herpublicatie juridisch is toegestaan of dat de uitkomst al projectwaarheid is.
