# Webactueel Transcriberen Runtime

Accountloze controlled-runtime voor `project-transcriberen`. De repository is de uitvoeringscapability; `webactueel-workflow` blijft domeinowner en bepaalt bronselectie, gebruiksrechten, kwaliteit, promotie en bronwrites.

## Doel

De runtime verzamelt en normaliseert toegestane broninhoud zonder nieuw account, API-key, OAuth, MCP/MQTT-server, proxy of externe transcriptdienst:

- publieke losse video-/mediabronnen en beschikbare ondertitels/metadata via `yt-dlp`;
- publieke YouTube-kanalen en playlists, inclusief kanaal-tabs `videos`, `shorts` en `streams`;
- **publieke YouTube uitsluitend via captions en metadata; nooit audio/video-download**;
- audio-normalisatie via `ffmpeg`/`ffprobe` en lokale speech-to-text via `whisper.cpp` alleen voor expliciet geautoriseerde niet-YouTube-audio;
- artikelen en pagina's via Trafilatura;
- RSS/Atom- en sitemap-linkdiscovery met de lokale Python/Trafilatura-laag;
- SHA-256, toolversies, requesthash, uitvoercommit en transformatieprovenance in ieder resultaat.

## Harde grenzen

- Alleen expliciete publieke `http://`/`https://` bronnen; private, loopback, link-local en credentialed URLs worden geweigerd.
- Geen cookies, login, credentials, DRM-bypass, betaalmuur-bypass, CAPTCHA-/age-control-bypass, proxy-fallback of private netwerkdoelen. Ook geërfde systeemproxy's worden expliciet uitgeschakeld.
- Publieke YouTube-bronnen zijn captions/metadata-only. Een losse video zonder bereikbare captions faalt gecontroleerd; in een kanaal/playlist wordt echte captionafwezigheid `no_usable_captions`, terwijl een bot-/loginchallenge of technische toegangsblokkade apart als `caption_access_error` wordt geregistreerd.
- Een bekende runner-brede YouTube-blokkade stopt verdere captionrequests binnen dezelfde collectie; resterende gevonden video's worden `not_attempted_source_access_blocked` in plaats van opnieuw tegen dezelfde blokkade aan te lopen.
- YouTube kan gedeelde cloud-IP's een bot-/loginchallenge geven voordat captions bereikbaar zijn. De repo omzeilt die niet en claimt dan geen transcript.
- `allow_audio_fallback=true` vereist óók `audio_access_authorized=true` én een concrete `rights_basis`; geautoriseerde niet-YouTube-audio is daarnaast begrensd op duur, downloadgrootte, WAV-grootte en commandotijd.
- XML met DTD/entity-declaraties wordt geweigerd voordat parsing plaatsvindt.
- Geen broninhoud automatisch promoveren tot projectwaarheid of rechtstreeks naar een Skill schrijven.
- `reuse_allowed` en `rights_basis` zijn expliciete requestvelden. `content.md` wordt alleen bewaard wanneer hergebruik is toegestaan én daadwerkelijk inhoud is verzameld.

## YouTube-collecties

Een kanaalroot (`/@handle`, `/channel/...`, `/c/...`, `/user/...`) wordt onderzocht via `/videos`, `/shorts` en `/streams`. Video-ID's worden gededupliceerd. Een playlist (`?list=...`) wordt als één collectie verwerkt.

- `max_items=0`: volledige gevonden collectie tot de harde veiligheidslimiet van 10.000 video's;
- `max_items=1..5000`: begrensde scan;
- discoveryfouten op een kanaaltab blijven zichtbaar in `discovery_errors`; een deels geslaagde discovery wordt nooit stilzwijgend als volledig behandeld;
- iedere gevonden video wordt afzonderlijk op publiek bereikbare handmatige/automatische captions gecontroleerd, tenzij een runner-brede blokkade al is bewezen;
- publieke YouTube activeert nooit audio-download of Whisper.

Zie `docs/youtube-collections.md` voor statussen en de availability probe.

## Toolchain en supply chain

