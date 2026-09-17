# Repository governance

Deze repository is een controlled runtime voor publieke YouTube-kanaalcaptions en maximaal 7 top-level comments per 2026-video. `main` bevat alleen generieke runtimecode en geen echte requeststate.

`runtime-requests` blijft de enige operationele append-only transportbranch. Een requestcommit mag precies één nieuw `requests/queue/<request_id>.json` toevoegen. De self-hosted runner voert nooit code vanaf die transportbranch uit en checkt uitsluitend `Yolol100/transcriberen@main` uit.

Acquisitie draait uitsluitend op `[self-hosted, linux, x64, webactueel-transcribe]`. De host blijft dedicated en bevat geen persoonlijke browserprofielen of projectsecrets. Bescherm `main` met PR/reviewchecks, force-push/deletion protection en de actuele repository-doctor/toolkitchecks.
