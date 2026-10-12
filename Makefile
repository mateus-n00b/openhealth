.PHONY: up down logs bootstrap

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

# Publica os schemas/cred-defs de governanca no Trust Anchor e no
# issuer-hospital (emissor padrao deste ambiente de dev). Requer que
# `make up` ja tenha subido os agentes e que python3 + deps de
# governance/trust-anchor/scripts/requirements.txt estejam disponiveis
# localmente (ou rode via `docker compose exec`, adaptando os --admin-url
# para os nomes de servico internos).
bootstrap:
	python3 -m pip install -q -r governance/trust-anchor/scripts/requirements.txt
	python3 governance/trust-anchor/scripts/register_role_schema.py \
		--admin-url http://localhost:8021 \
		--api-key $${TRUST_ANCHOR_ADMIN_API_KEY:-trust-anchor-admin-key}
	@echo
	@echo "Agora rode create_issuer_cred_def.py para cada emissor com o schema_id acima, ex.:"
	@echo "  python3 governance/trust-anchor/scripts/create_issuer_cred_def.py \\"
	@echo "    --admin-url http://localhost:8031 --api-key \$$ISSUER_HOSPITAL_ADMIN_API_KEY --schema-id <schema_id>"
