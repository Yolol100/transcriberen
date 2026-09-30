# Threat model

## Te beschermen eigenschappen

1. Queue-input kan alleen een publiek YouTube-kanaal aanwijzen.
2. De runtime gebruikt alleen de `/videos`-tab; directe video/Short/playlistinput wordt geweigerd.
3. Maximaal 1000 entries worden geinspecteerd en alleen bewezen uploaddata uit 2026 komen in het corpus.
4. Comments zijn begrensd tot 7 top-level items, YouTube-side `top` gesorteerd waar beschikbaar, zonder replies.
5. Een ontbrekende captiontrack is een schone per-video skip en activeert geen audiofallback.
6. Metadata die het jaar niet kan bewijzen wordt niet stil overgeslagen maar als `unresolved` opgenomen.
7. Resolve en GitHub-hosted acquisitie voeren exact dezelfde vertrouwde runtime-SHA uit.
8. Expliciete `access_blocked`-evidence is terminaal en activeert geen alternatieve machine of bypassroute.
9. De runtime gebruikt of bewaart geen YouTube-media, credentials of sessiestaat.
10. Lokale parity-cache mag alleen gevalideerde transcripttekst/minimale technische status bewaren en blijft buiten `main`.
11. `processed-index.json` mag uitsluitend current-run entries bevatten en geen historische cachedata van andere kanalen.
12. Comments/transcripts worden nooit automatisch project- of Skillwaarheid.
13. Video-acquisitie gebruikt maximaal 7 gelijktijdig actieve workers en start geen volgende batch nadat expliciete `access_blocked`-evidence is gezien.

## Trust boundaries

- **Onbetrouwbaar:** queue-JSON, publieke YouTube/InnerTube/timedtext/yt-dlp-responses en publieke comments.
- **Vertrouwd:** runtimecode op de vastgelegde commit-SHA, gepinde GitHub Actions, exact gecontroleerde yt-dlp/Deno-versies en resultaatvalidator.
- **Conditioneel vertrouwd:** GitHub-hosted ephemeral runner voor acquisitie; lokale SQLite-cache alleen bij handmatige parity/debuguitvoering.
- **Extern beheer:** GitHub-hosted Actions-infrastructuur en GitHub Rulesets/branch protection.

## Belangrijkste risico's en beheersing

- **Onverwachte requestfunctionaliteit:** onbekende JSON-velden worden fail-closed geweigerd; limieten zijn niet user-configurable.
- **Transportbranch-code execution / TOCTOU op main:** resolve legt de runtime-SHA vast; de runtime checkt exact die SHA uit en vergelijkt readback voor acquisitie.
- **Providerdrift:** caption-first InnerTube/timedtext is aanvullend en bounded; de gepinde yt-dlp-route blijft fallback. Resultaten moeten hetzelfde validatorcontract halen.
- **Credential/session leakage:** geen cookies, login, browserprofielen of proxy-erfenis.
- **Media-extractie:** acquisitieroutes gebruiken geen media-download; validator weigert media-artifacts.
- **Verkeerd jaar:** ieder manifestitem moet `upload_date` in 2026 hebben; ontbrekende metadata blijft `unresolved`; validator controleert reconciliatie.
- **Comment-explosie:** maximaal 7 top-level comments; replies worden provider-onafhankelijk gefilterd en de validator handhaaft de limiet.
- **Vals volledig resultaat:** metadata-, caption- of commentonvolledigheid forceert `partial`; validator weigert `ok` bij incomplete counts.
- **Geen captions:** per video `skipped_no_captions`, zonder audiofallback.
- **YouTube anti-bot/rate limiting:** `access_blocked` is terminaal. Bounded batches beperken de burst tot 7 video's; na blokkade wordt geen volgende netwerkbatch gestart.
- **Cache-integriteit:** alleen overeenkomende transcript-SHA en lengte worden bij lokale parity-runs hergebruikt; corruptie invalidereert de entry.
- **Cross-run cache leakage:** indexexport krijgt de expliciete current-run keyset; validator vereist exact dezelfde video-id set als het manifest.
- **Onverwachte output:** validator controleert manifest, progress, current-run index, ZIP-structuur en verboden mediaextensies.

## Niet opgelost door repositorycode

YouTube kan publieke endpoints voor datacenter-IP's wijzigen of blokkeren. De runtime behandelt dat als een expliciete externe blokkade en voegt geen cookies, proxy, account, CAPTCHA- of tokenbypass toe. GitHub Rulesets, repositoryrechten en Actions-beleid blijven repository-administratieverantwoordelijkheden.
