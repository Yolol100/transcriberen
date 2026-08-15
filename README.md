# Webactueel Transcriberen Runtime

Accountloze controlled-runtime voor `project-transcriberen`. De repository is een uitvoeringscapability; `webactueel-workflow` blijft domeinowner en bepaalt bronselectie, gebruiksrechten, kwaliteit, promotie en bronwrites.

## Doel

De runtime verzamelt en normaliseert toegestane broninhoud zonder nieuw account, API-key of MCP-server:

- publieke video-/mediabronnen en beschikbare ondertitels/metadata via `yt-dlp`;
- **publieke YouTube uitsluitend via captions en metadata; nooit audio/video-download**;
- audio-normalisatie via `ffmpeg`/`ffprobe` en lokale speech-to-text via `whisper.cpp` alleen voor expliciet geautoriseerde niet-YouTube-audio;
- artikelen en pagina's via `Trafilatura`;
- RSS/Atom- en sitemap-linkdiscovery met de lokale Python/Trafilatura-laag;
- SHA-256, toolversies, fetchmoment en transformatieprovenance in ieder resultaat.

## Harde grenzen

- Alleen expliciete publieke `http://`/`https://` bronnen; private, loopback, link-local en credentialed URLs worden geweigerd.
- Geen cookies, login, credentials, DRM-bypass, betaalmuur-bypass, CAPTCHA-/age-control-bypass of private netwerkdoelen.
- Publieke YouTube-bronnen zijn captions/metadata-only. Als geen bruikbare publieke captions beschikbaar zijn, stopt de runtime; Whisper is daar geen fallback.
- `allow_audio_fallback=true` vereist óók `audio_access_authorized=true` én een concrete `rights_basis` die de audio-toegang/transcriptie dekt.
- Geen broninhoud automatisch promoveren tot projectwaarheid.
- `reuse_allowed` en `rights_basis` zijn expliciete requestvelden. Zonder hergebruiktoestemming bevat het artifact alleen provenance/metadata en een inhoudshash, niet de geëxtraheerde tekst.
- Een transcript is een transformatie van bronmateriaal en kan fouten bevatten; bron- en transformatieprovenance blijft daarom onderdeel van het resultaat.

## Toolchain

- `yt-dlp` 2026.07.04, officiële immutable releasebinary; SHA-256 wordt vóór gebruik gecontroleerd.
- Node 22.23.2 als lokale EJS-runtime voor yt-dlp; geen remote EJS-componentdownload.
- FFmpeg/ffprobe uit de GitHub-hosted Ubuntu runtime; de werkelijk gebruikte versie wordt in het resultaat vastgelegd.
- `whisper.cpp` v1.9.2, officiële Ubuntu x64 releasebinary; SHA-256 wordt gecontroleerd.
- Whisper `base` model vanaf een vaste Hugging Face-revisie; SHA-256 wordt gecontroleerd. Het model wordt alleen opgehaald als geautoriseerde audiofallback expliciet aan staat.
- Trafilatura 2.1.0 voor artikeltekst en webcontentextractie.

Grote Whisper-modellen, ruwe media en gedownloade bronbestanden worden nooit in Git gecommit.

## Gebruik via ChatGPT/GitHub

De normale Chat-route schrijft alleen `requests/transcribe.json`. Een wijziging van dat bestand start `.github/workflows/transcribe.yml`.

Minimaal request:

```json
{
  "enabled": true,
  "request_id": "transcribe-voorbeeld-001",
  "owner": "webactueel-workflow",
  "project_id": "project-transcriberen",
  "url": "https://example.com/public-source",
  "mode": "auto",
  "language": "nl",
  "allow_audio_fallback": false,
  "audio_access_authorized": false,
  "reuse_allowed": false,
  "rights_basis": "analysis-only"
}
```

Ondersteunde `mode`-waarden: `auto`, `media`, `article`, `feed`, `sitemap`.

De workflow uploadt `transcription-result-<request_id>` met `result.json`, toolversies en alleen wanneer `reuse_allowed=true` een genormaliseerd `content.md`. Ruwe media worden nooit als artifact bewaard.

## Bewijsniveau

Repo-uitvoer is maximaal `controlled_runtime`. De runtime bewijst dat de opgegeven bron met de geregistreerde toolchain en requestgates is verwerkt. Hij bewijst niet dat de transcriptie semantisch foutloos is, dat herpublicatie juridisch is toegestaan of dat de uitkomst al projectwaarheid is.
