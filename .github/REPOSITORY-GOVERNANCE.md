# Repository governance

Deze repository is een controlled runtime voor publieke YouTube-kanaalcaptions en begrensde commentcontext. `main` bevat alleen generieke runtimecode en geen echte requeststate.

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

## GitHub-hosted execution boundary

De productiequeue `Transcribe Public Source` valideert transport en voert de publieke kanaalacquisitie uitsluitend uit op **GitHub-hosted `ubuntu-24.04`**. Er is geen self-hosted runner, custom runner, uitwijkmachine of machinefallback.

De resolve-job legt eerst de vertrouwde `main`-commit-SHA vast. De acquisition-job checkt **exact die immutable SHA** uit en controleert hem vóór uitvoering. Code vanaf de transportbranch `runtime-requests` wordt nooit als runtime uitgevoerd. `persist-credentials: false` is verplicht.

Geen cookies, login, persoonlijke browserprofielen, accountkeys, proxies of CAPTCHA-/PO-token-bypass. Een `access_blocked` bij kernacquisitie is terminaal en activeert geen alternatieve machine. De aparte handmatige `Corpus Knowledge Review` gebruikt eveneens uitsluitend een GitHub-hosted runner met lokale modelinference en mag geen netwerkacquisitie of automatische Skill-/projectbronpromotie starten.

## Kanaalpolicy

De publieke capability is vast: `/videos`, alleen 2026, maximaal 1000 entries, maximaal 7 top-level comments per gematchte video, YouTube-side `top`, geen replies. Een verruiming hiervan vereist een expliciete productscopewijziging plus tests, contract- en threat-modelupdate.

Branch protection en Rulesets zijn externe repository-admincontroles en kunnen niet volledig door repositorycode worden afgedwongen.
