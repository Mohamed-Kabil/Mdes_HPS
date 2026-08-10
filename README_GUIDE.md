# Guide non technique — À quoi sert ce projet ?

## En une phrase

Ce projet compare automatiquement **ce que Mastercard dit que son API MDES
doit faire** avec **ce que PowerCARD (le produit) fait réellement**, pour
repérer les écarts avant qu'ils ne deviennent des bugs en production.

## C'est quoi, MDES ?

MDES = **Mastercard Digital Enablement Service**. C'est le système de
Mastercard qui gère les cartes tokenisées — par exemple quand une carte
bancaire est ajoutée à Apple Pay ou Google Pay, MDES est impliqué pour créer,
activer, suspendre ou supprimer le "token" qui remplace le numéro de carte
réel.

Mastercard publie une documentation (une "spécification") qui décrit
précisément comment leur API doit être appelée, quels champs sont attendus,
lesquels sont obligatoires, etc. PowerCARD (le produit sur lequel travaille
l'équipe) doit implémenter cette spécification correctement pour dialoguer
avec Mastercard.

**Le problème que ce projet résout** : Mastercard met régulièrement à jour sa
spécification (nouveaux champs, champs devenus obligatoires, nouvelles règles
de validation...). Si personne ne surveille ces mises à jour, PowerCARD peut
se retrouver à ne plus être conforme sans que personne ne s'en aperçoive —
jusqu'à ce qu'un appel réel échoue.

## Les deux volets de ce projet

Il y a en réalité **deux familles d'API Mastercard MDES** différentes,
traitées par deux méthodes différentes ici :

### 1. MDES "Pre-Digitization" — comparaison automatisée (`mc_divergence/`)

Ce sont les API utilisées pour l'enrôlement/gestion des cartes côté
"digitisation" (5 API suivies en priorité). Pour celles-ci, le projet a un
**pipeline automatisé** :

1. **Récupérer** la dernière spécification Mastercard et les dernières
   "notes de version" (les annonces de changement) publiées sur le site de
   Mastercard.
2. **Comparer** chaque changement annoncé avec ce que PowerCARD a réellement
   implémenté (`data.yaml`, qui décrit tout ce que le produit sait faire
   aujourd'hui).
3. **Classer** chaque changement : entièrement pris en compte, partiellement
   pris en compte, pas du tout pris en compte, ou "à vérifier à la main"
   (quand l'outil n'est pas sûr).
4. **Produire un rapport** lisible, et **envoyer un email** récapitulatif à
   l'équipe si demandé.
5. Garder en mémoire (petite base de données) quelles alertes ont déjà été
   traitées, pour ne pas prévenir deux fois de la même chose.

Un petit **tableau de bord web** (`front/`) permet de voir tout ça dans un
navigateur plutôt qu'en ligne de commande — c'est purement une vitrine sur ce
que `mc_divergence/` produit, il ne fait pas de calcul lui-même.

### 2. MDES "Customer Service" — désormais automatisé aussi (`mdes_cs_divergence_report.py`)

Ce sont d'autres API MDES (recherche de token, activation, mise à jour,
suspension, réactivation, suppression d'un token). Le point de départ a été
un mapping **manuel** : lire directement le code source Java de PowerCARD
pour identifier précisément *où*, dans le code, chacune de ces 6 opérations
est traitée, et documenter ce mapping dans un tableau
(`mdes_api_to_java_mapping.md`) — nécessaire parce qu'en interne, plusieurs
opérations Mastercard différentes sont parfois gérées par une seule et même
fonction du code (qui choisit quoi faire selon un paramètre reçu).

Ce mapping a ensuite été **automatisé** : un script (qui vit dans un autre
projet, `pwc-api-sp5_api` — voir `MDES_CS_API_JAVA_MAPPING_LINK.md`) scanne
le code Java et regénère ce mapping champ par champ. Ce projet-ci le compare
alors à la spécification officielle Mastercard
(`mdes_cs_divergence_report.py`), exactement comme le volet 1 compare
`pre-dig.yaml` à `data.yaml` — même tableau de bord, section séparée.

Limite connue : l'extraction Java automatique n'est pas garantie à 100 % —
certains champs restent marqués "non vérifiables" quand le scan ne peut pas
suivre le code (voir `MDES_CS_API_JAVA_MAPPING_LINK.md`). Le mapping manuel
(`mdes_api_to_java_mapping.md`) reste utile en complément : il explique le
*pourquoi* (règles métier, variantes de chiffrement) que le scan automatique
ne documente pas.

## Comment lire les résultats

- **`mc_divergence/reports/`** : les rapports déjà générés (format lisible,
  un par vérification passée). Chaque changement Mastercard y est classé par
  gravité.
- **Le tableau de bord (`front/`)** : la même information, mais dans un
  navigateur, avec la possibilité de relancer une vérification en cliquant un
  bouton plutôt qu'en tapant une commande.
- **`mdes_api_to_java_mapping.md`** : à lire pour comprendre, pour les 6 API
  "Customer Service", quel fichier/quelle fonction du code Java traite quoi.

## Qui doit s'en servir, et quand

- **Après chaque annonce Mastercard** (nouvelle version de leur API, note de
  version publiée) : relancer l'audit pour savoir si ça concerne PowerCARD et
  si c'est déjà géré.
- **Avant une certification / un contrôle de conformité Mastercard** :
  s'appuyer sur le dernier rapport pour savoir où sont les zones grises
  ("à vérifier manuellement").
- **Quand quelqu'un modifie le code PowerCARD qui touche à MDES** : relancer
  la comparaison pour vérifier qu'on ne s'est pas éloigné de la spec
  Mastercard involontairement.

## Ce que ce projet ne fait PAS (pour éviter les malentendus)

- Il ne modifie rien dans PowerCARD — il ne fait que comparer et signaler.
- Il ne remplace pas une revue humaine : certains écarts sont marqués
  "à vérifier manuellement" (ou "non vérifiable" côté Customer Service)
  quand l'outil n'est pas sûr à 100 %.
- Un écart signalé n'est pas toujours un bug : ça peut être un champ
  optionnel du spec que le client n'utilise juste jamais. Chaque écart
  mérite d'être vérifié au cas par cas avant d'être traité comme un
  problème réel (des exemples vérifiés à la main sont documentés dans
  `MDES_CS_API_JAVA_MAPPING_LINK.md`).
