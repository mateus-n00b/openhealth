from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 9003

    # KEK do emissor, base64 de 32 bytes. DEV ONLY — em producao, delegar
    # a um KMS/HSM (ver crypto.py). Uma instancia deste servico por
    # emissor, cada qual com sua propria KEK: NUNCA compartilhar a mesma
    # KEK entre emissores diferentes — isso recriaria um cofre nacional
    # unico de chaves, o oposto do que a custodia descentralizada propoe.
    key_escrow_master_key: str

    class Config:
        case_sensitive = False


settings = Settings()
