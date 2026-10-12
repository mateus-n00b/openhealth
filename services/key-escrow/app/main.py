"""Key escrow por emissor — backup da DEK de cada ARQUIVO denso cifrado.

Decisao de arquitetura (ver docs/architecture-mapping.md, secao
"Criptografia e direito ao esquecimento"): o titular tem custodia
primaria das chaves (na HealthDID), mas o EMISSOR mantem uma copia de
backup, justificada por obrigacao legal propria de retencao de
prontuario (CFM, ate 20 anos) — nao pelo Ministerio da Saude nem por
qualquer entidade central. Por isso este servico e implantado **uma
instancia por emissor** (hospital, clinica, laboratorio), nunca uma
instancia nacional compartilhada: um cofre unico de chaves de todos os
pacientes do pais seria o pior tipo de ponto unico de falha possivel
nesta arquitetura.

Granularidade — 1 DEK por ARQUIVO, nunca por exame: um DiagnosticReport
pode ter varios arquivos (ex. serie DICOM com N imagens), cada um cifrado
com sua propria DEK descartavel (ver
services/fhir-vc-bridge/app/schemas.py::MediaAnchor). Por isso a chave
primaria aqui e' `asset_id` (= `MediaAnchor.media_id`, um por arquivo),
nao `report_id` (que agrupa varios assets de um mesmo exame e serve so
para consulta/purge em lote).

Fluxo:
  1. No momento da emissao, o sistema de origem do emissor cifra CADA
     arquivo com uma DEK AES-256-GCM propria e descartavel e chama
     POST /keys aqui para cada uma, enviando a DEK em transito (nunca em
     repouso em claro).
  2. Este servico cifra a DEK com a KEK do emissor (envelope encryption,
     ver crypto.py) e persiste so a versao cifrada. Retorna um
     `key_escrow_ref` opaco (= asset_id) — e isso, nao a chave, que vai no
     campo `MediaAnchor.key_escrow_ref` da credencial.
  3. GET /keys/{asset_id} decifra e devolve a DEK — endpoint sensivel: em
     producao PRECISA exigir mais que uma API key estatica (ex. prova de
     uma ordem judicial, processo de auditoria formal, ou reconstrucao
     apos perda de dispositivo com verificacao de identidade do titular).
     Aqui, cada chamada e apenas registrada em auditoria — autorizacao
     forte fica como TODO explicito.
  4. DELETE /keys/{asset_id} materializa o "crypto-shredding" de UM
     arquivo; DELETE /reports/{report_id}/keys faz o mesmo para todos os
     arquivos de um exame de uma vez. Junto com a exclusao da copia local
     na wallet do titular, isso completa a inacessibilidade pratica do
     ativo (ver discussao sobre direito ao esquecimento em
     docs/architecture-mapping.md). Enquanto qualquer uma das duas copias
     (titular ou escrow) existir, o dado permanece recuperavel.
"""

from __future__ import annotations

import base64
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.crypto import EnvelopeCrypto

