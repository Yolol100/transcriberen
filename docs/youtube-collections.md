# YouTube-kanalen en playlists

De runtime ondersteunt drie publieke YouTube-doelen zonder extra account, API-key, MCP/MQTT-server of proxy als vereiste:

- losse video-URL;
- kanaal-URL (`/@handle`, `/channel/...`, `/c/...`, `/user/...`);
- playlist-URL (`?list=...`).

## Werking

1. Een kanaal of playlist wordt met de lokaal gepinde `yt-dlp`-binary als metadata-lijst uitgelezen via `--flat-playlist --skip-download`.
2. Iedere gevonden video wordt daarna afzonderlijk door de bestaande caption-only route verwerkt.
3. Alleen publieke handmatige of automatisch gegenereerde ondertitels worden gebruikt.
4. Video's zonder bruikbare captions blijven in het resultaat staan met status `no_usable_captions`; er wordt voor publieke YouTube nooit audio/video gedownload en Whisper is geen fallback.
5. `max_items=0` betekent de volledige gevonden kanaal-/playlistverzameling. Een waarde van `1` tot en met `5000` begrenst een run wanneer een gerichte scan gewenst is.

## Uitvoer

Iedere succesvolle kanaal-/playlistrun maakt:

- `results/result.json`: runtimebewijs, toolversies, hashes en status per video;
- `results/content.md`: samengevoegde genormaliseerde captions, alleen wanneer `reuse_allowed=true` en een concrete rechtenbasis is opgegeven;
- `results/knowledge-handoff.json`: reviewpakket voor Webactueel-workflow met bronitems, hashes en `promotion_status=review_required`;
- `results/tool-versions.txt`: daadwerkelijk gebruikte toolversies.

De repository schrijft nooit zelfstandig naar een projectbron of Skill. `knowledge-handoff.json` is invoer voor de gecontroleerde Webactueel-workflow: eerst reviewen, dedupliceren en parafraseren, daarna ieder geaccepteerd inzicht naar precies één canonieke eigenaar routeren en pas via de bestaande write-/rollbackpoort toepassen.

## Toolkeuze

Voor publieke YouTube gebruikt deze repo bewust de al aanwezige `yt-dlp` + lokale Deno-route. Er is geen YouTube Data API of Caption API nodig en er wordt geen extra transcriptdienst toegevoegd. Daardoor ontstaat geen verplichte API-key, OAuth-flow, nieuw account, MCP/MQTT-server of externe transcriptie-infrastructuur.

Een publieke bron kan nog steeds door YouTube zelf tijdelijk of structureel tegen geautomatiseerde toegang worden geblokkeerd. De runtime omzeilt zulke blokkades niet en gebruikt geen cookies/login als verborgen fallback.
