# Security

## Scope

De runtime verwerkt uitsluitend een directe publieke YouTube-video- of Short-URL en haalt maximaal één publieke captiontrack op. De runtime downloadt geen video of audio.

## Harde grenzen

- geen cookies of ingelogde sessies;
- geen browserprofielen of persoonlijke credentials;
- geen proxyconfiguratie;
- geen CAPTCHA- of PO-token-bypass;
- geen media-download;
- geen comments, channel/search/playlist-discovery of andere bulkacquisitie;
- geen FFmpeg of Whisper.

Het requestcontract accepteert alleen `enabled`, `request_id`, `url` en `language`. Onbekende velden worden geweigerd.

## Self-hosted runner

De YouTube-acquisitie draait uitsluitend op een dedicated Linux x64 runner met label `webactueel-transcribe`, of lokaal via `scripts/run_local.sh`. De GitHub-hosted job valideert alleen het append-only queue-request.

De self-hosted job:

- checkt uitsluitend vertrouwde runtimecode vanaf `main` uit;
- gebruikt `persist-credentials: false`;
- verwijdert proxy-omgevingsvariabelen vóór acquisitie;
- hoort op een dedicated host zonder persoonlijke browserprofielen, SSH/cloudcredentials of andere projectsecrets te draaien.

## Uitvoer

Alleen minimale bron/captionprovenance en de genormaliseerde transcripttekst worden opgeslagen. Ruwe yt-dlp-metadata wordt niet gepersisteerd. De resultaatvalidator weigert onverwachte artifacts en bekende media-extensies.

Een YouTube anti-botblokkade wordt `access_blocked`; de runtime probeert die niet te omzeilen met cookies, login, proxying of mediafallback.
