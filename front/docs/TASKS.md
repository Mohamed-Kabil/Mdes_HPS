
# Front — tasks (volet Mastercard / mc_divergence)

Petit frontend qui donne une vue web sur ce que `mc_divergence/` produit
aujourd'hui en ligne de commande : l'audit Phase 1 (adoption des 5 APIs
prioritaires) et l'alerte Phase 2 (dernière release Mastercard, impacte ou non
une API suivie). Rien de plus pour l'instant — pas de gestion d'utilisateurs,
pas de déploiement, usage local.

## Décisions par défaut (à valider avant de coder — dis-moi si tu veux autre chose)

- **Stack** : HTML/CSS/JS vanilla, pas de build step (pas de React/Vite) —
  suffisant pour un outil interne de cette taille, zéro dépendance à installer.
- **Backend** : petit serveur Python (Flask) dans `front/server.py`, qui
  importe directement les fonctions déjà écrites dans `mc_divergence/`
  (`phase1_historical_audit.py`, `phase2_job_a_new_release_alert.py`) plutôt
  que de les dupliquer — le frontend ne réimplémente aucune logique de
  parsing/diff/fetch, il consomme.
- **Pas de nouvelle DB** : le serveur lit les fichiers déjà produits
  (`reports/*.md`, `cache/known_releases.json`, `cache/notes_raw/*.md`) et
  peut relancer les scripts à la demande — pas de nouvel état persistant créé
  côté front.

Si tu préfères éviter un serveur Python (ex. tout-statique + relance manuelle
des scripts en CLI, le front ne fait que lire les fichiers `reports/`), on
peut aussi partir sur ça — dis-le à l'étape 1.

---

## Étapes

### 1. Backend minimal — exposer les données en JSON
- [ ] `front/server.py` (Flask) avec 3 routes en lecture seule pour commencer :
  - `GET /api/phase1` — dernier rapport Phase 1 (taux d'adoption global,
    statut par API prioritaire, liste des écarts) — parsé depuis
    `reports/phase1_divergence_report.md` ou en ré-exécutant `run()` en mémoire
  - `GET /api/phase2/latest` — résultat du dernier check de release (reprend
    `filter_relevant_releases(..., limit=1)` de `phase2_job_a_new_release_alert.py`)
  - `GET /api/reports` — liste des fichiers dans `reports/` avec date/taille
- [ ] Tester chaque route à la main (`curl`/navigateur) avant de toucher au front

### 2. Page Dashboard
- [ ] `front/index.html` + `front/style.css` + `front/app.js`
- [ ] Bloc "APIs prioritaires" : les 5 APIs (RequestActivationMethods,
  DeliverActivationCode, AuthoriseService, NotifyServiceActivated,
  NotifyTokenUpdated), statut coloré (🟢 implémenté / 🟡 partiel / 🔴 non
  implémenté) tiré de `/api/phase1`
- [ ] Bloc "Dernière release Mastercard" : version, date, type de note, APIs
  impactées, tiré de `/api/phase2/latest`

### 3. Détail d'un changement
- [ ] Clic sur un écart ouvre le détail : description, endpoint, table des
  champs (name/type/min/max/required) — même niveau de détail que ce qu'on a
  affiché en CLI

### 4. Actions
- [ ] Bouton "Vérifier la dernière release maintenant" → déclenche
  `POST /api/phase2/run` (ré-exécute le job A, avec option d'envoyer l'email
  ou non) et rafraîchit l'affichage
- [ ] Bouton "Relancer l'audit Phase 1" → `POST /api/phase1/run` (peut être
  lent — spinner / statut pendant l'exécution)

### 5. Historique
- [ ] Liste des rapports/emails déjà générés (`reports/`), consultables
  (rendu Markdown → HTML côté serveur ou lien de téléchargement)

---

## Hors scope pour cette première version
- Authentification / multi-utilisateur
- Déploiement (hébergement, HTTPS, etc.) — usage local uniquement
- Édition de `data.yaml` depuis le front
- Réintroduction de `notifications.db` / Job B (abandonnés — voir
  `mastercard_divergence_prompt.md`)
