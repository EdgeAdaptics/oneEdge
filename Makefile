COMPOSE_DIR := deploy/docker-compose
COMPOSE := docker compose -f $(COMPOSE_DIR)/docker-compose.yml

.PHONY: up down logs console-up agent seed fmt

up:
	cd $(COMPOSE_DIR) && docker compose up -d --build

down:
	cd $(COMPOSE_DIR) && docker compose down --remove-orphans

logs:
	cd $(COMPOSE_DIR) && docker compose logs -f

console-up:
	cd $(COMPOSE_DIR) && docker compose up -d console-api console-web

agent:
	cd agents/oneedge-agent && go run ./cmd/oneedge-agent

seed:
	cd $(COMPOSE_DIR) && docker compose exec -T postgres \
		psql -U oneedge -d oneedge \
		-c "insert into devices (spiffe_id, display_name, status) values ('spiffe://oneedge.local/device/dev/demo', 'Demo Device', 'approved') on conflict (spiffe_id) do nothing;"

fmt:
	gofmt -w $(shell git ls-files '*.go')
