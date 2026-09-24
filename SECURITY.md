# Security

## Scope

De runtime verwerkt uitsluitend een publieke YouTube-kanaal-URL, normaliseert die naar `/videos`, inspecteert maximaal 1000 entries en neemt alleen video's met exacte `upload_date` in 2026 op. Per gematchte video wordt maximaal een publieke captiontrack en maximaal 7 top-level `top`-comments verwerkt.

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

Het requestcontract accepteert alleen `enabled`, `request_id`, `url` en `language`. Jaar, 1000-limiet, top-7, no-replies en maximaal 7 gelijktijdig actieve video's zijn vaste runtimepolicy en kunnen niet door queue-input worden verruimd.

## Hybride runnergrens

De queue probeert YouTube-acquisitie eerst op GitHub-hosted `ubuntu-24.04`. Alleen een gevalideerd resultaat met expliciete `access_blocked`-evidence mag automatisch doorvallen naar de dedicated Linux x64 runner met label `webactueel-transcribe`. Lokaal blijft `scripts/run_local.sh` ondersteund.

Voor beide remote acquisitieroutes geldt:

- exact dezelfde vertrouwde runtime-SHA als de resolve-job heeft vastgelegd;
- nooit runtimecode vanaf de transportbranch uitvoeren;
- `persist-credentials: false` gebruiken;
- proxy-omgevingsvariabelen voor acquisitie verwijderen;
- geen cookies, accounts, browserprofielen of andere YouTube-credentials gebruiken.

De self-hosted fallback controleert bovendien runner environment/OS/architectuur en hoort op een dedicated host zonder persoonlijke browserprofielen, SSH/cloudcredentials of projectsecrets te draaien.

De fallback-classifier kijkt naar kanaaldiscovery, unresolved metadata, captionstatus en commentstatus. Alleen `access_blocked` activeert fallback; generieke `error`-statussen mogen niet stil op de self-hosted host worden herhaald.

## Uitvoer en integriteit

- yt-dlp gebruikt `--skip-download` en `--no-cookies`;
- no-replies gebruikt expliciet `max-depth=1` plus runtime filtering;
- de validator weigert bekende media-extensies;
- alleen bewezen 2026-items mogen in `manifest.json` staan;
- metadatafouten worden als `unresolved` bewaard in plaats van stil overgeslagen;
- commentbestanden mogen nooit meer dan 7 comments bevatten;
- ontbrekende comments/captionfouten/metadatafouten maken de run `partial` in plaats van vals `ok`;
- ZIP-paden worden begrensd en het archief moet manifest/result/progress/index bevatten;
- captioncache op self-hosted/local wordt alleen hergebruikt na SHA- en lengtecontrole;
- `processed-index.json` bevat alleen current-run entries en lekt geen oude cachehistorie uit andere runs;
- comments worden per run opnieuw opgehaald en niet als duurzame waarheid gecachet;
- finale resultaten krijgen SHA256SUMS en een GitHub attestation;
- parallelle acquisitie is begrensd tot 7 workers en wordt in batches van maximaal 7 gestart;
- na expliciete `access_blocked`-evidence start de runtime geen volgende batch met nieuwe YouTube-netwerkacquisitie.

Een YouTube anti-bot- of rate-limitblokkade wordt `access_blocked`; de runtime probeert die niet te omzeilen. Als de GitHub-hosted poging wordt geblokkeerd, is de self-hosted run alleen een normale direct-network fallback en geen bypassmechanisme.
