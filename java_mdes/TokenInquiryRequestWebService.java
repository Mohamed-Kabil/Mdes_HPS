package com.acp.vision.pcrd.ws.impl.v2;
/* API-5215 */
import java.io.IOException;
import java.security.cert.Certificate;
import java.sql.Connection;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.List;

import jakarta.jws.WebService;

import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Response;

import com.acp.common.api.ITSP.model.*;
import com.acp.common.api.adapter.DateHeurXMLAdapter;
import com.acp.common.api.request.EncryptedRequest;
import com.acp.common.api.response.EncryptedResponse;
import com.acp.common.api.response.TokenInquiryByPanRs;
import com.acp.common.api.response.TokenInquiryRs;
import com.acp.provider.message.aggregate.*;
import com.acp.common.api.ITSP.model.TokenResponse;
import com.acp.common.api.vau.model.VauResponse;
import com.acp.provider.message.aggregate.ResponseInfo;
import com.acp.provider.message.api.EResultId;
import com.acp.provider.message.request.TokenInquiryRequestV35Rq;
import com.acp.provider.message.response.TokenInquiryRequestV35Rs;
import com.acp.provider.message.utils.ErrorCodes;
import com.acp.provider.ws.v2.ITokenInquiryRequestWebService;
import com.acp.vision.pcrd.utils.JwEncryptionJwSignatureUtils;
import com.acp.vision.pcrd.utils.ResponseUtilsV35;
import com.acp.vision.pcrd.ws.api.AbstractWebServiceV35;
import com.acp.vision.pcrd.ws.authentification.impl.AuthentificationWebService;
import com.acp.vision.pcrd.ws.exception.PCRDServiceException;
import com.acp.vision.pcrd.ws.init.InitConfig;
import com.acp.vision.pcrd.ws.mapper.TokenInquiryRequestV35RqMapper;
import com.acp.vision.pcrd.ws.mapper.TokenInquiryRequestV35RsMapper;
import com.acp.vision.pcrd.ws.mapper.ReqTokenRequestMapper;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mastercard.developer.encryption.EncryptionException;
import com.mastercard.developer.encryption.FieldLevelEncryption;
import com.mastercard.developer.encryption.FieldLevelEncryptionConfig;
import com.mastercard.developer.encryption.FieldLevelEncryptionConfigBuilder;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.servers.Server;
import io.swagger.v3.oas.annotations.tags.Tag;

import ma.hps.jpub.*;
import  com.acp.provider.message.aggregate.EncryptDataV35;
import com.acp.provider.message.aggregate.AuditInfoV35;
import com.acp.provider.message.aggregate.TokensV35;

import org.json.JSONException;
import org.json.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import static com.acp.vision.pcrd.utils.JwEncryptionJwSignatureUtils.prepareAndSendRequestToMC;
import static com.acp.vision.pcrd.ws.authentification.impl.AuthentificationWebService.*;


