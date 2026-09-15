# Repository agent contract

Deze repository is captions-only.

## Doel

Publieke YouTube-video of Short -> één captiontrack -> `transcript.txt`.

Geen captions -> `skipped_no_captions` en geen transcript.

Daarnaast mag een reeds aangeleverd transcriptcorpus lokaal fail-closed worden gevalideerd als `evidence_only`. Die intake voert zelf geen YouTube-discovery of netwerkacquisitie uit en promoveert transcriptinhoud nooit automatisch naar project-, Skill- of geheugenwaarheid.

## Niet uitbreiden zonder expliciete productscopewijziging

Voeg geen comments, search, channel/playlist discovery, ranking, topicfilters, engagement, knowledge-routing, artikel/feed/sitemapextractie, audio, FFmpeg, Whisper, cookies, login, proxies, CAPTCHA/PO-token-bypass of media-download toe.

Een aangeleverd corpus mag alleen via de aparte `external-youtube-caption-corpus-intake` worden gecontroleerd op structuur, provenance en hashes. Houd die capability gescheiden van `toolkit-contract.json` en de directe video/Short-runtime.

## Runtime

YouTube-acquisitie draait alleen op `[self-hosted, linux, x64, webactueel-transcribe]` of lokaal met `scripts/run_local.sh`. GitHub-hosted runners mogen alleen queue-input valideren.

De external-corpus-intake is uitsluitend lokale bestandsvalidatie; zij mag geen netwerktoegang nodig hebben.

## Wijzigingen

- behoud het minimale requestcontract: `enabled`, `request_id`, `url`, `language`;
- behoud `--skip-download` op iedere yt-dlp-route;
- onbekende requestvelden blijven fail-closed;
- update tests en `toolkit-contract.json` bij wijzigingen aan de directe acquisitiecapability;
- update tests en `external-corpus-contract.json` bij wijzigingen aan de lokale corpusintake;
- run vóór merge: Python compile, shell syntax, volledige unittest-suite en repository doctor.
