# Transcriberen — veilige YouTube-corpuscontrole en kennisvoorstellen

**Status op 16 oktober 2026:** de repository blijft publiek en is een uitvoeringslaag. `webactueel-workflow` blijft de enige controller; live Project Transcriberen is scope-/bronwaarheid en `transcribeer` is de gespecialiseerde intake. Bewaarde YouTube-tekst en comments blijven aanvullende, niet-vertrouwde evidence, nooit automatisch beleid.

## Wat is echt bewezen?

- Het Library-masterarchief **v15** bevat 18.875 unieke video-ID's en verwijst naar **15** aparte, ongewijzigde transcriptshards. De master SHA-256 is `2aa93bbe7b1db1d872c9d8614240dbbdf0f0c061e0de5c6e0e753a2954763e59`.
- Een read-only controle kan **100% van de lokaal opgeslagen video-ID's, transcriptbestanden en opgeslagen comments** valideren. Dit is **geen** 100% dekking van publiek beschikbare YouTube-comments.
- De vastgelegde bibliotheekbasis bevat **918 video's met bewaarde comments (9.828 top-level comments)** en **17.957 zonder opgeslagen comments**. Voor die laatste video's is niet bewezen dat comments ontbreken of uitstaan.
- Een eerdere [private run van 14 oktober](https://github.com/Yolol100/transcriberen/actions/runs/38496783695) blokkeerde op video 2; die timeout is opgelost. De [nieuwe echte v15-Qwen-run op main](https://github.com/Yolol100/transcriberen/actions/runs/38817420219) is **geslaagd op 15 oktober 2026**: 10/10 video's, 51 volledige bronsegmenten, 24 unieke evidence-only claimvoorstellen en 5 identieke modelduplicaten uitgesloten. Het definitieve bestand `qwen-b001-s00-10.json` is privé in Drive opgeslagen en onafhankelijk teruggelezen, met `independent_qa_complete=false` en geen automatische promotie.
- Repository Doctor, CodeQL en de synthetische Qwen-regressies blijven aparte controles. **Één succesvolle echte proef van tien video's** bewijst de werkende privé-Drive-handoff en laatste fase voor die specifieke sample, niet universele corpus-, actualiteits- of menselijke inhoudelijke goedkeuring.
- Het v15-masterbestand is onveranderd. Het bevat een actueel kanaalcataloguslabel voor 63 geverifieerde kanalen terwijl 13.764 historische video-indexrijen nog een verouderd `unverified_supplemental`-label hadden. Nieuwe runtimebeoordelingen gebruiken de geverifieerde catalogus uit **dezelfde SHA-gepinde master** (PR #84). Dit herlabelt geen reeds opgeslagen historische beoordelingen. Het kanaal Remote Career Scout en zijn 99 video's blijven ongeverifieerd.

## Kennisreview uit een bestaand Excel-transcriptonderzoek

Gebruik de [evidence-only Excel-importfilter](docs/EXCEL-INTAKE-EVIDENCE-RUBRIC.md) om automatische entiteitmatches, frameworknamen en schijnbare tegenspraken eerst te verifiëren. Een gevonden vermelding is geen bevestigde claim. Projectbronnen en Skills blijven ongewijzigd totdat de verantwoordelijke eigenaar de kennis expliciet accepteert.

## Alle 18.875 opgeslagen video's controleren

Bewaar de ZIPs **privé** en voer lokaal uit met de v15-master plus alle 15 shards in dezelfde map:

```bash
python -m scripts.audit_library_corpus \
  --master /private/corpus/YouTube_Kennisbron_Master.zip \
  --shard-dir /private/corpus \
  --output-dir /private/reports
```

Dit schrijft een compacte `coverage_summary.json` en `video_coverage.csv` met per video expliciet **bewaarde commentdekking** en **onbekende live commentbeschikbaarheid**. Het script gebruikt geen netwerk en publiceert geen bronbestanden of reacties in GitHub. Bij een ontbrekend shard, verkeerde hash, duplicate video-ID of commenttelfout is het resultaat `BLOCKED_INCOMPLETE`.

## Nog open / bewust geblokkeerd

- **100% live YouTube-commentcontrole is niet bewezen.** Een officiële, rechtmatig geautoriseerde provider plus geldige quota, paginering, beschikbaarheids-/privacystatus, rate limits, commentreplies en video-ID-correlatie zijn nodig. `not_stored` is geen synoniem van `comments_disabled`. Zonder bronrespons blijven die 17.957 video-ID's `not_checked`.
- **Nieuwe publieke YouTube-acquisitie** is onder het actuele live contract `BLOCKED_PROVIDER`. Deze repository is momenteel **geen** publieke YouTube-downloader. Geen cookies/login/proxy/CAPTCHA/PO-token-bypass of media-/audiofallback.
- De vroegere `.github/workflows/review.yml` vereist een private repository en is daarom niet geschikt op deze publieke repository. De rechtstreekse ChatGPT-upload van een grote ZIP naar een GitHub Actions-run blijft een aparte `BLOCKED_TRANSPORT`-route. De bewezen **GitHub OIDC → private Drive read/write** voor reeds daar aanwezige bronbestanden heft die beperking niet op.
- **De technische tien-video-Qwen-proef is geslaagd; inhoudelijke expert-/projectbronacceptatie is nog open.** Het opgeslagen resultatenbestand blijft `ai_reviewed_pending_independent_verification`. Iedere actuele platform-, security-, financiële of beleidsclaim vereist afzonderlijk officieel bronbewijs en goedkeuring door de juiste vakowner. Een onvolledige video of een bronhashconflict blijft een fout, nooit een PASS.

## Kennisvergelijking en veiligheid

Verschillen met actuele projectbronnen worden voorstellen: `UPDATE`, `ALREADY_COVERED`, `REJECTED` of `NEEDS_VERIFICATION`. Geen automatische promotie naar Skills, Drive-projectwaarheid, Memory of productiecode. Controleer alle materiële of veranderlijke claims eerst bij de vakowner en actuele primaire/officiële bronnen. GitHub/CI is alleen uitvoeringsbewijs.

Tests: `python -m unittest discover -s tests -p 'test_*.py' -v`. Zie [private handoffgrenzen](docs/CHATGPT_HANDOFF.md) voor de nog niet gerealiseerde rechtstreekse ChatGPT→GitHub-ZIP-overdracht.
