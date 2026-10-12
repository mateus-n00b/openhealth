# Camada de ledger (ancora de confianca)

O paper e explicito: a blockchain **nao** guarda dados clinicos — apenas
DIDs, schemas, credential definitions, entradas de status/revogacao e
politicas de confianca (Secao 3.4, Tabela 1). A avaliacao de desempenho do
paper foi feita em **Hyperledger Besu** com o **Hyperledger Caliper**,
sobre o modelo de operacoes conhecido como **Indy-Besu** (compatibilidade
das primitivas Indy — `createDid`, `createSchema`,
`createCredentialDefinition`, `createOrUpdateEntry`,
`createRevocationRegistry` — rodando em uma rede EVM permissionada).

Este esqueleto **nao** sobe uma rede Besu real por padrao (isso exige nos
validadores QBFT/IBFT, contratos Indy-Besu implantados e genesis proprio —
fora do escopo de um esqueleto de dev). Em vez disso:

## Modo dev (padrao deste repositorio)

Os agentes ACA-Py apontam para um `GENESIS_URL` de um ledger Indy publico
de testes (ver `.env.example`), o que e suficiente para exercitar todo o
fluxo de DIDs/schemas/cred-defs/credenciais/provas descrito no paper.

## Modo producao/homologacao (Rede Blockchain Brasil / Indy-Besu)

Para alinhar com o paper (Secao 3.4, referencia a Rede Blockchain Brasil —
RBB, baseada em Hyperledger Besu, *gasless* para o SUS):

1. Provisionar/obter acesso a rede Besu permissionada (RBB ou equivalente).
2. Implantar os contratos do projeto **Hyperledger Indy-Besu**
   (`did-ethr` / `cl-registry` / `revocation-registry` — nomes exatos
   variam por versao do projeto Indy-Besu) para expor as primitivas
   Indy-like sobre a EVM.
3. Configurar o ACA-Py com o plugin/driver de ledger compativel com
   Indy-Besu (VDR customizado) no lugar de `--genesis-url`, apontando para
   o endpoint RPC da rede Besu e o endereco dos contratos.
4. Repetir o bootstrap de governanca (`make bootstrap`) contra essa rede.

Um `docker-compose.besu.yml` com um devnet Besu QBFT de nó único pode ser
adicionado aqui como ambiente de validacao intermediario (mais fiel que o
ledger Indy de teste, mais simples que a RBB real) — nao incluido neste
esqueleto para nao acoplar o repositorio a uma versao especifica do
projeto Indy-Besu; ver
https://github.com/hyperledger/indy-besu para o estado atual do projeto
antes de implementar.

## Custos observados no paper (Tabela 1, referencia)

| Etapa | Frequencia | Custo estimado (rede publica EVM) |
|---|---|---|
| `createDid` | unica, por entidade | ~682k gas |
| `createSchema` + `createCredentialDefinition` | unica, por emissor | ~1.13M gas |
| Apresentacao/verificacao (off-chain via ZKP) | alta frequencia | zero |
| `createOrUpdateEntry` / `createRevocationRegistry` | baixa frequencia | ~150k–300k gas |

Em uma rede permissionada e *gasless* como a RBB, esses custos sao
eliminados/diluidos entre os nos do consorcio — por isso a arquitetura usa
a blockchain apenas nas etapas de setup/revogacao, nunca no caminho
critico do atendimento.
