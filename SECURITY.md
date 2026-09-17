# Security

## Scope

De runtime verwerkt uitsluitend een publieke YouTube-kanaal-URL, normaliseert die naar `/videos`, inspecteert maximaal 1000 entries en neemt alleen video’s met exacte `upload_date` in 2026 op. Per gematchte video wordt maximaal één publieke captiontrack en maximaal 7 top-level `top`-comments verwerkt.

## Harde grenzen

- geen directe video-, Short- of playlistinput;
- geen cookies of ingelogde sessies;
- geen browserprofielen of persoonlijke credentials;
- geen proxyconfiguratie;
- geen CAPTCHA- of PO-token-bypass;
- geen media-download;
- geen FFmpeg of Whisper;
- geen comment replies;
- geen project-/Skillpromotie vanuit deze runtime.

Het requestcontract accepteert alleen `enabled`, `request_id`, `url` en `language`. Jaar, 1000-limiet, top-7 en no-replies zijn vaste runtimepolicy en kunnen niet door queue-input worden verruimd.

## Self-hosted runner

De YouTube-acquisitie draait uitsluitend op een dedicated Linux x64 runner met label `webactueel-transcribe`, of lokaal via `scripts/run_local.sh`. De GitHub-hosted job valideert alleen het append-only queue-request.

De self-hosted job:

- checkt uitsluitend vertrouwde runtimecode vanaf `main` uit;
- gebruikt `persist-credentials: false`;
- controleert runner environment/OS/architectuur vóór acquisitie;
- verwijdert proxy-omgevingsvariabelen vóór acquisitie;
- hoort op een dedicated host zonder persoonlijke browserprofielen, SSH/cloudcredentials of projectsecrets te draaien.

## Uitvoer en integriteit

- yt-dlp gebruikt `--skip-download` en `--no-cookies`;
- de validator weigert bekende media-extensies;
- alleen 2026-items mogen in `manifest.json` staan;
- commentbestanden mogen nooit meer dan 7 comments bevatten en replies blijven uitgesloten;
- ZIP-paden worden begrensd en het archief moet manifest/result/progress bevatten;
- captioncache wordt alleen hergebruikt na SHA- en lengtecontrole;
- comments worden per run opnieuw opgehaald en niet als duurzame waarheid gecachet;
- resultaten krijgen SHA256SUMS en een GitHub attestation.

Een YouTube anti-bot- of rate-limitblokkade wordt `access_blocked`; de runtime probeert die niet te omzeilen.
