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