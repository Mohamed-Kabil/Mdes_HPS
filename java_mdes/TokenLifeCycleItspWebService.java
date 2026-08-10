package com.acp.vision.pcrd.ws.impl.v2;
/* API-5215 */
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import jakarta.jws.WebService;

import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import com.acp.common.api.ITSP.model.*;
import com.acp.common.api.clicktopay.model.EnrollConsumerToVisaIdCredentialResPayload;
import com.acp.common.api.clicktopay.model.ErrorCTPResponse;
import com.acp.common.api.mastercom.model.ErrorResponse;
import com.acp.common.api.response.TokenLifecycleRs;
import com.acp.provider.message.aggregate.ResponseInfo;
import com.acp.provider.message.api.EResultId;
import com.acp.provider.message.request.TokenLifeCycleItspV35Rq;
import com.acp.provider.message.response.TokenLifeCycleItspV35Rs;
import com.acp.provider.message.utils.ErrorCodes;
import com.acp.provider.ws.v2.ITokenLifeCycleItspWebService;
import com.acp.vision.pcrd.utils.AddedValueServiceConstants;
import com.acp.vision.pcrd.utils.ExternalApiTools;
import com.acp.vision.pcrd.utils.JwEncryptionJwSignatureUtils;
import com.acp.vision.pcrd.utils.ResponseUtilsV35;
import com.acp.vision.pcrd.ws.exception.PCRDServiceException;

import com.acp.vision.pcrd.ws.init.InitConfig;
import com.acp.vision.pcrd.ws.mapper.TokenLifeCycleItspV35RqMapper;
import com.acp.vision.pcrd.ws.mapper.TokenLifeCycleItspV35RsMapper;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.servers.Server;
import io.swagger.v3.oas.annotations.tags.Tag;
import ma.hps.jpub.css_token_request_rq_v35;
import ma.hps.jpub.css_token_request_rs_v35;
import com.acp.vision.pcrd.ws.api.AbstractWebServiceV35;


import ma.hps.jpub.*;
import com.acp.provider.message.aggregate.AuditInfoV35;
import com.acp.provider.message.aggregate.DeviceInformationV35;
import org.json.JSONObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


import static com.acp.vision.pcrd.utils.JwEncryptionJwSignatureUtils.prepareAndSendRequestToMC;

