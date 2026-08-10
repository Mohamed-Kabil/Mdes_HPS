# Prompt — Détection de divergences Mastercard MDES vs PowerCARD-Acquirer

## Contexte

Projet HPS Worldwide : détecter les écarts entre la documentation officielle Mastercard (MDES Pre-Digitization) et le YAML source de PowerCARD-Acquirer. Deux phases : (1) audit historique des divergences, (2) alerte email sur chaque nouvelle release Mastercard qui touche une des 5 APIs prioritaires.

Sources Mastercard :
- Spec actuelle : `https://static.developer.mastercard.com/content/mdes-pre-digitization/swagger/pre-dig.yaml`
- Release notes (tableau) : `https://developer.mastercard.com/mdes-pre-digitization/documentation/pre-release-notes/`
- Astuce : ajouter `/index.md` à n'importe quelle URL du portail Mastercard developer renvoie du markdown propre, sans scraping HTML.

Source interne : YAML extrait du code source PowerCARD-Acquirer (déjà géré par `diff_openapi_all.py`, avec résolution `$ref`, réparation YAML, diff structurel).

---

## APIs prioritaires

Les comparaisons (Phase 1) doivent traiter en priorité les APIs suivantes, avec les champs déjà identifiés comme changés à vérifier en premier lors du diff :

- **RequestActivationMethods** : `FundingAccountInfo.EncryptedPayload.EncryptedData.SourceTokenNumber`, `algorithmCypherMode`, `tag`, `aad` (impact potentiel sur le déchiffrement), `authRequestCorrelationId`, `authenticatorInfo`, `bindId`, `certifiedMFAAuthMethodId`, `deviceInfo`, `tokenRequestorDecisioningInfo`, `paymentData`, `recentAuthenticationInfo`, `reasonCodes` (nouvelles valeurs)
- **DeliverActivationCode** : `authRequestCorrelationId`, `deviceInfo`, `reasonCode` (nouvelles valeurs), `activationMethod.type` (nouvelles valeurs)
- **AuthoriseService** : `FundingAccountInfo.EncryptedPayload.EncryptedData.SourceTokenNumber`, `algorithmCypherMode`, `tag`, `aad`, `accountStatusInquirySentFor`, `sourceProvisioningData`, `provisioningContext`
- **Notify Service Activated** : `FundingAccountInfo.EncryptedPayload.EncryptedData.SourceTokenNumber`, `algorithmCypherMode`, `tag`, `aad`
- **NotifyTokenUpdated** : `authenticatorInfo`, `bindId`, `certifiedMFAAuthMethodId`, `bindingStatus`, `algorithmCypherMode`, `tag`, `aad` (impact potentiel sur le déchiffrement), `reasonCode` (nouvelles valeurs)

Ces cinq APIs partagent un pattern récurrent : les champs `EncryptedPayload.algorithmCypherMode/tag/aad` reviennent sur 4 des 5, donc traiter ce bloc comme une vérification transverse plutôt que répétée par API.

Traitement dans le pipeline :
- **Phase 1** : lors de l'étape 3 (diff par changement), trier la file de traitement pour que les changements touchant ces 5 APIs passent en premier, et les faire apparaître en tête du rapport et de l'email (section "APIs prioritaires" séparée du reste)

---

## Composants partagés

### 1. `fetch_mc_source.py`
- Récupère `pre-dig.yaml` (spec Mastercard actuelle) et le cache localement avec timestamp — **toujours re-téléchargé à chaque exécution de Phase 1**, jamais juste relu depuis le cache, pour que la dernière release Mastercard soit prise en compte automatiquement sans étape manuelle
- Récupère le tableau des release notes via `/index.md`, cache en JSON local

### 2. `parse_release_note.py`
- Prend une URL de release note, récupère son `/index.md`
- Parse en premier passage via regex/tableaux markdown
- Fallback Claude Haiku pour les notes au format incohérent
- Sortie structurée par note (une note peut contenir plusieurs changements) :
```json
{
  "version": "",
  "mdes_release": "",
  "published_date": "",
  "impacted_apis": [],
  "timeline": {"mtf_date": "", "production_date": ""},
  "changes": [
    {
      "title": "",
      "description": "",
      "endpoints": [],
      "fields": [{"name": "", "type": "", "min": "", "max": "", "required": true}]
    }
  ]
}
```

---

## Phase 1 — Audit historique (batch, exécution unique)

**Étapes :**
1. Re-télécharger `pre-dig.yaml` depuis Mastercard (toujours frais, jamais juste le cache local) et charger le tableau des release notes depuis le cutoff défini (ex. janvier 2025) jusqu'à aujourd'hui
2. Pour chaque note, appeler `parse_release_note.py` → obtenir la liste des changements
3. Pour chaque changement, comparer contre le YAML source PowerCARD actuel via le moteur de diff structurel de `diff_openapi_all.py` :
   - champ/endpoint présent et conforme → `implémenté`
   - présent mais divergent (type, longueur, requis) → `partiel`
   - absent → `non implémenté`
4. Générer un rapport de conformité :
   - par release : statut de chaque changement
   - vue globale : taux d'adoption, liste des écarts critiques
5. Envoyer un email à l'équipe avec le résumé des divergences (prioriser les `partiel` et `non implémenté`, ne pas noyer avec les `implémenté`)

**Livrable :** script `phase1_historical_audit.py` + rapport (markdown ou HTML) + email envoyé.

---

## Phase 2 — Alerte nouvelle release (récurrent)

**Étapes :**
1. Récupérer le tableau des release notes actuel
2. Ne vérifier que la dernière entrée du tableau (le tableau est trié du plus récent au plus ancien) — c'est ce qui en fait une alerte "nouvelle release" plutôt qu'un ré-audit de tout l'historique à chaque exécution
3. Parser la note via `parse_release_note.py` et vérifier si elle touche une des 5 APIs prioritaires
4. Si oui : envoyer immédiatement un email d'alerte (résumé des changements, endpoints, champs, timeline MTF/production). Si non : rien n'est envoyé
5. Ne jamais comparer au YAML PowerCARD dans ce job — notification pure

**Livrable :** script `phase2_job_a_new_release_alert.py`, exécuté par cron (fréquence à définir, ex. quotidien).

---

## Structure finale des fichiers

```
mc_divergence/
├── fetch_mc_source.py
├── parse_release_note.py
├── diff_openapi_all.py          # existant, réutilisé
├── send_email.py
├── phase1_historical_audit.py
├── phase2_job_a_new_release_alert.py
├── reports/
└── cache/
    ├── pre-dig.yaml
    └── known_releases.json
```

## Points à trancher avant implémentation
- Fréquence exacte du cron Job A
- Destinataires email (liste fixe ou escalade selon ancienneté du gap)
- Format d'envoi (SMTP direct vs Outlook/Graph selon l'infra HPS)
