#!/usr/bin/env python3
"""Bootstrap dos schemas AnonCreds do D-OH.

Cria (uma unica vez, globalmente) os schemas usados pelo ecossistema:
  - EntityRoleCredential : emitida pelo Trust Anchor para credenciar
    hospitais, clinicas, laboratorios, medicos e planos de saude
    (Fig. 2 / Secao 3.2 do paper).
  - DiagnosticReportCredential : emitida pelos emissores clinicos,
    consumida por services/fhir-vc-bridge (Algoritmo 1 do paper).

Corresponde a `createSchema` no ciclo de vida descrito na Tabela 1 do
paper ("Definicao do modelo FHIR e parametros da VC" — operacao unica e
offline, fora do caminho critico do atendimento).

Uso:
    python register_role_schema.py --admin-url http://localhost:8021 \
        --api-key $TRUST_ANCHOR_ADMIN_API_KEY
"""

from __future__ import annotations

import argparse

from _acapy import AcaPyAdmin

ENTITY_ROLE_SCHEMA_NAME = "EntityRoleCredential"
ENTITY_ROLE_SCHEMA_VERSION = "1.0"
ENTITY_ROLE_SCHEMA_ATTRIBUTES = [
    "entityDid",
    "entityName",
    "role",  # hospital | clinica | laboratorio | medico | plano_saude
    "registeredBy",  # DID do Trust Anchor
    "registeredAt",
]

DIAGNOSTIC_REPORT_SCHEMA_NAME = "DiagnosticReportCredential"
DIAGNOSTIC_REPORT_SCHEMA_VERSION = "1.0"
DIAGNOSTIC_REPORT_SCHEMA_ATTRIBUTES = [
    # Mantido em sincronia com
    # services/fhir-vc-bridge/app/fhir_mapper.py::DIAGNOSTIC_REPORT_SCHEMA_ATTRIBUTES
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


# NOTA — rotas AnonCreds, nao Indy legado: com wallet-type askar-anoncreds
# os endpoints antigos (/schemas, /schemas/created,
# /credential-definitions, /credential-definitions/created) nao existem —
# retornam 404. O perfil AnonCreds usa o prefixo /anoncreds/*, com corpo de
# requisicao aninhado (schema/credential_definition + options) e
# issuerId/schemaId/attrNames em vez de campos soltos em snake_case. Os
# nomes exatos de query params podem variar por versao do ACA-Py — se algo
# aqui nao bater, confira o Swagger em <admin-url>/api/docs.


def find_or_create_schema(
    admin: AcaPyAdmin, issuer_did: str, name: str, version: str, attributes: list[str]
) -> str:
    existing = admin.get(
        "/anoncreds/schemas",
        params={"schema_name": name, "schema_version": version, "schema_issuer_id": issuer_did},
    )
    ids = existing.get("schema_ids") or []
    if ids:
        print(f"[=] schema '{name}' ja existe: {ids[0]}")
        return ids[0]

    result = admin.post(
        "/anoncreds/schema",
        {
            "schema": {
                "issuerId": issuer_did,
                "attrNames": attributes,
                "name": name,
                "version": version,
            },
            "options": {},
        },
    )
    schema_id = result["schema_state"]["schema_id"]
    print(f"[+] schema '{name}' criado: {schema_id}")
    return schema_id


def find_or_create_cred_def(
    admin: AcaPyAdmin, issuer_did: str, schema_id: str, tag: str, support_revocation: bool
) -> str:
    existing = admin.get(
        "/anoncreds/credential-definitions",
        params={"schema_id": schema_id, "issuer_id": issuer_did},
    )
    ids = existing.get("credential_definition_ids") or []
    if ids:
        print(f"[=] cred-def '{tag}' ja existe: {ids[0]}")
        return ids[0]

    result = admin.post(
        "/anoncreds/credential-definition",
        {
            "credential_definition": {
                "issuerId": issuer_did,
                "schemaId": schema_id,
                "tag": tag,
            },
            "options": {
                "support_revocation": support_revocation,
                "revocation_registry_size": 1000 if support_revocation else None,
            },
        },
    )
    cred_def_id = result["credential_definition_state"]["credential_definition_id"]
    print(f"[+] cred-def '{tag}' criado: {cred_def_id}")
    return cred_def_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", required=True, help="Admin API do Trust Anchor")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    admin = AcaPyAdmin(args.admin_url, args.api_key)
    trust_anchor_did = admin.create_public_did_if_needed()

    role_schema_id = find_or_create_schema(
        admin, trust_anchor_did, ENTITY_ROLE_SCHEMA_NAME, ENTITY_ROLE_SCHEMA_VERSION, ENTITY_ROLE_SCHEMA_ATTRIBUTES
    )
    find_or_create_cred_def(
        admin, trust_anchor_did, role_schema_id, tag="doh-entity-role", support_revocation=True
    )

    # O schema e publicado pelo Trust Anchor (papel neutro de "schema
    # publisher" no Indy), mas o cred-def de DiagnosticReportCredential
    # precisa ser criado por CADA emissor (hospital/clinica/laboratorio)
    # contra este schema_id, pois o cred_def_id incorpora o DID do
    # issuer — ver create_issuer_cred_def.py.
    report_schema_id = find_or_create_schema(
        admin,
        trust_anchor_did,
        DIAGNOSTIC_REPORT_SCHEMA_NAME,
        DIAGNOSTIC_REPORT_SCHEMA_VERSION,
        DIAGNOSTIC_REPORT_SCHEMA_ATTRIBUTES,
    )

    print()
    print("Schema publicado. Para cada emissor, rode:")
    print(
        "  python create_issuer_cred_def.py --admin-url <issuer-admin-url> "
        f"--api-key <issuer-api-key> --schema-id {report_schema_id}"
    )


if __name__ == "__main__":
    main()