@Produces({MediaType.APPLICATION_JSON,
        MediaType.APPLICATION_XML
})
@WebService(endpointInterface = "com.acp.provider.ws.v2.ITokenLifeCycleItspWebService", targetNamespace = "http://v1.ws.provider.acp.com/", serviceName = "TokenLifeCycleItsp2")
@Tag(name = "TokenLifeCycleItsp")
@Server(url = "/PowerCardConnectApi/rest")
@Path("")
public class TokenLifeCycleItspWebService extends AbstractWebServiceV35<TokenLifeCycleItspV35Rq, TokenLifeCycleItspV35Rs>
        implements ITokenLifeCycleItspWebService {
    private static final long serialVersionUID = 1L;
    private static Logger log = LoggerFactory.getLogger(TokenLifeCycleItspWebService.class);

    private TokenLifeCycleItspV35RqMapper rqMapper =
            TokenLifeCycleItspV35RqMapper.INSTANCE;
    private TokenLifeCycleItspV35RsMapper rsMapper =
            TokenLifeCycleItspV35RsMapper.INSTANCE;

    protected TokenLifeCycleItspV35Rs execute(TokenLifeCycleItspV35Rq request,
                                              TokenLifeCycleItspV35Rs response, Connection connection)
            throws PCRDServiceException, SQLException {
        css_token_life_rq_v35 oraRq = new css_token_life_rq_v35();

        try {
            response = (TokenLifeCycleItspV35Rs) ResponseUtilsV35.loopAttributes(new TokenLifeCycleItspV35Rs());

        } catch (Exception e) {
            getLog().error("Fail to loopAttributes :", e);
        }

        response.setResponseInfo(new ResponseInfo());
        response.getResponseInfo().setErrorCode("00000");
        response.getResponseInfo().setResultID(EResultId.ProceedWithSuccess);
        response.getResponseInfo()
                .setResponseUID(request.getRequestInfo().getRequestUID());

        css_token_life_rs_v35[] oraRs = {new css_token_life_rs_v35()};

        //oraRs[0] = map(response, css_token_life_rs_v35.class);
        oraRs[0] = rsMapper.javaObjectToJavaCssType(response);

        //oraRq = map( request,css_token_life_rq_v35.class );
        oraRq = rqMapper.javaObjectToJavaCssType(request);

        oraRq.getrequestinfo().setproviderlogin(getLoginFromTeken());
        oraRq.getrequestinfo().setuserlanguage(getUserLanguage());

        PCRD_ITSP_TOKENIZATION_WS_V35_OUT service =
                new PCRD_ITSP_TOKENIZATION_WS_V35_OUT(connection);
        service.ws_token_life_cycle_v35(oraRq, oraRs);
        //response = map( oraRs[0], TokenLifeCycleItspV35Rs.class );
        response = rsMapper.javaCssTypeToJavaObject(oraRs[0]);
        if (!ErrorCodes.SUCCESS.equals(response.getResponseInfo().getErrorCode())) {


            return response;
        }

        log.info("Internal call passed correctly before calling API");

        String tokenRequestorID = request.getTokenRequestorID();
        String tokenReferenceID = request.getTspTokenId();

        String apiKey = JwEncryptionJwSignatureUtils.getInstance().getVtsApiKey().get(request.getInstitutionCode());
        String sharedSecret = JwEncryptionJwSignatureUtils.getInstance().getVtsSharedSecret().get(request.getInstitutionCode());







        String visURL = InitConfig.getInstance().getVariableGlobal("vtsEndPoint") +
                "/vtis/v1/tokenRequestors/" + tokenRequestorID + "/tokens/" + tokenReferenceID + "/lifecycle";

        String url = null;
        Object payloadObject = null;
        TokenActivateWrapper wrapper = new TokenActivateWrapper();

        if ("02".equals(response.getNetworkCode())) {

            switch (request.getAction()) {
                case "ACTIVATE":
                    url = InitConfig.getInstance().getVariableGlobal("mdesCSEndPoint") + "/mdes/csapi/v2/token/activate";
                    wrapper.setTokenActivateRequest(mapToRequestActivate(request));
                    break;
                case "SUSPEND":
                    url = InitConfig.getInstance().getVariableGlobal("mdesCSEndPoint") + "/mdes/csapi/v2/token/suspend";
                    wrapper.setTokenSuspendRequest(mapToRequestSuspend(request));
                    break;
                case "RESUME":
                    url = InitConfig.getInstance().getVariableGlobal("mdesCSEndPoint") + "/mdes/csapi/v2/token/unsuspend";
                    wrapper.setTokenUnsuspendRequest(mapToRequestUnSuspend(request));
                    break;
                case "DELETE":
                    url = InitConfig.getInstance().getVariableGlobal("mdesCSEndPoint") + "/mdes/csapi/v2/token/delete";
                    wrapper.setTokenDeleteRequest(mapToRequestDelete(request));
                    break;
                default:
                    getLog().error("Unknown action: " + request.getAction());
                    return response;
            }
        }

        try {
            ObjectMapper mapper = new ObjectMapper();
            mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
            String payload;

            Response rsItsp;
            if ("02".equals(response.getNetworkCode())) {



                payload = mapper.writeValueAsString(wrapper);
                rsItsp = prepareAndSendRequestToMC(request.getInstitutionCode(), "POST", url, payload, "SC");
            } else if ("01".equals(response.getNetworkCode())) {



                TokenLifecycleRequest token = mapToRequestVts(request);
                if (Arrays.asList("ACTIVATE", "DELETE", "SUSPEND", "RESUME").contains(request.getAction())) {
                    token.setDeviceInfo(null);
                }
                mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL); //
                mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
                payload = mapper.writeValueAsString(token);

                String path_xpaytoken="vtis/v1/tokenRequestors/" + tokenRequestorID + "/tokens/"
                        + tokenReferenceID + "/lifecycle";
                rsItsp = callVtsApis(visURL, "POST", request.getInstitutionCode(), payload, path_xpaytoken, apiKey, sharedSecret, TokenLifecycleRs.class);


            } else {


                getLog().warn("Unsupported network code: " + response.getNetworkCode());
                return response;
            }

            int status = rsItsp.getStatusInfo().getStatusCode();



            String visaCode = "";
            String tokenLifeCycleRes= "";
            if (status != 200) {


                tokenLifeCycleRes = rsItsp.readEntity(String.class);

                JSONObject obj = new JSONObject(tokenLifeCycleRes);
                visaCode = obj.getString("errorCode");
            }





            response.setNetworkCode(null);

            if (status == 200) {


                css_token_request_rq_v35 req = new css_token_request_rq_v35();
                css_token_request_rs_v35[] res = {new css_token_request_rs_v35()};
                req.setbankcode(request.getInstitutionCode());
                req.settokenrequestorid(request.getTokenRequestorID());
                req.setactionreason(request.getActionReason());
                service.put_token_request(req, res);

                response.setNetworkCode(null);
                response.setResponseInfo(new ResponseInfo());
                response.getResponseInfo().setErrorCode("00000");
                response.getResponseInfo().setResultID(EResultId.ProceedWithSuccess);
                response.getResponseInfo()
                        .setResponseUID(request.getRequestInfo().getRequestUID());







            }
            else if (status == 400) {
                JSONObject obj = new JSONObject(tokenLifeCycleRes);
                JSONObject error = obj.getJSONObject("errorResponse");
                visaCode = error.getString("reason");





                response.setNetworkCode(null);
                response.setResponseInfo(new ResponseInfo());
                response.getResponseInfo().setResultID(EResultId.SystemError);
                response.getResponseInfo().setResponseUID(request.getRequestInfo().getRequestUID());

                String internalCode = "";
                String internalDescription = "";

                switch (visaCode) {

                    case "VSE40002":
                        internalCode = "T0111";
                        internalDescription = "Token state exist";
                        break;

                    case "VSE40000":
                        internalCode = "T0117";
                        internalDescription = "Invalid Data";
                        break;

                    case "VSE40001":
                        internalCode = "T0118";
                        internalDescription = "Required Data missing";
                        break;

                    case "VSE40003":
                        internalCode = "T0112";
                        internalDescription = "Token not found";
                        break;

                    case "VSE40010":
                        internalCode = "T0109";
                        internalDescription = "CRYPTOGRAPHY ERROR";
                        break;

                    case "VSE40011":
                        internalCode = "T0113";
                        internalDescription = "Token not active";
                        break;



                }

                response.getResponseInfo().setErrorCode(internalCode);
                response.getResponseInfo().setErrorDescription(internalDescription);
            }
// Gestion des erreurs 500 (erreurs système VISA)
            else if (status == 500) {

                response.setNetworkCode(null);
                response.setResponseInfo(new ResponseInfo());

                // 500 = erreur interne VISA
                response.getResponseInfo().setErrorCode("T0115"); // VSE_INTERNAL_SYSTEM_ERROR ? Invalid Action (ou autre code interne si besoin)
                response.getResponseInfo().setErrorDescription("VISA Internal System Error");
                response.getResponseInfo().setResultID(EResultId.SystemError);
                response.getResponseInfo().setResponseUID(request.getRequestInfo().getRequestUID());

            }
            else if (status == 401) {

                response.setNetworkCode(null);
                response.setResponseInfo(new ResponseInfo());

                // 500 = erreur interne VISA
                response.getResponseInfo().setErrorCode("T0116");
                response.getResponseInfo().setErrorDescription("INVALID XPAY TOKEN");
                response.getResponseInfo().setResultID(EResultId.SystemError);
                response.getResponseInfo().setResponseUID(request.getRequestInfo().getRequestUID());

            }
            else {
                response.setNetworkCode(null);
                response.setResponseInfo(new ResponseInfo());
                response.getResponseInfo().setErrorCode("99999");
                response.getResponseInfo().setResultID(EResultId.SystemError);
                response.getResponseInfo().setResponseUID(request.getRequestInfo().getRequestUID());
                response.getResponseInfo().setErrorDescription("Error from external service");
            }


















        } catch (Exception e) {
            getLog().error("Customer service call exception", e);
            response.setNetworkCode(null);
            response.setResponseInfo(new ResponseInfo());
            response.getResponseInfo().setErrorCode("99999");
            response.getResponseInfo().setResultID(EResultId.SystemError);
            response.getResponseInfo().setResponseUID(request.getRequestInfo().getRequestUID());
            response.getResponseInfo().setErrorDescription("System Error");

        }
        response.setNetworkCode(null);
        return response;
    }

    protected TokenLifeCycleItspV35Rs cleanResponse(
            TokenLifeCycleItspV35Rs response) {
        return response;
    }

    public TokenLifeCycleItspV35Rs tokenLifeCycleItsp_35(
            TokenLifeCycleItspV35Rq request) {
        TokenLifeCycleItspV35Rs response = new TokenLifeCycleItspV35Rs();
        String message = null;


        try {


            message = validateRequest("TokenLifeCycleItsp", request);

        } catch (Exception e) {


            response.setResponseInfo(buildMessageError(e,
                    request.getRequestInfo().getRequestUID()));
            logResponse(response, request, "tokenLifeCycleItsp_35");
            return response;
        }


        if (message != null && !message.isEmpty()) {


            response.setResponseInfo(buildMessageError(message,
                    request.getRequestInfo().getRequestUID()));

            logResponse(response, request, "tokenLifeCycleItsp_35");
            return response;
        }


        response = (TokenLifeCycleItspV35Rs) encapsuleExecution(request,
                response);
        logResponse(response, request, "tokenLifeCycleItsp_35");
        return response;
    }

    @POST
    @Path("Itsp/TokenLifeCycleItsp/V2")
    @Operation(summary = "tokenLifeCycleItsp_35", description = "tokenLifeCycleItsp_35 Web Service ", responses =  {
            @ApiResponse(content = @Content(mediaType = "application/json", schema = @Schema(implementation = TokenLifeCycleItspV35Rs.class)
            )
                    , responseCode = "200", description = "ProceedWithSuccess")
    }
    )
    public Response tokenLifeCycleItsp_35Post(
            @RequestBody(description = "TokenLifeCycleItspV35Rq Request", required = true, content = @Content(mediaType = "application/json", schema = @Schema(implementation = TokenLifeCycleItspV35Rq.class)
            )
            )
            TokenLifeCycleItspV35Rq request) {
        TokenLifeCycleItspV35Rs response = new TokenLifeCycleItspV35Rs();
        response = tokenLifeCycleItsp_35(request);
        //logResponse(response,request,"tokenLifeCycleItsp_35");
        return Response.status(buildStatusResponce(response)).entity(response)
                .build();
    }

    public static TokenLifeCycleItspRq mapToRequestActivate(TokenLifeCycleItspV35Rq request) {

        if (request == null) {
            return null;
        }

        TokenLifeCycleItspRq response = new TokenLifeCycleItspRq();
        response.setTokenUniqueReference(request.getTspTokenId());
        response.setCommentText(request.getCommentText());
        response.setReasonCode(request.getActionReason());

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
    public static TokenSuspendRequest mapToRequestSuspend(TokenLifeCycleItspV35Rq request) {
        if (request == null) {
            return null;
        }

        TokenSuspendRequest response = new TokenSuspendRequest();
        response.setTokenUniqueReference(request.getTspTokenId());
        response.setCommentText(request.getCommentText());
        response.setReasonCode(request.getActionReason());

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
    public static TokenUnsuspendRequest mapToRequestUnSuspend(TokenLifeCycleItspV35Rq request) {
        if (request == null) {
            return null;
        }

        TokenUnsuspendRequest response = new TokenUnsuspendRequest();
        response.setTokenUniqueReference(request.getTspTokenId());
        response.setCommentText(request.getCommentText());
        response.setReasonCode(request.getActionReason());

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
    public static TokenDeleteRequest mapToRequestDelete(TokenLifeCycleItspV35Rq request) {
        if (request == null) {
            return null;
        }

        TokenDeleteRequest response = new TokenDeleteRequest();
        response.setTokenUniqueReference(request.getTspTokenId());
        response.setCommentText(request.getCommentText());
        response.setReasonCode(request.getActionReason());

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


    public static TokenLifecycleRequest mapToRequestVts(TokenLifeCycleItspV35Rq request) {
        if (request == null) {
            return null;
        }
        TokenLifecycleRequest response = new TokenLifecycleRequest();
        response.setOperatorID(null);
        response.setOperationType(request.getAction());
        response.setOperationReason(request.getAction());


        DeviceInformationV35 deviceInfoV35 = request.getDeviceInfo();
        if (deviceInfoV35 != null) {
            DeviceInfo deviceInfo = new DeviceInfo();
            deviceInfo.setDeviceID(deviceInfoV35.getDeviceID());
            deviceInfo.setDeviceIndex(deviceInfoV35.getDeviceIndex());
            response.setDeviceInfo(deviceInfo);
        }

        return response;
    }


}
