# Webactueel Transcriberen Runtime

Accountloze controlled-runtime voor `project-transcriberen`. De repository verzamelt publieke broninhoud; `webactueel-workflow` blijft eigenaar van bronselectie, kwaliteit, deduplicatie, kennispromotie en bronwrites.

## Kernregels

- Publieke YouTube: **metadata, openbare captions en optioneel openbare comments; nooit audio/video-download**.
- Captionkeuze bij `language=auto`: **Engels → Nederlands → eerste overige taal**. Binnen dezelfde taal: handmatige captions vóór automatische captions.
- Auto-vertaalde YouTube-captions worden via yt-dlp `skip=translated_subs` én een lokale `tlang`-controle uitgesloten.
- WebVTT/SRT wordt cue-gericht opgeschoond; VTT-metadata, inline timestamps, markup en rolling auto-caption overlap worden verwijderd.
- Zonder bruikbare caption wordt een item `no_captions`; publieke YouTube gebruikt nooit Whisper/mediafallback.
- Zoekresultaten kunnen lokaal worden gefilterd op jaar en minimale views/likes/comments en gerangschikt op relevantie, views, likes, comments of nieuwste upload.
- Ranking geldt alleen binnen de werkelijk gescande kandidaatset. `youtube-index.json` vermeldt daarom expliciet of discovery mogelijk begrensd was.
- Publieke comments zijn analyse-evidence. Persistente comment-artifacts verwijderen standaard auteursnaam/-id; commenttekst zelf kan nog persoonsgegevens bevatten en blijft taakgebonden.

## YouTube-capabilities

`mode=youtube` ondersteunt:

- `video`: één gewone video;
- `short`: één Short;
- `search`: YouTube zoeken via `ytsearch:` en daarna criteria toepassen;
- `playlist`: playlistitems;
- `channel_videos`: de `/videos`-tab van een kanaal;
- `channel_shorts`: de `/shorts`-tab van een kanaal;
- `channel_all`: video's en Shorts combineren, dedupliceren en vóór selectie eerlijk interleaven.

Per geselecteerd item wordt relevante metadata vastgelegd. Wanneer `analysis_content_allowed=true` of `reuse_allowed=true`, worden daarnaast de gekozen transcripttrack en optioneel geminimaliseerde comments als kortstondig workflowartifact opgeslagen.

### Werkbudgetten

Bulkdiscovery heeft standaard `scan_limit: 500`. `max_items` bepaalt hoeveel van de gescande/gerangschikte items daadwerkelijk worden verwerkt. Voor een bewust onbeperkte playlist/kanaalscan gebruikt u `scan_limit: 0` én `allow_unbounded: true`.

`max_comments: "all"` is eveneens een expliciet onbeperkte operatie en vereist `allow_unbounded: true`. “All” betekent: **best effort voor alle comments die YouTube via yt-dlp blootstelt**, niet een garantie dat verborgen, verwijderde, gemodereerde of tijdelijk niet-ophaalbare comments beschikbaar zijn.

Daarmee zijn zowel veilige standaardruns als expliciete “heel kanaal / alle beschikbare comments”-runs mogelijk zonder dat een gewone request ongemerkt onbeperkt werk start.

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
    "max_comments": "200",
    "allow_unbounded": false
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
    "max_comments": "200",
    "allow_unbounded": false
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

Heel kanaal zonder discoverylimiet en alle door yt-dlp bereikbare comments:

```json
{
  "youtube": {
    "scope": "channel_all",
    "max_items": 0,
    "scan_limit": 0,
    "include_comments": true,
    "max_comments": "all",
    "allow_unbounded": true
  }
}
```

Gebruik de volledige requestvelden uit het eerste voorbeeld eromheen. Een onbeperkte run blijft afhankelijk van YouTube-beschikbaarheid, rate limits en GitHub Actions-runtimegrenzen; `youtube-index.json` rapporteert fouten en completeness-signalen in plaats van absolute volledigheid te claimen.

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
- `whisper.cpp` v1.9.2 + gepind base-model, uitsluitend bij geautoriseerde niet-YouTube-audiofallback;
- Trafilatura 2.1.0;
- lokale Python parsing/normalisatie.

Er is geen YouTube Data API-key, login, cookies of MCP-server nodig. De runtime omzeilt geen login, DRM, betaalmuur, CAPTCHA of leeftijdscontrole.

## Output

De workflow publiceert `transcription-result-<request_id>` met:

- `result.json`: provenance, toolversies, rechten-/gebruiksmodus en samenvatting;
- `youtube-index.json`: discoverybudget, mogelijk-truncated signaal, selectie, collection status, transcript/comment-fouten en itemmetadata;
- `items/<video-id>/metadata.json`;
- `items/<video-id>/transcript.md` wanneer analyse/reuse-persistence is toegestaan en captions bestaan;
- `items/<video-id>/comments.json` wanneer comments zijn aangevraagd en analyse/reuse-persistence is toegestaan; directe auteursnaam/-id worden niet opgeslagen;
- `content.md`: samengestelde transcriptinput voor downstream kennisreview.

De resultvalidator controleert naast het hoofdcontract ook count-consistentie, transcript/content-hashes, itemmetadata, comment-identiteitsminimalisatie en dat er geen audio/video-bestanden in het result-artifact terechtkomen.

`analysis_content_allowed=true` betekent alleen kortstondige verwerking voor analyse/parafrase. Het geeft geen herpublicatie- of hergebruiksrecht. `reuse_allowed=true` blijft een aparte poort met concrete rechtenbasis.

## Kennisreview

De repository bepaalt niet zelfstandig welke tekst een Skill of projectbron moet wijzigen. Na acquisitie beoordeelt `webactueel-workflow` inhoud, bronkwaliteit, actualiteit, deduplicatie en de canonieke eigenaar. Alleen geaccepteerde inzichten mogen gecontroleerd naar een Skill of projectbron worden gepromoveerd.

## Technische grens

YouTube verandert regelmatig. yt-dlp ondersteunt search, playlists, tabs, captions en comments, maar een accountloze openbare extractor kan niet garanderen dat ieder item/comment altijd toegankelijk blijft. De runtime rapporteert fouten en begrenzingen expliciet en gebruikt voor publieke YouTube nooit mediafallback.
