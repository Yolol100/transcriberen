# Threat model

## Te beschermen eigenschappen

1. Queue-input kan alleen één publiek YouTube-kanaal aanwijzen.
2. De runtime gebruikt alleen de `/videos`-tab; directe video/Short/playlistinput wordt geweigerd.
3. Maximaal 1000 entries worden geïnspecteerd en alleen exacte uploaddata uit 2026 komen in het corpus.
4. Comments zijn begrensd tot 7 top-level items, YouTube-side `top` gesorteerd, zonder replies.
5. Een ontbrekende captiontrack is een schone per-video skip en activeert geen audiofallback.
6. De self-hosted host voert nooit onbetrouwbare code vanaf de transportbranch uit.
7. De runtime gebruikt of bewaart geen YouTube-media, credentials of sessiestaat.
8. Captioncache mag alleen gevalideerde transcripttekst/minimale technische status bewaren en blijft buiten `main`.
9. Comments/transcripts worden nooit automatisch project- of Skillwaarheid.

## Trust boundaries

- **Onbetrouwbaar:** queue-JSON, publieke YouTube/yt-dlp-responses en publieke comments.
- **Vertrouwd:** runtimecode op `main`, gepinde GitHub Actions, exact gecontroleerde yt-dlp/Deno-versies, dedicated runnerconfiguratie en lokale SQLite-cache.
- **Extern beheer:** runnerregistratie, runnerhost-isolatie en GitHub Rulesets/branch protection.

## Belangrijkste risico’s en beheersing

- **Onverwachte requestfunctionaliteit:** onbekende JSON-velden worden fail-closed geweigerd; limieten zijn niet user-configurable.
- **Transportbranch-code execution:** self-hosted checkt alleen `Yolol100/transcriberen@main` uit.
- **Credential/session leakage:** geen cookies, login, browserprofielen of proxy-erfenis.
- **Media-extractie:** alle acquisitieroutes gebruiken `--skip-download`; validator weigert media-artifacts.
- **Verkeerd jaar:** ieder manifestitem moet `upload_date` in 2026 hebben; validator controleert dit opnieuw.
- **Comment-explosie:** yt-dlp wordt begrensd met `max_comments=7,7,0,0,0`; runtime filtert replies nogmaals en validator handhaaft maximaal 7.
- **Geen captions:** per video `skipped_no_captions`, zonder audiofallback.
- **YouTube anti-bot/rate limiting:** `access_blocked`; geen bypassroute.
- **Cache-integriteit:** alleen overeenkomende transcript-SHA en lengte worden hergebruikt; corruptie invalidereert de entry.
- **Onverwachte output:** validator controleert manifest, progress, ZIP-structuur en verboden mediaextensies.

## Niet opgelost door repositorycode

Een persistent self-hosted systeem is niet automatisch een schone ephemeral VM. De host moet dedicated blijven. Runner enrollment/removal en branch/ruleset enforcement blijven repository-administratieverantwoordelijkheden. De hostbeheerder blijft verantwoordelijk voor back-up, toegangsrechten en schijfbescherming van de lokale captioncache.
