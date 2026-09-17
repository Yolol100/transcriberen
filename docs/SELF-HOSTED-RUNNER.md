# Dedicated self-hosted runner

De runtime gebruikt een operationele branch: `runtime-requests`. De GitHub-hosted `resolve`-job valideert het immutable queue-request, legt de exacte trusted runtime-SHA vast en publiceert daarna `pending`. Alleen de daaropvolgende kanaalacquisitie draait op de dedicated self-hosted host.

## Vereiste labels

- `self-hosted`
- `linux`
- `x64`
- `webactueel-transcribe`

## Hostvereisten

Gebruik een dedicated Linux x64-machine of VM met normale outbound HTTPS-toegang, Python 3.12+, `curl` en GNU `sha256sum`. Gebruik deze host niet voor persoonlijke browserprofielen, SSH/cloudcredentials of andere gevoelige workloads.

De toolchain is exact gepind op yt-dlp nightly `2026.09.16.232951` en Deno `2.9.7`. `scripts/install_tools.sh` gebruikt een exact passende aanwezige binary of downloadt anders de vastgelegde release en verifieert SHA-256 voor installatie. yt-dlp wordt altijd via de lokale wrapper gestart die Deno expliciet meegeeft.

De runtime gebruikt geen cookies, accounts of proxy's. Als YouTube de normale verbinding blokkeert, blijft het resultaat `access_blocked`.

## GitHub setup

Koppel de runner via repository Settings -> Actions -> Runners en voeg custom label `webactueel-transcribe` toe. Gebruik GitHub's actuele eenmalige registration token uit die setupflow; zet tokens nooit in deze repository of documentatie.

Als de runner offline is, blijft de commitstatus `runtime/Transcribe Public Source` op `pending`; er wordt niet automatisch teruggevallen naar GitHub-hosted YouTube-acquisitie.

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

De transportcommit mag niets anders wijzigen. De resolve-job checkt `main` uit, noteert `git rev-parse HEAD` en geeft die SHA door. De self-hosted job checkt precies die SHA uit en faalt als de lokale readback niet overeenkomt.

## Uitvoering

De runtime normaliseert het kanaal naar `/videos`, inspecteert maximaal 1000 entries en verwerkt alleen video's met bewezen `upload_date` in 2026. Per gematchte video wordt een captiontrack gekozen en worden maximaal 7 top-level comments met `comment_sort=top` geprobeerd. Replies worden door yt-dlp met `max-depth=1` uitgesloten en daarna nogmaals gefilterd.

Captioncache wordt op de host hergebruikt na SHA/length-readback. Comments worden per run opnieuw opgehaald. Een commentfout blokkeert een geldig transcript niet, maar maakt het totale corpus `partial`. Metadatafouten blijven als `unresolved` zichtbaar. De geexporteerde processed-index bevat alleen current-run entries.

## Toolbootstrap controleren

```bash
bash scripts/install_tools.sh
tools/bin/yt-dlp --version
tools/bin/deno --version
```

De bootstrap faalt bij versie- of hashafwijking. Dezelfde bootstrap wordt door Toolkit Contract CI gecontroleerd.

## Rollback

1. Stop de runner-service/proces.
2. Verwijder de runner in GitHub Settings -> Actions -> Runners.
3. Verwijder de lokale runnerregistratie volgens GitHub's remove-instructie.
4. Laat bestaande queuebestanden staan als audittrail; herschrijf de transportgeschiedenis niet.

Een niet-geregistreerde/offline runner veroorzaakt alleen een wachtende runtimejob; er is geen automatische cloudfallback.
