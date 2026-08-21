# Repository governance

Deze repository is een minimale controlled runtime voor publieke YouTube-captions. `main` bevat alleen generieke runtimecode en geen echte requeststate.

## Main

Configureer Rulesets/branch protection voor `main` met minimaal:

- pull request vereist vóór merge;
- actuele Toolkit Contract, CodeQL, Dependency Audit en Repository Doctor checks vereist;
- branch up-to-date vóór merge;
- force pushes en branch deletion geblokkeerd;
- geen normale contributor-bypass.

## runtime-requests

`runtime-requests` is de enige operationele append-only transportbranch. Een geautomatiseerde requestcommit mag precies één nieuw `requests/queue/<request_id>.json` toevoegen en niets anders.

Bescherm deze branch tegen history rewrites, force-pushes en deletion. De workflow valideert het append-only contract nogmaals voordat het request wordt gebruikt.

## Self-hosted boundary

De GitHub-hosted job mag alleen transport/input valideren. YouTube-acquisitie draait uitsluitend op:

`[self-hosted, linux, x64, webactueel-transcribe]`

De self-hosted job voert nooit code vanaf `runtime-requests` uit en checkt uitsluitend `Yolol100/transcriberen@main` uit met persisted credentials uitgeschakeld.

De host blijft dedicated en bevat geen persoonlijke browserprofielen, SSH/cloudcredentials of andere projectsecrets.

Branch protection, Rulesets en runnerregistratie zijn externe repository-admincontroles en kunnen niet volledig door repositorycode worden afgedwongen.
