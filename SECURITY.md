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

## GitHub-hosted runnergrens

De production queue gebruikt uitsluitend GitHub-hosted `ubuntu-24.04`. Er is geen custom runner, machinefallback of netwerkbypass.

Voor remote acquisitie geldt:

- exact dezelfde vertrouwde runtime-SHA als de resolve-job heeft vastgelegd;
- nooit runtimecode vanaf de transportbranch uitvoeren;
- `persist-credentials: false` gebruiken;
- proxy-omgevingsvariabelen voor acquisitie verwijderen;
- geen cookies, accounts, browserprofielen of andere YouTube-credentials gebruiken;
- metadata, captions en comments proberen eerst begrensde accountloze InnerTube/timedtext-providers en vallen alleen terug op de gepinde yt-dlp toolchain;
- expliciete `access_blocked`-evidence is terminaal, wordt als evidence opgeslagen en veroorzaakt een gefaalde run.

## Uitvoer en integriteit

- yt-dlp gebruikt `--skip-download` en `--no-cookies`;
- no-replies wordt provider-onafhankelijk afgedwongen en nogmaals runtime-gefilterd;
- de validator weigert bekende media-extensies;
- alleen bewezen 2026-items mogen in `manifest.json` staan;
- metadatafouten worden als `unresolved` bewaard in plaats van stil overgeslagen;
- commentbestanden mogen nooit meer dan 7 comments bevatten;
- ontbrekende comments/captionfouten/metadatafouten maken de run `partial` in plaats van vals `ok`;
- ZIP-paden worden begrensd en het archief moet manifest/result/progress/index bevatten;
- lokale parity-cache wordt alleen hergebruikt na SHA- en lengtecontrole;
- `processed-index.json` bevat alleen current-run entries en lekt geen oude cachehistorie uit andere runs;
- comments worden per run opnieuw opgehaald en niet als duurzame waarheid gecachet;
- finale resultaten krijgen SHA256SUMS en een GitHub attestation;
- parallelle acquisitie is begrensd tot 7 workers en wordt in batches van maximaal 7 gestart;
- na expliciete `access_blocked`-evidence start de runtime geen volgende batch met nieuwe YouTube-netwerkacquisitie.

Een YouTube anti-bot- of rate-limitblokkade wordt `access_blocked`. De runtime probeert die niet te omzeilen en schakelt niet over naar een andere host.
