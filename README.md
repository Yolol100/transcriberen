# ZIP Corpus Review

**Doel:** bestaande transcripties en opgeslagen reacties uit een aangeleverd ZIP-bestand beoordelen. Geen live YouTube-acquisitie, API-key, nieuwe provider of automatische bronwijzigingen.

## Stap 1 — bereid een ZIP voor

Accepteert een ZIP met records.jsonl (elk record bevat video_id, title, channel, transcript, comments) of het bestaande Webactueel-master/shardpakket. Voor het huidige Library-corpus geldt: de masterindex alleen is niet genoeg, alle 15 shard-ZIP's zijn vereist. Het huidige manifest omvat 18.875 video's.

Voer een lokale broncontrole uit:

    python scripts/intake.py --zip /private/input/YouTube_Kennisbron_Bundle.zip --out /private/validated --master-sha256 <PINNED_MASTER_SHA256>

Bij een generieke ZIP zonder master vervalt de optie --master-sha256. Deze controle leest geen YouTube-pagina's.

## Stap 2 — GitHub verwerkt per 500 video's

De workflow .github/workflows/review.yml gebruikt een **PRIVATE** repository en een daarin bewust door de eigenaar aangemaakte private GitHub Release met precies het asset YouTube_Kennisbron_Bundle.zip. Vul de tag, SHA256 van de complete ZIP, eventuele master SHA256, batch 1 en scope inventory in. Daarna scope batch om de maximaal 500 video's te verwerken in 20-video-slices met vier parallelle workers. Voor 18.875 video's zijn dit 38 batches; batch 38 bevat 375 video's.

De lokale Qwen3-inferentie draait op GitHub-hosted runners en gebruikt uitsluitend verifieerbare gepinde model-/runtime-downloads. Er wordt geen YouTube-netwerkacquisitie uitgevoerd. Alle aanwezige transcript- en commentchunks worden verwerkt; ontbrekende en gedeeltelijke bronnen blijven expliciet.

**BELANGRIJK:** deze repository is op dit moment openbaar. De workflow weigert daarom productie-invoer. Zet de repository eerst bewust op private en upload alleen materiaal dat je daar mag verwerken. Een bestand in een ChatGPT-gesprek verschijnt niet automatisch in GitHub. Zonder expliciete private overdracht kan GitHub die ZIP niet lezen. Het uploaden van deze content naar een publieke Release of broncode is geen aanvaardbare omweg.

## Stap 3 — voorstellen, geen automatische wijzigingen

Elke analysetaak produceert inventory.json, brongebonden JSON per video, een phase-4-claimledger en comparison.json. Claims blijven evidence-only. Aanvankelijke classificatie is NEEDS_VERIFICATION; ALREADY_COVERED is slechts een lexicale matchesuggestie wanneer je actuele bronbestanden meegeeft. UPDATE/REJECTED vereisen inhoudelijke toetsing. De juiste Webactueel-vakowner verifieert huidige Google Drive-projectbronnen, actuele officiële bronnen en de betreffende Skill voordat een aanpassing wordt toegestaan.

Je kunt een bronvergelijking offline uitvoeren met:

    python scripts/compare.py --ledger /private/review/ledger.json --sources /private/Webactueel_Sources.zip --out /private/review/comparison.json

De bronnen-ZIP bestaat uitsluitend uit relevante .md, .txt of .json bestanden. Een match is geen feitelijke of actuele verificatie. Zonder bronnen-ZIP worden geen bronupdates aangenomen.

## Veiligheid en grenzen

- Alleen opgeslagen ZIP-evidence; geen YouTube-search, video/audio-download of captionprovider.
- ZIP-fail-closed op veilige paden, master- en shard-SHA, records en duplicaten; geen stille truncatie.
- Bestaande bronbeperkingen, onbekende data en ontbrekende comments blijven zichtbaar.
- Geen automatische promotie van claims naar Project, Skill, Memory of websites.
- Geen ruwe transcripties committen of als openbaar Actions-artifact publiceren.
- CI-test: python -m unittest discover -s tests -p 'test_*.py' -v.

Historische code is niet de actuele werking van main. De oude commit 48f5ca180c5571b5decf6de011cad687f3f57001 blijft via Gitgeschiedenis herstelbaar.
