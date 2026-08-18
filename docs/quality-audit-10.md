# Formele 10-poort voor de Transcriberen runtime

## Benoemde scope

Deze audit beoordeelt de repository als **controlled-runtime voor publieke bronacquisitie en transcriptie**. De score gaat over code, veiligheidsgrenzen, reproduceerbaarheid, foutsemantiek, provenance, CI en onderhoudbaarheid.

Niet in de scoreclaim: universele beschikbaarheid van YouTube-captions vanaf iedere cloud-IP, juridische toestemming voor ieder extern brongebruik, semantische foutloosheid van broncaptions of automatische promotie naar projectwaarheid.

## 10/10 betekent hier

Een release-candidate krijgt alleen 10/10 wanneer op exact dezelfde PR-head alle toepasselijke poorten werkelijk zijn uitgevoerd en geslaagd:

1. **Correctheid** — normale routes, grenswaarden en regressies slagen; YouTube-video, kanaal en playlist worden juist gerouteerd.
2. **Fail-honest gedrag** — ontbrekende captions, toegangsblokkade, lokale verwerking, partial discovery en bewust niet-uitgevoerde items blijven afzonderlijke staten.
3. **Security** — publieke URL-gates, geen credentials/cookies/proxy, geen YouTube-audiofallback, XML DTD/entity-blokkade, commandotimeouts en resourcecaps zijn actief.
4. **Supply chain** — GitHub Actions op volledige commit-SHA; media-/transcriptieruntimes op SHA-256; de volledige productie-Python-wheelset is exact gepind en gehasht en wordt alleen met `--require-hashes --only-binary` geïnstalleerd; lock-drift en PyPA `pip-audit` zijn verplichte checks.
5. **Provenance/integriteit** — resultaat bindt canonical requesthash, commit en runtimebinarydigests; validator herberekent provenance en persisted content.
6. **CI/static analysis** — syntax, unit/negative tests, ShellCheck, toolkitcontract, CodeQL Python en CodeQL Actions slagen; CodeQL SARIF met security-severity `>= 7.0` blokkeert de check.
7. **Externe runtime-evidence** — availability probe draait op de kandidaathead; een upstream blokkade mag negatief bewijs zijn zolang de code die eerlijk rapporteert en geen verboden bypass inzet.
8. **Rollback** — vóór merge blijft `main` onaangeroerd en is het herstelpad het sluiten/niet mergen van de draft-PR. Na merge is de kleinste rollback een revert van de merge/squashcommit; bron- en artifactwrites blijven buiten deze repo en behouden hun eigen Webactueel-rollbackpoort.
9. **Monitoring/onderhoud** — wekelijkse availability probe, wekelijkse Dependabotchecks, periodieke CodeQL-scan en lock-driftcontrole bij dependencywijzigingen zijn geconfigureerd.
10. **Claimgrens** — geen GO/10-claim zolang een toepasselijke check rood/pending is, een critical/high securityprobleem openstaat of de kandidaathead sinds het bewijs is veranderd.

## Onafhankelijke online oracles, gecontroleerd 18 augustus 2026

- GitHub Docs: CodeQL ondersteunt afzonderlijk `python` en `actions` en adviseert een language matrix voor advanced setup.
- GitHub Docs: protected branches/rulesets kunnen required status checks en code-scanning merge protection afdwingen. Dit is repository-governance en staat buiten de bronpatch wanneer geen geschikte admin-writeactie beschikbaar is.
- GitHub Dependency Review Action 5.0.0 is gecontroleerd en geprobeerd; de echte run blokkeerde omdat Dependency Graph in deze repository niet is ingeschakeld. Dat is als onuitvoerbare repositoryinstelling vervangen door een uitvoerbare vulnerabilityscan, niet stilzwijgend genegeerd.
- PyPA `pip-audit` 2.10.1 is de actuele scanner voor bekende Python-packagekwetsbaarheden. De officiële `gh-action-pip-audit` v1.1.0 staat vast op geverifieerde commit `1220774d901786e6f652ae159f7b6bc8fea6d266`.
- GitHub CodeQL Action 4.37.3 staat vast op gecontroleerde commit `e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81`.
- pip Secure Installs: hash-checking mode is all-or-nothing; alle directe en transitieve requirements moeten gepind en gehasht zijn. De productie-installatie voldoet hieraan via `requirements.lock`.
- PyPI Trafilatura 2.1.0: de gekozen universele wheel in het lock heeft SHA-256 `0eded5207a806445ddebbe36eae30b9035fe6a2f233c36f6fe82663fca8b9d30`.

## Threat- en surfacegrens

De bronruntime is geen anoniem publiek endpoint. Uitvoering komt van een gecontroleerde wijziging aan `requests/transcribe.json` op `main` of van een handmatige GitHub workflowdispatch door iemand met repositoryrechten. Pull requests draaien de bronruntime zelf niet. Dat verlaagt de aanvalsvector voor willekeurige hostile URL-input, maar verandert de netwerkgrenzen niet: URLs en redirects worden op publieke adressen gecontroleerd, credentials/private doelen worden geweigerd en geërfde proxies zijn uitgeschakeld.

## Repository-governance follow-up

Na succesvolle checks is branch/ruleset-protectie voor `main` aanbevolen: vereis de unieke technische checks en eventueel CodeQL merge protection. Dit verandert de runtimecode niet en mag niet stilzwijgend worden geclaimd als ingesteld wanneer de gebruikte connector geen geschikte admin-writeactie biedt.

## Afsluitregel

De feitelijke score is geen handmatig ingevuld cijfer. Alleen de actuele GitHub-checks en runtime-evidence die bij dezelfde kandidaathead horen mogen deze scope op 10/10 zetten. GitHub kan PR-workflows op de door GitHub gegenereerde mergecandidate voor die head uitvoeren; een latere head maakt eerder bewijs stale en vereist een nieuwe volledige poort.
