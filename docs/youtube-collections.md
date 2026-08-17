# YouTube-video's, kanalen en playlists

De runtime ondersteunt drie publieke YouTube-doelen zonder extra account, API-key, MCP/MQTT-server of proxy als vereiste:

- losse video-URL;
- kanaal-URL (`/@handle`, `/channel/...`, `/c/...`, `/user/...`);
- playlist-URL (`?list=...`).

## Werking

1. Een kanaal of playlist wordt met de lokaal gepinde `yt-dlp`-binary als metadata-lijst uitgelezen via `--flat-playlist --skip-download`.
2. Iedere gevonden video wordt daarna afzonderlijk door de caption-only route verwerkt.
3. Alleen publieke handmatige of automatisch gegenereerde ondertitels worden gebruikt.
4. Video's zonder bruikbare captions krijgen status `no_usable_captions`. Een door YouTube geblokkeerde runtime krijgt `access_blocked`.
5. Voor publieke YouTube wordt nooit audio/video gedownload en Whisper is geen fallback.
6. `max_items=0` betekent de volledige gevonden kanaal-/playlistverzameling. Een waarde van `1` tot en met `5000` begrenst een gerichte scan.

## Uitvoer en promotie

Een YouTube-run maakt:

- `results/result.json`: runtimebewijs, toolversies, hashes en status per video;
- `results/content.md`: alleen wanneer er daadwerkelijk captions zijn én `reuse_allowed=true` met een concrete rechtenbasis;
- `results/knowledge-handoff.json`: gecontroleerde overdracht naar Webactueel-workflow;
- `results/tool-versions.txt`: daadwerkelijk gebruikte toolversies.

`promotion_status` is expliciet:

- `review_required`: er zijn captions beschikbaar; eerst reviewen, dedupliceren en parafraseren voordat een projectbron of Skill wordt bijgewerkt;
- `no_content`: geen bruikbare publieke captions; niets promoveren;
- `blocked`: YouTube blokkeerde de runtime/IP; niets promoveren en geen verborgen workaround gebruiken.

De repository schrijft nooit zelfstandig naar een projectbron of Skill. Een geaccepteerd inzicht moet door Webactueel-workflow naar precies één canonieke eigenaar worden gerouteerd en via de bestaande write-/rollbackpoort worden toegepast.

## Toolkeuze

Voor publieke YouTube gebruikt deze repo bewust de al aanwezige `yt-dlp` + lokale Deno-route. Er is geen YouTube Data API of Caption API nodig voor de gekozen route en er wordt geen extra transcriptdienst toegevoegd. Daardoor ontstaat geen verplichte API-key, OAuth-flow, nieuw account, MCP/MQTT-server of externe transcriptie-infrastructuur.

De runtime gebruikt `--no-config` en `--no-cookies` en activeert geen `.netrc`-authenticatie. Een verouderde `--no-netrc`-optie is verwijderd omdat de huidige gepinde yt-dlp-versie die optie niet ondersteunt.

## Bewezen beperking van GitHub-hosted Actions

Live tests op 17 augustus 2026 met een GitHub-hosted Ubuntu-runner toonden het volgende:

- publieke kanaal-enumeratie werkte zonder credentials;
- de daaropvolgende video-/subtitle-opvraag werd door YouTube geweigerd met de anti-botmelding `Sign in to confirm you're not a bot`;
- meerdere yt-dlp-playerclients (`web_safari`, `web_embedded`, `tv`, `android_vr`) kregen dezelfde blokkade;
- directe publieke `timedtext`-inventarisatie leverde voor de geteste video's geen tracks terug.

Daarom is accountloze caption-fetch vanaf een GitHub-hosted runner niet betrouwbaar te garanderen. De repo voegt bewust geen cookies, accountlogin, proxy, externe tokenprovider of andere bypass toe om dit te omzeilen. Bij zo'n blokkade schrijft de runtime bewijsartefacten met `access_blocked`/`promotion_status=blocked` en faalt de run zichtbaar. Een nieuwe run kan alleen zinvol zijn vanaf een publieke runtime/netwerkroute die YouTube zonder aanvullende authenticatie toestaat.
