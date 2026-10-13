# Transcriberen — ZIP naar kennisvoorstellen

**Gewenste ervaring:** upload één ZIP in ChatGPT of wijs een ZIP in de Library aan. De publieke repository verwerkt de reeds opgeslagen transcripties en reacties per 500 video's; ChatGPT geeft onderbouwde verbeterkandidaten terug voor Webactueel-bronnen en Skills.

## Wat nu bewezen werkt

- ZIP-validatie, inclusief de masterindex met 15 shards.
- Bestaande GitHub-hosted lokale Qwen3-analyse, 500-video-batches met 20-video-slices, evidence-only claims en synthetische CI-tests.
- GitHub geeft **geen** automatische toestemming om canonieke bronnen of Skills te wijzigen.

## Wat nog niet end-to-end werkt

**De repository blijft public.** De huidige `.github/workflows/review.yml` is een oude *private-repository-only* invoerroute. Ze vereist een ZIP als GitHub Release en weigert te draaien op een publieke repository. Maak ruwe transcript- of comment-ZIP's nooit openbaar om dat te omzeilen.

De bestaande ChatGPT GitHub-koppeling kan code en kleine tekstverzoeken schrijven en runresultaten lezen, maar **niet** een grote binaire ZIP rechtstreeks veilig naar GitHub Actions uploaden of een dispatch starten. Deze externe overdracht is dus `BLOCKED_TRANSPORT`.

De beoogde brug is: **ChatGPT-upload → private bronopslag → GitHub Actions met kortlevende, doelgebonden OIDC-toegang → volledige batches → private detailresultaten → ChatGPT-rapport**. Eerst moeten de private opslag/identiteit en het retourkanaal aantoonbaar verbonden zijn. Alleen daarna mag de public-gate veilig worden vervangen.

## Bediening na die eenmalige verbinding

1. Upload een ZIP of verwijs naar de Library-versie.
2. Vraag: **'Analyseer deze ZIP voor verbeteringen in Webactueel-bronnen en Skills.'**
3. Ontvang per betrokken Skill: `UPDATE`, `ALREADY_COVERED`, `REJECTED` of `NEEDS_VERIFICATION`, inclusief controleerbaar bewijs en ontbrekende verificatie.

**Geen online YouTube-acquisitie, geen 38 handmatige batchstarts, geen automatische kennisupdates.**

## Huidige technische tests

`python -m unittest discover -s tests -p 'test_*.py' -v`

[Ontwerp- en bevoegdheidsgrens](docs/CHATGPT_HANDOFF.md). De workflow bevat nog geen werkende ChatGPT→GitHub ZIP-overdracht. Groene tests zijn geen bewijs van een voltooide corpusrun.
