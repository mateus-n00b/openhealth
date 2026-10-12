#!/usr/bin/env bash
# Demonstra a emissao de uma DiagnosticReportCredential via fhir-vc-bridge,
# reproduzindo o exemplo do Algoritmo 1 do paper (Ressonancia Magnetica).
#
# Pre-requisitos:
#   - `docker compose up -d` e `make bootstrap` ja executados
#   - uma conexao DIDComm ja ativa entre issuer-hospital e holder-healthdid
#     (crie manualmente via Admin API /connections/create-invitation em
#     issuer-hospital e /out-of-band/receive-invitation em holder-healthdid,
#     ou adapte governance/trust-anchor/scripts/onboard_entity.py — a logica
#     de estabelecer conexao e a mesma).
#
# Uso:
#   CONNECTION_ID=<id> DID_PACIENTE=did:example:paciente:789 \
#     ./scripts/demo_issue_diagnostic_report.sh

set -euo pipefail

FHIR_VC_BRIDGE_URL="${FHIR_VC_BRIDGE_URL:-http://localhost:9005}"
CONNECTION_ID="${CONNECTION_ID:?defina CONNECTION_ID (conexao issuer-hospital <-> holder-healthdid)}"
DID_PACIENTE="${DID_PACIENTE:-did:example:paciente:789}"

curl -sS -X POST "${FHIR_VC_BRIDGE_URL}/diagnostic-reports/issue" \
  -H "Content-Type: application/json" \
  -d @- <<JSON | tee /dev/stderr | jq .
{
  "connection_id": "${CONNECTION_ID}",
  "did_paciente": "${DID_PACIENTE}",
  "diagnostic_report": {
    "report_id": "EXM-2025-0001",
    "status": "final",
    "category": [{"code": "RAD", "display": "Radiology"}],
    "code": {"code": "24727-0", "display": "Ressonancia Magnetica", "system": "http://loinc.org"},
    "subject_reference": "Patient/789",
    "performer": [{"reference": "Practitioner/456", "display": "Dr. Joao Silva"}],
    "result": [{"reference": "Observation/123", "display": "Sem alteracoes..."}],
    "effective_date_time": "2025-09-20T14:30:00Z",
    "issued": "2025-09-21T09:00:00Z"
  }
}
JSON
