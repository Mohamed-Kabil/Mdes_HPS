# MDES Customer Service — écarts spec officiel vs implémentation Java (auto-généré)

Spec officiel : `C:\Users\moham\Desktop\input\mdes-customer-service.yaml`
Extraction Java : `C:\Users\moham\Downloads\pwc-api-sp5_api\Mdes_cs_api\generated\mdes_cs_api_schemas.generated.json` (générée le 2026-08-07T10:32:39)

`non_implemente` = champ du spec absent de tout ce que le code Java construit actuellement. `non_verifiable` = un champ Java correspondant existe mais son identité n'a pas pu être résolue (voir MDES_CS_API_JAVA_MAPPING_LINK.md) — écart dans la donnée, pas une absence confirmée. `partiel` = résolu par le modèle local plutôt que par un scan direct. `implemente` = trouvé directement.

## Search — `POST /{id}/search`
35 champ(s) au total — 14 implémenté(s), 0 partiel(s), 0 non vérifiable(s), 21 non implémenté(s).

| Champ (spec officiel) | Statut | Requis | Champ Java correspondant |
|---|---|---|---|
| `CommentId` | non_implemente | non | — |
| `CompactResponse` | non_implemente | non | — |
| `CountryCode` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.AlternateAccountIdentifier` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.FinancialAccountId` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.Token` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.VirtualCardNumber` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedKey` | non_implemente | oui | — |
| `EncryptedAccountInformation.Iv` | non_implemente | non | — |
| `EncryptedAccountInformation.OaepHashingAlgorithm` | non_implemente | oui | — |
| `EncryptedAccountInformation.PublicKeyFingerprint` | non_implemente | oui | — |
| `EncryptedAccountInformation.aad` | non_implemente | non | — |
| `EncryptedAccountInformation.algorithmCipherMode` | non_implemente | non | — |
| `EncryptedAccountInformation.tag` | non_implemente | non | — |
| `InterbankCardAssociationId` | non_implemente | non | — |
| `PageInfo` | non_implemente | non | — |
| `PageInfo.Limit` | non_implemente | oui | — |
| `PageInfo.Offset` | non_implemente | oui | — |
| `TokenRequestorId` | non_implemente | non | — |
| `TokenStatusCodes` | non_implemente | non | — |
| `TokenTypes` | non_implemente | non | — |

## Token Activate — `POST /{id}/token/activate`
24 champ(s) au total — 8 implémenté(s), 0 partiel(s), 0 non vérifiable(s), 16 non implémenté(s).

| Champ (spec officiel) | Statut | Requis | Champ Java correspondant |
|---|---|---|---|
| `EncryptedAccountInformation` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData` | non_implemente | oui | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.AccountPan` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.AlternateAccountIdentifier` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.FinancialAccountId` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.Token` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.VirtualCardNumber` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedKey` | non_implemente | oui | — |
| `EncryptedAccountInformation.Iv` | non_implemente | non | — |
| `EncryptedAccountInformation.OaepHashingAlgorithm` | non_implemente | oui | — |
| `EncryptedAccountInformation.PublicKeyFingerprint` | non_implemente | oui | — |
| `EncryptedAccountInformation.aad` | non_implemente | non | — |
| `EncryptedAccountInformation.algorithmCipherMode` | non_implemente | non | — |
| `EncryptedAccountInformation.tag` | non_implemente | non | — |
| `PaymentAppInstanceId` | non_implemente | non | — |

## Token Update — `POST /{id}/token/update`
33 champ(s) au total — 1 implémenté(s), 0 partiel(s), 1 non vérifiable(s), 31 non implémenté(s).

| Champ (spec officiel) | Statut | Requis | Champ Java correspondant |
|---|---|---|---|
| `AuditInfo` | non_verifiable | oui | AuditInfo |
| `AuditInfo.Organization` | non_implemente | oui | — |
| `AuditInfo.Phone` | non_implemente | non | — |
| `AuditInfo.UserId` | non_implemente | oui | — |
| `AuditInfo.UserName` | non_implemente | oui | — |
| `CurrentFinancialAccountInformation` | non_implemente | non | — |
| `CurrentFinancialAccountInformation.CountryCode` | non_implemente | non | — |
| `CurrentFinancialAccountInformation.InterbankCardAssociationId` | non_implemente | non | — |
| `EncryptedAccountInformation` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData` | non_implemente | oui | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.AccountPan` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.AlternateAccountIdentifier` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.FinancialAccountId` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.Token` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.CurrentAccount.VirtualCardNumber` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.NewAccount` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.NewAccount.AccountPan` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.NewAccount.AccountPanSequenceNumber` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.NewAccount.ExpirationDate` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedData.NewAccount.NewFinancialAccountId` | non_implemente | non | — |
| `EncryptedAccountInformation.EncryptedKey` | non_implemente | oui | — |
| `EncryptedAccountInformation.Iv` | non_implemente | non | — |
| `EncryptedAccountInformation.OaepHashingAlgorithm` | non_implemente | oui | — |
| `EncryptedAccountInformation.PublicKeyFingerprint` | non_implemente | oui | — |
| `EncryptedAccountInformation.aad` | non_implemente | non | — |
| `EncryptedAccountInformation.algorithmCipherMode` | non_implemente | non | — |
| `EncryptedAccountInformation.tag` | non_implemente | non | — |
| `IssuerProductConfigurationId` | non_implemente | non | — |
| `RemoveAlternateAccountIdentifierSuffix` | non_implemente | non | — |
| `TokenUniqueReference` | non_implemente | non | — |
| `UpdateWalletProviderIndicator` | non_implemente | non | — |

## Token Suspend — `POST /{id}/token/suspend`
8 champ(s) au total — 8 implémenté(s), 0 partiel(s), 0 non vérifiable(s), 0 non implémenté(s).

## Token Unsuspend — `POST /{id}/token/unsuspend`
8 champ(s) au total — 8 implémenté(s), 0 partiel(s), 0 non vérifiable(s), 0 non implémenté(s).

## Token Delete — `POST /{id}/token/delete`
9 champ(s) au total — 8 implémenté(s), 0 partiel(s), 0 non vérifiable(s), 1 non implémenté(s).

| Champ (spec officiel) | Statut | Requis | Champ Java correspondant |
|---|---|---|---|
| `DeleteFromConsumerApp` | non_implemente | non | — |
