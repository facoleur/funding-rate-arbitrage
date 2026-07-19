# docker/

Contient les fichiers de configuration pour le déploiement en production.

- `Caddyfile.example` — reverse proxy Caddy à copier sur le VPS

---

## Déploiement VPS (prod live)

### 0. Pré-requis VPS (Ubuntu 24.04)

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin git ufw
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
usermod -aG docker $USER
```

### 1. Caddy (SSL automatique Let's Encrypt)

```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update && apt install caddy

cp /opt/option_arbitrage/docker/Caddyfile.example /etc/caddy/Caddyfile
# Éditer le domaine dans /etc/caddy/Caddyfile
systemctl enable caddy && systemctl restart caddy
```

### 2. Cloner le repo

```bash
git clone <repo-url> /opt/option_arbitrage
cd /opt/option_arbitrage
```

### 3. Créer le fichier `.env`

```bash
cat > /opt/option_arbitrage/.env << 'EOF'
POSTGRES_PASSWORD=changeme_strong_password

# Deribit mainnet — https://www.deribit.com/account/mainnet/api
# Scopes requis : trade:read_write
DERIBIT_CLIENT_ID=
DERIBIT_CLIENT_SECRET=

# Derive mainnet — https://app.derive.xyz → Settings → Session Keys
# DERIVE_WALLET_ADDRESS = Smart Contract Wallet (SCW), PAS l'adresse MetaMask EOA
DERIVE_WALLET_ADDRESS=0x
DERIVE_SUBACCOUNT_ID=
DERIVE_SESSION_PRIVATE_KEY=0x    # Expire dans 30 jours — mettre un rappel !

# Telegram alerts (optionnel)
BOT_TOKEN=
CHAT_ID=

CONFIG_PATH=/app/config.yaml
EOF

chmod 600 /opt/option_arbitrage/.env
```

### 4. config.yaml — mode live, limites $50/exchange

Éditer `/opt/option_arbitrage/config.yaml` :

```yaml
executor:
  mode: live

limits:
  max_notional_per_trade_usd: 40
  max_positions_open: 3
  max_daily_loss_usd: 15
```

### 5. Build frontend

```bash
cd /opt/option_arbitrage/frontend
npm ci
npm run build
# → dist/ servi par Caddy
```

### 6. Démarrer la stack

```bash
cd /opt/option_arbitrage
POSTGRES_PASSWORD=changeme_strong_password make prod
```

### 7. Vérification

```bash
# WS connecté + 814/814 channels Deribit ack
docker compose logs workers -f | grep -E "ws|connected|ack"

# Prix frais (age_sec < 5)
docker compose exec postgres psql -U option_arb -d option_arb \
  -c "SELECT exchange, count(*), round(extract(epoch from now()-max(updated_at))) lag_sec FROM ticker_state GROUP BY exchange;"

# Front accessible
curl -s https://arb.mondomaine.com/api/tickers | jq length
```

### Opérations courantes

```bash
# Kill-switch d'urgence
make kill      # crée data/EXECUTOR_DISABLED → executor s'arrête proprement
make resume    # relance l'executor

# Mise à jour du code
git pull
make prod      # rebuild + redémarrage

# Rebuild frontend uniquement
cd frontend && npm run build

# Logs
make logs svc=workers
make logs svc=executor

# Backup DB
docker compose exec postgres pg_dump -U option_arb option_arb > backup_$(date +%Y%m%d).sql
```

### Rappels critiques

- **Session key Derive expire dans 30 jours** — régénérer dans `app.derive.xyz` → Settings → Session Keys
- **Ne jamais committer `.env`** — il est dans `.gitignore`
- **Kill-switch avant toute mise à jour** : `make kill` avant `git pull && make prod`, puis `make resume`
