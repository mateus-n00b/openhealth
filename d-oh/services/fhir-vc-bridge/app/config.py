from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuracao do servico fhir-vc-bridge.

    Este servico e o ponto de integracao central proposto no paper: recebe
    dados clinicos estruturados no formato FHIR/HL7, os encapsula em uma
    Verifiable Credential (W3C) e delega a emissao ao ACA-Py do emissor
    correspondente (Algoritmo 1 do paper).
    """

    port: int = 9000

    # Admin API do agente ACA-Py do emissor. Em producao, o bridge deve
    # resolver dinamicamente qual agente/emissor chamar (multi-emissor),
    # em vez de um unico ACAPY_ISSUER_ADMIN_URL fixo — ver TODO em main.py.
    acapy_issuer_admin_url: str = "http://issuer-hospital:8031"
    acapy_admin_api_key: str | None = None

    # Servico de ancoragem hibrida (hash de ativos densos no IPFS —
    # Secao 3.3.1 do paper: "registra-se apenas o hash criptografico do
    # arquivo no formato da VC, enquanto a imagem completa e armazenada em
    # um repositorio seguro na nuvem").
    ipfs_anchor_url: str = "http://ipfs-anchor:9001"

    # Registro de confianca (Fig. 2 — hierarquia de governanca)
    trust_registry_url: str = "http://trust-registry:9002"

    # Backup de chaves do emissor (crypto-shredding / direito ao
    # esquecimento — ver services/key-escrow). O bridge nao chama este
    # servico diretamente hoje (o registro da DEK acontece no sistema de
    # origem do emissor, antes do payload chegar aqui); mantido na config
    # para health-check e para a integracao futura de purge coordenado
    # (DELETE em key-escrow ao processar um pedido de eliminacao do titular).
    key_escrow_url: str = "http://key-escrow-hospital:9003"

    # Schema AnonCreds usado para credenciais de laudo/exame. Criado uma vez
    # via governance/trust-anchor/scripts/register_role_schema.py (ou script
    # equivalente por emissor) e referenciado aqui apos o bootstrap.
    diagnostic_report_cred_def_id: str | None = None

    class Config:
        env_prefix = ""
        case_sensitive = False


settings = Settings()
