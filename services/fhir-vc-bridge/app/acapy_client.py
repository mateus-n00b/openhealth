"""Cliente HTTP fino sobre a Admin API do ACA-Py do emissor.

Concentra toda a interacao com o gestor de identidades (ACA-Py) em um so
lugar, para que o restante do bridge trabalhe apenas com conceitos FHIR/VC.

Referencias de protocolo Aries usadas:
  - RFC 0453 / Issue Credential 2.0  (emissao)
  - RFC 0454 / Present Proof 2.0     (apresentacao — ver verifier_client.py)
"""

from __future__ import annotations

import httpx


class AcaPyAdminError(RuntimeError):
    pass


class AcaPyIssuerClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 15.0):
        headers = {"X-API-KEY": api_key} if api_key else {}
        self._client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, json_body: dict) -> dict:
        resp = await self._client.post(path, json=json_body)
        if resp.status_code >= 300:
            raise AcaPyAdminError(f"POST {path} -> {resp.status_code}: {resp.text}")
        return resp.json()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        resp = await self._client.get(path, params=params)
        if resp.status_code >= 300:
            raise AcaPyAdminError(f"GET {path} -> {resp.status_code}: {resp.text}")
        return resp.json()

    # -- Schema / Credential Definition (equivalentes a createSchema /
    #    createCredentialDefinition no modelo Indy-Besu citado no paper) ----
    #
    # NOTA — rotas AnonCreds (askar-anoncreds), nao Indy legado: os agentes
    # deste esqueleto usam wallet-type askar-anoncreds, entao as rotas
    # antigas (/schemas, /credential-definitions e as variantes
    # /*/created) nao existem e retornam 404. O perfil AnonCreds expoe
    # /anoncreds/* com corpo aninhado (schema/credential_definition +
    # options) e issuerId/schemaId/attrNames em vez de campos soltos em
    # snake_case. Confira <admin-url>/api/docs se algum nome de campo/query
    # param nao bater com a versao do ACA-Py instalada.

    async def find_or_create_schema(
        self, issuer_did: str, schema_name: str, schema_version: str, attributes: list[str]
    ) -> str:
        existing = await self._get(
            "/anoncreds/schemas",
            params={
                "schema_name": schema_name,
                "schema_version": schema_version,
                "schema_issuer_id": issuer_did,
            },
        )
        schema_ids = existing.get("schema_ids") or []
        if schema_ids:
            return schema_ids[0]

        result = await self._post(
            "/anoncreds/schema",
            {
                "schema": {
                    "issuerId": issuer_did,
                    "attrNames": attributes,
                    "name": schema_name,
                    "version": schema_version,
                },
                "options": {},
            },
        )
        return result["schema_state"]["schema_id"]

    async def find_or_create_cred_def(
        self, issuer_did: str, schema_id: str, tag: str, support_revocation: bool = True
    ) -> str:
        existing = await self._get(
            "/anoncreds/credential-definitions",
            params={"schema_id": schema_id, "issuer_id": issuer_did},
        )
        cred_def_ids = existing.get("credential_definition_ids") or []
        if cred_def_ids:
            return cred_def_ids[0]

        result = await self._post(
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
        return result["credential_definition_state"]["credential_definition_id"]

    # -- Emissao de credencial (Etapa 3 do Algoritmo 1: assinatura) ---------

    async def issue_credential(
        self,
        connection_id: str,
        cred_def_id: str,
        attributes: list[dict[str, str]],
        comment: str = "",
        auto_remove: bool = False,
    ) -> dict:
        """Envia a credencial via issue-credential-2.0 (RFC 0453).

        Equivale a `createOrUpdateEntry` no ciclo de vida descrito no paper
        (Tabela 1): fora do caminho critico do atendimento, a verificacao
        posterior e feita off-chain via present-proof.
        """

        body = {
            "connection_id": connection_id,
            "comment": comment,
            "auto_remove": auto_remove,
            "credential_preview": {
                "@type": "issue-credential/2.0/credential-preview",
                "attributes": attributes,
            },
            "filter": {
                "anoncreds": {"cred_def_id": cred_def_id},
                # fallback para builds do ACA-Py que ainda usam o filtro "indy"
                "indy": {"cred_def_id": cred_def_id},
            },
        }
        return await self._post("/issue-credential-2.0/send", body)
