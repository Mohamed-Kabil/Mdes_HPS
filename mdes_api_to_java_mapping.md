# MDES Customer Service API → Java Implementation Mapping

| MDES API (Mastercard) | Path | Java file (java_mdes/) | Entry point / branch |
|---|---|---|---|
| Search | `POST /{id}/search` | `TokenInquiryRequestWebService.java` | `tokenInquiryRequest_35()` → `execute()`, network-code `"02"` branch (lines 147-169); variant selected by `mapToRequestSearchByTUR()` (566-588), `mapToRequestSearchByPan()` (485-518), `mapToRequestSearchByDeviceId()` (590-612) |
| Token Activate | `POST /{id}/token/activate` | `TokenLifeCycleItspWebService.java` | `tokenLifeCycleItsp_35()` → `execute()`, `switch (request.getAction())` case `"ACTIVATE"` (144-147) → `mapToRequestActivate()` (431-453) |
| Token Update | `POST /{id}/token/update` | `PanLifeCycleItspWebService.java` | `panLifeCycleItsp_35()` → `execute()`, `request.getActionReason().equals("ACCOUNT_UPDATE")` branch (125-183) |
| Token Suspend | `POST /{id}/token/suspend` | `TokenLifeCycleItspWebService.java` | `tokenLifeCycleItsp_35()` → `execute()`, `switch (request.getAction())` case `"SUSPEND"` (148-151) → `mapToRequestSuspend()` (454-475) |
| Token Unsuspend | `POST /{id}/token/unsuspend` | `TokenLifeCycleItspWebService.java` | `tokenLifeCycleItsp_35()` → `execute()`, `switch (request.getAction())` case `"RESUME"` (152-155) → `mapToRequestUnSuspend()` (476-497) |
| Token Delete | `POST /{id}/token/delete` | `TokenLifeCycleItspWebService.java` | `tokenLifeCycleItsp_35()` → `execute()`, `switch (request.getAction())` case `"DELETE"` (156-159) → `mapToRequestDelete()` (498-519) |

## Not part of the 6 (found in the same files, out of scope)

| What | Java file | Notes |
|---|---|---|
| Account Closed (calls `/paa/paymentaccount/static/1/0/closeAccount`, not `csapi`) | `PanLifeCycleItspWebService.java` | `request.getActionReason().equals("ACCOUNT_CLOSED")` branch (185-202) — different Mastercard API entirely |
| Visa/VTS token inquiry, activate/suspend/unsuspend/delete, PAN lifecycle | `TokenInquiryRequestWebService.java`, `TokenLifeCycleItspWebService.java`, `PanLifeCycleItspWebService.java` | `networkCode == "01"` branches — unrelated to MDES, uses Visa Token Service model classes |

Line numbers verified against the files in `java_mdes/` as of this conversation.
