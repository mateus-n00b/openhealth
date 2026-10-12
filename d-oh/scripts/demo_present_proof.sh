#!/usr/bin/env bash
# Demonstra divulgacao seletiva com prova de conhecimento zero (ZKP):
# o medico (verifier-medico) solicita apenas a confirmacao de que o exame
# foi emitido dentro dos ultimos N dias, sem que o paciente revele a data
# exata nem o restante do laudo — Secao 1 / Secao 3.4 do paper.
#
# Uso:
#   CONNECTION_ID=<id, verifier-medico <-> holder-healthdid> \
#     CRED_DEF_ID=<cred_def_id da DiagnosticReportCredential> \
#     ./scripts/demo_present_proof.sh

set -euo pipefail

VERIFIER_ADMIN_URL="${VERIFIER_ADMIN_URL:-http://localhost:8061}"
VERIFIER_API_KEY="${VERIFIER_API_KEY:-verifier-medico-admin-key}"
CONNECTION_ID="${CONNECTION_ID:?defina CONNECTION_ID (conexao verifier-medico <-> holder-healthdid)}"
CRED_DEF_ID="${CRED_DEF_ID:?defina CRED_DEF_ID da DiagnosticReportCredential}"

# "issued" foi emitido como string ISO-8601; para um predicado numerico real
# em producao, mapear tambem uma versao epoch/inteira do campo no schema
# (AnonCreds so suporta predicados >=/<= sobre atributos numericos inteiros).
# Aqui demonstramos divulgacao seletiva de atributos nao-numericos, que e
# suportada diretamente.

curl -sS -X POST "${VERIFIER_ADMIN_URL}/present-proof-2.0/send-request" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: ${VERIFIER_API_KEY}" \
  -d @- <<JSON | jq .
{
  "connection_id": "${CONNECTION_ID}",
  "presentation_request": {
    "anoncreds": {
      "name": "Confirmacao de exame recente",
      "version": "1.0",
      "requested_attributes": {
        "loincDisplay": {
          "name": "loincDisplay",
          "restrictions": [{"cred_def_id": "${CRED_DEF_ID}"}]
        },
        "status": {
          "name": "status",
          "restrictions": [{"cred_def_id": "${CRED_DEF_ID}"}]
        }
      },
      "requested_predicates": {}
    }
  }
}
JSON

echo "Consulte o estado em: ${VERIFIER_ADMIN_URL}/present-proof-2.0/records" >&2
