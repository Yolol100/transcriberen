# Threat model

## Te beschermen eigenschappen

1. Queue-input kan alleen een publiek YouTube-kanaal aanwijzen.
2. De runtime gebruikt alleen de `/videos`-tab; directe video/Short/playlistinput wordt geweigerd.
3. Maximaal 1000 entries worden geinspecteerd en alleen bewezen uploaddata uit 2026 komen in het corpus.
4. Comments zijn begrensd tot 7 top-level items, YouTube-side `top` gesorteerd, zonder replies.
5. Een ontbrekende captiontrack is een schone per-video skip en activeert geen audiofallback.
6. Metadata die het jaar niet kan bewijzen wordt niet stil overgeslagen maar als `unresolved` opgenomen.
7. Resolve, GitHub-hosted acquisitie en eventuele self-hosted fallback voeren exact dezelfde vertrouwde runtime-SHA uit.
8. Alleen expliciete `access_blocked`-evidence mag de self-hosted fallback activeren; generieke fouten niet.
9. De runtime gebruikt of bewaart geen YouTube-media, credentials of sessiestaat.
10. Captioncache mag alleen gevalideerde transcripttekst/minimale technische status bewaren en blijft buiten `main`.
11. `processed-index.json` mag uitsluitend current-run entries bevatten en geen historische cachedata van andere kanalen.
12. Comments/transcripts worden nooit automatisch project- of Skillwaarheid.

## Trust boundaries

- **Onbetrouwbaar:** queue-JSON, publieke YouTube/yt-dlp-responses en publieke comments.
- **Vertrouwd:** runtimecode op de vastgelegde commit-SHA, gepinde GitHub Actions, exact gecontroleerde yt-dlp/Deno-versies en resultaatvalidator/classifier.
- **Conditioneel vertrouwd:** GitHub-hosted ephemeral runner voor eerste acquisitiepoging; dedicated self-hosted runner en lokale SQLite-cache voor fallback/persistente cache.
- **Extern beheer:** runnerregistratie, runnerhost-isolatie en GitHub Rulesets/branch protection.

## Belangrijkste risico's en beheersing

- **Onverwachte requestfunctionaliteit:** onbekende JSON-velden worden fail-closed geweigerd; limieten zijn niet user-configurable.
- **Transportbranch-code execution / TOCTOU op main:** resolve legt de runtime-SHA vast; hosted attempt en fallback checken exact die SHA uit en vergelijken readback voor acquisitie.
- **Onnodige self-hosted execution:** fallback vereist gevalideerde `access_blocked`-evidence uit discovery, metadata, captions of comments; gewone `error`-statussen triggeren niet automatisch.
- **Credential/session leakage:** geen cookies, login, browserprofielen of proxy-erfenis.
- **Media-extractie:** alle acquisitieroutes gebruiken `--skip-download`; validator weigert media-artifacts.
- **Verkeerd jaar:** ieder manifestitem moet `upload_date` in 2026 hebben; ontbrekende metadata blijft `unresolved`; validator controleert reconciliatie.
- **Comment-explosie:** yt-dlp gebruikt `max_comments=7,7,0,0,1`; `max-depth=1` sluit replies uit; runtime filtert replies opnieuw en validator handhaaft maximaal 7.
- **Vals volledig resultaat:** metadata-, caption- of commentonvolledigheid forceert `partial`; validator weigert `ok` bij incomplete counts.
- **Geen captions:** per video `skipped_no_captions`, zonder audiofallback.
- **YouTube anti-bot/rate limiting:** `access_blocked`; GitHub-hosted blokkade mag naar normale self-hosted direct-network fallback, maar er is geen bypassroute.
- **Cache-integriteit:** alleen overeenkomende transcript-SHA en lengte worden op self-hosted/local hergebruikt; corruptie invalidereert de entry.
- **Cross-run cache leakage:** indexexport krijgt de expliciete current-run keyset; validator vereist exact dezelfde video-id set als het manifest.
- **Onverwachte output:** validator controleert manifest, progress, current-run index, ZIP-structuur en verboden mediaextensies.

## Niet opgelost door repositorycode

Een persistent self-hosted systeem is niet automatisch een schone ephemeral VM. De fallbackhost moet dedicated blijven. Runner enrollment/removal en branch/ruleset enforcement blijven repository-administratieverantwoordelijkheden. De hostbeheerder blijft verantwoordelijk voor back-up, toegangsrechten en schijfbescherming van de lokale captioncache.
