#!/usr/bin/env bash
# System health report → Telegram (separate chat from the trading alerts).
# Installed on the VPS by the release workflow, run every 2h by cron:
#   0 */2 * * * /srv/arbitrage/scripts/vps-monitor.sh >> /srv/arbitrage/data/monitor.log 2>&1
#
# Reads BOT_TOKEN + MONITOR_CHAT_ID from /srv/arbitrage/.env (same bot as the
# trading alerter, different chat). No-op if MONITOR_CHAT_ID is unset.
set -euo pipefail

ENV_FILE="${ENV_FILE:-/srv/arbitrage/.env}"
COMPOSE_DIR="${COMPOSE_DIR:-/srv/arbitrage}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8001/health}"
DISK_WARN=85   # percent
MEM_WARN=90    # percent

[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
: "${BOT_TOKEN:?BOT_TOKEN missing}"
if [ -z "${MONITOR_CHAT_ID:-}" ]; then
  echo "MONITOR_CHAT_ID unset — skipping"
  exit 0
fi

host=$(hostname)
up=$(uptime -p 2>/dev/null | sed 's/^up //' || true)
load=$(cut -d' ' -f1-3 /proc/loadavg)

# memory
read -r mem_total mem_avail < <(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{print t, a}' /proc/meminfo)
mem_used_pct=$(( (mem_total - mem_avail) * 100 / mem_total ))
mem_used_gb=$(awk "BEGIN{printf \"%.1f\", ($mem_total-$mem_avail)/1048576}")
mem_total_gb=$(awk "BEGIN{printf \"%.1f\", $mem_total/1048576}")
swap_line=$(free -m | awk '/Swap/{printf "%d/%d MB", $3, $2}')

# disk (root fs)
disk_pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
disk_line=$(df -h --output=used,size / | tail -1 | awk '{print $1"/"$2}')

# docker
cd "$COMPOSE_DIR"
ps_all=$(docker ps -a --format '{{.Names}}\t{{.State}}\t{{.Status}}' 2>/dev/null || true)
bad=$(printf '%s\n' "$ps_all" | awk -F'\t' '$2!="running" || $3 ~ /unhealthy/ {print "  ⚠️ "$1": "$3}')
oom=$(printf '%s\n' "$ps_all" | awk -F'\t' '$3 ~ /Exited \(137\)/ {print "  💥 "$1" OOM-killed"}')
running_n=$(printf '%s\n' "$ps_all" | grep -c 'running' || true)
top_mem=$(docker stats --no-stream --format '{{.Name}} {{.MemUsage}} ({{.MemPerc}})' 2>/dev/null \
          | sort -k3 -h -r | head -3 | sed 's/^/  /')
dsize=$(docker system df --format '{{.Type}}: {{.Size}} (reclaimable {{.Reclaimable}})' 2>/dev/null | sed 's/^/  /')

# api health
http=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")

flag=""
[ "$disk_pct" -ge "$DISK_WARN" ] && flag="${flag} 🔴DISK"
[ "$mem_used_pct" -ge "$MEM_WARN" ] && flag="${flag} 🔴MEM"
[ -n "$bad$oom" ] && flag="${flag} 🔴DOCKER"
[ "$http" != "200" ] && flag="${flag} 🔴API"
head="🖥 <b>${host}</b>${flag:+ —$flag}"

msg=$(cat <<EOF
${head}
uptime: ${up:-?} · load: ${load}
mem: ${mem_used_gb}/${mem_total_gb} GB (${mem_used_pct}%) · swap: ${swap_line}
disk /: ${disk_line} (${disk_pct}%)
api ${HEALTH_URL##*/}: HTTP ${http}
docker: ${running_n} running
${bad:-  all healthy}
${oom}
top mem:
${top_mem}
${dsize}
EOF
)

curl -sS --max-time 15 \
  "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d chat_id="${MONITOR_CHAT_ID}" \
  -d parse_mode="HTML" \
  -d disable_web_page_preview=true \
  --data-urlencode text="$msg" >/dev/null
echo "$(date -Is) sent (flags:${flag:-none})"
