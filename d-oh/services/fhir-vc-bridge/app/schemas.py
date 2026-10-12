from typing import Optional

from pydantic import BaseModel, Field


class Coding(BaseModel):
    code: str
    display: Optional[str] = None
    system: Optional[str] = None  # ex. "http://loinc.org"


class CodeableConcept(BaseModel):
    coding: list[Coding]
    text: Optional[str] = None


class Reference(BaseModel):
    reference: str
    display: Optional[str] = None


class MediaAnchor(BaseModel):
    """Ancora de um ativo denso (imagem/exame) armazenado fora da VC.

    Preenchido a partir da resposta do services/ipfs-anchor — ver
    Secao 3.3.1 e Algoritmo 1 (linha 12: `fhir_report.media`) do paper.

    Decisao de arquitetura: todo ativo denso e cifrado com AES-256-GCM
    NA ORIGEM (pelo sistema do emissor), antes de sequer chegar ao
    services/ipfs-anchor — o IPFS so armazena ciphertext. `hash` e
    calculado sobre o ciphertext (e' o que esta de fato ancorado/CID no
    IPFS). A DEK (Data Encryption Key) em si NUNCA aparece na credencial
    nem em nenhum campo deste modelo — ela fica em duas custodias
    separadas: a wallet do titular (HealthDID) e o backup em
    services/key-escrow do emissor (ver docstring daquele servico sobre
    por que e' um backup por emissor, nao um cofre nacional).

    Entrega do conteudo decifrado: quando o titular compartilha o exame
    com um verificador, o ciphertext (ou sua referencia) e a DEK+nonce
    viajam junto com a apresentacao da VC por um anexo DIDComm (Aries
    RFC 0017) fora do payload da propria prova AnonCreds — nao
    implementado neste esqueleto, e um ponto de extensao em
    agents/holder-healthdid.

    Granularidade — 1 DEK por ARQUIVO, nunca por exame: um DiagnosticReport
    pode ter varios arquivos (ex. serie DICOM com N imagens). Cada arquivo
    e' cifrado com sua PROPRIA DEK descartavel, entao cada arquivo produz
    um MediaAnchor proprio (ver `DiagnosticReportIn.media: list[...]`
    abaixo) com seu proprio `nonce` e `key_escrow_ref`. Nunca reaproveitar
    uma DEK entre dois arquivos, mesmo do mesmo exame — e' essa
    granularidade que mantem valida a analise de seguranca do nonce
    aleatorio (ver campo `nonce`).
    """

    media_id: str  # identifica este arquivo dentro do exame, ex. "EXM-2025-0001-img-01"
    reference: str  # ex. "ipfs://<cid>" (aponta para o CIPHERTEXT, nunca para o conteudo em claro)
    hash: str        # sha256 do CIPHERTEXT, ex. "sha256:<hex>"
    encryption_algorithm: str = "AES-256-GCM"
    # Nonce/IV em base64 usado na cifragem — publico (nao e segredo), mas
    # com uma invariante obrigatoria: a DEK referenciada por
    # key_escrow_ref deve ser usada para UMA UNICA cifragem (uma DEK
    # descartavel por ARQUIVO — nunca reaproveitada entre arquivos, nem
    # entre arquivos do mesmo exame). Nonce aleatorio de 96 bits e seguro
    # nesse regime (NIST SP 800-38D permite ate ~2^32 invocacoes por
    # chave, e aqui ha exatamente 1 invocacao por DEK).
    nonce: str
    key_escrow_ref: str  # referencia opaca (= media_id) para services/key-escrow recuperar a DEK deste arquivo


class DiagnosticReportIn(BaseModel):
    """Subconjunto de FHIR R4 DiagnosticReport usado no Algoritmo 1 do paper.

    Este e o payload que um sistema de origem (PACS, LIS, prontuario do
    emissor) envia ao bridge para virar uma Verifiable Credential.
    """

    report_id: str = Field(..., description="Identificador do relatorio (ex. EXM-2025-0001)")
    status: str = Field(default="final")
    category: list[Coding]
    code: Coding  # ex. LOINC 24727-0 "Ressonancia Magnetica"
    subject_reference: str  # ex. "Patient/789"
    performer: list[Reference] = Field(default_factory=list)
    result: list[Reference] = Field(default_factory=list)
    effective_date_time: str
    issued: str
    media: list[MediaAnchor] = Field(default_factory=list)  # um item por arquivo cifrado (1 DEK cada)


class IssueCredentialRequest(BaseModel):
    """Requisicao ao bridge para emitir uma DiagnosticReportCredential.

    connection_id: conexao DIDComm ja estabelecida entre o agente do
    emissor e a carteira HealthDID do titular (estabelecimento de conexao
    e responsabilidade de fora deste servico — ver scripts/demo_*.sh).
    """

    connection_id: str
    did_paciente: str  # DID do titular (ex. "did:example:paciente:789")
    diagnostic_report: DiagnosticReportIn


class IssueCredentialResponse(BaseModel):
    credential_exchange_id: str
    fhir_report: dict