- `yt-dlp` 2026.07.04, officiële releasebinary met vaste SHA-256.
- Deno 2.9.5 als gepinde lokale EJS-runtime met vaste SHA-256.
- FFmpeg/ffprobe uit de GitHub-hosted Ubuntu runtime; daadwerkelijke versies én runtime-binarydigests worden in provenance vastgelegd.
- `whisper.cpp` v1.9.2 plus gepind `base` model alleen voor geautoriseerde niet-YouTube-audiofallback.
- Trafilatura 2.1.0; de directe universele wheel wordt vóór installatie tegen de geregistreerde PyPI SHA-256 gecontroleerd.
- Gedownloade tools worden eerst in een unieke tijdelijke stagingmap gevalideerd en pas daarna naar hun runtimepad geïnstalleerd.
- GitHub Actions zijn op volledige commit-SHA vastgezet; Dependabot onderhoudt pip- en Actions-updates.

`bgutil-ytdlp-pot-provider` en `youtube-transcript-api` zijn bewust geen vaste dependencies. De lokale bgutil/Deno-provider is live getest maar hief de GitHub-hosted YouTube-botchallenge niet op; transcript-API-routes lossen dezelfde cloud-IP-afhankelijkheid niet betrouwbaar op zonder infrastructuur die buiten de repo-eisen valt.

## Request

De normale Chat-/GitHub-route schrijft `requests/transcribe.json`. Een geldig request bevat onder meer:

```json
{
  "enabled": true,
  "request_id": "transcribe-voorbeeld-001",
  "owner": "webactueel-workflow",
  "project_id": "project-transcriberen",
  "url": "https://www.youtube.com/@OpenAI",
  "mode": "auto",
  "language": "nl",
  "max_items": 0,
  "allow_audio_fallback": false,
  "audio_access_authorized": false,
  "reuse_allowed": false,
  "rights_basis": "analysis-only",
  "source_context": {
    "project_id": "project-transcriberen",
    "source_set_version": "set-at-execution"
  }
}
```

Ondersteunde `mode`-waarden: `auto`, `media`, `article`, `feed`, `sitemap`.

## Uitvoer, provenance en bron-/Skill-update

De workflow uploadt `transcription-result-<request_id>` met minimaal `result.json` en toolversies. Resultaten bevatten een `provenance`-blok met de SHA-256 van het canonieke resolved request, de uitgevoerde GitHub-commit, Python/platformgegevens en hashes van daadwerkelijk gebruikte runtimebinaries. De validator berekent die gegevens opnieuw en controleert ook een gepersisteerde `content.md` opnieuw op SHA-256 en lengte.

YouTube-collecties leveren daarnaast `source-register.json` en `knowledge-handoff.json`; beide zijn aan dezelfde requesthash en uitvoercommit gebonden. `content.md` bestaat alleen wanneer `reuse_allowed=true` én minimaal één captiontrack succesvol is verzameld.

De repository muteert geen projectbron of Skill zelfstandig. `knowledge-handoff.json` is reviewmateriaal, geen direct uitvoerbaar updateplan. Webactueel-workflow accepteert alleen onderbouwde inzichten, dedupliceert/parafraseert ze, routeert ieder geaccepteerd inzicht naar precies één canonieke eigenaar en past een write alleen toe via de bestaande gecontroleerde write-route met actuele readback/hash, backup, validatie en rollback.

## Kwaliteitspoorten

PR's worden technisch getoetst met:

- unit- en negatieve regressietests;
- Python syntaxcheck en ShellCheck;
- toolkit-/policycontract;
- installatie en verificatie van de gepinde media-toolchain;
- Dependency Review op nieuwe dependencyrisico's;
- CodeQL voor Python én GitHub Actions-workflows;
- een niet-blokkerende YouTube Availability Probe die externe runner-bereikbaarheid apart registreert;
- Dependabot voor periodiek dependency-/Actiononderhoud.

De availability probe draait bij relevante PR-wijzigingen en wekelijks op de default branch en bewaart een JSON-evidenceartifact. Externe YouTube-bereikbaarheid is daarmee observeerbaar maar blijft bewust geen misleidende mergegarantie.

Zie `docs/quality-audit-10.md` voor de formele 10-poort en claimgrens.

## Bewijsniveau

Repo-uitvoer is maximaal `controlled_runtime`. De runtime bewijst wat met de geregistreerde toolchain vanaf de actuele runner kon worden verwerkt. Hij bewijst niet dat captions vanaf ieder netwerk altijd bereikbaar zijn, dat transcriptie semantisch foutloos is, dat herpublicatie juridisch is toegestaan of dat de uitkomst al projectwaarheid is.
