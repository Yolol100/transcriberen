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

## Nieuwe, strikt afgebakende review-capability

`knowledge-analysis-contract.json` definieert uitsluitend een aanvullende read-only evidence-analyse van vooraf bestaande archieven op GitHub-hosted Actions. Het oorspronkelijke kanaal-2026-/1000-input-/top-7-beleid blijft van toepassing op **nieuwe netwerk-acquisitie**, niet op historische corpusonderzoeken.

| Risico | Maatregel / bewijsgrens |
| --- | --- |
| Prompt injection in captions/comments | Broninhoud is uitsluitend data; instructies afkomstig uit de bron mogen nooit toolactie of promotie starten |
| Modelgewichten/binary supply chain | Gepinde download-URL's, SHA-256 voor beiden, fail-closed bij download- of digestfout; lokaal loopbackmodel |
| Onbedoelde externe data-uitstroom | Alleen localhost-inferentie; geen OpenAI/GitHub Models/derde AI-API of gebruiker-provided secret |
| ZIP-slip, compressiebom, enorme JSONL | Weigering van onveilige ZIP-members, streaminglimiet op geneste BZ2-expansie, maximumrecordgrootte en intakecount |
| Historische transcriptlengte | Alleen de afzonderlijke archiefanalyse accepteert maximaal 3.000.000 UTF-8-bytes per video; nooit afkappen; afwijking wordt geblokkeerd. De netwerkacquisitie in `toolkit-contract.json` blijft onveranderd |
| Onbetrouwbare eerdere review-artifacts | Hervatten vereist `workflow_dispatch` op de exacte huidige `main`-commit; de model- en source-checkpoints worden per chunk, commentstatus, citaten en metadata opnieuw gevalideerd |

| Onvolledige oorspronkelijke kanaalrun | Bronreceipt blijft `partial`/`access_blocked` met unresolved/video-aantallen, nooit groen afgeleid van alleen aanwezige bestanden |
| Stale of vreemde hervatbestanden | Filter op exacte geselecteerde video-ID's; bron-/comments-/transcript-/model-/policyhash vereist voor veilig hergebruik |
| Hallucinaties, creatorreclame, onjuiste bronidentiteit | Strikte beperkte JSON, echte exacte citaatankers, leeftijd/provenance en onzekerheid; menselijke controle van elke materiele bronupdate |
| Auteursrechten/privacy in publieke repository | Geen volledige historische Library-corpus op main; geen automatisch publiceren van release-assets; compact artefact met korte gecontroleerde evidencecitaten |
| Verwarring tussen AI-scan en afgeronde inhoudsaudit | `ai_reviewed_pending_independent_verification` is alleen modelreview. Geen claim van onafhankelijke bronverificatie, QA of beleidsactivatie |

Alle afzonderlijke risico's worden bewaakt door `scripts/doctor.py`, `tests/test_knowledge_analysis.py`, `tests/test_doctor.py` en de bestaande GitHub-CI.
