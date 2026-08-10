
package com.acp.vision.pcrd.ws.impl.v2;
/* API-5215 */
import java.io.IOException;
import java.sql.Connection;
import java.time.LocalDate;

import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.time.Year;
import jakarta.jws.WebService;

import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.Response;
import com.acp.common.api.ITSP.model.PanLifeCycleItspRq;
import com.acp.common.api.ITSP.model.*;
import com.acp.common.api.response.PanLifeCycleRs;
import com.acp.provider.message.aggregate.*;
import com.acp.provider.message.aggregate.EncryptDataV35;
import com.acp.provider.message.api.AbstractMessageV35Rq;

import com.acp.provider.message.api.EResultId;
import com.acp.provider.message.request.PanLifeCycleItspV35Rq;
import com.acp.provider.message.response.PanLifeCycleItspV35Rs;
import com.acp.provider.message.utils.ErrorCodes;
import com.acp.provider.ws.v2.IPanLifeCycleItspWebService;
import com.acp.vision.pcrd.utils.JwEncryptionJwSignatureUtils;
import com.acp.vision.pcrd.utils.ResponseUtilsV35;
import com.acp.vision.pcrd.ws.api.AbstractWebServiceV35;
import com.acp.vision.pcrd.ws.exception.PCRDServiceException;
import com.acp.vision.pcrd.ws.init.InitConfig;
import com.acp.vision.pcrd.ws.mapper.PanLifeCycleItspV35RqMapper;
import com.acp.vision.pcrd.ws.mapper.PanLifeCycleItspV35RsMapper;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.parameters.RequestBody;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.servers.Server;
import io.swagger.v3.oas.annotations.tags.Tag;

import ma.hps.jpub.PCRD_ITSP_TOKENIZATION_WS_V35_OUT;
import ma.hps.jpub.css_pan_lifecy_itsp_rq_v35;
import ma.hps.jpub.css_pan_lifecy_itsp_rs_v35;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import static com.acp.vision.pcrd.utils.JwEncryptionJwSignatureUtils.prepareAndSendRequestToMC;
import static com.acp.vision.pcrd.ws.authentification.impl.AuthentificationWebService.*;