@Produces({jakarta.ws.rs.core.MediaType.APPLICATION_JSON,
    jakarta.ws.rs.core.MediaType.APPLICATION_XML
})
@WebService(endpointInterface = "com.acp.provider.ws.v2.ITokenInquiryRequestWebService", targetNamespace = "http://v1.ws.provider.acp.com/", serviceName = "TokenInquiryRequest2")
@Tag(name = "TokenInquiryRequest")
@Server(url = "/PowerCardConnectApi/rest")
@Path("")
public class TokenInquiryRequestWebService extends AbstractWebServiceV35<TokenInquiryRequestV35Rq, TokenInquiryRequestV35Rs>
    implements ITokenInquiryRequestWebService {
    private static final long serialVersionUID = 1L;
    private static Logger log = LoggerFactory.getLogger(TokenInquiryRequestWebService.class);

    private TokenInquiryRequestV35RqMapper rqMapper =
        TokenInquiryRequestV35RqMapper.INSTANCE;
    private TokenInquiryRequestV35RsMapper rsMapper =
        TokenInquiryRequestV35RsMapper.INSTANCE;
    private ReqTokenRequestMapper reqTokenRequestMapper =
            ReqTokenRequestMapper.INSTANCE;

    protected TokenInquiryRequestV35Rs execute(
        TokenInquiryRequestV35Rq request, TokenInquiryRequestV35Rs response,
        Connection connection)
            throws PCRDServiceException, java.sql.SQLException, IOException {
        css_token_inquiry_req_rq_v35 oraRq = new css_token_inquiry_req_rq_v35();

        try {
            response = (TokenInquiryRequestV35Rs) ResponseUtilsV35.loopAttributes(new TokenInquiryRequestV35Rs());

        } catch (Exception e) {
            getLog().error("Fail to loopAttributes :", e);
        }

        response.setResponseInfo(new ResponseInfo());
        response.getResponseInfo().setErrorCode("00000");
        response.getResponseInfo().setResultID(EResultId.ProceedWithSuccess);
        response.getResponseInfo()
                .setResponseUID(request.getRequestInfo().getRequestUID());

        css_token_inquiry_req_rs_v35[] oraRs =
            { new css_token_inquiry_req_rs_v35() };

        //oraRs[0] = map(response, css_token_inquiry_req_rs_v35.class);
        oraRs[0] = rsMapper.javaObjectToJavaCssType(response);

        //oraRq = map( request,css_token_inquiry_req_rq_v35.class );
        oraRq = rqMapper.javaObjectToJavaCssType(request);

        oraRq.getrequestinfo().setproviderlogin(getLoginFromTeken());
        oraRq.getrequestinfo().setuserlanguage(getUserLanguage());

        PCRD_ITSP_TOKENIZATION_WS_V35_OUT service =
            new PCRD_ITSP_TOKENIZATION_WS_V35_OUT(connection);
        service.ws_token_inquiry_req_v35(oraRq, oraRs);
        //response = map( oraRs[0], TokenInquiryRequestV35Rs.class );
        response = rsMapper.javaCssTypeToJavaObject(oraRs[0]);
        if (!ErrorCodes.SUCCESS.equals(response.getResponseInfo().getErrorCode())) {
            return response;
        }

        log.info("Internal call passed correctly before calling API");




        ObjectMapper mapper = new ObjectMapper();
        mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
        mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

        String networkCode = response.getNetworkCode();
        String itspRs = null;
        int status = 0;
if (request.getTokenVaultSource().equals("R")) {
    if ("02".equals(networkCode)) {
        String url = InitConfig.getInstance().getVariableGlobal("mdesCSEndPoint") + "/mdes/csapi/v2/search";
        TokenActivateWrapper wrapper = new TokenActivateWrapper();

        try {
            if (request.getTokenUniqueReference() != null) {
                wrapper.setSearchRequest(mapToRequestSearchByTUR(request));
            } else if (request.getEncryptData().getPan() != null) {
                SearchRequest searchRequest = mapToRequestSearchByPan(request);
                String searchRequestJson = mapper.writeValueAsString(searchRequest);
                String encryptedPayload = encryptItspPayload(request.getInstitutionCode(), searchRequestJson,"SC");
                SearchRequestString searchRequestt = mapper.readValue(encryptedPayload, SearchRequestString.class);
                wrapper.setSearchRequest(searchRequestt);
            } else if (request.getDeviceId() != null) {
                wrapper.setSearchRequest(mapToRequestSearchByDeviceId(request));
            }

            String payload = mapper.writeValueAsString(wrapper);
            Response rsItsp = prepareAndSendRequestToMC(request.getInstitutionCode(), "POST", url, payload, "SC");

            itspRs = rsItsp.readEntity(String.class);
            status = rsItsp.getStatusInfo().getStatusCode();

        } catch (Exception e) {
            getLog().error("MC service call exception", e);
        }

    } else if ("01".equals(networkCode)) {
        try {
            Response rsItsp = null;
            if (request.getTokenUniqueReference() != null) {

                String apiKey = JwEncryptionJwSignatureUtils.getInstance().getVtsApiKey().get(request.getInstitutionCode());
                String url = InitConfig.getInstance().getVariableGlobal("vtsEndPoint") +
                        "/vtis/v1/tokenRequestors/" + request.getTokenRequestorId() +
                        "/tokens/" + request.getTokenUniqueReference() +
                        "/details";
                String sharedSecret = JwEncryptionJwSignatureUtils.getInstance().getVtsSharedSecret().get(request.getInstitutionCode());

                String path_xpaytoken = "vtis/v1/tokenRequestors/" + request.getTokenRequestorId() + "/tokens/" + request.getTokenUniqueReference() + "/details";
                rsItsp = callVtsApis(url, "GET", request.getInstitutionCode(), "", path_xpaytoken, apiKey, sharedSecret, TokenInquiryByPanRs.class);

            } else if (request.getPanUniqueReference() != null) {
                String apiKey = JwEncryptionJwSignatureUtils.getInstance().getVtsApiKey().get(request.getInstitutionCode());

                String url = InitConfig.getInstance().getVariableGlobal("vtsEndPoint") +
                        "/vtis/v1/pan/retrieveTokenInfo";

                String sharedSecret = JwEncryptionJwSignatureUtils.getInstance().getVtsSharedSecret().get(request.getInstitutionCode());

                String path_xpaytoken = "vtis/v1/pan/retrieveTokenInfo";
                TokenDetailsRequest tokenDetailsRequest = mapToVisaTokeByPanUniqueRef(request, request.getInstitutionCode());
                String requestJson = mapper.writeValueAsString(tokenDetailsRequest);

                rsItsp = callVtsApis(url, "POST", request.getInstitutionCode(), requestJson, path_xpaytoken, apiKey, sharedSecret, TokenInquiryByPanRs.class);


            }

            itspRs = rsItsp.readEntity(String.class);
            status = rsItsp.getStatusInfo().getStatusCode();

        } catch (Exception e) {
            getLog().error("Visa service call exception", e);
        }
    }

    response.setNetworkCode(null);

    if (status == 200) {



        if ("02".equals(networkCode)) {
            try {
                TokenActivateWrapper wrapper = mapper.readValue(itspRs, TokenActivateWrapper.class);
                SearchResponse searchResponse = wrapper.getSearchResponse();

                response = mapSearchResponseToTokenInquiry(searchResponse);

                css_tab_token_request_rq_v35 req = new css_tab_token_request_rq_v35();
                css_token_request_rs_v35[] res = {new css_token_request_rs_v35()};

                List<css_token_request_rq_v35> tokenList = new ArrayList<>();
                for (Account account : searchResponse.getAccounts().getAccount()) {
                    if (account.getTokens() != null && account.getTokens().getToken() != null) {
                        for (Token token : account.getTokens().getToken()) {
                            ReqTokenRequest javaReq = new ReqTokenRequest();
                            javaReq.setTokenRequestorID(token.getTokenRequestorId());

                            TokenInformationItspV35 tokenInfo = new TokenInformationItspV35();
                            tokenInfo.setTokenStatus(token.getCurrentStatusCode());
                            javaReq.setActionReason(tokenInfo.getTokenStatus());

                            css_token_request_rq_v35 cssToken = reqTokenRequestMapper.javaObjectToJavaCssType(javaReq);
                            tokenList.add(cssToken);
                        }
                    }
                }

                css_token_request_rq_v35[] tokenArray = tokenList.toArray(new css_token_request_rq_v35[0]);

                try {
                    req.setArray(tokenArray);
                } catch (SQLException e) {
                    e.printStackTrace();
                }

                service.put_token_requests(req, res);


            } catch (Exception e) {
                getLog().error("Error mapping MC response", e);
            }

        } else if ("01".equals(networkCode)) {
            try {
                ResponseInfo responseInfo = new ResponseInfo();
                responseInfo.setErrorCode("00000");
                responseInfo.setResultID(EResultId.ProceedWithSuccess);
                responseInfo.setResponseUID(request.getRequestInfo().getRequestUID());
                responseInfo.setErrorDescription("SUCCESS");
                response.setResponseInfo(responseInfo);

                JsonNode rootNode = mapper.readTree(itspRs);

                List<TokensV35> tokensList = new ArrayList<>();

                JsonNode tokenDetailsArray = rootNode.get("tokenDetails");
                if (tokenDetailsArray != null && tokenDetailsArray.isArray()) {
                    for (JsonNode tokenNode : tokenDetailsArray) {
                        TokensV35 token = new TokensV35();

                        token.setTokenRequestorId(tokenNode.path("tokenRequestorID").asText());
                        token.setTokenUniqueReference(tokenNode.path("tokenReferenceID").asText());
                        token.setPanUniqueReference(tokenNode.path("panReferenceID").asText());


                        // TokenInformation
                        TokenInformationItspV35 tokenInfo = new TokenInformationItspV35();
                        tokenInfo.setTokenNumber(tokenNode.path("tokenReferenceID").asText());

                        String statusVisa = tokenNode.path("tokenStatus").asText();
                        switch (statusVisa) {
                            case "ACTIVE":
                                tokenInfo.setTokenStatus("A");
                                break;
                            case "DEACTIVATED":
                                tokenInfo.setTokenStatus("D");
                                break;
                            case "SUSPENDED":
                                tokenInfo.setTokenStatus("S");
                                break;
                            case "INACTIVE":
                                tokenInfo.setTokenStatus("I");
                                break;
                            case "TOKENIZATION_REQUESTED":
                                tokenInfo.setTokenStatus("W");
                                break;
                            default:
                                tokenInfo.setTokenStatus("U");
                        }
                     /*   req.setactionreason(tokenInfo.setTokenStatus);

                        service.put_token_request(req, res);*/

//A revenir
                              /*  DateHeurXMLAdapter adapter = new DateHeurXMLAdapter();
                                String sysDateFormatted = adapter.marshal(new Date());
                                tokenInfo.setTokenStatusDate(sysDateFormatted);*/
                        String type = tokenNode.path("tokenType").asText();
                        switch (type) {
                            case "CARD_ON_FILE":
                                tokenInfo.setTokenType("01");
                                break;
                            case "SECURE_ELEMENT":
                                tokenInfo.setTokenType("02");
                                break;
                            default:
                                tokenInfo.setTokenType("00");
                        }
                        token.setTokenInformation(tokenInfo);

                        tokensList.add(token);
                    }
                }

                response.setTokens(tokensList.toArray(new TokensV35[0]));

                css_tab_token_request_rq_v35 req = new css_tab_token_request_rq_v35();
                css_token_request_rs_v35[] res = {new css_token_request_rs_v35()};

                List<css_token_request_rq_v35> tokenList = new ArrayList<>();
                for (TokensV35 token : tokensList) {
                    ReqTokenRequest javaReq = new ReqTokenRequest();
                    javaReq.setTokenRequestorID(token.getTokenRequestorId());

                    if (token.getTokenInformation() != null) {
                        javaReq.setActionReason(token.getTokenInformation().getTokenStatus());
                    }

                    css_token_request_rq_v35 cssToken = reqTokenRequestMapper.javaObjectToJavaCssType(javaReq);
                    tokenList.add(cssToken);
                }

                css_token_request_rq_v35[] tokenArray = tokenList.toArray(new css_token_request_rq_v35[0]);

                try {
                    req.setArray(tokenArray);
                } catch (SQLException e) {
                    e.printStackTrace();
                }

                service.put_token_requests(req, res);


            } catch (Exception e) {
                getLog().error("Error mapping Visa response", e);
            }
        }


    } else {
        ResponseInfo responseInfo = new ResponseInfo();
        responseInfo.setErrorCode("99999");
        responseInfo.setResultID(EResultId.SystemError);
        responseInfo.setResponseUID(request.getRequestInfo().getRequestUID());
        responseInfo.setErrorDescription("Error from external service");
        response.setResponseInfo(responseInfo);
    }

}
        return response;
    }

    protected TokenInquiryRequestV35Rs cleanResponse(
        TokenInquiryRequestV35Rs response) {
        ResponseInfo responseInfo = response.getResponseInfo();
        response = new TokenInquiryRequestV35Rs();
        response.setResponseInfo(responseInfo);
        return response;
    }

    public TokenInquiryRequestV35Rs tokenInquiryRequest_35(
        TokenInquiryRequestV35Rq request) {
        TokenInquiryRequestV35Rs response = new TokenInquiryRequestV35Rs();
        String message = null;

        try {
            message = validateRequest("TokenInquiryRequest", request);
        } catch (Exception e) {
            response.setResponseInfo(buildMessageError(e,
                    request.getRequestInfo().getRequestUID()));
            logResponse(response, request, "tokenInquiryRequest_35");
            return response;
        }

        if (message != null && !message.isEmpty()) {
            response.setResponseInfo(buildMessageError(message,
                    request.getRequestInfo().getRequestUID()));

            logResponse(response, request, "tokenInquiryRequest_35");
            return response;
        }
        response = (TokenInquiryRequestV35Rs) encapsuleExecution(request,
                response);
        logResponse(response, request, "tokenInquiryRequest_35");
        return response;
    }

    @jakarta.ws.rs.POST
    @Path("Itsp/TokenInquiryRequest/V2")
    @Operation(summary = "tokenInquiryRequest_35", description = "tokenInquiryRequest_35 Web Service ", responses =  {
        @ApiResponse(content = @Content(mediaType = "application/json", schema = @Schema(implementation = TokenInquiryRequestV35Rs.class)
        )
        , responseCode = "200", description = "ProceedWithSuccess")
    }
    )
    public Response tokenInquiryRequest_35Post(
        @RequestBody(description = "TokenInquiryRequestRq Request", required = true, content = @Content(mediaType = "application/json", schema = @Schema(implementation = TokenInquiryRequestRq.class)
    )
    )
    TokenInquiryRequestRq request) {
        TokenInquiryRequestV35Rq requestv35 =new TokenInquiryRequestV35Rq();
        TokenInquiryRequestV35Rs responsev35=new TokenInquiryRequestV35Rs();
        EncryptDataV35 decryptedValue=new EncryptDataV35();

        String decryptedData = null;

        ObjectMapper mapper = new ObjectMapper();
        if (decryptedData != null) {
            try {
                decryptedData = decryptItspPayload(request.getInstitutionCode(), request.getEncryptedData());


            } catch (Exception e) {
                getLog().error("ERROR WIHLE DECRYPT REQUEST :", e);

                responsev35.setResponseInfo(new ResponseInfo());
                responsev35.getResponseInfo().setErrorCode("T0109");
                responsev35.getResponseInfo().setErrorDescription("CRYPTOGRAPHY ERROR");
                responsev35.getResponseInfo().setResultID(EResultId.Error);
                responsev35.getResponseInfo().setResponseUID(request.getRequestInfo().getRequestUID());
                return Response.status(buildStatusResponce(responsev35)).entity(responsev35).build();
            }
        }
      //  if (decryptedData != null) {
            try {


                mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
                if (decryptedData != null) {

                    decryptedValue = mapper.readValue(decryptedData, EncryptDataV35.class);

                }

                requestv35 = mapper.convertValue(request, TokenInquiryRequestV35Rq.class);
               if (decryptedData != null) {
                   requestv35.setEncryptData(decryptedValue);
               }



            } catch (IOException e) {
                getLog().error("ERROR WHILE PARSING JSON REQUEST :", e);
            }
    //    }

         responsev35 = tokenInquiryRequest_35(requestv35);


        //logResponse(response,request,"tokenInquiryRequest_35");
        return Response.status(buildStatusResponce(responsev35)).entity(responsev35)
                       .build();
    }

    public static SearchRequest mapToRequestSearchByPan(TokenInquiryRequestV35Rq request) {
        if (request == null) {
            return null;
        }

        SearchRequest response = new SearchRequest();
        response.setExcludeDeletedIndicator("false");
        response.setIncludeDeviceTokensOnly("false");
        response.setExcludeTokensDeletedFromConsumerApp("false");
        EncryptedAccountInformation encryptedAccountInformation = new EncryptedAccountInformation();

        EncryptedData encryptedData = new EncryptedData();
        CurrentAccount currentAccount = new CurrentAccount();
        currentAccount.setAccountPan(request.getEncryptData().getPan());
        encryptedData.setCurrentAccount(currentAccount);
        encryptedAccountInformation.setEncryptedData(encryptedData);

        response.setEncryptedAccountInformation(encryptedAccountInformation);



        AuditInfoV35 auditV35 = request.getAuditInfo();
        if (auditV35 != null) {
            AuditInfo audits = new AuditInfo();
            audits.setUserId(auditV35.getUserId());
            audits.setUserName(auditV35.getUserName());
            audits.setOrganisation(auditV35.getOrganisation());
            audits.setPhone(auditV35.getPhone());
            response.setAuditInfo(audits);
        }


        return response;
    }
    public TokenInquiryRequestV35Rs mapSearchResponseToTokenInquiry(SearchResponse searchResponse) {
        TokenInquiryRequestV35Rs response = new TokenInquiryRequestV35Rs();
        List<TokensV35> tokensList = new ArrayList<>();

        if (searchResponse != null &&
                searchResponse.getAccounts() != null &&
                searchResponse.getAccounts().getAccount() != null) {

            for (Account account : searchResponse.getAccounts().getAccount()) {
                if (account.getTokens() != null && account.getTokens().getToken() != null) {
                    for (Token token : account.getTokens().getToken()) {
                        TokensV35 tokenV35 = new TokensV35();
                        tokenV35.setPan(account.getAccountPanSuffix());
                        tokenV35.setPanUniqueReference(token.getPrimaryAccountNumberUniqueReference());
                        tokenV35.setTokenRequestorId(token.getTokenRequestorId());
                        tokenV35.setTokenUniqueReference(token.getTokenUniqueReference());
                        tokenV35.setWalletId(token.getWalletId());
                        tokenV35.setTransactionId(token.getCorrelationId());

                        TokenInformationItspV35 tokenInfo = new TokenInformationItspV35();
                        tokenInfo.setTokenType(token.getTokenType());
                        tokenInfo.setTokenNumber(token.getTokenSuffix());
                        tokenInfo.setTokenStatus(token.getCurrentStatusCode());
                        tokenV35.setTokenInformation(tokenInfo);

                        // DeviceInfo
                        DeviceInformationV35 deviceInfo = new DeviceInformationV35();
                        if (token.getDevice() != null) {
                            deviceInfo.setDeviceID(token.getDevice().getDeviceId());
                            deviceInfo.setDeviceName(token.getDevice().getDeviceName());
                        }
                        tokenV35.setDeviceInfo(deviceInfo);

                        RiskInformationItspV35 riskInfo = new RiskInformationItspV35();
                        tokenV35.setRiskInformation(riskInfo);

                        tokensList.add(tokenV35);
                    }
                }
            }
        }
        response.setTokens(tokensList.toArray(new TokensV35[0]));


        return response;
    }

    public static SearchRequest mapToRequestSearchByTUR(TokenInquiryRequestV35Rq request) {
        if (request == null) {
            return null;
        }
        SearchRequest response = new SearchRequest();
        response.setTokenUniqueReference(request.getTokenUniqueReference());
        response.setExcludeDeletedIndicator("false");
        response.setIncludeDeviceTokensOnly("false");
        response.setExcludeTokensDeletedFromConsumerApp("false");

        AuditInfoV35 auditV35 = request.getAuditInfo();
        if (auditV35 != null) {
            AuditInfo audits = new AuditInfo();
            audits.setUserId(auditV35.getUserId());
            audits.setUserName(auditV35.getUserName());
            audits.setOrganisation(auditV35.getOrganisation());
            audits.setPhone(auditV35.getPhone());
            response.setAuditInfo(audits);
        }


        return response;
    }

    public static SearchRequest mapToRequestSearchByDeviceId(TokenInquiryRequestV35Rq request) {
        if (request == null) {
            return null;
        }
        SearchRequest response = new SearchRequest();
        response.setPaymentAppInstanceId(request.getDeviceId());
        response.setExcludeDeletedIndicator("false");
        response.setIncludeDeviceTokensOnly("false");
        response.setExcludeTokensDeletedFromConsumerApp("false");

        AuditInfoV35 auditV35 = request.getAuditInfo();
        if (auditV35 != null) {
            AuditInfo audits = new AuditInfo();
            audits.setUserId(auditV35.getUserId());
            audits.setUserName(auditV35.getUserName());
            audits.setOrganisation(auditV35.getOrganisation());
            audits.setPhone(auditV35.getPhone());
            response.setAuditInfo(audits);
        }


        return response;
    }
    public TokenDetailsRequest mapToVisaTokenDetailsRequest(TokenInquiryRequestV35Rq request, String BanKCode) {
        TokenDetailsRequest visaRequest = new TokenDetailsRequest();

        if (request.getPanUniqueReference() != null && !request.getPanUniqueReference().isEmpty()) {
            visaRequest.setPanReferenceID(request.getPanUniqueReference());
        }

       if (request.getEncryptData() != null) {
            try {
                String pan = extractPanFromEncryptedData(request.getEncryptData().getPan());

                if (pan != null ) {
                    String encryptedPan = encryptAndSignPayload(pan, BanKCode);
                    visaRequest.setEncryptedData(encryptedPan);
                } else {
                    System.err.println("PAN est vide ou invalide dans EncryptedData.");
                }
            } catch (EncryptionException e) {
                System.err.println("Erreur lors du chiffrement du PAN: " + e.getMessage());
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
       }

        return visaRequest;
    }

    public String extractPanFromEncryptedData(String encryptedData) {
        if (encryptedData != null && !encryptedData.isEmpty()) {
            return encryptedData.replace("\"", "");
        } else {
            return null;
        }
    }


    public TokenDetailsRequest mapToVisaTokeByPanUniqueRef(TokenInquiryRequestV35Rq request, String BanKCode) {
        TokenDetailsRequest visaRequest = new TokenDetailsRequest();

        if (request.getPanUniqueReference() != null && !request.getPanUniqueReference().isEmpty()) {
            visaRequest.setPanReferenceID(request.getPanUniqueReference());
        }

        return visaRequest;
    }


}
