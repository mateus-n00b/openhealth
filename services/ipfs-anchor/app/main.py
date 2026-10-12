"""Servico de ancoragem hibrida para ativos densos (Secao 3.3.1 do paper).

"Imagens de alta densidade (como ressonancias magneticas) sao armazenadas
em infraestruturas cloud tradicionais, enquanto apenas as ancoras
criptograficas residem nas VCs e na blockchain, assegurando a proveniencia,
rastreabilidade e a imutabilidade sem comprometer o desempenho transacional
da rede."

Este servico recebe o arquivo, o fixa (pin) no IPFS e retorna
{cid, sha256, size}. O sha256 e o campo que entra em
`fhir_report.media[0].hash` no Algoritmo 1 do fhir-vc-bridge; o CID do IPFS
e a referencia de onde o ativo completo pode ser recuperado
(`fhir_report.media[0].reference`).

NOTA: em producao, "infraestruturas cloud tradicionais" citadas no paper
podem ser um bucket S3/MinIO com controle de acesso, em vez de IPFS publico.
A interface deste servico (POST /anchor -> {cid|url, sha256, size}) e
estavel independente do backend escolhido — trocar a implementacao interna
sem afetar fhir-vc-bridge.

REQUISITO DE SEGURANCA — nunca aceitar dado de saude em claro: o IPFS e'
uma rede de conteudo enderecavel e potencialmente publica (um CID vazado
= arquivo recuperavel por qualquer um). Por isso este servico so aceita
ativos ja cifrados na origem (AES-256-GCM, feito pelo sistema do emissor
antes de chamar este endpoint — ver services/fhir-vc-bridge/app/schemas.py
::MediaAnchor e services/key-escrow). Para reduzir o risco de um chamador
esquecer de cifrar, o endpoint exige o parametro `pre_encrypted=true`
explicitamente — isto NAO verifica criptograficamente que o conteudo esta
cifrado (nao ha como, de fora, distinguir ciphertext de dado binario
aleatorio), e' apenas uma trava de "confirmacao consciente" contra erro de
integracao.
"""

from __future__ import annotations

import hashlib

import httpx
from fastapi import FastAPI, Form, HTTPException, UploadFile
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 9001
    ipfs_api_url: str = "http://ipfs:5001"
    ipfs_gateway_url: str = "http://ipfs:8081"

    class Config:
        case_sensitive = False


settings = Settings()

app = FastAPI(
    title="D-OH IPFS Anchor",
    description="Ancoragem de hash + pin em IPFS para ativos clinicos densos.",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/anchor")
async def anchor_asset(file: UploadFile, pre_encrypted: bool = Form(...)) -> dict:
    if not pre_encrypted:
        raise HTTPException(
            status_code=400,
            detail=(
                "services/ipfs-anchor nunca aceita dado de saude em claro. "
                "Cifre com AES-256-GCM na origem, registre a DEK em "
                "services/key-escrow e reenvie com pre_encrypted=true."
            ),
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="arquivo vazio")

    sha256_hex = hashlib.sha256(content).hexdigest()

    async with httpx.AsyncClient(base_url=settings.ipfs_api_url, timeout=60.0) as client:
        resp = await client.post(
            "/api/v0/add",
            files={"file": (file.filename, content, file.content_type)},
            params={"pin": "true"},
        )
        if resp.status_code >= 300:
            raise HTTPException(status_code=502, detail=f"falha ao fixar no IPFS: {resp.text}")
        cid = resp.json()["Hash"]

    return {
        "reference": f"ipfs://{cid}",
        "gateway_url": f"{settings.ipfs_gateway_url}/ipfs/{cid}",
        "hash": f"sha256:{sha256_hex}",
        "size": len(content),
    }
