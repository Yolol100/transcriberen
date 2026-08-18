# Webactueel Transcriberen Runtime

Accountloze controlled-runtime voor `project-transcriberen`. De repository verzamelt publieke broninhoud; `webactueel-workflow` blijft eigenaar van bronselectie, kwaliteit, deduplicatie, kennispromotie en bronwrites.

## Kernregels

- Publieke YouTube: **metadata, openbare captions en optioneel openbare comments; nooit audio/video-download**.
- Captionkeuze bij `language=auto`: **Engels → Nederlands → eerste overige taal**. Binnen dezelfde taal: handmatige captions vóór automatische captions.
- Auto-vertaalde YouTube-captions worden bij discovery overgeslagen. De selector controleert daarnaast caption-URL’s op YouTube `tlang`-vertaling, omdat `skip=translated_subs` in edge-cases niet voldoende kan zijn.
- Als een YouTube-video geen bruikbare openbare captiontrack heeft, wordt dat item als `no_captions` vastgelegd. Er is bewust geen Whisper/mediafallback voor publieke YouTube.
- Zoekresultaten kunnen lokaal worden gefilterd op jaar en minimale views/likes/comments en gerangschikt op relevantie, views, likes, comments of nieuwste upload.
- Een ranking bij YouTube-search geldt alleen binnen de opgehaalde kandidaatset (`candidate_limit`), niet als absolute ranglijst van heel YouTube.
- Publieke comments kunnen persoonsgegevens bevatten. Ze zijn analyse-evidence en worden niet automatisch projectwaarheid.

## YouTube-capabilities

`mode=youtube` ondersteunt:

- `video`: één gewone video;
- `short`: één Short;
- `search`: YouTube zoeken via `ytsearch:` en daarna criteria toepassen;
- `playlist`: alle of een begrensd aantal playlistitems;
- `channel_videos`: de `/videos`-tab van een kanaal;
- `channel_shorts`: de `/shorts`-tab van een kanaal;
- `channel_all`: video's en Shorts van hetzelfde kanaal combineren en dedupliceren.

Per geselecteerd item wordt relevante metadata vastgelegd. Wanneer `analysis_content_allowed=true` of `reuse_allowed=true`, worden daarnaast de gekozen transcripttrack en optioneel comments als kortstondig workflowartifact opgeslagen.

### Voorbeelden

Eén video, automatisch de beste taal volgens Engels → Nederlands → overige:

```json
{
  "enabled": true,
  "request_id": "youtube-video-001",
  "owner": "webactueel-workflow",
  "project_id": "project-transcriberen",
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "mode": "youtube",
  "language": "auto",
  "youtube": {
    "scope": "video",
    "include_comments": true,
    "comment_sort": "top",
    "max_comments": "200"
  },
  "allow_audio_fallback": false,
  "audio_access_authorized": false,
  "analysis_content_allowed": true,
  "reuse_allowed": false,
  "rights_basis": "analysis-paraphrase-only",
  "source_context": {
    "project_id": "project-transcriberen",
    "source_set_version": "set-at-execution"
  }
}
```

Zoek kandidaten uit 2025, rangschik binnen de kandidaatset op views en verwerk de top 20:

```json
{
  "enabled": true,
  "request_id": "youtube-search-2025-001",
  "owner": "webactueel-workflow",
  "project_id": "project-transcriberen",
  "mode": "youtube",
  "language": "auto",
  "youtube": {
    "scope": "search",
    "query": "WordPress performance",
    "year_from": 2025,
    "year_to": 2025,
    "sort_by": "views",
    "candidate_limit": 100,
    "max_items": 20,
    "include_comments": true,
    "comment_sort": "top",
    "max_comments": "200"
  },
  "allow_audio_fallback": false,
  "audio_access_authorized": false,
  "analysis_content_allowed": true,
  "reuse_allowed": false,
  "rights_basis": "analysis-paraphrase-only",
  "source_context": {
    "project_id": "project-transcriberen",
    "source_set_version": "set-at-execution"
  }
}
```

Heel kanaal: zet `scope` op `channel_all` en `max_items` op `0`. Alleen Shorts: `channel_shorts`. Alle comments per geselecteerde video: `max_comments: "all"`. Grote kanalen/commentsets blijven afhankelijk van YouTube-beschikbaarheid, rate limits en de GitHub Actions-limiet.

## Niet-YouTube-bronnen

De bestaande routes blijven beschikbaar:

- publieke media met captions via `yt-dlp`;
- alleen voor expliciet geautoriseerde **niet-YouTube** media: tijdelijke audio-normalisatie via FFmpeg en lokale `whisper.cpp` fallback;
- artikelen via Trafilatura;
- RSS/Atom/sitemap-discovery via Python/XML.

## Toolchain

- `yt-dlp` 2026.07.04, gepinde officiële immutable releasebinary met SHA-256-controle;
- Deno 2.9.5 als gepinde lokale EJS-runtime voor yt-dlp;
- FFmpeg/ffprobe uit de GitHub-hosted Ubuntu runtime;
- `whisper.cpp` v1.9.2 + gepind base-model, uitsluitend wanneer geautoriseerde niet-YouTube-audiofallback is aangezet;
- Trafilatura 2.1.0;
- lokale Python parsing/normalisatie.

Er is geen YouTube Data API-key, login, cookies of MCP-server nodig. De runtime omzeilt geen login, DRM, betaalmuur, CAPTCHA of leeftijdscontrole.

## Output

De workflow publiceert `transcription-result-<request_id>` met:

- `result.json`: provenance, toolversies, rechten-/gebruiksmodus en samenvatting;
- `youtube-index.json` bij YouTube-batches: selectie, ranking, status en itemmetadata;
- `items/<video-id>/metadata.json`;
- `items/<video-id>/transcript.md` wanneer analyse/reuse-persistence is toegestaan en captions bestaan;
- `items/<video-id>/comments.json` wanneer comments zijn aangevraagd en analyse/reuse-persistence is toegestaan;
- `content.md`: samengestelde transcriptinput voor downstream kennisreview.

`analysis_content_allowed=true` betekent alleen kortstondige verwerking voor analyse/parafrase. Het geeft geen herpublicatie- of hergebruiksrecht. `reuse_allowed=true` blijft een aparte poort met concrete rechtenbasis.

## Kennisreview

De repository bepaalt niet zelfstandig welke tekst een Skill of projectbron moet wijzigen. Na acquisitie beoordeelt `webactueel-workflow` inhoud, bronkwaliteit, actualiteit, deduplicatie en de canonieke eigenaar. Alleen geaccepteerde inzichten mogen gecontroleerd naar een Skill of projectbron worden gepromoveerd.

## Technische grens

YouTube verandert regelmatig. yt-dlp ondersteunt search, playlists, tabs, captions en comments, maar een accountloze openbare extractor kan niet garanderen dat ieder item/comment altijd toegankelijk blijft. De runtime rapporteert fouten per item waar mogelijk in plaats van mediafallback te gebruiken.
