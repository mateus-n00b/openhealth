"""Criptografia de envelope para a chave escrow (DEV ONLY).

Cada exame e cifrado na origem (pelo sistema do emissor) com uma
Data Encryption Key (DEK) AES-256-GCM propria e descartavel. Este servico
nao gera a DEK — apenas a recebe uma unica vez (no momento do
credenciamento), a cifra com a Key Encryption Key (KEK) do emissor e
persiste somente a versao cifrada. A DEK em claro nunca e escrita em disco.

ATENCAO — isto e um esqueleto: a KEK aqui vem de uma variavel de ambiente
em texto plano, o que e aceitavel apenas para desenvolvimento. Em producao
a KEK deve residir em um KMS/HSM gerenciado (AWS KMS, GCP KMS, HashiCorp
Vault Transit, etc.) e as operacoes wrap/unwrap devem ser delegadas a ele
— a KEK nunca deve existir em memoria do processo da aplicacao.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EnvelopeCrypto:
    def __init__(self, kek_b64: str):
        if not kek_b64 or kek_b64.startswith("change-me"):
            raise ValueError(
                "KEY_ESCROW_MASTER_KEY nao foi configurada (ainda esta com o placeholder "
                "do .env.example). Gere uma com `openssl rand -base64 32` e defina no seu "
                "`.env` (nunca no `.env.example`)."
            )

        try:
            kek = base64.b64decode(kek_b64, validate=True)
        except binascii.Error as exc:
            raise ValueError(
                "KEY_ESCROW_MASTER_KEY nao e base64 valido. Gere uma chave com "
                "`openssl rand -base64 32` e cole o valor exatamente como impresso "
                "(sem quebras de linha) no seu `.env`."
            ) from exc

        if len(kek) != 32:
            raise ValueError(
                f"KEY_ESCROW_MASTER_KEY tem {len(kek)} bytes apos decodificar; "
                "precisa ter exatamente 32 (AES-256). Gere com `openssl rand -base64 32`."
            )
        self._aead = AESGCM(kek)

    def wrap(self, dek_plaintext: bytes) -> tuple[str, str]:
        """Cifra a DEK com a KEK. Retorna (wrapped_dek_b64, nonce_b64)."""

        nonce = os.urandom(12)
        wrapped = self._aead.encrypt(nonce, dek_plaintext, associated_data=None)
        return base64.b64encode(wrapped).decode(), base64.b64encode(nonce).decode()

    def unwrap(self, wrapped_dek_b64: str, nonce_b64: str) -> bytes:
        wrapped = base64.b64decode(wrapped_dek_b64)
        nonce = base64.b64decode(nonce_b64)
        return self._aead.decrypt(nonce, wrapped, associated_data=None)
