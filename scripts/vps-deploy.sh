#!/usr/bin/env bash
#
# Déploiement prod, exécuté SUR le VPS par le workflow Release via :
#   ssh ubuntu@vps 'bash /srv/arbitrage/scripts/vps-deploy.sh'
#
# La seule commande passée par SSH est `bash <fichier>` : aucun heredoc, aucune
# redirection, aucun `export` — donc indépendante du shell de login (bash, fish, zsh…).
# Tout ce qui suit tourne dans CE bash, pas dans le shell de login.
#
# Pré-requis déposés par les étapes scp du workflow, avant cet appel :
#   /srv/arbitrage/prod.env                 (secrets + RELEASE_TAG + GHCR_OWNER + GITHUB_TOKEN/ACTOR)
#   /srv/arbitrage/docker-compose*.yml
#   /srv/arbitrage/config.prod.yaml
#   /srv/arbitrage/arbitrage.caddy
#   /srv/arbitrage/docker/nginx.conf
#   /srv/arbitrage/frontend/dist/           (build Vite)
set -euo pipefail

cd /srv/arbitrage

# --- .env : swap atomique (rename sur le même FS) puis chargement -------------
mv prod.env .env
chmod 600 .env
set -a
# shellcheck disable=SC1091
source .env
set +a

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

# --- Auth GHCR (token éphémère du job, roté à chaque déploiement) -------------
echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

# --- Config de prod ----------------------------------------------------------
cp config.prod.yaml config.yaml

# --- Executor coupé pendant le restart (évite les positions orphelines) ------
touch data/EXECUTOR_DISABLED
"${compose[@]}" stop executor 2>/dev/null || true
sleep 3

# --- Nouvelle image + migrations -------------------------------------------------
"${compose[@]}" pull
"${compose[@]}" up migrate

# --- Restart api / workers / frontend -----------------------------------------
"${compose[@]}" up -d --no-deps api workers frontend

# --- Executor réactivé ------------------------------------------------------------
rm -f data/EXECUTOR_DISABLED
"${compose[@]}" up -d --no-deps executor

# --- Snippet Caddy + reload -------------------------------------------------------
cp arbitrage.caddy /srv/caddy/sites/arbitrage.caddy
( cd /srv/caddy && docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile )

# --- Healthcheck API (retry 30s) -----------------------------------------------
for i in $(seq 1 6); do
  curl -sf http://localhost:8001/health && break
  if [ "$i" -eq 6 ]; then
    "${compose[@]}" logs api --tail=50
    exit 1
  fi
  sleep 5
done

# --- Cron monitoring système (toutes les 2h → Telegram) ----------------------
chmod +x scripts/vps-monitor.sh scripts/vps-setup-swap.sh
( crontab -l 2>/dev/null | grep -v 'vps-monitor.sh' ; \
  echo '0 */2 * * * /srv/arbitrage/scripts/vps-monitor.sh >> /srv/arbitrage/data/monitor.log 2>&1' \
) | crontab -

# --- Purge des vieilles images (garder les 3 plus récentes) ------------------
docker images "ghcr.io/${GHCR_OWNER}/arbitrage" -q \
  | tail -n +4 | xargs -r docker rmi 2>/dev/null || true
