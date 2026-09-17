# Dedicated self-hosted runner

De runtime gebruikt één operationele branch: `runtime-requests`. De GitHub-hosted `resolve`-job valideert het immutable queue-request en publiceert daarna `pending`. Alleen de daaropvolgende kanaalacquisitie draait op de dedicated self-hosted host.

## Vereiste labels

- `self-hosted`
- `linux`
- `x64`
- `webactueel-transcribe`

## Hostvereisten

Gebruik een dedicated Linux x64-machine of VM met normale outbound HTTPS-toegang, Python 3.12+, `curl` en GNU `sha256sum`. Gebruik deze host niet voor persoonlijke browserprofielen, SSH/cloudcredentials of andere gevoelige workloads.

De toolchain blijft exact gepind op yt-dlp `2026.08.20.234504` en Deno `2.9.5`. `scripts/install_tools.sh` gebruikt een exact passende aanwezige binary of downloadt anders de vastgelegde release en verifieert SHA-256 vóór installatie. yt-dlp wordt altijd via de lokale wrapper gestart die Deno expliciet meegeeft.

De runtime gebruikt geen cookies, accounts of proxy’s. Als YouTube de normale verbinding blokkeert, blijft het resultaat `access_blocked`.

## GitHub setup

Koppel de runner via repository Settings -> Actions -> Runners en voeg custom label `webactueel-transcribe` toe. Gebruik GitHub’s actuele eenmalige registration token uit die setupflow; zet tokens nooit in deze repository of documentatie.

Als de runner offline is, blijft de commitstatus `runtime/Transcribe Public Source` op `pending`; er wordt niet automatisch teruggevallen naar GitHub-hosted YouTube-acquisitie.

## Queuepad

Een run start door precies één nieuw bestand toe te voegen:

`requests/queue/<request_id>.json`

```json
{
  "enabled": true,
  "request_id": "brian-coords-2026",
  "url": "https://www.youtube.com/@BrianCoords",
  "language": "auto"
}
```

De transportcommit mag niets anders wijzigen. De self-hosted job checkt de transportbranch nooit uit; alleen `main` wordt uitgevoerd.

## Uitvoering

De runtime normaliseert het kanaal naar `/videos`, inspecteert maximaal 1000 entries en verwerkt alleen video’s met exacte uploaddatum in 2026. Per gematchte video wordt één captiontrack gekozen en worden maximaal 7 top-level comments met `comment_sort=top` geprobeerd; replies blijven uit.

Captioncache wordt op de host hergebruikt na SHA/length-readback. Comments worden per run opnieuw opgehaald. Een commentfout blokkeert een geldig transcript niet.

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
3. Verwijder de lokale runnerregistratie volgens GitHub’s remove-instructie.
4. Laat bestaande queuebestanden staan als audittrail; herschrijf de transportgeschiedenis niet.

Een niet-geregistreerde/offline runner veroorzaakt alleen een wachtende runtimejob; er is geen automatische cloudfallback.
