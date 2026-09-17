# Threat model

Te beschermen eigenschappen:

1. Een request kan alleen één publiek YouTube-kanaal aanwijzen.
2. Alleen de `/videos`-tab wordt gebruikt; directe video/Short/playlistinput wordt geweigerd.
3. Maximaal 1000 entries worden per run geïnspecteerd en alleen `upload_date` uit 2026 wordt geaccepteerd.
4. Comments zijn begrensd tot 7 top-level items, `top` gesorteerd, zonder replies.
5. Geen media, credentials, sessiestaat of bypassmechanisme wordt gebruikt.
6. De self-hosted runner voert alleen vertrouwde `main`-code uit.
7. Captioncache is execution state; comments worden per run opnieuw opgehaald en projectkennis blijft buiten deze repo.

Onbetrouwbaar: queue-JSON, YouTube/yt-dlp-responses en publieke comments. Vertrouwd: `main`, gepinde Actions/toolversies en de dedicated runner. Een anti-bot/rate-limitblokkade wordt als `access_blocked` behandeld; er is geen bypassroute.
