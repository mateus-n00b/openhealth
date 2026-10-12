# Mapeamento: paper → esqueleto de codigo

Referencia rapida para quem le o paper e precisa achar o componente de
codigo correspondente (e vice-versa).

## Atores (Figura 1)

| Ator no paper | Componente |
|---|---|
| Emissor (hospitais, clinicas, laboratorios) | `agents/issuer-hospital`, `agents/issuer-clinic`, `agents/issuer-lab` |
| Titular (paciente) | `agents/holder-healthdid` + `wallet-healthdid/` |
| Verificador (medico e demais consumidores) | `agents/verifier-medico` |

## Ferramenta operacional (nao faz parte do modelo do paper)

| Necessidade pratica | Componente |
|---|---|
| Operar a rede sem curl/scripts (CRUD de entidades, DIDs, conexoes, papeis, emissao de EHR de teste) | `services/admin-console` (FastAPI + Jinja2, porta 9010) |

`admin-console` e' uma ferramenta do time que administra o consorcio/Trust
Anchor, nao um componente do modelo de atores do paper — nunca deveria
existir com acesso direto a Admin API de todos os agentes (inclusive o do
titular) fora de ambiente de desenvolvimento/demo. Ver docstring de
`services/admin-console/app/config.py`.

## Governanca (Figura 2, Secao 3.2)

| Conceito | Componente |
|---|---|
| Ministerio da Saude (Trust Anchor) | `governance/trust-anchor/` |
| Hierarquia de papeis e permissoes | `governance/roles.yaml` |
| Registro auditavel / supervisao | `services/trust-registry` |
| Credenciamento de uma entidade | `governance/trust-anchor/scripts/onboard_entity.py` |
| Bootstrap de schemas (`EntityRoleCredential`, `DiagnosticReportCredential`) | `governance/trust-anchor/scripts/register_role_schema.py` |

## Prova de conceito (Secao 3.3)

| Conceito | Componente |
|---|---|
| Carteira digital HealthDID (askar-anoncreds via ACA-Py) | `agents/holder-healthdid/acapy-config.yml` |
| Algoritmo 1 — Etapa 1 (estruturacao FHIR DiagnosticReport) | `services/fhir-vc-bridge/app/fhir_mapper.py::build_fhir_diagnostic_report` |
| Algoritmo 1 — Etapa 2 (acoplamento ao credentialSubject) | `services/fhir-vc-bridge/app/fhir_mapper.py::build_credential_subject` / `to_anoncreds_attributes` |
| Algoritmo 1 — Etapa 3 (assinatura criptografica) | Delegada ao ACA-Py — `services/fhir-vc-bridge/app/acapy_client.py::issue_credential` |
| DIDs anonimos do paciente | DIDs locais (`did:peer` / `did:sov` conforme config) mantidos pela wallet `holder-healthdid` |
| Estrategia hibrida de armazenamento (hash na VC, ativo denso fora) | `services/ipfs-anchor` |
| Cifragem do ativo denso na origem (AES-256-GCM) | Responsabilidade do sistema do emissor, antes de chamar `services/ipfs-anchor` (que exige `pre_encrypted=true`) |
| Backup de chave (custodia dupla titular+emissor) | `services/key-escrow` (uma instancia por emissor) |

## Blockchain / contratos (Secao 3.4, Tabela 1)

| Operacao no paper | Onde acontece |
|---|---|
| `createDid` | ACA-Py `/wallet/did/create` + publicacao no ledger (todos os agentes, via `_acapy.py::create_public_did_if_needed`) |
| `createSchema` | `governance/trust-anchor/scripts/register_role_schema.py` |
| `createCredentialDefinition` | `register_role_schema.py` (EntityRoleCredential) e `create_issuer_cred_def.py` (DiagnosticReportCredential, por emissor) |
| `createOrUpdateEntry` / `createRevocationRegistry` | Fluxo de revogacao do ACA-Py (`/revocation/*`) — nao exercitado por script de demo neste esqueleto; ponto de extensao |
| Verificacao off-chain via ZKP | `present-proof-2.0` no `agents/verifier-medico` — ver `scripts/demo_present_proof.sh` |
| Rede permissionada / Indy-Besu / RBB | `ledger/README.md` |

## Divulgacao seletiva / ZKP (Secao 1, Secao 3.4)

O paper descreve BBS+/ZKP para divulgacao seletiva a nivel de atributo. A
PoC do paper usa AnonCreds (askar-anoncreds), que ja oferece:
- **Divulgacao seletiva**: o verificador so recebe os atributos que
  solicitou, nao a credencial inteira.
- **Provas de predicado (ZKP)**: ex. provar `issued >= X` sem revelar o
  valor exato — usado em `scripts/demo_present_proof.sh`.

Migrar para BBS+/JSON-LD (proof type `BbsBlsSignature2020`) e um ponto de
extensao isolado em `services/fhir-vc-bridge/app/acapy_client.py` (trocar
o filtro `anoncreds`/`indy` por `ld_proof` nas chamadas de
`/issue-credential-2.0/send`), sem impacto no restante da arquitetura.
