# Repository agent contract

Deze repository is captions-only.

## Doel

Publieke YouTube-video of Short -> één captiontrack -> `transcript.txt`.

Geen captions -> `skipped_no_captions` en geen transcript.

## Niet uitbreiden zonder expliciete productscopewijziging

Voeg geen comments, search, channel/playlist discovery, ranking, topicfilters, engagement, knowledge-routing, artikel/feed/sitemapextractie, audio, FFmpeg, Whisper, cookies, login, proxies, CAPTCHA/PO-token-bypass of media-download toe.

## Runtime

YouTube-acquisitie draait alleen op `[self-hosted, linux, x64, webactueel-transcribe]` of lokaal met `scripts/run_local.sh`. GitHub-hosted runners mogen alleen queue-input valideren.

## Wijzigingen

- behoud het minimale requestcontract: `enabled`, `request_id`, `url`, `language`;
- behoud `--skip-download` op iedere yt-dlp-route;
- onbekende requestvelden blijven fail-closed;
- update tests en `toolkit-contract.json` bij contractwijzigingen;
- run vóór merge: Python compile, shell syntax, volledige unittest-suite en repository doctor.