DB_PATH = Path("/data/key_escrow.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_crypto = EnvelopeCrypto(settings.key_escrow_master_key)


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
            CREATE TABLE IF NOT EXISTS escrowed_keys (
                asset_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                patient_did TEXT NOT NULL,
                issuer_did TEXT NOT NULL,
                wrapped_dek TEXT NOT NULL,
                wrap_nonce TEXT NOT NULL,
                created_at TEXT NOT NULL,
                purged_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_escrowed_keys_report ON escrowed_keys (report_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id TEXT NOT NULL,
                action TEXT NOT NULL,
                requested_by TEXT,
                at TEXT NOT NULL
            )
            """
        )


def _audit(conn: sqlite3.Connection, asset_id: str, action: str, requested_by: str | None) -> None:
    conn.execute(
        "INSERT INTO audit_log (asset_id, action, requested_by, at) VALUES (?, ?, ?, ?)",
        (asset_id, action, requested_by, datetime.now(timezone.utc).isoformat()),
    )


app = FastAPI(
    title="D-OH Key Escrow",
    description=(
        "Backup por emissor das chaves AES-256-GCM de cada arquivo denso cifrado na origem "
        "(1 DEK por arquivo). Uma instancia por emissor — nunca um cofre nacional compartilhado."
    ),
)


@app.on_event("startup")
def _startup() -> None:
    _init_db()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


class StoreKeyRequest(BaseModel):
    asset_id: str  # = MediaAnchor.media_id — identifica este ARQUIVO, unico globalmente neste emissor
    report_id: str  # exame ao qual o arquivo pertence, so para agrupamento/purge em lote
    patient_did: str
    issuer_did: str
    dek_b64: str  # DEK em claro, em transito (TLS obrigatorio em producao) — nunca persistida assim


class StoreKeyResponse(BaseModel):
    key_escrow_ref: str


@app.post("/keys", response_model=StoreKeyResponse, status_code=201)
async def store_key(req: StoreKeyRequest, requested_by: str | None = None) -> StoreKeyResponse:
    dek = base64.b64decode(req.dek_b64)
    wrapped_dek, wrap_nonce = _crypto.wrap(dek)

    with _db() as conn:
        existing = conn.execute(
            "SELECT asset_id FROM escrowed_keys WHERE asset_id = ?", (req.asset_id,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="chave ja escrowed para este asset_id")

        conn.execute(
            """
            INSERT INTO escrowed_keys
                (asset_id, report_id, patient_did, issuer_did, wrapped_dek, wrap_nonce, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                req.asset_id,
                req.report_id,
                req.patient_did,
                req.issuer_did,
                wrapped_dek,
                wrap_nonce,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        _audit(conn, req.asset_id, "issue", requested_by)

    return StoreKeyResponse(key_escrow_ref=req.asset_id)


class RetrieveKeyResponse(BaseModel):
    dek_b64: str


@app.get("/keys/{asset_id}", response_model=RetrieveKeyResponse)
async def retrieve_key(asset_id: str, requested_by: str | None = None) -> RetrieveKeyResponse:
    # TODO(autorizacao forte): este endpoint hoje so exige a API key do
    # servico (ver docker-compose.yml). Antes de qualquer uso alem de
    # desenvolvimento, condicionar a liberacao da chave a uma evidencia
    # concreta de autorizacao (ex. token de consentimento vinculado a uma
    # apresentacao DIDComm ativa do titular, ou processo formal de
    # auditoria/ordem judicial), nunca a posse isolada de uma API key.
    with _db() as conn:
        row = conn.execute("SELECT * FROM escrowed_keys WHERE asset_id = ?", (asset_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="chave nao encontrada")
        if row["purged_at"] is not None:
            raise HTTPException(status_code=410, detail="chave foi eliminada (crypto-shredding)")

        dek = _crypto.unwrap(row["wrapped_dek"], row["wrap_nonce"])
        _audit(conn, asset_id, "retrieve", requested_by)

    return RetrieveKeyResponse(dek_b64=base64.b64encode(dek).decode())


def _purge_row(conn: sqlite3.Connection, asset_id: str, requested_by: str | None) -> None:
    conn.execute(
        "UPDATE escrowed_keys SET wrapped_dek = '', wrap_nonce = '', purged_at = ? WHERE asset_id = ?",
        (datetime.now(timezone.utc).isoformat(), asset_id),
    )
    _audit(conn, asset_id, "purge", requested_by)


@app.delete("/keys/{asset_id}", status_code=204, response_model=None)
async def purge_key(asset_id: str, requested_by: str | None = None) -> None:
    """Elimina permanentemente a copia escrow da DEK de UM arquivo
    (crypto-shredding). So torna o arquivo definitivamente inacessivel se
    a copia local na wallet do titular tambem for apagada — ver docstring
    do modulo. Nao remove o hash/CID ja ancorados na VC/ledger (isso e
    imutavel por design); torna apenas o conteudo cifrado permanentemente
    ilegivel.
    """

    with _db() as conn:
        row = conn.execute("SELECT asset_id FROM escrowed_keys WHERE asset_id = ?", (asset_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="chave nao encontrada")
        _purge_row(conn, asset_id, requested_by)


@app.delete("/reports/{report_id}/keys", status_code=200)
async def purge_report_keys(report_id: str, requested_by: str | None = None) -> dict:
    """Crypto-shredding de TODOS os arquivos de um exame de uma vez —
    conveniencia para quando o titular exerce o direito de eliminacao
    sobre um DiagnosticReport inteiro (que pode ter N arquivos/DEKs)."""

    with _db() as conn:
        rows = conn.execute(
            "SELECT asset_id FROM escrowed_keys WHERE report_id = ? AND purged_at IS NULL", (report_id,)
        ).fetchall()
        for row in rows:
            _purge_row(conn, row["asset_id"], requested_by)

    return {"purged_assets": [r["asset_id"] for r in rows]}
