# Webactueel Transcriberen Runtime

Kanaal-only publieke YouTube-corpusacquisitie zonder betaalde API, MCP of plugin.

## Vast contract

`YouTube-kanaal -> /videos -> alleen uploadjaar 2026 -> maximaal 1000 video’s -> publieke captions + maximaal 7 top-level comments per video -> ZIP`

De oude directe single-video/Short-ingang bestaat niet meer. Requests accepteren alleen een kanaal-URL en optioneel een captiontaal.

```json
{
  "enabled": true,
  "request_id": "brian-coords-2026",
  "url": "https://www.youtube.com/@BrianCoords",
  "language": "auto"
}
```

Vaste regels: jaar `2026`, maximaal `1000` kanaalvideo’s per run, commentsortering `top`, maximaal `7` top-level comments en geen replies. De runtime normaliseert een kanaal automatisch naar `/videos`, zodat Shorts niet via de `/shorts`-tab worden verzameld.

## Output

Per video uit 2026:
- `videos/<video_id>/metadata.json`
- `videos/<video_id>/transcript.txt` wanneer bruikbare publieke captions bestaan
- `videos/<video_id>/comments.json` met maximaal 7 top-level comments

Per run: `result.json`, `manifest.json`, `progress.json`, `processed-index.json`, `channel-corpus.zip` en `SHA256SUMS.txt`.

Comments zijn aanvullend: uitgeschakelde/onbereikbare comments blokkeren een geldig transcript niet. Geen captions blijft een schone `skipped_no_captions` per video.

## Veiligheidsgrenzen

Geen video/audio-download, cookies, login, browserprofielen, proxy, CAPTCHA-bypass, PO-token-bypass, FFmpeg of Whisper. yt-dlp draait met `--skip-download` en `--no-cookies`. YouTube-acquisitie draait lokaal of op de dedicated self-hosted runner `[self-hosted, linux, x64, webactueel-transcribe]`.

De captioncache blijft lokale execution state. Kennis uit transcripts/comments wordt nooit door deze repo automatisch naar Skills, bronnen of projectwaarheid gepromoveerd.

## Lokaal

Python 3.12+, Linux x64/WSL2, `curl` en `sha256sum`:
```bash
bash scripts/run_local.sh requests/transcribe.json
```

## Licentie

Deze repository bevat momenteel geen open-sourcelicentie. Hergebruik, distributie of afgeleide werken zijn niet toegestaan zonder expliciete toestemming van de rechthebbende.
