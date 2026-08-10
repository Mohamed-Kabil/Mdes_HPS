# API Field Changes

## RequestActivationMethods

| Field Path | Change Type | Comment |
|---|---|---|
| FundingAccountInfo->EncryptedPayload->EncryptedData->SourceTokenNumber | New field | — |
| FundingAccountInfo->EncryptedPayload->algorithmCypherMode | New field | May impact the decryption mechanism (truncated in source) |
| FundingAccountInfo->EncryptedPayload->tag | New field | May impact the decryption mechanism (truncated in source) |
| FundingAccountInfo->EncryptedPayload->aad | New field | May impact the decryption mechanism (truncated in source) |
| authRequestCorrelationId | New field | — |
| authenticatorInfo | New field | — |
| bindId | New field | — |
| certifiedMFAAuthMethodId | New field | — |
| deviceInfo | New field | — |
| tokenRequestorDecisioningInfo | New field | — |
| paymentData | New field | — |
| recentAuthenticationInfo | New field | — |
| reasonCodes | New values | — |

## DeliverActivationCode

| Field Path | Change Type | Comment |
|---|---|---|
| authRequestCorrelationId | New field | — |
| deviceInfo | New field | — |
| reasonCode | New values | — |
| activationMethod.type | New values | — |


## AuthoriseService

| Field Path | Change Type | Comment |
|---|---|---|
| FundingAccountInfo->EncryptedPayload->EncryptedData->SourceTokenNumber | New field | — |
| FundingAccountInfo->EncryptedPayload->algorithmCypherMode | New field | — |
| FundingAccountInfo->EncryptedPayload->tag | New field | — |
| FundingAccountInfo->EncryptedPayload->aad | New field | — |
| accountStatusInquirySentFor | New field | — |
| sourceProvisioningData | New field | — |
| provisioningContext | New field | — |

## Notify Service Activated

| Field Path | Change Type | Comment |
|---|---|---|
| FundingAccountInfo->EncryptedPayload->EncryptedData->SourceTokenNumber | New field | — |
| FundingAccountInfo->EncryptedPayload->algorithmCypherMode | New field | — |
| FundingAccountInfo->EncryptedPayload->tag | New field | — |
| FundingAccountInfo->EncryptedPayload->aad | New field | — |

## NotifyTokenUpdated

| Field Path | Change Type | Comment |
|---|---|---|
| authenticatorInfo | New field | — |
| bindId | New field | — |
| certifiedMFAAuthMethodId | New field | — |
| bindingStatus | New field | — |
| FundingAccountInfo->EncryptedPayload->algorithmCypherMode | New field | May impact the decryption mechanism (truncated in source) |
| FundingAccountInfo->EncryptedPayload->tag | New field | May impact the decryption mechanism (truncated in source) |
| FundingAccountInfo->EncryptedPayload->aad | New field | May impact the decryption mechanism (truncated in source) |
| reasonCode | New values | — |
