# Webactueel Transcriberen Runtime

Accountloze controlled-runtime voor `project-transcriberen`. De repository is een uitvoeringscapability; `webactueel-workflow` blijft domeinowner en bepaalt bronselectie, gebruiksrechten, kwaliteit, promotie en bronwrites.

## Doel

De runtime verzamelt en normaliseert publieke broninhoud zonder account, API-key of MCP-server:

- publieke video/audio en beschikbare ondertitels via `yt-dlp`;
- audio-normalisatie en metadata via `ffmpeg`/`ffprobe`;
- lokale speech-to-text fallback via `whisper.cpp`;
- artikelen en pagina's via `Trafilatura`;
- RSS/Atom- en sitemap-linkdiscovery via `Trafilatura`;
- SHA-256, toolversies en bronprovenance in ieder resultaat.

## Harde grenzen

- Alleen expliciete publieke `http://`/`https://` bronnen.
- Geen cookies, login, credentials, DRM-bypass, betaalmuur-bypass of private netwerkdoelen.
- Geen broninhoud automatisch promoveren tot projectwaarheid.
- Controleer hergebruik-/publicatierechten vóór tekst, audio of media buiten de analysecontext wordt gekopieerd of gebundeld.
- Een transcript is een transformatie van bronmateriaal en kan fouten bevatten; bewaar bron- en transformatieprovenance.

## Toolchain

- `yt-dlp` 2026.07.04, officiële Unix zipimport binary, met ingebouwde EJS-component.
- Node.js 22.23.2 als JavaScript-runtime voor yt-dlp EJS.
- FFmpeg/ffprobe uit de GitHub-hosted Ubuntu runtime.
- `whisper.cpp` v1.8.6, lokaal gebouwd; standaardmodel `base`.
- Trafilatura 2.1.0 voor artikeltekst, feeds en sitemaps.

`yt-dlp` wordt met een vastgelegde SHA-256 gecontroleerd. `whisper.cpp` wordt vanaf de vaste release-tag gebouwd. Grote Whisper-modellen en bronmedia worden nooit in Git gecommit.

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
  "whisper_model": "base"
}
```

Ondersteunde `mode`-waarden: `auto`, `media`, `article`, `feed`, `sitemap`.

De workflow uploadt `transcription-result` met genormaliseerde tekst/links, metadata, checksums en een machineleesbaar `result.json`. Ruwe gedownloade media worden niet als artifact bewaard.

## Bewijsniveau

Repo-uitvoer is maximaal `controlled_runtime`. De runtime bewijst dat de opgegeven publieke bron met de geregistreerde toolchain is verwerkt. Hij bewijst niet dat de transcriptie semantisch foutloos is, dat herpublicatie juridisch is toegestaan of dat de uitkomst al projectwaarheid is.
