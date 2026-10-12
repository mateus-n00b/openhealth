from fastapi import FastAPI, HTTPException

from app.acapy_client import AcaPyAdminError, AcaPyIssuerClient
from app.config import settings
from app.fhir_mapper import (
    DIAGNOSTIC_REPORT_SCHEMA_ATTRIBUTES,
    build_fhir_diagnostic_report,
    to_anoncreds_attributes,
)
from app.schemas import IssueCredentialRequest, IssueCredentialResponse

app = FastAPI(
    title="D-OH FHIR-VC Bridge",
    description=(
        "Ponte entre recursos clinicos FHIR/HL7 e Verifiable Credentials, "
        "implementando o Algoritmo 1 do paper Decentralized-OpenHealth. "
        "Delega a assinatura/emissao ao ACA-Py do emissor."
    ),
)

# TODO(multi-emissor): hoje o bridge fala com um unico ACA-Py fixo
# (settings.acapy_issuer_admin_url), assumindo um deployment por emissor.
# Em producao, resolver o cliente ACA-Py correto a partir do DID do emissor
# autenticado na requisicao (ex. via services/trust-registry), mantendo um
# client cacheado por emissor.
_acapy = AcaPyIssuerClient(
    base_url=settings.acapy_issuer_admin_url,
    api_key=settings.acapy_admin_api_key,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.on_event("shutdown")
async def _shutdown() -> None:
    await _acapy.aclose()


@app.post("/diagnostic-reports/issue", response_model=IssueCredentialResponse)
async def issue_diagnostic_report_credential(req: IssueCredentialRequest) -> IssueCredentialResponse:
    """Emite uma DiagnosticReportCredential a partir de um payload FHIR.

    Pre-requisitos (fora do escopo deste endpoint, ver scripts/demo_*.sh):
      1. Conexao DIDComm ja estabelecida entre o agente emissor e a
         HealthDID do titular (req.connection_id).
      2. Schema/cred-def "DiagnosticReportCredential" ja registrados
         (ver governance/trust-anchor/scripts/register_role_schema.py).
      3. Emissor credenciado no trust-registry (Fig. 2 do paper) — a
         verificacao explicita deste passo e um TODO: hoje o bridge confia
         no fato de estar rodando atras do ACA-Py do proprio emissor.
    """

    fhir_report = build_fhir_diagnostic_report(req.diagnostic_report)

    # Estrategia de armazenamento hibrido (Secao 3.3.1): se o payload
    # referenciar um ativo denso ja ancorado via services/ipfs-anchor, o
    # hash chega pronto em req.diagnostic_report.media — este endpoint nao
    # faz upload, apenas repassa a ancora recebida.

    if not settings.diagnostic_report_cred_def_id:
        raise HTTPException(
            status_code=503,
            detail=(
                "DIAGNOSTIC_REPORT_CRED_DEF_ID nao configurado. Rode o bootstrap "
                "de governanca (make bootstrap) antes de emitir credenciais."
            ),
        )

    attributes = to_anoncreds_attributes(
        fhir_report,
        did_paciente=req.did_paciente,
        did_emissor=req.diagnostic_report.performer[0].reference
        if req.diagnostic_report.performer
        else "",
    )

    try:
        result = await _acapy.issue_credential(
            connection_id=req.connection_id,
            cred_def_id=settings.diagnostic_report_cred_def_id,
            attributes=attributes,
            comment=f"DiagnosticReportCredential {fhir_report['id']}",
        )
    except AcaPyAdminError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return IssueCredentialResponse(
        credential_exchange_id=result.get("cred_ex_id", result.get("credential_exchange_id", "")),
        fhir_report=fhir_report,
    )


@app.get("/schema/diagnostic-report-attributes")
async def diagnostic_report_schema_attributes() -> dict:
    """Utilitario para scripts de bootstrap consultarem os atributos do schema."""

    return {"attributes": DIAGNOSTIC_REPORT_SCHEMA_ATTRIBUTES}
