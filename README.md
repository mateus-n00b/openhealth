# Decentralized-OpenHealth (D-OH) — Esqueleto de Implementação

Esqueleto de código para a arquitetura proposta em *"Identidade Digital
Descentralizada e Interoperabilidade FHIR/HL7: Uma Proposta de OpenHealth
para o Brasil"* (Sousa, Sousa & Evaristo). Não é uma implementação completa
— é a estrutura sobre a qual o time deve construir o D-OH, com os
componentes, contratos e pontos de integração já definidos.

## Ideia central do paper → decisões deste esqueleto

| Conceito do paper | Como aparece aqui |
|---|---|
| Emissor / Titular / Verificador (Fig. 1) | Um agente **ACA-Py** por papel: `agents/issuer-*`, `agents/holder-healthdid`, `agents/verifier-medico` |
| Ministério da Saúde como *Trust Anchor* (Fig. 2) | `governance/trust-anchor` — agente ACA-Py + registro de papéis |
| Hierarquia de governança (Hospitais, Clínicas, Laboratórios, Médicos, Planos, Ministério) | `governance/roles.yaml` + `services/trust-registry` |
| Carteira digital **HealthDID** (askar-anoncreds via ACA-Py) | `agents/holder-healthdid` + `wallet-healthdid/README.md` |
| Integração FHIR-VC (Algoritmo 1 do paper) | `services/fhir-vc-bridge` |
| Armazenamento híbrido (hash na VC/blockchain, ativo denso no IPFS) | `services/ipfs-anchor` — só aceita ciphertext (AES-256-GCM cifrado na origem) |
| Custódia de chave (titular + backup do emissor, crypto-shredding) | `services/key-escrow` — ver `docs/architecture-mapping.md` |
| Blockchain como âncora de confiança, não como base de dados (Hyperledger Besu / modelo Indy-Besu) | `ledger/` (genesis, notas de rede permissionada) |
| ZKPs / divulgação seletiva | present-proof (AnonCreds predicates) via `agents/verifier-medico`, ver `scripts/demo_present_proof.sh` |
| LGPD — consentimento explícito, custódia do titular | Toda emissão de credencial exige `connection_id` estabelecida a partir do HealthDID (titular no controle) — ver `services/fhir-vc-bridge` |
| Operação manual da rede (credenciar entidade, emitir EHR de teste) | `services/admin-console` — painel web CRUD (ferramenta do time do consórcio, não a HealthDID do paciente) |

## Atores mapeados em agentes ACA-Py

- `governance/trust-anchor` — Ministério da Saúde. Credencia (emite `EntityRoleCredential`) os demais participantes e mantém o registro auditável (`services/trust-registry`).
- `agents/issuer-hospital`, `agents/issuer-clinic`, `agents/issuer-lab` — emissores de credenciais clínicas (ex. `DiagnosticReportCredential`, ver Algoritmo 1 do paper), sempre através de `services/fhir-vc-bridge`.
- `agents/holder-healthdid` — backend da carteira do paciente (HealthDID). Representa a custódia soberana do titular.
- `agents/verifier-medico` — verificador que solicita apresentação de credenciais (nunca acessa dados diretamente, sempre via consentimento do titular).

## Por que ACA-Py

O paper usa explicitamente o *Aries Cloud Agent Python* como gestor da
carteira `askar-anoncreds` na prova de conceito. Neste esqueleto, cada ator
do modelo de governança (Fig. 2) é uma instância ACA-Py independente,
conectada por protocolo DIDComm (Aries RFC 0023/0036/0037/0454/0510), o que
reflete diretamente a descentralização proposta: não há banco de dados
central de identidades, apenas agentes que se comunicam ponto a ponto.

## Subindo o ambiente de desenvolvimento

```bash
cp .env.example .env
docker compose up -d
```

Isso sobe: 6 agentes ACA-Py (trust anchor + 3 emissores + holder + verifier),
`tails-server` (registro de revogação AnonCreds), `ipfs` (armazenamento
híbrido), os serviços Python (`fhir-vc-bridge`, `ipfs-anchor`,
`trust-registry`, `key-escrow-hospital`) e o `admin-console` (painel web
em [http://localhost:9010](http://localhost:9010) — CRUD de entidades,
DIDs/wallets, conexões DIDComm, credenciamento de papel e emissão de EHR
de teste, sem precisar de `curl`/scripts).

Por padrão os agentes apontam para um ledger Indy de testes público via
`GENESIS_URL` (ver `.env.example`). Para produção/homologação, ver
`ledger/README.md` sobre como apontar para uma rede permissionada real
(ex. Rede Blockchain Brasil / Hyperledger Besu, modelo *Indy-Besu*).

Bootstrap de governança (cria schema/cred-def de papéis e credencia as
entidades de exemplo):

```bash
make bootstrap
```

Fluxo de demonstração (emissão de `DiagnosticReportCredential` e
apresentação seletiva via predicado — ZKP):

```bash
scripts/demo_issue_diagnostic_report.sh
scripts/demo_present_proof.sh
```

## O que este esqueleto NÃO inclui (propositalmente)

- Deploy real de contratos Indy-Besu / rede Hyperledger Besu permissionada — apenas os pontos de configuração (`ledger/`).
- App móvel da HealthDID (Aries Bifold ou similar) — apenas o backend ACA-Py que ela consumiria.
- Autenticação *out-of-band* de cidadãos (ex. integração com portal gov.br/SUS) — ponto de extensão sinalizado em `wallet-healthdid/README.md`.
- Hardening de produção (TLS, admin API key, secrets manager, multi-tenancy). Todo `acapy-config.yml` está marcado `DEV ONLY` onde relevante.

## Roadmap (seção "Trabalhos futuros" do paper)

- **Delegação de acesso / tutela digital** — extensão de `governance/roles.yaml` e do `trust-registry` para vínculos de guardião↔dependente.
- **Wearables/IoMT** — nova ontologia FHIR (Observation de telemetria) em `services/fhir-vc-bridge/app/fhir_mapper.py`.
- **Interoperabilidade cross-border (EUDI Wallet, Mercosul)** — ponto de extensão em `wallet-healthdid/README.md`.

Ver `docs/architecture-mapping.md` para o mapeamento completo paper → código.