@Produces({jakarta.ws.rs.core.MediaType.APPLICATION_JSON,
        jakarta.ws.rs.core.MediaType.APPLICATION_XML
})
@WebService(endpointInterface = "com.acp.provider.ws.v2.IPanLifeCycleItspWebService", targetNamespace = "http://v1.ws.provider.acp.com/", serviceName = "PanLifeCycleItsp2")
@Tag(name = "PanLifeCycleItsp")
@Server(url = "/PowerCardConnectApi/rest")
@Path("")
public class PanLifeCycleItspWebService extends AbstractWebServiceV35<PanLifeCycleItspV35Rq, PanLifeCycleItspV35Rs>
        implements IPanLifeCycleItspWebService {
    private static final long serialVersionUID = 1L;
    private static Logger log = LoggerFactory.getLogger(PanLifeCycleItspWebService.class);

    private PanLifeCycleItspV35RqMapper rqMapper =
            PanLifeCycleItspV35RqMapper.INSTANCE;
    private PanLifeCycleItspV35RsMapper rsMapper =
            PanLifeCycleItspV35RsMapper.INSTANCE;

    protected PanLifeCycleItspV35Rs execute(PanLifeCycleItspV35Rq request,
                                            PanLifeCycleItspV35Rs response, Connection connection)
            throws PCRDServiceException, java.sql.SQLException, JsonProcessingException {
        css_pan_lifecy_itsp_rq_v35 oraRq = new css_pan_lifecy_itsp_rq_v35();

        try {
            response = (PanLifeCycleItspV35Rs) ResponseUtilsV35.loopAttributes(new PanLifeCycleItspV35Rs());

        } catch (Exception e) {
            getLog().error("Fail to loopAttributes :", e);
        }

        response.setResponseInfo(new ResponseInfo());
        response.getResponseInfo().setErrorCode("00000");
        response.getResponseInfo().setResultID(EResultId.ProceedWithSuccess);
        response.getResponseInfo()
                .setResponseUID(request.getRequestInfo().getRequestUID());

        css_pan_lifecy_itsp_rs_v35[] oraRs =
                {new css_pan_lifecy_itsp_rs_v35()};

        //oraRs[0] = map(response, css_pan_lifecy_itsp_rs_v35.class);
        oraRs[0] = rsMapper.javaObjectToJavaCssType(response);

        //oraRq = map( request,css_pan_lifecy_itsp_rq_v35.class );
        oraRq = rqMapper.javaObjectToJavaCssType(request);

        oraRq.getrequestinfo().setproviderlogin(getLoginFromTeken());
        oraRq.getrequestinfo().setuserlanguage(getUserLanguage());

        PCRD_ITSP_TOKENIZATION_WS_V35_OUT service =
                new PCRD_ITSP_TOKENIZATION_WS_V35_OUT(connection);
        service.ws_pan_life_cycle_v35(oraRq, oraRs);
        //response = map( oraRs[0], PanLifeCycleItspV35Rs.class );
        response = rsMapper.javaCssTypeToJavaObject(oraRs[0]);
        if (!ErrorCodes.SUCCESS.equals(response.getResponseInfo().getErrorCode())) {
            return response;
        }

        log.info("Internal call passed correctly before calling API");
        ResponseInfo respInfo = null;
        try {
            ObjectMapper mapper = new ObjectMapper();
            Response rsItsp = null;
            respInfo = new ResponseInfo();
            String url =null;
            if(response.getNetworkCode().equals("02")){
                ObjectNode mDesRequest = mapper.createObjectNode();

                if (request.getActionReason().equals("ACCOUNT_UPDATE")) {

                    ObjectNode EncryptedData = mapper.createObjectNode();

                    ObjectNode TokenUpdateRequest = mapper.createObjectNode();
                    ObjectNode EncryptedAccountInformation = mapper.createObjectNode();
                    ObjectNode CurrentAccount = mapper.createObjectNode();
                    ObjectNode NewAccount = mapper.createObjectNode();

                    CurrentAccount.put("AccountPan", request.getEncryptData().getCardholderInfo().getPan());
                    NewAccount.put("AccountPan", request.getEncryptData().getReplaceCardholderInfo().getPan());


                    String expiryDateStr = request.getEncryptData()
                            .getReplaceCardholderInfo()
                            .getExpiryDate(); // ex: "2608"

                    if (expiryDateStr == null || !expiryDateStr.matches("\\d{4}")) {
                        throw new IllegalArgumentException("Invalid expiry date format, expected YYMM");
                    }

                    String year = expiryDateStr.substring(0, 2); // YY
                    String month = expiryDateStr.substring(2, 4); // MM

                    String formattedExpDate = month + year; // MMyy
                   /* Date expiryDateNew = request.getEncryptData().getReplaceCardholderInfo().getExpiryDate();
                    ZoneId zone = ZoneId.systemDefault();
                    LocalDate localExpiryDateNew = expiryDateNew.toInstant().atZone(zone).toLocalDate();
                    String formattedExpDate = String.format("%02d%02d", localExpiryDateNew.getMonthValue(), localExpiryDateNew.getYear() % 100);
                    */
                    NewAccount.put("ExpirationDate", formattedExpDate);
                    EncryptedData.set("CurrentAccount", CurrentAccount);
                    EncryptedData.set("NewAccount", NewAccount);


                    EncryptedAccountInformation.set("EncryptedData", EncryptedData);

                    ObjectNode encryptionInputRoot = mapper.createObjectNode();
                    encryptionInputRoot.set("EncryptedAccountInformation", EncryptedAccountInformation);

                    String encryptedPayload = encryptItspPayload(
                            request.getInstitutionCode(),
                            encryptionInputRoot.toString(),"SC"
                    );

                    JsonNode encryptedNode = mapper.readTree(encryptedPayload);
                    JsonNode encryptedAccountInformationNode = encryptedNode.get("EncryptedAccountInformation");
                    TokenUpdateRequest.set("EncryptedAccountInformation", encryptedAccountInformationNode);
                    mDesRequest.set("TokenUpdateRequest", TokenUpdateRequest);
                    mDesRequest.put("CommentText", request.getCommentText());
                    ObjectNode auditInfo = mapper.createObjectNode();
                    auditInfo.put("UserId", request.getAuditInfo().getUserId());
                    auditInfo.put("UserName", request.getAuditInfo().getUserName());
                    auditInfo.put("Organization", request.getAuditInfo().getOrganisation());
                    auditInfo.put("Phone", request.getAuditInfo().getPhone());

                    mDesRequest.set("AuditInfo", auditInfo);

                    url = InitConfig.getInstance().getVariableGlobal("mdesCSEndPoint") + "/mdes/csapi/v2/token/update";

                } else if (request.getActionReason().equals("ACCOUNT_CLOSED")) {
                    ObjectNode encryptedData = mapper.createObjectNode();

                    encryptedData.put("accountNumber", request.getEncryptData().getCardholderInfo().getPan());
                    ObjectNode encryptionInputRoot = mapper.createObjectNode();
                    encryptionInputRoot.set("encryptedData", encryptedData);

                    String encryptedPayload = encryptItspPayload(
                            request.getInstitutionCode(),
                            encryptionInputRoot.toString(),
                            "PAM");
                    JsonNode encryptedNode = mapper.readTree(encryptedPayload);
                    JsonNode encryptedAccountInformationNode = encryptedNode.get("encryptedPayload");
                    mDesRequest.set("encryptedPayload", encryptedAccountInformationNode);
                    mDesRequest.put("requestId", request.getRequestInfo().getRequestUID());
                    url = InitConfig.getInstance().getVariableGlobal("mdesPAMEndPoint") + "/paa/paymentaccount/static/1/0/closeAccount";

                }

                String finalMasterCardJson = mapper.writerWithDefaultPrettyPrinter().writeValueAsString(mDesRequest);
                rsItsp = prepareAndSendRequestToMC(request.getInstitutionCode(), "POST", url, finalMasterCardJson, "PAM");

            }

            else {
                ObjectNode visaRequest = mapper.createObjectNode();
                visaRequest.put("operationReason", request.getCommentText());
                visaRequest.put("operationReasonCode", request.getActionReason());
                visaRequest.put("operationType", request.getAction());
                ObjectNode encryptedData = mapper.createObjectNode();
                ObjectNode cardholderInfo = mapper.createObjectNode();
                ObjectNode replaceCardholderInfo = mapper.createObjectNode();
                ObjectNode accountLevelInfo = mapper.createObjectNode();
                ObjectNode customerContactInfo = mapper.createObjectNode();
                ObjectNode address = mapper.createObjectNode();
                ObjectNode replaceExpirationDate = mapper.createObjectNode();
                String expiryDateOld = request.getEncryptData().getCardholderInfo().getExpiryDate();
                String expiryDateNew = request.getEncryptData().getReplaceCardholderInfo().getExpiryDate();

                ZoneId zone = ZoneId.systemDefault();





                int serverYear = Year.now(ZoneId.systemDefault()).getValue(); // 2025
                int century = (serverYear / 100) * 100; // 2000
                getLog().info("serverYear -_: {}",serverYear);
                getLog().info("century : {}",century);
                int yy = Integer.parseInt(request.getEncryptData().getCardholderInfo().getExpiryDate().substring(0, 2));
                int month = Integer.parseInt(request.getEncryptData().getCardholderInfo().getExpiryDate().substring(2, 4));
                getLog().info("yy : {}",yy);
                getLog().info("month : {}",month);
                int year = century + yy;
                getLog().info("year : {}",year);

                int yyNew = Integer.parseInt(request.getEncryptData().getReplaceCardholderInfo().getExpiryDate().substring(0, 2));
                int monthNew = Integer.parseInt(request.getEncryptData().getReplaceCardholderInfo().getExpiryDate().substring(2, 4));
                getLog().info("yyNew : {}",yyNew);
                getLog().info("monthNew : {}",monthNew);

                int yearNew = century + yyNew;
                getLog().info("yearNew : {}",yearNew);
                String formatedNewMonth = String.format("%02d", monthNew);
                String formatedMonth = String.format("%02d", month);
                getLog().info("formatedNewMonth : {}",formatedNewMonth);
                getLog().info("formatedMonth : {}",formatedMonth);

                if (request.getTspPanId() != null) {
                    if (request.getActionReason().equals("EXP_DATE_UPDATE")) {
                        ObjectNode expirationDate = mapper.createObjectNode();
                        expirationDate.put("month", formatedNewMonth );
                        expirationDate.put("year", String.valueOf(yearNew));
                        replaceExpirationDate.set("expirationDate", expirationDate);
                        encryptedData.set("replaceExpirationDate", replaceExpirationDate);
                        encryptedData.put("panReferenceID", request.getTspPanId());

                    } else if (request.getActionReason().equals("ACCOUNT_UPDATE")) {

                        ObjectNode expirationDateNew = mapper.createObjectNode();
                        expirationDateNew.put("month", formatedNewMonth);
                        expirationDateNew.put("year", String.valueOf(yearNew));

                        replaceCardholderInfo.set("expirationDate", expirationDateNew);
                        replaceCardholderInfo.put("primaryAccountNumber", Long.parseLong(request.getEncryptData().getReplaceCardholderInfo().getPan()));

                        //LBO
                        // encryptedData.put("panReferenceID", request.getTspPanId());
                        cardholderInfo.put("primaryAccountNumber", Long.parseLong(request.getEncryptData().getCardholderInfo().getPan()));
                        ObjectNode expirationDateOld = mapper.createObjectNode();
                        expirationDateOld.put("month", formatedMonth);
                        expirationDateOld.put("year",String.valueOf(year));
                        cardholderInfo.set("expirationDate", expirationDateOld);
                        //LBO
                        encryptedData.set("cardholderInfo", cardholderInfo);
                        encryptedData.set("replaceCardholderInfo", replaceCardholderInfo);


                    } else if (request.getActionReason().equals("ACCOUNT_CLOSED")) {
                        encryptedData.put("panReferenceID", request.getTspPanId());

                    }

                } else {
                    address.put("line1", request.getAuditInfo().getPhone());
                    address.put("companyName", request.getAuditInfo().getOrganisation());
                    customerContactInfo.set("address", address);
                    accountLevelInfo.set("customerContactInfo", customerContactInfo);
                    cardholderInfo.put("primaryAccountNumber", Long.parseLong(request.getEncryptData().getCardholderInfo().getPan()));
                    ObjectNode expirationDateOld = mapper.createObjectNode();
                    expirationDateOld.put("month", yy);
                    expirationDateOld.put("year", formatedMonth);
                    cardholderInfo.set("expirationDate", expirationDateOld);


                    replaceCardholderInfo.put("primaryAccountNumber", Long.parseLong(request.getEncryptData().getReplaceCardholderInfo().getPan()));
                    ObjectNode expirationDateNew = mapper.createObjectNode();
                    expirationDateNew.put("month", yyNew);
                    expirationDateNew.put("year", formatedNewMonth);

                    replaceCardholderInfo.set("expirationDate", expirationDateNew);
                    encryptedData.set("cardholderInfo", cardholderInfo);
                    encryptedData.set("cardholderInfo", cardholderInfo);
                    encryptedData.set("replaceCardholderInfo", replaceCardholderInfo);
                    encryptedData.set("accountLevelInfo", accountLevelInfo);


                }




                // rajae   String encryptedPayload = encrpytAndSignPayload(encryptedData.toString(), request.getInstitutionCode());



                //LBO//
                // getLog().info("Encrypted data PanLifecycle ==> : {}",encryptedData.toString());
                //LBO//

                visaRequest.put("encryptedData", JwEncryptionJwSignatureUtils.getInstance()
                        .encryptAndSigneToVts(mapper.writeValueAsString(encryptedData)));
                getLog().info("writeValueAsString Encrypted data PanLifecycle >> : {}",mapper.writeValueAsString(encryptedData));


                String finalVisaJson = mapper.writerWithDefaultPrettyPrinter().writeValueAsString(visaRequest);
                String apiKey = JwEncryptionJwSignatureUtils.getInstance().getVtsApiKey().get(request.getInstitutionCode());
                url = InitConfig.getInstance().getVariableGlobal("vtsEndPoint") +
                        "/vtis/v1/pan/lifecycle";
                String sharedSecret = JwEncryptionJwSignatureUtils.getInstance().getVtsSharedSecret().get(request.getInstitutionCode());

                String path_xpaytoken = "vtis/v1/pan/lifecycle";
                rsItsp = callVtsApis(url, "POST", request.getInstitutionCode(), finalVisaJson, path_xpaytoken, apiKey, sharedSecret, PanLifeCycleRs.class);




            }
            int status = rsItsp.getStatusInfo().getStatusCode();
            response.setNetworkCode(null);

            if (status == 200) {
                respInfo.setResultID(EResultId.ProceedWithSuccess);
                respInfo.setResponseUID(request.getRequestInfo().getRequestUID());
                respInfo.setErrorCode("00000");
                respInfo.setErrorDescription("SUCCESS");

            } else {
                respInfo.setResultID(EResultId.SystemError);
                respInfo.setResponseUID(request.getRequestInfo().getRequestUID());
                respInfo.setErrorCode("99999");
                respInfo.setErrorDescription("ERROR");
            }
        } catch (Exception e) {
            getLog().error("Customer service call exception", e);
        }
        response.setResponseInfo(respInfo);

        //API-2360
        return response;

    }

    protected PanLifeCycleItspV35Rs cleanResponse(
            PanLifeCycleItspV35Rs response) {
        ResponseInfo responseInfo = response.getResponseInfo();
        response = new PanLifeCycleItspV35Rs();
        response.setResponseInfo(responseInfo);
        return response;
    }

    public PanLifeCycleItspV35Rs panLifeCycleItsp_35(
            PanLifeCycleItspV35Rq request) {
        PanLifeCycleItspV35Rs response = new PanLifeCycleItspV35Rs();
        String message = null;

        try {
            message = validateRequest("PanLifeCycleItsp", request);
        } catch (Exception e) {
            response.setResponseInfo(buildMessageError(e,
                    request.getRequestInfo().getRequestUID()));
            logResponse(response, request, "panLifeCycleItsp_35");
            return response;
        }

        if (message != null && !message.isEmpty()) {
            response.setResponseInfo(buildMessageError(message,
                    request.getRequestInfo().getRequestUID()));

            logResponse(response, request, "panLifeCycleItsp_35");
            return response;
        }
        response = (PanLifeCycleItspV35Rs) encapsuleExecution(request, response);
        logResponse(response, request, "panLifeCycleItsp_35");
        return response;
    }

    @jakarta.ws.rs.POST
    @Path("Itsp/PanLifeCycleItsp/V2")
    @Operation(summary = "panLifeCycleItsp_35", description = "panLifeCycleItsp_35 Web Service ", responses =  {
            @ApiResponse(content = @Content(mediaType = "application/json", schema = @Schema(implementation = PanLifeCycleItspV35Rs.class)
            )
                    , responseCode = "200", description = "ProceedWithSuccess")
    }
    )
    public Response panLifeCycleItsp_35Post(
            @RequestBody(description = "PanLifeCycleItspRq Request", required = true, content = @Content(mediaType = "application/json", schema = @Schema(implementation = PanLifeCycleItspRq.class)
            )
            )
            PanLifeCycleItspRq request) {
        PanLifeCycleItspV35Rs responsev35= new PanLifeCycleItspV35Rs();
        PanLifeCycleItspV35Rq requestv35= new PanLifeCycleItspV35Rq();


        EncryptDataV35 decryptedValue=new EncryptDataV35();

        String decryptedData = null;

        ObjectMapper mapper = new ObjectMapper();
        try {
            decryptedData = decryptItspPayload(request.getInstitutionCode(),request.getEncryptedData());


        } catch (Exception e) {
            getLog().error("ERROR WIHLE DECRYPT REQUEST :", e);

            responsev35.setResponseInfo(new ResponseInfo());
            responsev35.getResponseInfo().setErrorCode("T0109");
            responsev35.getResponseInfo().setErrorDescription("CRYPTOGRAPHY ERROR");
            responsev35.getResponseInfo().setResultID(EResultId.Error);
            responsev35.getResponseInfo().setResponseUID(request.getRequestInfo().getRequestUID());
            return Response.status(buildStatusResponce(responsev35)).entity(responsev35).build();
        }
        try {


            mapper.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
            if (decryptedData != null) {

                decryptedValue = mapper.readValue(decryptedData, EncryptDataV35.class);

            }

            requestv35 = mapper.convertValue(request, PanLifeCycleItspV35Rq.class);
            if (decryptedData != null) {

                requestv35.setEncryptData(decryptedValue);

            }



        } catch (IOException e) {
            getLog().error("ERROR WHILE PARSING JSON REQUEST :", e);
        }

        responsev35 = panLifeCycleItsp_35(requestv35);

        if (!responsev35.getResponseInfo().getErrorCode().equals("00000")) {
            return Response.status(Response.Status.OK).entity(responsev35.getResponseInfo()).build();
        }


        //logResponse(response,request,"panLifeCycleItsp_35");
        return Response.status(buildStatusResponce(responsev35)).entity(responsev35)
                .build();
    }
}
