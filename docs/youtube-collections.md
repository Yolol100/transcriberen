# YouTube-kanalen en playlists

De runtime ondersteunt drie publieke YouTube-doelen zonder extra account, API-key, OAuth, MCP/MQTT-server, proxy of externe transcriptdienst als vereiste:

- losse video-URL;
- kanaal-URL (`/@handle`, `/channel/...`, `/c/...`, `/user/...`);
- playlist-URL (`?list=...`).

## Werking

1. Een kanaalroot wordt als drie publieke oppervlakken onderzocht: `/videos`, `/shorts` en `/streams`. Een playlist blijft één collectie.
2. De lokaal gepinde `yt-dlp`-binary leest de collecties uit via `--flat-playlist --skip-download`; video-ID's worden over de kanaaltabs heen gededupliceerd. Iedere tab wordt diep genoeg gelezen om dubbele ID's aan het begin van een volgende tab niet ten onrechte als de collectiegrens te behandelen.
3. Iedere gevonden video gaat daarna afzonderlijk door de bestaande caption-only route.
4. Alleen publiek bereikbare handmatige of automatisch gegenereerde ondertitels worden gebruikt.
5. De per-video status onderscheidt:
   - `captions_collected`: captions zijn verzameld;
   - `no_usable_captions`: de captionroute kon draaien, maar exposeerde geen bruikbare captiontrack;
   - `caption_access_error`: captionbeschikbaarheid kon door YouTube-/netwerk-/tooltoegang niet betrouwbaar worden bepaald, bijvoorbeeld bij een bot-/loginchallenge;
   - `processing_error`: onverwachte lokale verwerkingsfout.
6. Voor publieke YouTube worden nooit audio/video gedownload en Whisper is geen fallback.
7. `max_items=0` betekent de volledige gevonden collectie tot de harde veiligheidslimiet van 10.000 video's. Een waarde van `1` tot en met `5000` begrenst een gerichte run; bij zo'n begrensde kanaalscan is de volgorde videos, Shorts, streams.

De totale `scan_status` is `captions_collected`, `partial`, `no_usable_captions`, `source_access_blocked` of `processing_error`, afhankelijk van de combinatie van per-video statussen.

## Uitvoer

Iedere verwerkte kanaal-/playlistrun maakt:

- `results/result.json`: runtimebewijs, toolversies, hashes, collectiestatus en status per video;
- `results/source-register.json`: controleerbaar register van de ontdekte video's en hun captionstatus;
- `results/knowledge-handoff.json`: reviewpakket voor Webactueel-workflow met bronitems en promotiepoort;
- `results/tool-versions.txt`: daadwerkelijk gebruikte toolversies;
- `results/content.md`: samengevoegde genormaliseerde captions, alleen wanneer `reuse_allowed=true`, een concrete rechtenbasis is opgegeven én minimaal één captiontrack succesvol is verzameld.

Zonder verzamelde captions blijft `content_chars=0`, wordt geen placeholder als inhoud opgeslagen en verwijst de handoff niet naar `content.md`.

De repository schrijft nooit zelfstandig naar een projectbron of Skill. `knowledge-handoff.json` is reviewinput en geen direct `UPDATE-PLAN.json`. Webactueel-workflow beoordeelt eerst de inzichten, dedupliceert en parafraseert, kiest per geaccepteerd inzicht precies één canonieke eigenaar en gebruikt daarna pas de bestaande gecontroleerde write-route met actuele readback/hash, backup, validatie en rollback.

## Toolkeuze

Voor publieke YouTube gebruikt deze repo bewust de al aanwezige `yt-dlp` + lokale Deno/EJS-route. Er is geen YouTube Data API, Caption API, transcript-API of extra account nodig.

De kandidaat `bgutil-ytdlp-pot-provider` 1.3.1 is op een schone GitHub-hosted Ubuntu-runner getest in lokale Deno-scriptmodus. Installatie en plugin-load werkten zonder account, key, proxy of permanente server, maar YouTube bleef op die runner de playerrequest met botbevestiging blokkeren. De provider is daarom niet als vaste dependency toegevoegd: hij lost de geteste blokkade niet op en vergroot de dependencyketen aanzienlijk.

## Externe YouTube-beperking

Kanaalontdekking is live geverifieerd op een GitHub-hosted runner zonder credentials. Captionbereikbaarheid is daar niet gegarandeerd: YouTube kan gedeelde cloud-IP's een `Sign in to confirm you're not a bot`/`LOGIN_REQUIRED`-challenge geven voordat ondertitels beschikbaar komen.

Onder de harde repo-eisen bestaat daarvoor geen betrouwbare universele workaround: cookies/login, residential proxy, self-hosted infrastructuur en externe transcriptdiensten zijn bewust geen verborgen fallback. De runtime registreert zo'n blokkade als `caption_access_error` en, wanneer geen enkele video captions oplevert, als totale `source_access_blocked`; hij noemt dat niet langer ten onrechte `no_usable_captions`.

`.github/workflows/youtube-live-smoke.yml` is daarom een handmatige **YouTube Availability Probe**. Hij controleert vanaf de actuele GitHub-runner of kanaalontdekking werkt en of publieke captions op dat moment vanaf dat IP bereikbaar zijn, zonder dat die externe beschikbaarheid een misleidende verplichte PR-gate wordt.
