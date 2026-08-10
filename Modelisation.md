# Modélisation — Détection de divergences API (MDES & PowerCARD)

Ce document modélise l'ensemble du travail réalisé dans ce projet : deux chantiers de détection de divergences documentaires/structurelles entre spécifications d'API, partageant un même moteur de comparaison.

Diagrammes en **PlantUML** — à rendre via [plantuml.com/plantuml](http://www.plantuml.com/plantuml) (coller le bloc de code), l'extension VS Code "PlantUML", ou tout viewer markdown compatible.

---

## 1. Vue d'ensemble

Deux chantiers distincts, un moteur de diff commun :

```plantuml
@startuml
skinparam componentStyle rectangle

package "Chantier 1 — MDES Pre-Digitization (Mastercard)" {
  [pre-dig.yaml + release notes\n(developer.mastercard.com)] as MC1
  [data.yaml\n(PowerCARD-Acquirer, code source)] as MC2
}

package "Chantier 2 — CreateCreditCard (PowerCARD)" {
  [doc\n(export Fluid Topics)] as CC1
  [sandbox\n(spec générée)] as CC2
  [PDF\n(FT_api.pdf)] as CC3
}

component "Moteur commun\ndiff_openapi_all.py\n($ref resolution, structural diff)" as ENGINE
[Rapport MDES\n+ email + notifications.db] as REPORT1
[divergence_report.json\n(doc vs sandbox vs pdf)] as REPORT2

MC1 --> ENGINE
MC2 --> ENGINE
CC1 --> ENGINE
CC2 --> ENGINE
CC3 --> ENGINE

ENGINE --> REPORT1
ENGINE --> REPORT2
@enduml
```

---

## 2. Chantier 1 — Pipeline MDES (`mc_divergence/`)

### 2.1 Architecture des composants

```plantuml
@startuml
skinparam componentStyle rectangle

package "Sources externes" {
  [developer.mastercard.com\n/index.md trick] as A1
  [pre-dig.yaml\n(spec Mastercard actuelle)] as A2
}

package "mc_divergence" {
  [fetch_mc_source.py] as F
  [parse_release_note.py] as P
  [diff_openapi_all.py\n(réutilisé)] as D
  [phase1_historical_audit.py] as PH1
  [send_email.py] as SE
  database "notifications.db\n(SQLite)" as DB
}

[data.yaml\n(PowerCARD-Acquirer)] as DY
[reports/phase1_divergence_report.md] as Rapport
[reports/email divergence date - jj-mm-aa.md] as Email
[Boîte mail destinataire] as Boite

A1 --> F
A2 --> F
F --> PH1 : cache/known_releases.json\ncache/pre-dig.yaml\ncache/notes_raw/*.md
PH1 --> P
P --> PH1 : changements structurés\n{title, endpoints, fields}
PH1 --> D
DY --> D
D --> PH1
PH1 --> Rapport
PH1 --> Email
PH1 --> SE
SE --> Boite : SMTP réel
PH1 --> DB
@enduml
```

### 2.2 Modèle de données — un "changement" de release note

```plantuml
@startuml
class ReleaseNote {
  +version : string
  +mdes_release : string
  +published_date : string
  +impacted_apis : string[]
  +timeline : Timeline
  +changes : Change[]
}

class Timeline {
  +mtf_date : string
  +mtf_superseded : string[]
  +production_date : string
  +production_superseded : string[]
}

class Change {
  +title : string
  +description : string
  +endpoints : string[]
  +endpoints_inferred : bool
  +fields : Field[]
}

class Field {
  +name : string
  +description : string
  +type : string
  +min : string
  +max : string
  +required : bool
  +required_raw : string
}

class AuditedChange extends Change {
  +status : string
  +_is_priority : bool
  +endpoint_results : EndpointResult[]
}

class EndpointResult {
  +endpoint : string
  +endpoint_exists : bool
  +fields : FieldResult[]
  +status : string
}

class FieldResult {
  +name : string
  +status : string
  +matched_path : string
  +reasons : string[]
}

ReleaseNote "1" *-- "many" Change
ReleaseNote "1" *-- "1" Timeline
Change "1" *-- "many" Field
AuditedChange "1" *-- "many" EndpointResult
EndpointResult "1" *-- "many" FieldResult
@enduml
```

**Statuts possibles** (`STATUS_RANK`, du plus grave au moins grave) :
`non_implemente` (3) → `a_verifier_manuellement` (2) → `partiel` (1) → `implemente` (0)

### 2.3 Séquence — exécution de `phase1_historical_audit.py`

```plantuml
@startuml
actor Utilisateur as U
participant "phase1_historical_audit.py" as P1
participant "fetch_mc_source.py" as FMS
participant "parse_release_note.py" as PRN
participant "diff_openapi_all.py" as DOA
database "notifications.db" as DB
participant "send_email.py" as SE

U -> P1 : python phase1_historical_audit.py --send
P1 -> FMS : fetch_release_notes() / fetch_pre_dig_spec()
FMS --> P1 : cache/known_releases.json, cache/pre-dig.yaml
P1 -> P1 : load_releases_since(cutoff=2025-01)

loop pour chaque note depuis le cutoff
  P1 -> PRN : get_note_markdown(url) + parse_note(text)
  PRN --> P1 : [{title, endpoints, fields}, ...]
  P1 -> DOA : flatten_endpoint(data.yaml, path)
  DOA --> P1 : champs aplatis de data.yaml
  P1 -> P1 : find_matches() + compare_field()\n→ implemente/partiel/non_implemente/a_verifier
end

P1 -> DOA : audit_predig_vs_data_direct()\n(vérification structurelle directe, 5 API prioritaires)
DOA --> P1 : écarts fiables + mineurs (bruit filtré)
P1 -> P1 : render_report() + render_email_draft()
P1 -> DB : insert_pending_notifications()\n(status=pending, +90j)
P1 -> SE : send_email(subject, body, attachments=[rapport.md])
SE --> U : Email envoyé\n(ou erreur SMTP claire si config manquante)
@enduml
```

### 2.4 Modèle de la table `notifications` (SQLite)

```plantuml
@startuml
entity NOTIFICATIONS {
  * id : INTEGER <<PK, AUTOINCREMENT>>
  --
  version : TEXT
  change_title : TEXT
  impacted_apis : TEXT
  url : TEXT
  detected_at : TEXT
  notified_at : TEXT
  status : TEXT <<'pending' / 'implemented' / 'dismissed'>>
  next_check_at : TEXT
  reminder_count : INTEGER
}
@enduml
```

### 2.5 État d'avancement

| Composant | Statut |
|---|---|
| `fetch_mc_source.py` | ✅ Fait |
| `parse_release_note.py` | ✅ Fait (4 formats de tableau gérés) |
| `phase1_historical_audit.py` | ✅ Fait (audit note + vérification directe pre-dig.yaml) |
| `send_email.py` | ✅ Fait (SMTP réel, pièces jointes, `.env`) |
| `phase2_job_a_new_release_alert.py` | ❌ Pas fait |
| `phase2_job_b_recheck_sweep.py` | ❌ Pas fait |

---

## 3. Chantier 2 — CreateCreditCard (`credit card/`)

### 3.1 Architecture

```plantuml
@startuml
skinparam componentStyle rectangle

package "Sources" {
  [createcreditcard_v3.yaml\n(doc, export Fluid Topics)] as DOC
  [creditcardsand.yaml\n(sandbox, OpenAPI complet)] as SAND
  [FT_api.pdf\n(435 pages, doc technique)] as PDFRAW
}

[pdf_to_yaml.py\n(extracteur v1 — éprouvé)] as V1
[data_from_pdf_v4.yaml] as PDFYAML
[diff_openapi_all.py] as ENGINE
[divergence_report.json\n(+ classification manuelle\nINFO/LOW/MEDIUM/HIGH)] as REPORT

PDFRAW --> V1
V1 --> PDFYAML
DOC --> ENGINE
SAND --> ENGINE
PDFYAML --> ENGINE
ENGINE --> REPORT
@enduml
```

### 3.2 Résultat de la comparaison doc vs sandbox (fraîchement rejouée)

*(le rendu en camembert n'est pas supporté par le moteur PlantUML testé — tableau à la place)*

| Catégorie | Nombre | % du total (1317) |
|---|---:|---:|
| Bruit (`pattern`/`minLength`/`maxLength`/`required`) | 968 | 73.5% |
| `description_drift` (cosmétique) | 234 | 17.8% |
| `field_missing_in` (dont 68 = pattern `keyValues[]`) | 72 | 5.5% |
| `enum` | 18 | 1.4% |
| `format` | 17 | 1.3% |
| `type` | 2 | 0.2% |
| `required_set_mismatch` | 2 | 0.2% |
| `content_type_mismatch` | 1 | 0.1% |

### 3.3 Causes racines identifiées (signal réel, après filtrage du bruit)

| Cause | Détail |
|---|---|
| Pattern `keyValues[]` absent du sandbox | 68 occurrences à ~17 emplacements imbriqués différents — un seul vrai sujet, pas 68 |
| 4 champs isolés absents du sandbox | `communicationChannels[].channelContent`, `customerDetails.existingClient(+.bankCode,.clientCode)` |
| `required_set_mismatch` (requête) | doc exige `cardDetails`+`creditAccount`+`customerDetails`+`requestInfo` ; sandbox n'exige que 2 des 4 |
| `required_set_mismatch` (réponse 200) | doc exige `responseInfo` ; sandbox n'exige rien — **pattern répété : sandbox sous-documente systématiquement les réponses** |
| 2 `type` mismatch réels | `auxiliaryFeeAmount`, `numberOfDependents` : `string` (doc) vs `number` (sandbox) |
| 2 `format` mismatch réels | `tmpPreferenceStartDate`/`tmpPrefernceEndDate` : `date` (doc) vs `date-time` (sandbox) |
| 17 `enum` où sandbox est plus précis | doc ne liste aucune valeur, sandbox si (ex. `phoneType: [0-4]`, `gender: [M,F,N]`) — **doc à enrichir** |

### 3.4 Le PDF — un vocabulaire différent, pas la même API renommée

```plantuml
@startuml
skinparam componentStyle rectangle

package "FT_api.pdf (legacy PowerCARD)" {
  [RqUID] as RQ
  [Card] as CARD
  [PersonInfo] as PI
  [CrdAcctInfo] as CAI
  [FileNumber] as FN
  [CustomerInformation] as CI
  [MerchantInformation] as MI
}

package "doc/sandbox (API REST actuelle)" {
  [requestInfo.requestUID] as RI
  [cardDetails] as CD
  [customerDetails] as CUD
  [creditAccount] as CRA
  [? aucun équivalent identifié] as AUCUN1
  [? aucun équivalent identifié] as AUCUN2
}

RQ ..> RI : mapping confirmé
CARD ..> CD : mapping confirmé
PI ..> CUD : mapping confirmé
CAI ..> CRA : mapping confirmé
FN ..> AUCUN1 : non résolu
CI ..> AUCUN2 : non résolu
MI ..> AUCUN2 : non résolu
@enduml
```

---

## 4. Chantier 3 (préparatoire) — Nouveau PDF confidentiel

Document décrit mais jamais vu (confidentialité) — extracteur écrit à l'aveugle, **jamais testé**.

```plantuml
@startuml
skinparam componentStyle rectangle

package "Structure décrite (8 sections par endpoint)" {
  [Overview] as S1
  [Functional description\n+ image] as S2
  [Version] as S3
  [Request Message\n(6 col: # / Field Name / Data type\n/ Parent / Occurrence / Field Description)] as S4
  [Response Message\n(mêmes 6 colonnes)] as S5
  [Specific Error Codes] as S6
  [RESTful Response Codes\n(Status / Description / Success x / Error x)] as S7
  [Consuming a RESTful API\n(URI / Method / Params) + exemple] as S8
}

[pdf_to_yaml_v2.py] as V2
[YAML de sortie\n(jamais validé contre le vrai fichier)] as OUT

S1 --> V2
S2 --> V2 : extraction image
S3 --> V2
S4 --> V2 : arbre reconstruit via colonne Parent\n(confirmé : Parent = nom du champ parent)
S5 --> V2
S6 --> V2
S7 --> V2 : x/x → success: bool
S8 --> V2 : pilote le vrai path + method
V2 --> OUT
@enduml
```

**Différence clé vs v1** : la hiérarchie ne dépend plus des liens hypertexte vers des tables "Complex Type: X" — chaque ligne indique directement son parent par son nom de champ. L'ancien mécanisme est conservé en repli uniquement.

**État** : script écrit et syntaxiquement valide, **zéro exécution réussie** — le PDF réel est confidentiel et non accessible dans cette session. Toute incertitude de structure (libellés de section, seuil de taille de police pour distinguer un titre d'un en-tête de tableau) est signalée par des `WARNING` explicites sur `stderr`, jamais silencieuse.

---

## 5. Récapitulatif des scripts du projet

| Fichier | Rôle | Statut |
|---|---|---|
| `diff_openapi_all.py` | Moteur de diff générique (2+ sources, $ref resolution, réparation YAML) | ✅ Éprouvé, réutilisé partout |
| `pdf_to_yaml.py` | Extraction PDF → YAML (ancienne structure, `FT_api.pdf`) | ✅ Éprouvé |
| `pdf_to_yaml_v2.py` | Extraction PDF → YAML (nouvelle structure avec Parent, confidentielle) | ⚠️ Jamais testé |
| `check_field_changes.py` | Vérification champ-par-champ ciblée (liste de changements manuels) | ✅ Fait |
| `diff_predig_vs_data.py` | Diff direct `pre-dig.yaml` ↔ `data.yaml` (résolution des `$ref` niveau conteneur) | ✅ Fait |
| `mc_divergence/fetch_mc_source.py` | Récupération + cache des sources Mastercard | ✅ Fait |
| `mc_divergence/parse_release_note.py` | Parsing des notes de release (4 formats de tableau) | ✅ Fait |
| `mc_divergence/phase1_historical_audit.py` | Orchestration Phase 1 complète | ✅ Fait |
| `mc_divergence/send_email.py` | Envoi SMTP réel avec pièces jointes | ✅ Fait |
| `mc_divergence/phase2_job_a_new_release_alert.py` | Alerte nouvelle release (Phase 2) | ❌ À faire |
| `mc_divergence/phase2_job_b_recheck_sweep.py` | Relance des rappels à échéance (Phase 2) | ❌ À faire |

---

## 6. Diagramme de cas d'utilisation — vue d'ensemble du projet

Couvre les 3 chantiers et leurs acteurs (utilisateur, source externe Mastercard, transport email). Les cas non encore implémentés (Phase 2) sont marqués explicitement.

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle

actor "Utilisateur / Stagiaire" as User
actor "Serveur SMTP" as SMTP
actor "Destinataire email" as Dest
rectangle "Mastercard\n(developer.mastercard.com)\n(source externe)" as MC

rectangle "Pipeline MDES (mc_divergence/)" {
  usecase "Récupérer les sources Mastercard" as UC1
  usecase "Parser une note de release" as UC2
  usecase "Auditer un changement vs data.yaml" as UC3
  usecase "Vérifier pre-dig.yaml vs data.yaml\n(diff structurel direct)" as UC4
  usecase "Générer le rapport de divergence" as UC5
  usecase "Générer le brouillon d'email" as UC6
  usecase "Envoyer l'email (avec pièce jointe)" as UC7
  usecase "Gérer les notifications\n(insertion / dédoublonnage SQLite)" as UC8
  usecase "(Non fait) Alerter une nouvelle release" as UC8a
  usecase "(Non fait) Relancer un rappel à échéance" as UC8b
}

rectangle "Comparaison CreateCreditCard\n(doc / sandbox / pdf)" {
  usecase "Extraire le PDF\n(ancienne structure, pdf_to_yaml.py)" as UC9
  usecase "Comparer doc / sandbox / pdf" as UC10
  usecase "Classifier les divergences\n(fiable vs bruit)" as UC11
  usecase "Construire un mapping\nlegacy PowerCARD ↔ REST" as UC12
}

rectangle "Extraction PDF confidentiel\n(pdf_to_yaml_v2.py)" {
  usecase "Diagnostiquer la structure\n(--dump-headers)" as UC13
  usecase "Extraire un endpoint isolé\n(--endpoint, debug)" as UC14
  usecase "Extraire le document complet\n(--extract)" as UC15
}

User --> UC1
User --> UC2
User --> UC3
User --> UC5
User --> UC7
User --> UC9
User --> UC10
User --> UC11
User --> UC12
User --> UC13
User --> UC14
User --> UC15

MC --> UC1

UC1 ..> UC2 : <<include>>
UC2 ..> UC3 : <<include>>
UC3 ..> UC4 : <<extend>>
UC3 ..> UC8 : <<include>>
UC3 ..> UC5 : <<include>>
UC5 ..> UC6 : <<include>>
UC6 ..> UC7 : <<extend>>
UC7 --> SMTP
SMTP --> Dest

UC8 ..> UC8a : <<extend>>
UC8 ..> UC8b : <<extend>>
UC8a ..> UC6 : <<include>>
UC8b ..> UC6 : <<include>>

UC9 ..> UC10 : <<include>>
UC10 ..> UC11 : <<include>>
UC11 ..> UC12 : <<extend>>
UC12 ..> UC6 : <<include>>

UC13 ..> UC14 : <<extend>>
UC14 ..> UC15 : <<extend>>
UC15 ..> UC6 : <<include>>
@enduml
```

---

## 7. Diagramme de cas d'utilisation — Pipeline MDES uniquement

Version isolée du chantier Mastercard seul (sans CreateCreditCard ni l'extraction PDF confidentielle), pour une lecture ciblée.

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle

actor "Utilisateur / Stagiaire" as User
actor "Serveur SMTP" as SMTP
actor "Destinataire email" as Dest
rectangle "Mastercard\n(developer.mastercard.com)\n(source externe)" as MC

rectangle "Pipeline MDES (mc_divergence/)" {
  usecase "Récupérer les sources Mastercard" as UC1
  usecase "Parser une note de release" as UC2
  usecase "Auditer un changement vs data.yaml" as UC3
  usecase "Vérifier pre-dig.yaml vs data.yaml\n(diff structurel direct)" as UC4
  usecase "Générer le rapport de divergence" as UC5
  usecase "Générer le brouillon d'email" as UC6
  usecase "Envoyer l'email (avec pièce jointe)" as UC7
  usecase "Gérer les notifications\n(insertion / dédoublonnage SQLite)" as UC8
  usecase "(Non fait) Alerter une nouvelle release" as UC8a
  usecase "(Non fait) Relancer un rappel à échéance" as UC8b
}

User --> UC1
User --> UC2
User --> UC3
User --> UC5
User --> UC7

MC --> UC1

UC1 ..> UC2 : <<include>>
UC2 ..> UC3 : <<include>>
UC3 ..> UC4 : <<extend>>
UC3 ..> UC8 : <<include>>
UC3 ..> UC5 : <<include>>
UC5 ..> UC6 : <<include>>
UC6 ..> UC7 : <<extend>>
UC7 --> SMTP
SMTP --> Dest

UC8 ..> UC8a : <<extend>>
UC8 ..> UC8b : <<extend>>
UC8a ..> UC6 : <<include>>
UC8b ..> UC6 : <<include>>
@enduml
```

---

## 8. Diagramme de classes — CreateCreditCard (doc / sandbox / pdf)

```plantuml
@startuml
skinparam classAttributeIconSize 0

class SourceSpecification {
  +etiquette : string
  +chemin_fichier : string
  +format : string
  --
  {type : doc | sandbox | pdf}
}

class PointDeTerminaison {
  +chemin : string
  +methode : string
  +idOperation : string
}

class SchemaChamp {
  +nom : string
  +type : string
  +longueurMin : int
  +longueurMax : int
  +motif : string
  +valeursEnum : string[]
  +requis : bool
  +description : string
}

class Divergence {
  +champ : string
  +categorie : string
  +valeurs : map<string,string>
  --
  {non_implemente | partiel | implemente}
}

class ClassificationBruit {
  +fiable : bool
  +attributsBruyants : string[]
  --
  {minLength/required = bruit connu}
}

class RapportDivergence {
  +totalDivergences : int
  +genereLe : string
}

class MappingChampLegacy {
  +nomChampPdf : string
  +nomChampRest : string
  +confiance : string
  --
  {mapping_confirme | non_resolu}
}

SourceSpecification "1" *-- "many" PointDeTerminaison
PointDeTerminaison "1" *-- "many" SchemaChamp
RapportDivergence "1" *-- "many" Divergence
Divergence "1" --> "1" ClassificationBruit
Divergence "2..3" --> "1" SchemaChamp : compare
MappingChampLegacy "many" --> "1" SchemaChamp : PDF
MappingChampLegacy "many" --> "1" SchemaChamp : REST
@enduml
```

---

## 9. Diagramme de classes — Mastercard MDES (enrichi)

Reprend et enrichit le modèle de la section 2.2 en ajoutant les classes utilisées par `field_changes_vs_data_report.py` (`ApiFieldChangeEntry`, `PreDigFieldDefinition`, `DataYamlFieldDefinition`).

```plantuml
@startuml
skinparam classAttributeIconSize 0

class NoteDeRelease {
  +version : string
  +releaseMdes : string
  +datePublication : string
  +apisImpactees : string[]
}

class Chronologie {
  +dateMtf : string
  +dateMtfRemplacee : string[]
  +dateProduction : string
  +dateProductionRemplacee : string[]
}

class Changement {
  +titre : string
  +description : string
  +endpoints : string[]
  +endpointsInferes : bool
}

class ChampNote {
  +nom : string
  +description : string
  +type : string
  +min : string
  +max : string
  +requis : bool
}

class EntreeChangementChampApi {
  +endpoint : string
  +cheminChamp : string
  +typeChangement : string
  +commentaire : string
  --
  {source : api_field_changes.md}
}

class DefinitionChampPreDig {
  +type : string
  +longueurMin : int
  +longueurMax : int
  +requis : bool
  --
  {resolu depuis pre-dig.yaml}
}

class DefinitionChampDataYaml {
  +type : string
  +longueurMin : int
  +longueurMax : int
  +requis : bool
  --
  {resolu depuis data.yaml}
}

class ChangementAudite extends Changement {
  +statut : string
  +estPrioritaire : bool
}

class ResultatEndpoint {
  +endpoint : string
  +endpointExiste : bool
  +statut : string
}

class ResultatChamp {
  +nom : string
  +statut : string
  +cheminTrouve : string
  +raisons : string[]
  --
  {non_implemente | partiel |\na_verifier_manuellement | implemente}
}

NoteDeRelease "1" *-- "many" Changement
NoteDeRelease "1" *-- "1" Chronologie
Changement "1" *-- "many" ChampNote
ChangementAudite "1" *-- "many" ResultatEndpoint
ResultatEndpoint "1" *-- "many" ResultatChamp

EntreeChangementChampApi "1" --> "1" DefinitionChampPreDig : resout
EntreeChangementChampApi "1" --> "1" DefinitionChampDataYaml : compare
DefinitionChampPreDig "1" -- "1" DefinitionChampDataYaml : compare_attrs()
@enduml
```

---

## 10. Diagramme de cas d'utilisation — Comparaison CreateCreditCard uniquement

Version isolée du chantier CreateCreditCard seul (sans MDES ni l'extraction PDF confidentielle). Un seul acteur : pas de source externe active (les 3 fichiers doc/sandbox/pdf sont déjà en place), pas de flux email/SMTP pour ce chantier. Les cas marqués "(Non fait)" sont recommandés mais jamais réalisés dans cette session.

```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle

actor "Utilisateur / Stagiaire" as User

rectangle "Comparaison CreateCreditCard (doc / sandbox / pdf)" {
  usecase "Extraire le PDF\n(ancienne structure, pdf_to_yaml.py)" as UC1
  usecase "Comparer doc / sandbox / pdf\n(diff_openapi_all.py)" as UC2
  usecase "Classifier les divergences\n(fiable vs bruit)" as UC3
  usecase "Construire un mapping\nlegacy PowerCARD ↔ REST" as UC4
  usecase "(Non fait) Vérifier empiriquement\nles contradictions type/format" as UC5
  usecase "(Non fait) Enrichir doc avec\nles enum/format manquants" as UC6
  usecase "Générer le rapport\n(divergence_report.json)" as UC7
}

User --> UC1
User --> UC2
User --> UC3
User --> UC4
User --> UC5
User --> UC6

UC1 ..> UC2 : <<include>>
UC2 ..> UC3 : <<include>>
UC3 ..> UC7 : <<include>>
UC3 ..> UC4 : <<extend>>
UC3 ..> UC5 : <<extend>>
UC3 ..> UC6 : <<extend>>
@enduml
```

---

## 11. Diagramme de séquence — Comparaison à 3 inputs (docs / Fluid Topics / data.yaml)

Diagramme de conception — cette combinaison précise de sources n'a pas été exécutée dans cette session, il modélise le flux prévu. `Fluid Topics` = `FT_api.pdf` (le nom du fichier signifie "Fluid Topics API"), extrait au préalable en YAML structuré via `pdf_to_yaml.py`.

```plantuml
@startuml
actor "Utilisateur / Stagiaire" as User
participant "pdf_to_yaml.py" as Extractor
participant "diff_openapi_all.py" as Engine
database "docs\n(createcreditcard_v3.yaml)" as Docs
database "Fluid Topics\n(FT_api.pdf)" as FluidPdf
database "data.yaml" as Data

User -> Extractor : python pdf_to_yaml.py FT_api.pdf --extract
Extractor -> FluidPdf : lecture (PyMuPDF + pdfplumber)
FluidPdf --> Extractor : texte + tableaux bruts (435 pages)
Extractor --> User : data_from_pdf_v4.yaml\n(YAML structuré)

User -> Engine : python diff_openapi_all.py\ndoc=createcreditcard_v3.yaml\npdf_doc=data_from_pdf_v4.yaml\ndata=data.yaml

Engine -> Docs : load_spec() + repair_first_list_item_indentation()
Docs --> Engine : schéma doc résolu

Engine -> Engine : load_spec(data_from_pdf_v4.yaml)\n(sortie de pdf_to_yaml.py, déjà structurée)

Engine -> Data : load_spec()
Data --> Engine : schéma data.yaml résolu

Engine -> Engine : normalize_path_key()\n(fait correspondre les endpoints entre les 3 sources\nmalgré des chemins/versions différents)

loop pour chaque endpoint commun
  Engine -> Engine : resolve_refs()\n(sur les 3 schémas)
  Engine -> Engine : flatten_schema()\n(aplati properties/required/type/enum/pattern)
  Engine -> Engine : diff_field_sets()\n(compare champ par champ, 3 sources)
end

Engine --> User : divergence_report.json\n(champ manquant / attribut différent / description différente)
@enduml
```

---

## 12. Diagramme d'activité avec couloirs (équivalent BPMN) — Pipeline MDES

PlantUML n'a pas de vraie notation BPMN 2.0 native (pas de pools/lanes/gateways BPMN) — ceci est un diagramme d'activité UML avec couloirs, visuellement équivalent (mêmes losanges de décision, mêmes couloirs par rôle), reflétant fidèlement la logique réelle de `phase1_historical_audit.py` (`audit_change()`, `compare_field()`, le flag `--send`, la gestion d'erreur SMTP).

Deux flux distincts : le premier couvre la vérification structurelle directe par endpoint ; le second couvre le filtrage des notes de release pertinentes avant de passer au traitement email.

### Flux 1 — Vérification structurelle directe (endpoints, sans passer par les notes)

```plantuml
@startuml
|Utilisateur|
start
:Lancer\npython phase1_historical_audit.py --send;

|phase1_historical_audit.py|
:Charger pre-dig.yaml depuis le site web\n(developer.mastercard.com);
:Charger les 5 API prioritaires utilisées\n(RAM, DAC, AS, NSA, NTU);
:Extraire les schémas complets de ces 5 API\ndepuis pre-dig.yaml;
:Charger data.yaml;

repeat
  :Chercher le champ dans data.yaml\n(find_matches);
  if (Champ trouvé ?) then (oui)
    if (Type / min / max / required identiques ?) then (oui)
      :Statut = implemente;<<#lightgreen>>
    else (non)
      :Statut = partiel;<<#orange>>
    endif
  else (non)
    :Statut = non_implemente;<<#red>>
  endif
repeat while (encore des endpoints à traiter ?) is (oui) not (non)

:Générer le rapport (render_report);
:Générer le brouillon d'email (render_email_draft);

|phase1_historical_audit.py|
if (Flag --send ?) then (oui)
  |send_email.py|
  if (SMTP_HOST / USER / PASSWORD présents ?) then (oui)
    :Envoyer l'email réel avec pièce jointe;
    |Destinataire|
    :Réceptionner l'email;
  else (non)
    :Erreur SMTP claire, exit 1;<<#red>>
  endif
else (non)
  |phase1_historical_audit.py|
  :Garder uniquement le fichier local\n(email divergence date - jj-mm-aa.md);
endif

stop
@enduml
```

### Flux 2 — `releases_check()` : filtrage des notes de release pertinentes

Le process email n'est pas un placeholder — c'est littéralement le même bloc que dans le Flux 1 (génération du rapport, brouillon email, insertion notifications, envoi SMTP).

```plantuml
@startuml
|Utilisateur|
start
:Lancer\nreleases_check();

|releases_check()|
:Charger les release notes depuis le cutoff;
:Parser une note de release;

if (La note concerne une des 5 API utilisées ?) then (non)
  :Fin du traitement de cette note;<<#red>>
  stop
else (oui)
endif

:Générer le rapport (render_report);
:Générer le brouillon d'email (render_email_draft);

|releases_check()|
if (Flag --send ?) then (oui)
  |send_email.py|
  if (SMTP_HOST / USER / PASSWORD présents ?) then (oui)
    :Envoyer l'email réel avec pièce jointe;
    |Destinataire|
    :Réceptionner l'email;
  else (non)
    :Erreur SMTP claire, exit 1;<<#red>>
  endif
else (non)
  |releases_check()|
  :Garder uniquement le fichier local\n(email divergence date - jj-mm-aa.md);
endif

stop
@enduml
```
