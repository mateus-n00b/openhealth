"""Mapeamento FHIR (R4 DiagnosticReport) -> atributos de Verifiable Credential.

Implementa a Etapa 1 e parte da Etapa 2 do Algoritmo 1 do paper
("Geracao de Credencial Verificavel com FHIR DiagnosticReport"):

    1. Estruturacao do Recurso Medico (FHIR R4)
    2. Construcao da Credencial Verificavel (W3C) / acoplamento do
       payload FHIR ao credentialSubject

A Etapa 3 (assinatura criptografica / prova) e delegada ao ACA-Py do
emissor (ver acapy_client.py) — o ACA-Py assina a credencial no momento da
emissao, entao este modulo so precisa produzir o recurso FHIR e o conjunto
de atributos a oferecer.

NOTA sobre o esquema de assinatura: o paper descreve BBS+ / JSON-LD para
habilitar ZKPs de divulgacao seletiva no nivel de atributo (Secao 1), mas a
prova de conceito (Secao 3.3.1) usa uma wallet askar-anoncreds via ACA-Py.
Este esqueleto segue a PoC (AnonCreds), que ja oferece divulgacao seletiva
e provas de predicado (ZKP) nativamente via present-proof-2.0 — ver
scripts/demo_present_proof.sh. Trocar para BBS+/JSON-LD (credenciais
`vc-di`, proof type `BbsBlsSignature2020`) e um ponto de extensao direto:
substituir issue_credential() em acapy_client.py pelo endpoint
`/issue-credential-2.0/send` com `filter.ld_proof` no lugar de
`filter.anoncreds`.
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas import DiagnosticReportIn

FHIR_CONTEXT = "https://www.w3.org/2018/credentials/v1"
DIAGNOSTIC_REPORT_CREDENTIAL_TYPE = ["VerifiableCredential", "DiagnosticReportCredential"]


def build_fhir_diagnostic_report(payload: DiagnosticReportIn) -> dict[str, Any]:
    """Etapa 1 do Algoritmo 1: monta o recurso FHIR DiagnosticReport."""

    report: dict[str, Any] = {
        "resourceType": "DiagnosticReport",
        "id": payload.report_id,
        "status": payload.status,
        "category": [c.model_dump(exclude_none=True) for c in payload.category],
        "code": payload.code.model_dump(exclude_none=True),
        "subject": {"reference": payload.subject_reference},
        "performer": [p.model_dump(exclude_none=True) for p in payload.performer],
        "result": [r.model_dump(exclude_none=True) for r in payload.result],
        "effectiveDateTime": payload.effective_date_time,
        "issued": payload.issued,
    }

    if payload.media:
        # Ancoragem do hash de cada ativo denso armazenado externamente
        # (IPFS) — linha 12 do Algoritmo 1. Um item de lista por ARQUIVO
        # (nao por exame): cada um foi cifrado com sua propria DEK
        # descartavel antes de chegar ao services/ipfs-anchor — ver
        # docstring de app/schemas.py::MediaAnchor. `hash` e' sempre sobre
        # o CIPHERTEXT; a DEK nunca entra neste payload.
        report["media"] = [m.model_dump(exclude_none=True) for m in payload.media]

    return report


def build_credential_subject(fhir_report: dict[str, Any], did_paciente: str) -> dict[str, Any]:
    """Etapa 2 do Algoritmo 1: acopla o payload FHIR ao sujeito da credencial."""

    return {
        "id": did_paciente,
        "fhirResource": fhir_report,
    }


def to_anoncreds_attributes(
    fhir_report: dict[str, Any], did_paciente: str, did_emissor: str
) -> list[dict[str, str]]:
    """Converte o recurso FHIR em atributos planos AnonCreds.

    AnonCreds (usado pela wallet askar-anoncreds da PoC) exige atributos
    string simples — nao objetos aninhados/listas. Serializamos o recurso
    FHIR completo (incluindo a lista de `media`, um item por arquivo
    cifrado) em `fhirResource`, para preservar toda a estruturacao
    semantica como no Algoritmo 1, e expomos campos indexados adicionais
    para permitir provas de predicado (ex. `issued` para provar
    "exame emitido nos ultimos N dias" sem revelar a data exata — ZKP).

    `mediaHash` so e' populado como atributo plano quando ha EXATAMENTE um
    arquivo (caso comum de laudo/exame simples) — com multiplos arquivos
    (ex. serie DICOM), cada hash/nonce/key_escrow_ref individual so existe
    dentro do `fhirResource` serializado; nao ha, no AnonCreds, um jeito
    nativo de expor uma lista como atributo indexavel para predicado.
    """

    code = fhir_report.get("code", {})
    media_list = fhir_report.get("media") or []
    media_hash = media_list[0].get("hash", "") if len(media_list) == 1 else ""

    return [
        {"name": "reportId", "value": fhir_report["id"]},
        {"name": "status", "value": fhir_report["status"]},
        {"name": "loincCode", "value": code.get("code", "")},
        {"name": "loincDisplay", "value": code.get("display", "")},
        {"name": "subjectDid", "value": did_paciente},
        {"name": "issuerDid", "value": did_emissor},
        {"name": "effectiveDateTime", "value": fhir_report["effectiveDateTime"]},
        {"name": "issued", "value": fhir_report["issued"]},
        {"name": "mediaCount", "value": str(len(media_list))},
        {"name": "mediaHash", "value": media_hash},
        {"name": "fhirResource", "value": json.dumps(fhir_report, ensure_ascii=False)},
    ]


# Atributos do schema AnonCreds correspondente (usado em
# governance/trust-anchor/scripts/register_role_schema.py e equivalentes).
DIAGNOSTIC_REPORT_SCHEMA_ATTRIBUTES = [
    "reportId",
    "status",
    "loincCode",
    "loincDisplay",
    "subjectDid",
    "issuerDid",
    "effectiveDateTime",
    "issued",
    "mediaCount",
    "mediaHash",
    "fhirResource",
]
