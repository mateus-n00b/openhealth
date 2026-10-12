"""Cliente sobre a Admin API do ACA-Py, para as operacoes que o painel
expoe como CRUD web: DIDs/wallets, conexoes DIDComm e emissao de
credenciais de papel (EntityRoleCredential).

Duplica propositalmente parte da logica de
governance/trust-anchor/scripts/onboard_entity.py e _acapy.py — os dois
vivem em contextos de build Docker separados (imagens diferentes) e, para
um esqueleto, copiar essas ~80 linhas e' mais simples e mais legivel do
que criar um pacote Python compartilhado. Se isso divergir com o tempo,
esse e' o sinal de que vale a pena extrair um pacote comum.

Rotas sincronas (httpx.Client): FastAPI roda handlers `def` (nao `async
def`) em threadpool automaticamente, entao isso nao bloqueia o event loop
do servico mesmo fazendo chamadas de rede bloqueantes.
"""

from __future__ import annotations

import time

import httpx

from app.config import AgentConfig


class AcaPyAdminError(RuntimeError):
    pass


def _client(agent: AgentConfig) -> httpx.Client:
    headers = {"X-API-KEY": agent.api_key} if agent.api_key else {}
    return httpx.Client(base_url=agent.admin_url, headers=headers, timeout=30.0)


def _get(agent: AgentConfig, path: str, params: dict | None = None) -> dict:
    with _client(agent) as client:
        resp = client.get(path, params=params)
        if resp.status_code >= 300:
            raise AcaPyAdminError(f"GET {agent.key}{path} -> {resp.status_code}: {resp.text}")
        return resp.json()


def _post(agent: AgentConfig, path: str, json_body: dict | None = None) -> dict:
    with _client(agent) as client:
        resp = client.post(path, json=json_body or {})
        if resp.status_code >= 300:
            raise AcaPyAdminError(f"POST {agent.key}{path} -> {resp.status_code}: {resp.text}")
        return resp.json()


# -- DIDs / wallet --------------------------------------------------------

def list_dids(agent: AgentConfig) -> list[dict]:
    result = _get(agent, "/wallet/did")
    return result.get("results") or []


def create_did(agent: AgentConfig, make_public: bool) -> dict:
    created = _post(agent, "/wallet/did/create", {"method": "sov", "options": {"key_type": "ed25519"}})
    did_info = created["result"]
    if make_public:
        _post(agent, f"/wallet/did/public?did={did_info['did']}")
    return did_info


def get_public_did(agent: AgentConfig) -> dict | None:
    result = _get(agent, "/wallet/did/public")
    return result.get("result")


# -- Conexoes DIDComm -------------------------------------------------------

def list_connections(agent: AgentConfig) -> list[dict]:
    return _get(agent, "/connections").get("results") or []


def create_invitation(agent: AgentConfig, alias: str) -> dict:
    """Cria um convite OOB no agente `agent`. Retorna o corpo completo
    (inclui `invitation` para colar em receive_invitation de outro
    agente, e `invi_msg_id` para localizar a conexao depois)."""

    return _post(
        agent,
        "/out-of-band/create-invitation",
        {
            "alias": alias,
            "handshake_protocols": ["https://didcomm.org/didexchange/1.1"],
            "use_public_did": True,
        },
    )


def receive_invitation(agent: AgentConfig, invitation: dict) -> dict:
    return _post(agent, "/out-of-band/receive-invitation", invitation)


def wait_connection_active(agent: AgentConfig, connection_id: str, timeout_s: int = 20) -> str:
    deadline = time.monotonic() + timeout_s
    state = "unknown"
    while time.monotonic() < deadline:
        state = _get(agent, f"/connections/{connection_id}")["state"]
        if state in ("active", "completed"):
            return state
        time.sleep(1)
    raise TimeoutError(f"conexao {connection_id} em {agent.key} nao ativou a tempo (ultimo estado: {state})")


def find_connection_by_invitation(agent: AgentConfig, invi_msg_id: str) -> str:
    results = _get(agent, "/connections", params={"invitation_msg_id": invi_msg_id}).get("results") or []
    if not results:
        raise AcaPyAdminError(f"conexao nao encontrada em {agent.key} para invitation_msg_id={invi_msg_id}")
    return results[0]["connection_id"]


# -- EntityRoleCredential (schema/cred-def, rotas AnonCreds) ---------------

ENTITY_ROLE_SCHEMA_NAME = "EntityRoleCredential"
ENTITY_ROLE_SCHEMA_VERSION = "1.0"


def find_entity_role_cred_def(trust_anchor: AgentConfig, trust_anchor_did: str) -> str:
    schemas = _get(
        trust_anchor,
        "/anoncreds/schemas",
        params={
            "schema_name": ENTITY_ROLE_SCHEMA_NAME,
            "schema_version": ENTITY_ROLE_SCHEMA_VERSION,
            "schema_issuer_id": trust_anchor_did,
        },
    )
    schema_ids = schemas.get("schema_ids") or []
    if not schema_ids:
        raise AcaPyAdminError(
            "schema EntityRoleCredential nao encontrado — rode "
            "governance/trust-anchor/scripts/register_role_schema.py primeiro"
        )

    cred_defs = _get(
        trust_anchor,
        "/anoncreds/credential-definitions",
        params={"schema_id": schema_ids[0], "issuer_id": trust_anchor_did},
    )
    cred_def_ids = cred_defs.get("credential_definition_ids") or []
    if not cred_def_ids:
        raise AcaPyAdminError(
            "cred-def EntityRoleCredential nao encontrado — rode "
            "governance/trust-anchor/scripts/register_role_schema.py primeiro"
        )
    return cred_def_ids[0]


def issue_entity_role_credential(
    trust_anchor: AgentConfig,
    connection_id: str,
    cred_def_id: str,
    entity_did: str,
    entity_name: str,
    role: str,
    trust_anchor_did: str,
    registered_at: str,
) -> dict:
    return _post(
        trust_anchor,
        "/issue-credential-2.0/send",
        {
            "connection_id": connection_id,
            "comment": f"EntityRoleCredential para {entity_name}",
            "credential_preview": {
                "@type": "issue-credential/2.0/credential-preview",
                "attributes": [
                    {"name": "entityDid", "value": entity_did},
                    {"name": "entityName", "value": entity_name},
                    {"name": "role", "value": role},
                    {"name": "registeredBy", "value": trust_anchor_did},
                    {"name": "registeredAt", "value": registered_at},
                ],
            },
            "filter": {
                "anoncreds": {"cred_def_id": cred_def_id},
                "indy": {"cred_def_id": cred_def_id},
            },
        },
    )
