# Excel-transcriptanalyse: evidence-only importfilter

**Status:** documentatievoorstel. Dit bestand introduceert geen nieuwe acquisitieroute, model, netwerkcall of automatische project-/Skill-write. Het blijft verenigbaar met `AGENTS.md`, `scripts/compare.py` en `scripts/knowledge_phase4.py`.

## Invoer en scope

Gebruik uitsluitend een al toegestaan, privaat opgeslagen Excel-onderzoek als *discovery-index*. Relevant zijn `Bronnen catalogus`, `Bronvermeldingen`, `Skillcatalogus`, `Skillbewijs`, `Frameworks`, `Frameworkbewijs` en `Tegenspraak-signalen`. Bewaar de werkboek-SHA-256, beoordelingsdatum en gebruikte tabbladen in een privaat reviewrecord. De ruwe workbook, transcripttekst en clientinformatie horen niet op de publieke default branch.

## Controle per kennisvoorstel

1. Koppel een hypothese aan een echte `video_id`, kanaal, volledige video-URL, exact fragment, bronlocatie/hash en een **geverifieerde** datum, of `unknown`.
2. Een grote trefwoordfrequentie of een tekst in een videotitel bewijst geen concrete methode. Bekijk inhoudscontext en onderscheid `mentioned`, `explained`, `demonstrated`, `endorsed` en `externally_verified`.
3. Gebruik contextuele disambiguatie: `RAG` is niet altijd retrieval-augmented generation; `clarity` is niet automatisch Microsoft Clarity; `The ONE Thing` en `Zero to One` kunnen gewone uitdrukkingen zijn. Noem geen auteur 'geciteerd' zonder expliciete citaatcontext.
4. Dedupliceer **binnen hetzelfde claimtype** op `video_id + canonieke_entiteit + claimtype`. Aliasvarianten bij dezelfde bron samenvoegen, maar geen twee verschillende producten of makers forceren onder dezelfde naam.
5. Geef de voorkeur aan herhaalde concrete demonstraties, of een enkel duidelijk voorbeeld dat onafhankelijk te toetsen is. Meerdere video's zijn geen waarheidsbewijs. Beoordeel de relevantie voor het actuele project apart.
6. Een tegenspraak vraagt twee expliciete, inhoudelijk incompatibele uitspraken van **dezelfde maker** over hetzelfde besluit en vergelijkbare voorwaarden. Verschil in jaartal, publicatieonderwerp of gebruikte tool is niet voldoende.
7. Vergelijk met de live, actieve en juiste Drive-projectbron. Leg exact vast wat er ontbreekt, inclusief bestandsnaam, passage en eigenaar. Laat `scripts/compare.py` uitsluitend wijzen op mogelijke overlap; een semantische match is geen inhoudelijke goedkeuring.

## Besluit

- `ALREADY_COVERED`: de actieve bron dekt het inzicht; geen nieuwe kennis of README-regel.
- `REJECTED`: ambigu, generiek, onjuist of buiten scope; bewaar alleen minimale reviewreden.
- `NEEDS_VERIFICATION`: inhoud plausibel maar context, primaire bron of projectbewijs ontbreekt.
- `UPDATE`: beperkt voorstel met exacte brondoelpassage en bewijs, **geen toestemming om automatisch te schrijven**.

**Grenzen:** uitsluitend bestaande lokale/gekoppelde corpora; geen publieke YouTube-acquisitie, geen prompts uit transcriptinhoud uitvoeren, geen klantdata of broncitaten in deze publieke repo. De juiste vakowner en `webactueel-workflow` houden bronacceptatie, toestemming, back-up, SHA/manifest en readback in beheer.

## Optionele offline kwaliteitscheck (CSV-export)

De offline controle `scripts/audit_excel_discovery.py` is een **conservatieve reviewpoort**, geen bronverzamelaar of automatische kennisvalidator. Er zijn geen extra Python-dependencies voor deze CSV-route.

1. Exporteer uit het bestaande, geautoriseerde werkboek alleen de tabbladen `Bronvermeldingen` en `Video index` naar **twee afzonderlijke CSV-bestanden**, met ongewijzigde kolomnamen en zonder rijen te verwijderen.
2. Gebruik daarnaast de lokaal, uit precies dezelfde toegestane corpusversie opgebouwde `video_screening.csv`. Controleer de bron-SHA's en de ID-populatie; voer geen netwerk- of YouTube-opdrachten uit.
3. Voer de controle uitsluitend buiten de publieke repository uit:

```sh
python -m scripts.audit_excel_discovery \\
  --mentions-csv /private/review/Bronvermeldingen.csv \\
  --excel-index-csv /private/review/Video-index.csv \\
  --raw-screening-csv /private/review/video_screening.csv \\
  --output-dir /private/review/controle-uitvoer-nieuw
```

De uitvoermap mag vooraf **niet bestaan**. De tool leest invoer zonder deze te wijzigen, vereist unieke overeenkomstige video-ID's, accepteert een letterlijk Excel-apostrofeteken voor een verder geldige ID, en blokkeert ongeldige datumvlaggen, beschadigde nulbytes en onveilige inputgroottes. `entity_reviews.csv` is voorlopig alleen voor de bekende ambigue voorbeelden (Microsoft Clarity, RAG, Zero to One, The ONE Thing, Astro en Atomic Habits). Andere namen blijven buiten deze specifieke regelset en worden niet automatisch afgekeurd. `CONTEXT_PRESENT_UNVERIFIED` betekent **geen** bewezen claim; `AMBIGUOUS_NEEDS_REVIEW` betekent **geen** definitieve afwijzing. `date_flag_conflicts.csv` toont afwijkende bronvlaggen zonder publicatiedata of werkboekrijen stil te corrigeren. `summary.json` bewaart alleen tellingen en invoer-SHA's.

Alle uitvoer blijft privaat. Controleer inhoud, officiële bron en vakowner afzonderlijk voordat er zelfs maar een `UPDATE`-voorstel kan worden geaccepteerd. Synthetische regressies: `python -m unittest tests.test_excel_discovery_review -v`.

## Reviewrecord (schema-illustratie, geen runtimecontract)

```json
{
  "status": "NEEDS_VERIFICATION",
  "video_id": "EXAMPLE_VIDEO_ID",
  "url": "https://www.youtube.com/watch?v=EXAMPLE_VIDEO_ID",
  "channel": "example-channel",
  "publication_date": "unknown",
  "canonical_entity": "example-concept",
  "claim_type": "method",
  "evidence_level": "explained",
  "source_sha256": "example-source-hash-to-be-replaced",
  "owner": "proposed-owner",
  "existing_drive_target": "not_yet_verified",
  "official_confirmation": "not_checked",
  "auto_promoted": false
}
```

Dit voorbeeld bevat opzettelijk geen echte client-, maker- of corpusgegevens. Gebruik een eigen gevalideerd recordformaat wanneer de bestaande repositorycontracten dat vereisen.