"""Configuracao do admin-console: registro estatico dos agentes ACA-Py e
demais servicos do D-OH que este painel administra.

DEV ONLY — este servico assume acesso direto a Admin API de TODOS os
agentes (inclusive holder-healthdid, a carteira do titular). Isso e'
aceitavel para um painel operado pelo time do projeto em ambiente de
desenvolvimento/demo, mas nunca deveria existir como componente de
producao: nenhum operador de infraestrutura deveria ter acesso
administrativo direto a wallet do paciente. Ver README do projeto sobre
por que agentes de producao devem ficar atras de autenticacao propria
(multi-tenant JWT para o holder, por exemplo).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_settings import BaseSettings


@dataclass(frozen=True)
class AgentConfig:
    key: str
    label: str
    admin_url: str
    api_key: str | None


class Settings(BaseSettings):
    port: int = 9010

    trust_registry_url: str = "http://trust-registry:9002"
    fhir_vc_bridge_url: str = "http://fhir-vc-bridge:9000"

    trust_anchor_admin_url: str = "http://trust-anchor:8021"
    trust_anchor_admin_api_key: str | None = None

    issuer_hospital_admin_url: str = "http://issuer-hospital:8031"
    issuer_hospital_admin_api_key: str | None = None

    issuer_clinic_admin_url: str = "http://issuer-clinic:8041"
    issuer_clinic_admin_api_key: str | None = None

    issuer_lab_admin_url: str = "http://issuer-lab:8051"
    issuer_lab_admin_api_key: str | None = None

    verifier_medico_admin_url: str = "http://verifier-medico:8061"
    verifier_medico_admin_api_key: str | None = None

    holder_healthdid_admin_url: str = "http://holder-healthdid:8071"
    holder_healthdid_admin_api_key: str | None = None

    class Config:
        case_sensitive = False


settings = Settings()

AGENTS: dict[str, AgentConfig] = {
    "trust-anchor": AgentConfig(
        "trust-anchor", "Ministerio da Saude (Trust Anchor)",
        settings.trust_anchor_admin_url, settings.trust_anchor_admin_api_key,
    ),
    "issuer-hospital": AgentConfig(
        "issuer-hospital", "Hospital (Emissor)",
        settings.issuer_hospital_admin_url, settings.issuer_hospital_admin_api_key,
    ),
    "issuer-clinic": AgentConfig(
        "issuer-clinic", "Clinica (Emissor)",
        settings.issuer_clinic_admin_url, settings.issuer_clinic_admin_api_key,
    ),
    "issuer-lab": AgentConfig(
        "issuer-lab", "Laboratorio (Emissor)",
        settings.issuer_lab_admin_url, settings.issuer_lab_admin_api_key,
    ),
    "verifier-medico": AgentConfig(
        "verifier-medico", "Medico (Verificador)",
        settings.verifier_medico_admin_url, settings.verifier_medico_admin_api_key,
    ),
    "holder-healthdid": AgentConfig(
        "holder-healthdid", "Paciente (HealthDID)",
        settings.holder_healthdid_admin_url, settings.holder_healthdid_admin_api_key,
    ),
}

# Mantido em sincronia com governance/roles.yaml
ROLES = ["hospital", "clinica", "laboratorio", "medico", "plano_saude"]
