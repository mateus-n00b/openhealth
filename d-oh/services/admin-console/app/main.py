"""Painel administrativo web do D-OH (esqueleto de demo/operacao manual).

CRUD simples sobre tres coisas:
  - Entidades registradas no trust-registry (hospitais, clinicas, etc.)
  - DIDs/wallets dos agentes ACA-Py
  - Papeis (onboarding: conecta o Trust Anchor a um agente e emite a
    EntityRoleCredential)
  - Emissao de uma DiagnosticReportCredential simples (via fhir-vc-bridge)

Isto e' uma ferramenta operacional para quem administra a rede D-OH
(equipe do consorcio/Trust Anchor) — nao e' a HealthDID do paciente nem um
painel publico. Ver docstring de app/config.py sobre por que este
componente nao deve existir como esta em producao (acesso administrativo
direto a Admin API de todos os agentes, inclusive o do titular).
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import acapy_admin
from app.acapy_admin import AcaPyAdminError
from app.config import AGENTS, ROLES, settings

app = FastAPI(title="D-OH Admin Console")
templates = Jinja2Templates(directory="app/templates")


def _agents_context() -> dict:
    return {"agents": AGENTS, "roles": ROLES}


# -- Dashboard --------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", _agents_context())


# -- Entidades (trust-registry) ---------------------------------------------

@app.get("/entities", response_class=HTMLResponse)
def entities_list(request: Request):
    entities: list[dict] = []
    error = None
    try:
        with httpx.Client(base_url=settings.trust_registry_url, timeout=15.0) as client:
            resp = client.get("/entities")
            entities = resp.json() if resp.status_code == 200 else []
    except httpx.HTTPError as exc:
        error = f"trust-registry indisponivel: {exc}"
    return templates.TemplateResponse(
        request, "entities_list.html", {**_agents_context(), "entities": entities, "error": error}
    )


@app.get("/entities/new", response_class=HTMLResponse)
def entity_new_form(request: Request):
    return templates.TemplateResponse(request, "entity_new.html", {**_agents_context(), "error": None})


@app.post("/entities/new")
def entity_new_submit(
    did: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
    registered_by: str = Form(...),
):
    with httpx.Client(base_url=settings.trust_registry_url, timeout=15.0) as client:
        client.post(
            "/entities",
            json={"did": did, "name": name, "role": role, "registered_by": registered_by},
        )
    return RedirectResponse("/entities", status_code=303)


@app.post("/entities/{did:path}/revoke")
def entity_revoke(did: str):
    with httpx.Client(base_url=settings.trust_registry_url, timeout=15.0) as client:
        client.post(f"/entities/{did}/revoke")
    return RedirectResponse("/entities", status_code=303)


# -- DIDs / wallets -----------------------------------------------------------

@app.get("/dids", response_class=HTMLResponse)
def dids_list(request: Request, agent: str = "trust-anchor"):
    agent_cfg = AGENTS[agent]
    error = None
    dids: list[dict] = []
    try:
        dids = acapy_admin.list_dids(agent_cfg)
    except (AcaPyAdminError, httpx.HTTPError) as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "dids.html",
        {**_agents_context(), "selected_agent": agent, "dids": dids, "error": error},
    )


@app.post("/dids/create")
def dids_create(agent: str = Form(...), make_public: bool = Form(False)):
    acapy_admin.create_did(AGENTS[agent], make_public)
    return RedirectResponse(f"/dids?agent={agent}", status_code=303)


# -- Conexoes DIDComm (necessarias para onboarding de papel e emissao de EHR) -

@app.get("/connections", response_class=HTMLResponse)
def connections_list(request: Request, agent: str = "trust-anchor"):
    agent_cfg = AGENTS[agent]
    error = None
    connections: list[dict] = []
    try:
        connections = acapy_admin.list_connections(agent_cfg)
    except (AcaPyAdminError, httpx.HTTPError) as exc:
        error = str(exc)
    return templates.TemplateResponse(
        request,
        "connections.html",
        {**_agents_context(), "selected_agent": agent, "connections": connections, "error": error, "invitation": None},
    )


@app.post("/connections/invite", response_class=HTMLResponse)
def connections_invite(request: Request, agent: str = Form(...), alias: str = Form("")):
    invitation = acapy_admin.create_invitation(AGENTS[agent], alias or f"convite-{agent}")
    connections = acapy_admin.list_connections(AGENTS[agent])
    return templates.TemplateResponse(
        request,
        "connections.html",
        {
            **_agents_context(),
            "selected_agent": agent,
            "connections": connections,
            "error": None,
            "invitation": invitation,
        },
    )


@app.post("/connections/receive")
def connections_receive(agent: str = Form(...), invitation_json: str = Form(...)):
    import json

    acapy_admin.receive_invitation(AGENTS[agent], json.loads(invitation_json))
    return RedirectResponse(f"/connections?agent={agent}", status_code=303)


# -- Papeis (onboarding de entidade: conexao + EntityRoleCredential) ---------

@app.get("/roles/onboard", response_class=HTMLResponse)
def roles_onboard_form(request: Request):
    return templates.TemplateResponse(
        request, "roles_onboard.html", {**_agents_context(), "result": None, "error": None}
    )


@app.post("/roles/onboard", response_class=HTMLResponse)
def roles_onboard_submit(
    request: Request,
    entity_agent: str = Form(...),
    entity_name: str = Form(...),
    role: str = Form(...),
):
    trust_anchor = AGENTS["trust-anchor"]
    entity = AGENTS[entity_agent]
    error = None
    result = None
    try:
        ta_public = acapy_admin.get_public_did(trust_anchor)
        if not ta_public:
            raise AcaPyAdminError("Trust Anchor nao tem DID publico — crie um em /dids?agent=trust-anchor")
        ta_did = ta_public["did"]

        entity_public = acapy_admin.get_public_did(entity)
        if not entity_public:
            raise AcaPyAdminError(f"{entity.label} nao tem DID publico — crie um em /dids?agent={entity_agent}")
        entity_did = entity_public["did"]

        invitation = acapy_admin.create_invitation(trust_anchor, f"onboard-{entity_agent}")
        receive = acapy_admin.receive_invitation(entity, invitation["invitation"])
        entity_connection_id = receive["connection_id"]
        acapy_admin.wait_connection_active(entity, entity_connection_id)
        ta_connection_id = acapy_admin.find_connection_by_invitation(trust_anchor, invitation["invi_msg_id"])

        cred_def_id = acapy_admin.find_entity_role_cred_def(trust_anchor, ta_did)
        registered_at = datetime.now(timezone.utc).isoformat()
        acapy_admin.issue_entity_role_credential(
            trust_anchor, ta_connection_id, cred_def_id, entity_did, entity_name, role, ta_did, registered_at
        )

        with httpx.Client(base_url=settings.trust_registry_url, timeout=15.0) as client:
            client.post(
                "/entities",
                json={"did": entity_did, "name": entity_name, "role": role, "registered_by": ta_did},
            )

        result = {
            "entity_did": entity_did,
            "trust_anchor_did": ta_did,
            "connection_id": ta_connection_id,
        }
    except (AcaPyAdminError, httpx.HTTPError, TimeoutError) as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request, "roles_onboard.html", {**_agents_context(), "result": result, "error": error}
    )


# -- Emissao de EHR simples (DiagnosticReportCredential via fhir-vc-bridge) --

@app.get("/ehr/issue", response_class=HTMLResponse)
def ehr_issue_form(request: Request):
    return templates.TemplateResponse(request, "ehr_issue.html", {**_agents_context(), "result": None, "error": None})


@app.post("/ehr/issue", response_class=HTMLResponse)
def ehr_issue_submit(
    request: Request,
    connection_id: str = Form(...),
    did_paciente: str = Form(...),
    report_id: str = Form(...),
    loinc_code: str = Form(...),
    loinc_display: str = Form(...),
    subject_reference: str = Form(...),
    performer_reference: str = Form(""),
    effective_date_time: str = Form(...),
    issued: str = Form(...),
):
    body = {
        "connection_id": connection_id,
        "did_paciente": did_paciente,
        "diagnostic_report": {
            "report_id": report_id,
            "status": "final",
            "category": [{"code": "RAD", "display": "Radiology"}],
            "code": {"code": loinc_code, "display": loinc_display, "system": "http://loinc.org"},
            "subject_reference": subject_reference,
            "performer": [{"reference": performer_reference}] if performer_reference else [],
            "result": [],
            "effective_date_time": effective_date_time,
            "issued": issued,
        },
    }

    error = None
    result = None
    try:
        with httpx.Client(base_url=settings.fhir_vc_bridge_url, timeout=30.0) as client:
            resp = client.post("/diagnostic-reports/issue", json=body)
            if resp.status_code >= 300:
                error = f"{resp.status_code}: {resp.text}"
            else:
                result = resp.json()
    except httpx.HTTPError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request, "ehr_issue.html", {**_agents_context(), "result": result, "error": error}
    )
