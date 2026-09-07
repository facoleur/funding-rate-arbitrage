# Enola — snapshots d'architecture

`enola` (binaire : `~/.local/bin/enola`) est un **serveur MCP + CLI** qui extrait
l'architecture d'un repo sous forme de faits interrogeables (`module`, `symbol`,
`route`, `storage`, `dependency`, `service`) et fait tourner des *explainers*
(cycles, god-class, hotspots, complexité, couches, intent…).

But : donner à un agent une carte du codebase **avant** qu'il explore, et pouvoir
grader ce qu'un changement fait à la structure (`enola check`).

```bash
enola --generate            # génère un snapshot dans .enola/ et sort
enola --explain             # rapport de stats lisible, sort
enola dashboard --open      # dashboard web read-only du dernier snapshot
enola                       # démarre le serveur MCP (stdio)
```

---

## `.enola/` — dossier de sortie (généré, à gitignorer)

Créé par `enola --generate` à la racine du repo. Contenu 100 % dérivé du code,
régénérable en ~360 ms.

| Fichier | Rôle |
|---|---|
| `llm_context.md` | Livrable principal : carte d'archi condensée (modules, routes, tables, dépendances, modules critiques) à injecter dans le contexte d'un agent. ~10 Ko. |
| `facts.jsonl` | Graphe brut : 1 ligne = 1 fait. Source de vérité que le serveur MCP interroge. |
| `insights.json` | Findings des explainers, avec évidence + actions suggérées. |
| `snapshot.meta.json` / `receipt.json` | Métadonnées : version enola, hash du snapshot, commit git, extractors/explainers utilisés, couverture de parsing. Le `receipt` est signé (hashes des sorties) → tamper-evident. |
| `extractor_cache.json` | Cache par fichier (hash → facts) pour n'analyser au run suivant que ce qui a changé. |

**À ajouter au `.gitignore`** (`/.enola/`). Artefact machine, se régénère seul,
sinon bruit de diff à chaque changement de code.

À côté, `~/.enola/` (hors repo) : historique inter-snapshots (`graphs/`,
revisions ~450 o chacune) qui alimente `enola log` / `enola diff` / `enola blame`.
Automatique, rien à gérer.

---

## `mcp-arch.yaml` — config de scan / serveur (optionnel)

Cherché à la racine par défaut (`enola: no mcp-arch.yaml … using built-in
defaults` = absent). Sert à cadrer *ce qui est analysé* et à déclarer un cluster
multi-repo.

```yaml
# mcp-arch.yaml — tout est optionnel
ignore:
  - "**/migrations/versions/**"      # 22 révisions Alembic = bruit
  - "frontend/src/api/generated/**"
  - "**/*.generated.ts"

# multi-repo : indexer plusieurs repos dans UN graphe (edges cross-repo)
repos:
  - path: .
  - path: ../autre-service
```

Config du client MCP qui lance le serveur :

```json
{ "command": "enola", "args": ["mcp-arch.yaml"] }
```

Pour un monorepo simple : **pas nécessaire**. Ajouter juste le bloc `ignore` si le
parsing ramasse trop de fichiers générés.

---

## `enola-intent.yaml` — règles d'architecture vérifiables

Fichier **écrit à la main**, versionné. Fait tourner l'explainer `intent` (0
insight = fichier absent) et sert de base à `enola check` (exit 1 sur violation en
CI).

Structure : des **composants** (sélecteurs sur le graphe) + des **règles** qui
interdisent / autorisent des edges entre eux, chacune avec un `because:`
obligatoire.

### Exemple taillé pour ce repo

```yaml
# enola-intent.yaml — valider avec `enola constraints lint`

components:
  - name: frontend
    paths: ["frontend/src/**"]
  - name: db
    paths: ["backend/src/option_arb/db/**"]
  - name: api
    paths: ["backend/src/option_arb/api/**"]
  - name: executor
    paths: ["backend/src/option_arb/services/executor.py"]
  - name: exchanges
    paths: ["backend/src/option_arb/exchanges/**"]
  - name: services
    paths: ["backend/src/option_arb/services/**"]

rules:
  - id: frontend-never-touches-db
    forbid: frontend
    to: db
    via: depends_on
    because: "Le frontend lit tout via REST. Un import DB depuis le front recouple l'UI au schéma Postgres."

  - id: no-funding-code
    forbid_name: services
    pattern: "*funding*"
    because: "L'arbitrage de funding est parti volontairement (CLAUDE.md règle 1). Aucun symbole ne doit le réintroduire."

  - id: executor-stays-isolated
    forbid: executor
    to: api
    via: calls
    because: "L'executor est le composant à plus haut blast-radius, dans son propre container. Il ne dépend jamais de la couche API."

  - id: exchanges-do-not-know-services
    forbid: exchanges
    to: services
    via: depends_on
    mode: advisory   # signalé, ne casse pas le build
    because: "Les adaptateurs sont pilotés, ils ne pilotent pas. Un adaptateur qui remonte vers services inverse le sens des dépendances."
```

### Verbes de règle (vus dans les recettes livrées)

| Verbe | Sens |
|---|---|
| `forbid` / `allow` + `only` | edges entre composants |
| `forbid_fact` | le composant ne doit exister pour aucun fait |
| `forbid_name` + `pattern` | convention de nommage |
| `require_edge` + `direction` | tout membre doit émettre / recevoir tel edge |
| `private` | rien n'entre dans le composant |
| `protect` + `owners` | seuls ces composants peuvent appeler la surface publique |

`via:` ∈ `calls | depends_on | implements | imports`.
`mode: advisory` = rapport sans échec.

### Variante : réutiliser une recette livrée

enola embarque des recettes (`layered`, `ports-and-adapters`, `modular-monolith`,
`event-driven`, `supply-chain`, `cqrs`, `clean`, `vanilla-rails`…). On les
instancie en liant leurs rôles à ses dossiers :

```yaml
use_recipe:
  - recipe: ports-and-adapters
    as: backend-hexagonal
    bind:
      core:     ["backend/src/option_arb/services/**", "backend/src/option_arb/economics.py"]
      ports:    ["backend/src/option_arb/exchanges/base.py"]
      adapters: ["backend/src/option_arb/exchanges/deribit/**",
                 "backend/src/option_arb/exchanges/derive/**",
                 "backend/src/option_arb/exchanges/aevo/**",
                 "backend/src/option_arb/exchanges/rocket/**"]

  - recipe: supply-chain      # rôle auto-sélecteur, rien à binder
    as: deps
```

`ports-and-adapters` apporte alors : « le core ne nomme aucun adaptateur », «
chaque adaptateur implémente un port », « les adaptateurs ne s'appellent pas entre
eux » (advisory), etc.

---

## `enola/constraints/*.yaml` — mêmes règles, éclatées par domaine

Quand `enola-intent.yaml` grossit, un fichier par domaine sous
`enola/constraints/` (ex. `frontend.yaml`, `executor.yaml`). `enola constraints
lint` parse l'inline **et** ce dossier ensemble.

---

## Workflow

```bash
enola constraints lint      # valide la syntaxe + que chaque sélecteur matche qqch
enola constraints mine      # propose des quasi-invariants détectés dans le graphe
enola baseline pin          # fige l'état AVANT édition
# … modifs …
enola check                 # exit 1 si une règle déclarée est violée  → CI
```

Codes de sortie de `enola check` : `0` propre · `1` régression · `2` erreur ·
`3` non comparable (re-pin la baseline).
