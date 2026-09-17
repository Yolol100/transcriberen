# Kanaal-only captions 2026

De gratis bulkroute gebruikt dezelfde gepinde yt-dlp/Deno-runtime als voorheen, maar de publieke capability is nu uitsluitend kanaalgericht.

Vaste route: kanaal-URL -> `/videos` -> maximaal 1000 entries -> volledige metadata per entry -> alleen `upload_date` in 2026 -> publieke captions -> maximaal 7 top-level comments met `comment_sort=top` -> manifest + deterministische ZIP.

Comments zijn non-gating. Een video zonder captions kan nog wel `comments.json` en `metadata.json` krijgen. Replies worden zowel bij acquisitie begrensd als bij readback weggefilterd.

De captioncache blijft bestaan op `video_id + requested_language`; comments worden niet persistent gecachet zodat een volgende run de actuele topselectie kan ophalen.
