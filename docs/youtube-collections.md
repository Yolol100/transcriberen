# YouTube-kanalen en playlists

De runtime ondersteunt drie publieke YouTube-doelen zonder extra account, API-key, OAuth, MCP/MQTT-server, proxy of externe transcriptdienst als vereiste:

- losse video-URL;
- kanaal-URL (`/@handle`, `/channel/...`, `/c/...`, `/user/...`);
- playlist-URL (`?list=...`).

## Werking

1. Een kanaalroot wordt als drie publieke oppervlakken onderzocht: `/videos`, `/shorts` en `/streams`. Een playlist blijft één collectie.
2. De lokaal gepinde `yt-dlp`-binary leest de collecties uit via `--flat-playlist --skip-download`; video-ID's worden over de kanaaltabs heen gededupliceerd.
3. Iedere gevonden video gaat daarna afzonderlijk door de bestaande caption-only route.
4. Alleen publiek bereikbare handmatige of automatisch gegenereerde ondertitels worden gebruikt.
5. Video's zonder bruikbare captions blijven in het resultaat staan met status `no_usable_captions`; voor publieke YouTube worden nooit audio/video gedownload en Whisper is geen fallback.
6. `max_items=0` betekent de volledige gevonden collectie tot de harde veiligheidslimiet van 10.000 video's. Een waarde van `1` tot en met `5000` begrenst een gerichte run; bij zo'n begrensde kanaalscan is de volgorde videos, Shorts, streams.

## Uitvoer

Iedere verwerkte kanaal-/playlistrun maakt:

- `results/result.json`: runtimebewijs, toolversies, hashes, collectiestatus en status per video;
- `results/source-register.json`: controleerbaar register van de ontdekte video's en hun captionstatus;
- `results/knowledge-handoff.json`: reviewpakket voor Webactueel-workflow met bronitems en promotiepoort;
- `results/tool-versions.txt`: daadwerkelijk gebruikte toolversies;
- `results/content.md`: samengevoegde genormaliseerde captions, alleen wanneer `reuse_allowed=true` en een concrete rechtenbasis is opgegeven.

De repository schrijft nooit zelfstandig naar een projectbron of Skill. `knowledge-handoff.json` is invoer voor de gecontroleerde Webactueel-workflow: eerst reviewen, dedupliceren en parafraseren, daarna ieder geaccepteerd inzicht naar precies één canonieke eigenaar routeren en pas via actuele readback/hash, backup, validatie en rollback toepassen.

## Toolkeuze

Voor publieke YouTube gebruikt deze repo bewust de al aanwezige `yt-dlp` + lokale Deno/EJS-route. Er is geen YouTube Data API, Caption API, transcript-API of extra account nodig.

De kandidaat `bgutil-ytdlp-pot-provider` 1.3.1 is op een schone GitHub-hosted Ubuntu-runner getest in lokale Deno-scriptmodus. Installatie en plugin-load werkten zonder account, key, proxy of permanente server, maar YouTube bleef op die runner de playerrequest met botbevestiging blokkeren. De provider is daarom niet als vaste dependency toegevoegd: hij lost de geteste blokkade niet op en vergroot de dependencyketen aanzienlijk.

## Externe YouTube-beperking

Kanaalontdekking is live geverifieerd op een GitHub-hosted runner zonder credentials. Captionbereikbaarheid is daar niet gegarandeerd: YouTube kan gedeelde cloud-IP's een `Sign in to confirm you're not a bot`/`LOGIN_REQUIRED`-challenge geven voordat ondertitels beschikbaar komen.

Onder de harde repo-eisen bestaat daarvoor geen betrouwbare universele workaround: cookies/login, residential proxy, self-hosted infrastructuur en externe transcriptdiensten zijn bewust geen verborgen fallback. De runtime rapporteert in dat geval `no_usable_captions` in plaats van de blokkade te omzeilen of inhoud te verzinnen.

`.github/workflows/youtube-live-smoke.yml` is daarom een handmatige **YouTube Availability Probe**. Hij controleert vanaf de actuele GitHub-runner of kanaalontdekking werkt en of publieke captions op dat moment vanaf dat IP bereikbaar zijn, zonder dat die externe beschikbaarheid een misleidende verplichte PR-gate wordt.
