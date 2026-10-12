# HealthDID — carteira digital do titular

A **HealthDID** e a carteira do cidadao descrita no paper (Secao 3.3.1):
mantém as informacoes do paciente criptograficamente protegidas, com a
custodia sempre nas maos do titular ("o titular sempre sabe quando e como
seus dados serao utilizados").

## O que este esqueleto fornece

`agents/holder-healthdid/` — o **backend** ACA-Py da carteira: gerencia a
wallet `askar-anoncreds` (exatamente como descrito na prova de conceito do
paper), recebe ofertas de credencial, responde a solicitacoes de prova, e
expoe tudo isso via Admin API DIDComm.

## O que falta para uma HealthDID completa (fora do escopo deste esqueleto)

1. **Front-end / app do cidadao** — interface que consome a Admin API do
   `holder-healthdid` (ou, em producao, um sub-wallet multi-tenant) para:
   listar credenciais, mostrar solicitacoes de prova pendentes com opcao
   explicita de aceitar/recusar (consentimento LGPD), e disparar
   apresentacoes seletivas (ZKP). Pode ser web (reaproveitando a decisao
   da PoC do paper) ou mobile (ex. baseado em Aries Bifold / Credo-TS).

2. **Multi-tenancy para escala nacional** — `agents/holder-healthdid` como
   esta configurado e uma unica wallet (adequado para PoC/demo). Para
   milhoes de pacientes do SUS, subir o ACA-Py em modo
   `--multitenant --multitenant-admin` e criar uma sub-wallet por paciente
   via `POST /multitenancy/wallet`, autenticada por token JWT emitido pelo
   agente base. O onboarding do paciente nessa sub-wallet deveria ocorrer
   a partir de uma **autenticacao out-of-band** (o paper cita o portal
   gov.br/SUS como exemplo) que vincula a nova sub-wallet a identidade
   civil do cidadao sem armazenar PII na blockchain.

3. **Delegacao de acesso / tutela digital** (roadmap do paper, Secao 4) —
   protocolo para um guardiao (responsavel legal) operar a HealthDID de um
   dependente. Ponto de extensao natural: um novo papel `guardiao` em
   `governance/roles.yaml` + uma credencial `GuardianshipCredential` que o
   verificador aceita como prova de delegacao antes de liberar
   apresentacao/emissao em nome do dependente.

4. **Wearables / IoMT** (roadmap do paper, Secao 4) — a HealthDID
   precisaria ancorar fluxos de telemetria (frequencia cardiaca, glicemia)
   como `Observation` FHIR periodicas. Reaproveitar
   `services/fhir-vc-bridge/app/fhir_mapper.py`, adicionando um mapeador
   `build_fhir_observation()` ao lado de `build_fhir_diagnostic_report()`.

5. **Interoperabilidade cross-border** (EUDI Wallet, Mercosul) — avaliar
   compatibilidade do formato de credencial (hoje AnonCreds) com o formato
   exigido por essas iniciativas (tipicamente SD-JWT VC ou mdoc/mDL no
   ecossistema EUDI), possivelmente exigindo emissao dupla ou conversao no
   momento da apresentacao.

6. **Entrega do ativo denso decifrado ao verificador** — a apresentacao
   AnonCreds (`present-proof-2.0`) so prova os atributos do schema (ex.
   `loincDisplay`, `status`); ela nao carrega o ciphertext do exame nem a
   DEK. Para o medico efetivamente visualizar a imagem, a HealthDID
   precisa, junto (ou logo apos) a apresentacao aceita pelo titular,
   enviar por um anexo DIDComm (Aries RFC 0017) o ciphertext (ou a
   referencia `ipfs://<cid>`) mais a DEK+nonce — nunca reaproveitando essa
   DEK para outro arquivo (ver invariante em
   `services/fhir-vc-bridge/app/schemas.py::MediaAnchor`). Esse passo e' o
   que efetivamente materializa "o titular decide quando e como o dado e
   usado" para o ativo denso, e nao esta implementado neste esqueleto —
   e' o proximo ponto de extensao logico em `agents/holder-healthdid`.

7. **Eliminacao/"direito ao esquecimento" (crypto-shredding)** — como a
   VC/hash/CID no ledger sao imutaveis por design, "esquecer" um exame
   significa tornar o ciphertext permanentemente ilegivel, nao apagar o
   registro. Como a granularidade e' 1 DEK por ARQUIVO (um exame pode ter
   varios), isso exige apagar AS DUAS copias de CADA DEK: a local na
   wallet e a de backup em `services/key-escrow`
   (`DELETE /keys/{asset_id}` por arquivo, ou
   `DELETE /reports/{report_id}/keys` para eliminar todos de uma vez).
   Enquanto qualquer copia sobreviver, o dado permanece recuperavel — a
   HealthDID deveria oferecer essa acao como um fluxo explicito ao
   titular, disparando o DELETE no key-escrow do emissor correspondente.

8. **Recuperacao da chave raiz da wallet (perda de dispositivo)** —
   decisao de arquitetura: biometria (Face ID/Touch ID/BiometricPrompt) e'
   usada apenas como *gate* local — destrava o acesso a chave que ja esta
   presa ao Secure Enclave/TEE/Keystore do aparelho — NUNCA como fonte de
   derivacao criptografica da chave em si. Motivo: biometria nao e'
   segredo (impressao digital e rosto sao capturaveis por terceiros) e nao
   e' revogavel (ao contrario de um dispositivo perdido ou uma chave
   comprometida, nao da' pra "trocar de digital"); usa-la para
   regenerar/derivar a chave tornaria qualquer comprometimento do
   template biometrico permanente e irreversivel, e concentraria dado
   sensivel (LGPD art. 5o, II) na raiz de todo o material criptografico
   do titular. Ver discussao completa no historico de decisao do projeto.

   A recuperacao em si (o que fazer quando o titular perde o aparelho)
   fica resolvida por um esquema de limiar (Shamir Secret Sharing) sobre
   um segredo de recuperacao **separado** da chave de assinatura do dia a
   dia — default proposto (ajustavel): **2 de 3**, com os shares
   distribuidos entre:
     - o proprio titular (ex. impresso em papel/QR no ato de
       cadastramento, ou em um segundo dispositivo de confianca);
     - o operador do consorcio/Trust Anchor (ver `governance/trust-anchor`
       — na Via 2 do modelo de negocio, e' a propria operadora da rede;
       na Via 1, seria o Ministerio da Saude);
     - um terceiro slot reservado para um **guardiao legal**, hoje inativo
       — so entra em uso quando o item 3 (Delegacao de acesso / tutela
       digital) for implementado. Ate la, a recuperacao funciona em 2 de 2
       (titular + operador do consorcio).

   Por que nao 1 de 2 (so titular + operador)? Porque isso faria do
   operador do consorcio um custodio unilateral capaz de recuperar a
   identidade do titular sozinho — o mesmo problema de concentracao de
   poder que criticamos ao propor o operador como Trust Anchor. Exigir 2
   partes para reconstruir evita que qualquer ATOR UNICO (incluindo o
   proprio operador da rede) consiga se passar pelo titular sem a
   cooperacao de outra parte.

   Isso nao esta implementado neste esqueleto — e' um ponto de extensao
   em `agents/holder-healthdid` (geracao dos shares no enrollment) e
   exigiria um novo servico (`services/key-recovery`, no mesmo espirito
   de `services/key-escrow`) para o operador do consorcio armazenar e
   liberar seu share mediante um processo de verificacao de identidade do
   titular fora de banda (nunca so' por posse de um segundo fator).
