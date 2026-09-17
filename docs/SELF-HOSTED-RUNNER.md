# Dedicated self-hosted fallback runner

De runtime gebruikt een operationele branch: `runtime-requests`. De GitHub-hosted `resolve`-job valideert het immutable queue-request, legt de exacte trusted runtime-SHA vast en publiceert daarna `pending`.

Daarna probeert een GitHub-hosted `ubuntu-24.04` runner eerst de volledige kanaalacquisitie. Alleen wanneer het gevalideerde resultaat expliciete `access_blocked`-evidence bevat, start automatisch de dedicated self-hosted fallback.

## Vereiste labels

- `self-hosted`
- `linux`
- `x64`
- `webactueel-transcribe`

## Hostvereisten

Gebruik een dedicated Linux x64-machine of VM met normale outbound HTTPS-toegang, Python 3.12+, `curl` en GNU `sha256sum`. Gebruik deze host niet voor persoonlijke browserprofielen, SSH/cloudcredentials of andere gevoelige workloads.

De toolchain is exact gepind op yt-dlp nightly `2026.09.16.232951` en Deno `2.9.7`. `scripts/install_tools.sh` gebruikt een exact passende aanwezige binary of downloadt anders de vastgelegde release en verifieert SHA-256 voor installatie. yt-dlp wordt altijd via de lokale wrapper gestart die Deno expliciet meegeeft.

De runtime gebruikt geen cookies, accounts of proxy's. Als ook de normale verbinding van de dedicated host door YouTube wordt geblokkeerd, blijft het resultaat `access_blocked`.

## Wanneer fallback start

`scripts/classify_hybrid_result.py` activeert fallback alleen wanneer `access_blocked` zichtbaar is in een van deze gevalideerde bronnen:

- kanaaldiscovery (`result.status=access_blocked`);
- unresolved videometadata;
- captionstatus;
- commentstatus.

Een gewone `error` of een `partial` zonder access-block-evidence triggert de self-hosted runner niet. Dit voorkomt dat programmeerfouten of andere acquisitieproblemen stil op een andere machine opnieuw worden uitgevoerd.

## GitHub setup

Koppel de runner via repository Settings -> Actions -> Runners en voeg custom label `webactueel-transcribe` toe. Gebruik GitHub's actuele eenmalige registration token uit die setupflow; zet tokens nooit in deze repository of documentatie.

Als de GitHub-hosted poging slaagt, wordt deze runner niet gebruikt. Als fallback nodig is maar de runner offline is, blijft de fallbackjob queued en blijft commitstatus `runtime/Transcribe Public Source` op `pending` totdat de runner beschikbaar is.

## Queuepad

Een run start door precies een nieuw bestand toe te voegen:

`requests/queue/<request_id>.json`

```json
{
  "enabled": true,
  "request_id": "brian-coords-2026",
  "url": "https://www.youtube.com/@BrianCoords",
  "language": "auto"
}
```

De transportcommit mag niets anders wijzigen. De resolve-job checkt `main` uit, noteert `git rev-parse HEAD` en geeft die SHA door. Zowel de hosted attempt als een eventuele fallback checkt precies die SHA uit en faalt als de lokale readback niet overeenkomt.

## Uitvoering

De runtime normaliseert het kanaal naar `/videos`, inspecteert maximaal 1000 entries en verwerkt alleen video's met bewezen `upload_date` in 2026. Per gematchte video wordt een captiontrack gekozen en worden maximaal 7 top-level comments met `comment_sort=top` geprobeerd. Replies worden door yt-dlp met `max-depth=1` uitgesloten en daarna nogmaals gefilterd.

De self-hosted captioncache wordt hergebruikt na SHA/length-readback. GitHub-hosted runners zijn ephemeral en hebben geen persistente hostcache. Comments worden per run opnieuw opgehaald. Een commentfout blokkeert een geldig transcript niet, maar maakt het totale corpus `partial`. Metadatafouten blijven als `unresolved` zichtbaar. De geexporteerde processed-index bevat alleen current-run entries.

## Toolbootstrap controleren

```bash
bash scripts/install_tools.sh
tools/bin/yt-dlp --version
tools/bin/deno --version
```

De bootstrap faalt bij versie- of hashafwijking. Dezelfde bootstrap wordt door Toolkit Contract CI gecontroleerd.

## Rollback

1. Revert de hybride workflowcommit om terug te keren naar self-hosted-only gedrag.
2. Stop daarna desgewenst de runner-service/proces.
3. Verwijder de runner in GitHub Settings -> Actions -> Runners.
4. Verwijder de lokale runnerregistratie volgens GitHub's remove-instructie.
5. Laat bestaande queuebestanden staan als audittrail; herschrijf de transportgeschiedenis niet.

Een offline fallbackrunner heeft geen invloed op runs die al volledig op GitHub-hosted slagen.
