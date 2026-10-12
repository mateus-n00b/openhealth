#!/usr/bin/env python3
"""Cria o credential-definition de DiagnosticReportCredential para UM emissor.

Deve ser rodado uma vez por emissor (hospital, clinica, laboratorio) apos
register_role_schema.py ter publicado o schema global. O cred_def_id
resultante e o valor a configurar em DIAGNOSTIC_REPORT_CRED_DEF_ID no
ambiente do services/fhir-vc-bridge correspondente a esse emissor
(ver docker-compose.yml, secao fhir-vc-bridge).

Uso:
    python create_issuer_cred_def.py \
        --admin-url http://localhost:8031 \
        --api-key $ISSUER_HOSPITAL_ADMIN_API_KEY \
        --schema-id <schema_id impresso por register_role_schema.py>
"""

from __future__ import annotations

import argparse

from _acapy import AcaPyAdmin


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-url", required=True)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--schema-id", required=True)
    parser.add_argument("--tag", default="doh-diagnostic-report")
    args = parser.parse_args()

    admin = AcaPyAdmin(args.admin_url, args.api_key)
    issuer_did = admin.create_public_did_if_needed()

    # Rotas AnonCreds (askar-anoncreds), nao as rotas Indy legado — ver
    # nota equivalente em register_role_schema.py.
    existing = admin.get(
        "/anoncreds/credential-definitions",
        params={"schema_id": args.schema_id, "issuer_id": issuer_did},
    )
    ids = existing.get("credential_definition_ids") or []
    if ids:
        print(f"[=] cred-def ja existe: {ids[0]}")
        cred_def_id = ids[0]
    else:
        result = admin.post(
            "/anoncreds/credential-definition",
            {
                "credential_definition": {
                    "issuerId": issuer_did,
                    "schemaId": args.schema_id,
                    "tag": args.tag,
                },
                "options": {
                    "support_revocation": True,
                    "revocation_registry_size": 1000,
                },
            },
        )
        cred_def_id = result["credential_definition_state"]["credential_definition_id"]
        print(f"[+] cred-def criado: {cred_def_id}")

    print()
    print("Defina no ambiente do fhir-vc-bridge deste emissor:")
    print(f"  DIAGNOSTIC_REPORT_CRED_DEF_ID={cred_def_id}")


if __name__ == "__main__":
    main()
