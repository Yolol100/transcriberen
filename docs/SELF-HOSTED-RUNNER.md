# Dedicated self-hosted runner

De runtime gebruikt één operationele branch: `runtime-requests`. De GitHub-hosted `resolve`-job valideert het immutable queue-request. Alleen de daaropvolgende captionextractie draait op de dedicated self-hosted host.

## Vereiste labels

De runner moet alle labels hebben:

- `self-hosted`
- `linux`
- `x64`
- `webactueel-transcribe`

## Hostvereisten

Gebruik een dedicated Linux x64-machine of VM met normale outbound HTTPS-toegang, Python 3.12+, yt-dlp `2026.08.20.234504`, Deno `2.9.5` en GNU `sha256sum`. Gebruik deze host niet voor persoonlijke browserprofielen, SSH/cloudcredentials of andere gevoelige workloads.

De runtime gebruikt geen cookies, accounts of proxy's. Als YouTube de normale verbinding van deze host ook blokkeert, blijft het resultaat `access_blocked`.

## GitHub setup

Koppel de runner via repository Settings -> Actions -> Runners en voeg custom label `webactueel-transcribe` toe. Gebruik GitHub's actuele eenmalige registration token uit die setupflow; zet tokens nooit in deze repository of documentatie.

Start de runner volgens GitHub's gegenereerde instructies en controleer dat hij online staat voordat een request naar `runtime-requests` wordt gepusht.

## Queuepad

Een run start door precies één nieuw bestand toe te voegen:

`requests/queue/<request_id>.json`

Voorbeeld:

```json
{
  "enabled": true,
  "request_id": "caption-test-001",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "language": "auto"
}
```

De transportcommit mag niets anders wijzigen. De self-hosted job checkt de transportbranch nooit uit; alleen `main` wordt uitgevoerd.

## Rollback

1. Stop de runner-service/proces.
2. Verwijder de runner in GitHub Settings -> Actions -> Runners.
3. Verwijder de lokale runnerregistratie volgens GitHub's remove-instructie.
4. Laat bestaande queuebestanden staan als audittrail; herschrijf de transportgeschiedenis niet.

Een niet-geregistreerde/offline runner veroorzaakt alleen een wachtende runtimejob; er wordt niet automatisch teruggevallen naar GitHub-hosted YouTube-acquisitie.
