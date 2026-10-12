"""Registro de confianca auditavel (Fig. 2 do paper — modelo de governanca).

O Ministerio da Saude e a "entidade principal, por ser amplamente
confiavel e deter autoridade para validar e endossar outros participantes
da rede". Este servico e o espelho off-chain e consultavel dessa
autoridade: quem foi credenciado, com qual papel, por quem, e se o
credenciamento segue valido.

Este servico NAO substitui a credencial criptografica (`EntityRoleCredential`
emitida via ACA-Py pelo Trust Anchor) — ele e um indice auditavel e rapido
de consulta para verificadores (Secao 3.2: "o Ministerio da Saude ...
exerce funcoes de auditoria e supervisao"). A fonte de verdade
criptografica continua sendo a credencial assinada + o ledger.

Persistencia: sqlite simples para a PoC. Trocar por Postgres em producao
(ver docker-compose.yml — volume `trust-registry-data`).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DB_PATH = Path("/data/trust_registry.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class Role(str, Enum):
    ministerio_saude = "ministerio_saude"
    hospital = "hospital"
    clinica = "clinica"
    laboratorio = "laboratorio"
    medico = "medico"
    plano_saude = "plano_saude"


class Status(str, Enum):
    active = "active"
    revoked = "revoked"


class EntityIn(BaseModel):
    did: str
    name: str
    role: Role
    registered_by: str  # DID do Trust Anchor que credenciou a entidade
    credential_exchange_id: str | None = None


class Entity(EntityIn):
    status: Status = Status.active
    registered_at: str


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                did TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                registered_by TEXT NOT NULL,
                credential_exchange_id TEXT,
                registered_at TEXT NOT NULL
            )
            """
        )


app = FastAPI(
    title="D-OH Trust Registry",
    description="Indice auditavel de entidades credenciadas pelo Ministerio da Saude (Trust Anchor).",
)


@app.on_event("startup")
def _startup() -> None:
    _init_db()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/entities", response_model=Entity, status_code=201)
async def register_entity(entity: EntityIn) -> Entity:
    now = datetime.now(timezone.utc).isoformat()
    with _db() as conn:
        existing = conn.execute("SELECT did FROM entities WHERE did = ?", (entity.did,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="entidade ja registrada")
        conn.execute(
            """
            INSERT INTO entities (did, name, role, status, registered_by, credential_exchange_id, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity.did,
                entity.name,
                entity.role.value,
                Status.active.value,
                entity.registered_by,
                entity.credential_exchange_id,
                now,
            ),
        )
    return Entity(**entity.model_dump(), status=Status.active, registered_at=now)


@app.get("/entities/{did}", response_model=Entity)
async def get_entity(did: str) -> Entity:
    with _db() as conn:
        row = conn.execute("SELECT * FROM entities WHERE did = ?", (did,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="entidade nao encontrada")
    return Entity(**dict(row))


@app.get("/entities", response_model=list[Entity])
async def list_entities(role: Role | None = None, status: Status | None = None) -> list[Entity]:
    query = "SELECT * FROM entities WHERE 1=1"
    params: list[str] = []
    if role is not None:
        query += " AND role = ?"
        params.append(role.value)
    if status is not None:
        query += " AND status = ?"
        params.append(status.value)
    with _db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [Entity(**dict(r)) for r in rows]


@app.post("/entities/{did}/revoke", response_model=Entity)
async def revoke_entity(did: str) -> Entity:
    """Revoga o credenciamento de uma entidade (ex. suspensao de registro
    profissional). NOTA: isso atualiza apenas o indice; a revogacao
    criptografica real da EntityRoleCredential deve ser feita via
    revocation registry do ACA-Py (createRevocationRegistry, Tabela 1 do
    paper) — ver governance/trust-anchor/scripts/onboard_entity.py.
    """

    with _db() as conn:
        row = conn.execute("SELECT * FROM entities WHERE did = ?", (did,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="entidade nao encontrada")
        conn.execute("UPDATE entities SET status = ? WHERE did = ?", (Status.revoked.value, did))
        updated = dict(row)
        updated["status"] = Status.revoked.value
    return Entity(**updated)


@app.get("/entities/{did}/verify")
async def verify_entity(did: str, expected_role: Role | None = None) -> dict:
    """Utilitario para verificadores checarem rapidamente se um emissor e
    valido antes/depois de validar a credencial criptografica em si."""

    with _db() as conn:
        row = conn.execute("SELECT * FROM entities WHERE did = ?", (did,)).fetchone()
    if not row:
        return {"valid": False, "reason": "not_registered"}
    entity = dict(row)
    if entity["status"] != Status.active.value:
        return {"valid": False, "reason": "revoked"}
    if expected_role is not None and entity["role"] != expected_role.value:
        return {"valid": False, "reason": "role_mismatch"}
    return {"valid": True, "role": entity["role"]}
