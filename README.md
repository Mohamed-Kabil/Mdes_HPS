# MDES Project

Outils de suivi des divergences entre les spécifications Mastercard MDES et
ce que PowerCARD implémente réellement. Deux volets, deux méthodes (voir
`README_GUIDE.md` pour une explication non technique du "pourquoi") :

1. **MDES Pre-Digitization** (`mc_divergence/`) — pipeline automatisé,
   spec Mastercard (`pre-dig.yaml`) vs spec interne (`data.yaml`).
2. **MDES Customer Service** (`mdes_cs_divergence_report.py`) — spec
   Mastercard (`mdes-customer-service.yaml`) vs extraction du code Java
   (`pwc-api-sp5_api`, projet externe — voir `MDES_CS_API_JAVA_MAPPING_LINK.md`).

Les deux sont consultables via un même tableau de bord web (`front/`).

## Installation

```
pip install -r requirements.txt
```

Dépendances : PyYAML, Flask, openpyxl.

## Secrets — à faire avant tout envoi d'email réel

```
cp mc_divergence/.env.example mc_divergence/.env
```

Puis remplir `mc_divergence/.env` avec de vraies valeurs (voir les
commentaires dans le fichier pour Gmail/Office365/mot de passe
d'application). **`.env` est gitignore — ne jamais le committer.**
`.env.example` (sans vraies valeurs) est le seul des deux versionné.

## Fichiers externes — pas vendorisés dans ce repo

Plusieurs fichiers volumineux ou partagés avec d'autres projets ne sont
**pas** copiés dans ce repo : ils sont référencés par chemin absolu (avec
variable d'environnement pour override), même logique que `.env`. Si vous
clonez ce repo sur une autre machine, il faut soit recréer ces fichiers aux
mêmes emplacements, soit pointer les variables d'environnement ailleurs.

| Fichier | Emplacement par défaut | Variable d'env | Rôle |
|---|---|---|---|
| `data.yaml` (spec PowerCARD-Acquirer, 150+ web services) | `C:\Users\moham\Desktop\input\data.yaml` | `DATA_YAML_PATH` | côté "implémenté" pour le volet 1 |
| `mdes-customer-service.yaml` (spec officielle Mastercard CS) | `C:\Users\moham\Desktop\input\mdes-customer-service.yaml` | `MDES_CS_SPEC_YAML` | côté "officiel" pour le volet 2 |
| `mdes_cs_api_schemas.generated.json` (extraction Java) | `C:\Users\moham\Downloads\pwc-api-sp5_api\Mdes_cs_api\generated\mdes_cs_api_schemas.generated.json` | `MDES_CS_MAPPING_JSON` | côté "implémenté" pour le volet 2, généré par un script qui vit dans le checkout `pwc-api-sp5_api`, pas ici (voir `MDES_CS_API_JAVA_MAPPING_LINK.md`) |

Sans ces fichiers aux bons emplacements, les routes correspondantes du
dashboard répondent 503 avec un message expliquant quoi régénérer/déplacer
— ce n'est pas une erreur silencieuse.

## Lancer le tableau de bord

```
python front/app.py
```

→ http://127.0.0.1:5000 — interface "Système de conformité réseaux"
(templates Jinja2, voir `front/INTEGRATION_NOTES.md`), avec deux "réseaux" :
MDES Pre-Digitization (volet 1) et MDES Customer Service (volet 2). Chacun a
6 sections dans sa sidebar : Comparaison, Releases, Email, Historique,
Configuration, Notes.

Comparaison/Releases ont chacun un lien "Actualiser l'analyse" qui
régénère le rapport Excel ; Email prépare un brouillon (objet/intro/
destinataires modifiables) avec confirmation explicite avant tout envoi
réel — jamais automatique. Le rapport xlsx joint apparaît aussi dans
Historique (les deux volets partagent `mc_divergence/reports/`).

**L'ancien tableau de bord** (JS/JSON, un seul écran) est archivé intact
dans `front_legacy/` — rien n'a été supprimé, juste remplacé comme frontend
actif. Voir `front/INTEGRATION_NOTES.md` pour le détail complet de ce qui a
changé, ce qui est nouveau (Historique réel, Notes, Parametres SMTP) et les
simplifications faites en cours de route.

## Vérification rapide après un clone

1. `pip install -r requirements.txt`
2. `cp mc_divergence/.env.example mc_divergence/.env` puis remplir
3. Vérifier/créer les 3 fichiers externes du tableau ci-dessus
4. `python front/app.py` puis ouvrir http://127.0.0.1:5000 — les deux
   réseaux (MDES Pre-Digitization, MDES Customer Service) doivent charger,
   Comparaison affichant les KPI/cartes dès la première visite (pas besoin
   de cliquer "Actualiser" — seule la donnée déjà en cache est utilisée sauf
   demande explicite)
5. `python mc_divergence/phase1_historical_audit.py --help`,
   `python mdes_cs_divergence_report.py --help` et
   `python mdes_cs_prereleases.py --help` pour confirmer que les imports
   se résolvent

## Écarts connus (pas des bugs de l'outil)

- **Token Update (volet 2)** : 2 champs `unresolved` dans l'extraction Java
  (roundtrip sérialisation/chiffrement que le scan mécanique ne peut pas
  suivre sans le modèle local). Détails et comment le résoudre dans
  `MDES_CS_API_JAVA_MAPPING_LINK.md`.
- **Search / Token Activate (volet 2)** : le chiffrement du payload
  (`EncryptedAccountInformation.*`) n'est réellement pas implémenté côté
  Java pour l'instant — confirmé par lecture du code source ET par la doc
  Mastercard elle-même. Pas un faux positif, voir même document.
- **`notifications.db`** (volet 1) n'existe pas tant que
  `phase1_historical_audit.py` n'a pas tourné au moins une fois — premier
  lancement = base de dédoublonnage vide.
- **Pas d'historique git** avant ce commit initial.

## Autres documents utiles

- `README_GUIDE.md` — explication non technique de ce que fait le projet et pourquoi.
- `MDES_CS_API_JAVA_MAPPING_LINK.md` — détail du volet 2 : comment l'extraction Java est générée, ses limites connues, et le résultat de vérifications manuelles du code source.
- `HANDOFF_JAVA_MAPPING_SCRIPT.md` — notes de conception pour reproduire ce type de script (spec vs code Java) sur une autre famille d'API.
- `mastercard_divergence_prompt.md`, `Modelisation.md` — contexte de conception du volet 1.
- `mdes_api_to_java_mapping.md` — mapping manuel (hand-curated, avec explications) des 6 endpoints Customer Service vers `java_mdes/*.java`, complémentaire à l'extraction générée du volet 2.
