#!/usr/bin/env python3
"""Credencia uma entidade (hospital/clinica/laboratorio/medico/plano de
saude) na rede D-OH, do ponto de vista do Trust Anchor (Ministerio da
Saude) — Secao 3.2 e Figura 2 do paper.

Passos:
  1. Cria uma conexao DIDComm (Out-of-Band, didexchange) entre o agente do
     Trust Anchor e o agente da entidade.
  2. Emite uma EntityRoleCredential para a entidade (schema criado por
     register_role_schema.py).
  3. Registra a entidade em services/trust-registry (indice auditavel).

Como os agentes rodam no mesmo docker-compose network, este script chama
diretamente a Admin API de ambos os agentes (viavel para bootstrap/dev;
em producao esse fluxo seria conduzido por um portal/backoffice do
Ministerio da Saude, nao por um script operado manualmente).

Uso:
    python onboard_entity.py \
        --trust-anchor-url http://localhost:8021 --trust-anchor-key $TA_KEY \
        --entity-admin-url http://localhost:8031 --entity-api-key $HOSP_KEY \
        --entity-name "Hospital Geral do Estado" --role hospital \
        --trust-registry-url http://localhost:9002
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import httpx
from _acapy import AcaPyAdmin

VALID_ROLES = {"hospital", "clinica", "laboratorio", "medico", "plano_saude"}


def establish_connection(trust_anchor: AcaPyAdmin, entity: AcaPyAdmin) -> tuple[str, str]:
    """Cria convite OOB no Trust Anchor e o entrega diretamente ao agente da
    entidade, retornando (connection_id no trust anchor, connection_id na
    entidade)."""

    invitation = trust_anchor.post(
        "/out-of-band/create-invitation",
        {
            "alias": "doh-onboarding",
            "handshake_protocols": ["https://didcomm.org/didexchange/1.1"],
            "use_public_did": True,
        },
    )
    ta_connection_id = invitation["invi_msg_id"]

    receive = entity.post(
        "/out-of-band/receive-invitation",
        invitation["invitation"],
    )
    entity_connection_id = receive["connection_id"]

    # Aguarda handshake concluir (didexchange e assincrono)
    for _ in range(30):
        state = entity.get(f"/connections/{entity_connection_id}")["state"]
        if state in ("active", "completed"):
            break
        time.sleep(1)
    else:
        raise TimeoutError(f"conexao nao ativou a tempo (ultimo estado: {state})")

    # Resolve o connection_id correspondente do lado do trust anchor
    ta_connections = trust_anchor.get("/connections", params={"invitation_msg_id": ta_connection_id})
    results = ta_connections.get("results") or []
    if not results:
        raise RuntimeError("nao foi possivel localizar a conexao no trust anchor")

    return results[0]["connection_id"], entity_connection_id


def find_cred_def(trust_anchor: AcaPyAdmin, trust_anchor_did: str) -> str:
    from register_role_schema import ENTITY_ROLE_SCHEMA_NAME, ENTITY_ROLE_SCHEMA_VERSION

    # Rotas AnonCreds (askar-anoncreds), nao Indy legado — ver nota em
    # register_role_schema.py.
    schemas = trust_anchor.get(
        "/anoncreds/schemas",
        params={
            "schema_name": ENTITY_ROLE_SCHEMA_NAME,
            "schema_version": ENTITY_ROLE_SCHEMA_VERSION,
            "schema_issuer_id": trust_anchor_did,
        },
    )
    schema_ids = schemas.get("schema_ids") or []
    if not schema_ids:
        raise RuntimeError("EntityRoleCredential schema nao encontrado — rode register_role_schema.py antes")

    cred_defs = trust_anchor.get(
        "/anoncreds/credential-definitions",
        params={"schema_id": schema_ids[0], "issuer_id": trust_anchor_did},
    )
    cred_def_ids = cred_defs.get("credential_definition_ids") or []
    if not cred_def_ids:
        raise RuntimeError("EntityRoleCredential cred-def nao encontrado — rode register_role_schema.py antes")
    return cred_def_ids[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trust-anchor-url", required=True)
    parser.add_argument("--trust-anchor-key", default=None)
    parser.add_argument("--entity-admin-url", required=True)
    parser.add_argument("--entity-api-key", default=None)
    parser.add_argument("--entity-name", required=True)
    parser.add_argument("--role", required=True, choices=sorted(VALID_ROLES))
    parser.add_argument("--trust-registry-url", required=True)
    args = parser.parse_args()

    trust_anchor = AcaPyAdmin(args.trust_anchor_url, args.trust_anchor_key)
    entity = AcaPyAdmin(args.entity_admin_url, args.entity_api_key)

    ta_did = trust_anchor.create_public_did_if_needed()
    entity_did = entity.create_public_did_if_needed()

    print(f"[i] trust anchor DID: {ta_did}")
    print(f"[i] entidade DID:     {entity_did}")

    ta_connection_id, _entity_connection_id = establish_connection(trust_anchor, entity)
    print(f"[+] conexao estabelecida (trust anchor connection_id={ta_connection_id})")

    cred_def_id = find_cred_def(trust_anchor, ta_did)
    registered_at = datetime.now(timezone.utc).isoformat()

    trust_anchor.post(
        "/issue-credential-2.0/send",
        {
            "connection_id": ta_connection_id,
            "comment": f"EntityRoleCredential para {args.entity_name}",
            "credential_preview": {
                "@type": "issue-credential/2.0/credential-preview",
                "attributes": [
                    {"name": "entityDid", "value": entity_did},
                    {"name": "entityName", "value": args.entity_name},
                    {"name": "role", "value": args.role},
                    {"name": "registeredBy", "value": ta_did},
                    {"name": "registeredAt", "value": registered_at},
                ],
            },
            "filter": {
                "anoncreds": {"cred_def_id": cred_def_id},
                "indy": {"cred_def_id": cred_def_id},
            },
        },
    )
    print("[+] EntityRoleCredential emitida")

    httpx.post(
        f"{args.trust_registry_url}/entities",
        json={
            "did": entity_did,
            "name": args.entity_name,
            "role": args.role,
            "registered_by": ta_did,
        },
        timeout=15.0,
    ).raise_for_status()
    print("[+] entidade registrada no trust-registry")


if __name__ == "__main__":
    main()
