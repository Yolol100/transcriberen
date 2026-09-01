# Threat model

## Te beschermen eigenschappen

1. Een queue-request mag alleen één directe publieke YouTube-video of Short aanwijzen.
2. De self-hosted host mag nooit onbetrouwbare code vanaf de transportbranch uitvoeren.
3. De runtime mag geen YouTube-media, credentials of sessiestaat gebruiken of opslaan.
4. Een ontbrekende captiontrack moet een schone skip zijn, geen aanleiding voor audiofallback.
5. Resultaten mogen alleen de minimale afgesproken artifacts bevatten.
6. De persistente captioncache mag alleen gevalideerde transcripttekst en minimale technische status bewaren en mag nooit op `main` worden gecommit.

## Trust boundaries

- **Onbetrouwbaar:** queue-JSON en alle publieke YouTube/yt-dlp-responses.
- **Vertrouwd:** runtimecode op `main`, gepinde GitHub Actions, exact gecontroleerde yt-dlp/Deno-versies, de dedicated runnerconfiguratie en de lokale SQLite-cache op die dedicated host.
- **Extern beheer:** runnerregistratie, runnerhost-isolatie en GitHub Rulesets/branch protection.

## Belangrijkste risico's en beheersing

- **Onverwachte requestfunctionaliteit:** onbekende JSON-velden worden fail-closed geweigerd.
- **Transportbranch-code execution:** de self-hosted job checkt alleen `Yolol100/transcriberen@main` uit.
- **Credential/session leakage:** geen cookies, login, browserprofielen of proxy-erfenis; persisted checkout credentials staan uit.
- **Media-extractie:** iedere yt-dlp-opdracht bevat `--skip-download`; de validator weigert media-artifacts.
- **Geen captions:** status `skipped_no_captions`, zonder transcript of fallback.
- **YouTube anti-bot/rate limiting:** status `access_blocked`; geen bypassroute.
- **Cache-integriteit:** alleen een `ok`-resultaat met overeenkomende transcript-SHA en lengte wordt als cache-hit hergebruikt; beschadigde cachedata wordt verwijderd en opnieuw opgehaald.
- **Doelspecifieke state in Git:** de SQLite-database blijft uitsluitend op de trusted execution host. `processed-index.json` is alleen run-readback en bevat geen transcripttekst.
- **Onverwachte output:** alleen `result.json`, optioneel `transcript.txt`, `processed-index.json` en `SHA256SUMS.txt` zijn toegestaan.

## Niet opgelost door repositorycode

Een persistent self-hosted systeem is niet automatisch een schone ephemeral VM. De host moet dedicated blijven en runner enrollment/removal en branch/ruleset enforcement blijven repository-administratieverantwoordelijkheden. De hostbeheerder is daarnaast verantwoordelijk voor back-up, toegangsrechten en schijfbescherming van de lokale captioncache.
