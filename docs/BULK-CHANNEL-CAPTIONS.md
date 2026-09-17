# Kanaal-only captions 2026

De gratis bulkroute gebruikt dezelfde gecontroleerde yt-dlp/Deno-runtime, maar de publieke capability is uitsluitend kanaalgericht.

Vaste route: kanaal-URL -> `/videos` -> maximaal 1000 entries -> volledige metadata per entry -> alleen bewezen `upload_date` in 2026 -> publieke captions -> maximaal 7 top-level comments met `comment_sort=top` -> manifest + deterministische ZIP.

No-replies wordt expliciet aan yt-dlp doorgegeven als `max_comments=7,7,0,0,1`; `max-depth=1` sluit replies uit. Runtime-readback filtert replies nogmaals.

Comments blijven non-gating voor een geldig transcript. Ontbrekende comments maken de totale run wel `partial`. Een video zonder captions kan nog wel `comments.json` en `metadata.json` krijgen. Metadata die geen 2026-lidmaatschap kan bewijzen wordt als `unresolved` opgenomen en eveneens als partial geteld.

De queue probeert de acquisitie eerst op GitHub-hosted `ubuntu-24.04`. Alleen expliciete `access_blocked`-evidence uit discovery, metadata, captions of comments activeert automatisch de dedicated self-hosted fallback. Een gewone fout of partial zonder blokkade-evidence blijft op de hosted route en triggert de fallback niet.

De captioncache blijft persistent op self-hosted/local op `video_id + requested_language`; GitHub-hosted runners zijn ephemeral. Comments worden niet persistent gecachet zodat een volgende run de actuele topselectie kan ophalen. `processed-index.json` exporteert alleen de entries van de huidige run en nooit de volledige persistente cachehistorie.

Resolve, hosted attempt en eventuele self-hosted fallback gebruiken dezelfde immutable trusted runtime-SHA, zodat wijzigingen op `main` tijdens de run niet stil een andere executable basis opleveren.
