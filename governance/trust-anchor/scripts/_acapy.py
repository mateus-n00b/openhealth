"""Helper minimo para chamar a Admin API do ACA-Py a partir dos scripts de
bootstrap de governanca. Deliberadamente simples (sync, sem retries) —
scripts de bootstrap rodam uma vez, manualmente ou em CI de setup.
"""

from __future__ import annotations

import httpx


class AcaPyAdmin:
    def __init__(self, base_url: str, api_key: str | None = None):
        headers = {"X-API-KEY": api_key} if api_key else {}
        self.client = httpx.Client(base_url=base_url, headers=headers, timeout=30.0)

    def post(self, path: str, json_body: dict | None = None) -> dict:
        resp = self.client.post(path, json=json_body or {})
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, params: dict | None = None) -> dict:
        resp = self.client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def create_public_did_if_needed(self) -> str:
        """Garante que o agente tem um DID publico no ledger e retorna o DID.

        Em dev, o DID ainda precisa ser registrado no ledger (ex. via
        endpoint /register do von-network ou processo equivalente da rede
        permissionada) antes de ser aceito nas transacoes — este helper
        cobre apenas a criacao local da chave.
        """

        public = self.get("/wallet/did/public")
        if public.get("result"):
            return public["result"]["did"]

        created = self.post("/wallet/did/create", {"method": "sov", "options": {"key_type": "ed25519"}})
        did = created["result"]["did"]
        self.post(f"/wallet/did/public?did={did}")
        return did
