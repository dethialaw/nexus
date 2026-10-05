# Spec 0001 : squelette du monorepo

État au 5 octobre 2026, issu de la séance de cadrage. S'appuie sur [`CONTEXT.md`](../../CONTEXT.md), les ADR [0001](../adr/0001-contenu-historise-par-copie.md) à [0005](../adr/0005-coeur-metier-adaptateurs-et-instantanes-gardes.md) et [`data-model.md`](../data-model.md), qui priment en cas de conflit.

Les décisions marquées **(C)** ont été tranchées par Claude parce qu'elles sont faciles à défaire ; les autres l'ont été par le mainteneur.

## Objectif

Une PR qui livre un monorepo vide de fonctionnalités mais complet dans sa structure : chaque outil est en place, la CI est verte, le schéma de `data-model.md` est migré avec ses gardes, et les deux points d'entrée démarrent. La première fonctionnalité pourra ensuite s'écrire en TDD sans toucher à l'outillage.

## Arborescence

```
nexus/
├── AGENTS.md, CLAUDE.md          # CLAUDE.md contient seulement « @AGENTS.md » (Claude Code lit CLAUDE.md)
├── CONTEXT.md
├── README.md                     # présentation, démarrage local, « tous droits réservés »
├── compose.yaml                  # PostgreSQL + pgvector local
├── .pre-commit-config.yaml
├── .claude/
│   ├── settings.json             # hooks git-guardrails, plugin utilisateur mattpocock-skills désactivé
│   └── skills/                   # skills vendorés + LICENSE (MIT, Matt Pocock)
├── .github/
│   ├── workflows/ci.yml, pr-title.yml, external.yml
│   └── dependabot.yml
├── docs/
│   ├── adr/, specs/, data-model.md
├── backend/
│   ├── AGENTS.md, CLAUDE.md
│   ├── pyproject.toml, uv.lock, .python-version, .env.example
│   ├── Dockerfile                # une image, deux commandes
│   ├── alembic.ini
│   ├── alembic/                  # env.py (URL directe), versions/
│   ├── src/nexus/
│   │   ├── core/
│   │   │   ├── shared/           # ports Clock, UnitOfWork ; type Embedding ; erreurs
│   │   │   ├── ingestion/        # Connecteur, Source, Abonnement, Article brut → Article, Page liée, Exécution, Collecte
│   │   │   │   ├── source_config.py   # modèles Pydantic par Connecteur + construction du source_key
│   │   │   │   └── source_catalog.py  # CatalogEntry + sync_source_catalog
│   │   │   ├── qualification/    # Nature, Jugement « même événement »
│   │   │   ├── profile/          # Utilisateur, Intérêt, Journal du Profil, Score, Signal, Engagement, Miroir
│   │   │   ├── delivery/         # Candidat, Fenêtre du Briefing, Règle de diversité, Composition, Briefing, Entrée, Synthèse
│   │   │   ├── conversation/     # Conversation, Citation, Mémoire longue, port ChatAgent, outils en lecture
│   │   │   └── pipeline.py       # enchaînement d'une Exécution
│   │   ├── adapters/
│   │   │   ├── persistence/      # modèles déclaratifs, mapping, dépôts, UnitOfWork, TypeDecorator vecteur, gardes ORM
│   │   │   ├── model_gateway/    # tâche → modèle (classify, summarize, briefing, chat, embed) ; prompts ; LangChain
│   │   │   ├── connectors/       # rss.py, hackernews.py, reddit.py
│   │   │   ├── web/              # Pages liées et follow_page
│   │   │   ├── agent/langgraph/  # graphe, prompt, enrobage des outils
│   │   │   ├── tracing/          # Langfuse
│   │   │   └── source_catalog/   # source_catalog.toml + reader.py
│   │   ├── entrypoints/
│   │   │   ├── api/              # app FastAPI, routers, schémas d'API, export de l'OpenAPI
│   │   │   └── batch/            # __main__.py
│   │   ├── settings.py           # pydantic-settings
│   │   └── bootstrap.py          # racine de composition
│   ├── tests/
│   │   ├── unit/                 # cœur, faux adaptateurs en mémoire, contrat d'imports
│   │   ├── integration/          # adaptateurs contre PostgreSQL + pgvector
│   │   └── external/             # Neon et Gemini, hors PR
│   └── evals/                    # réservé, non créé dans le squelette (voir plus bas)
└── frontend/
    ├── AGENTS.md, CLAUDE.md
    ├── package.json, pnpm-lock.yaml, .nvmrc, .env.example
    ├── next.config.ts, tsconfig.json, eslint.config.mjs, vitest.config.ts
    └── src/
        ├── app/                  # App Router
        ├── components/
        └── lib/api/              # openapi.json et schema.d.ts générés, client.ts
```

Dans chaque section du cœur : `entities.py`, `ports.py`, `services.py`, découpés seulement s'ils grossissent (ADR-0005).

### Catalogue de Sources

- `core/ingestion/source_catalog.py` : `CatalogEntry` (Pydantic) et `sync_source_catalog`, testés en unitaire sans fichier.
- `adapters/source_catalog/source_catalog.toml`, lu par `importlib.resources` : livré dans l'image et dans les tests sans chemin à configurer. Deux tableaux : `[[source]]` et `[[retired]]` (une `source_key` par entrée).
- Synchronisation idempotente (upsert par `source_key`) au début de chaque Exécution, **limitée aux Sources communes** (`owner_user_id IS NULL`). Règles, chacune couverte par un test unitaire :
  1. Une clé de `[[retired]]` désactive la Source (`removed_from_catalog`) **seulement si elle est active** ; une Source déjà inactive garde sa raison d'origine, et une remise ultérieure dans `[[source]]` ne la rallume pas. Ces retraits ne comptent pas dans le seuil.
  2. Une Source commune active absente de `[[source]]` et de `[[retired]]` est une disparition inexpliquée. Si leur nombre dépasse `max(3, 20 % des Sources communes actives)`, ou si `[[source]]` est vide, **rien n'est appliqué** et l'anomalie `catalog_sync_blocked` est inscrite dans `execution.anomalies`.
  3. Une clé revenue dans `[[source]]` n'est réactivée que si sa raison est `removed_from_catalog`.
  4. Retirer de `[[retired]]` une clé déjà inactive n'a aucun effet, ni désactivation ni décompte : la liste se nettoie sans risque.
- Un test unitaire charge le vrai fichier : il doit être valide, sans `source_key` en double ni clé présente dans les deux tableaux.

### Évaluations des LLM (réservé)

`backend/evals/` accueillera les évaluations (Jev contre Gemini, calibrage des seuils) : hors de `tests/`, jamais collecté par pytest ni lancé en CI, dépendances dans un groupe uv `evals`, lancé à la main. Les jeux de données ne sont **jamais commités** (Extraits d'éditeurs, Intérêts) : `evals/data/` ignoré par git, ou datasets Langfuse.

## AGENTS.md

Trois fichiers, écrits dans cette PR : [`/AGENTS.md`](../../AGENTS.md), [`backend/AGENTS.md`](../../backend/AGENTS.md) et [`frontend/AGENTS.md`](../../frontend/AGENTS.md). Ils font foi ; la liste ci-dessous n'en résume que l'origine.

- Racine : documents de référence, GitHub Flow, Conventional Commits, secrets, mise à jour des docs, skills.
- Back-end : règle d'import du cœur, entités `frozen`, persistance (ADR-0005), tables gardées, `message` enregistré en une fois, contenu collecté = donnée (D57), outils de l'agent en lecture seule, protections de la récupération web dont la limite par domaine, passerelle de modèles, tests.
- Front-end : client généré, contenu collecté rendu comme texte, règles d'affichage tirées du glossaire.

Chaque `CLAUDE.md` contient seulement `@AGENTS.md`.

## Outillage du back-end

| Sujet | Choix |
|---|---|
| Python | 3.14 via `.python-version` ; repli sur 3.13 si une dépendance n'a pas de wheel **(C)** |
| Dépendances | uv, `uv.lock` commité, groupes `dev` et `evals` |
| Lint et format | ruff (`check` + `format`), règles `E, F, I, UP, B, SIM, ASYNC, S, RUF, PT`, ligne de 100 **(C)** |
| Typage | **mypy `strict`** + plugin Pydantic ; les modèles SQLAlchemy 2 (`Mapped[...]`) n'ont pas besoin de plugin **(C)** |
| Tests | pytest + pytest-asyncio (`asyncio_mode = auto`) ; marqueurs `integration` et `external` ; `addopts = -m "not external"` **(C)** |
| Imports | import-linter (quatre contrats ci-dessous) + test de liste autorisée |
| Configuration | pydantic-settings ; secrets en `SecretStr` ; toute variable nouvelle est ajoutée à `.env.example` |
| Image | `backend/Dockerfile` multi-étapes avec uv, utilisateur non root ; `[project.scripts]` déclare `nexus-api` (uvicorn) et `nexus-batch` ; l'image lance l'API par défaut, le batch par surcharge de la commande **(C)** |
| Hooks locaux | pre-commit : ruff, gitleaks, vérification de fin de ligne ; la CI reste la seule garde obligatoire **(C)** |

### Contrats import-linter

1. `forbidden` : `nexus.core` n'importe ni `nexus.adapters`, ni `nexus.entrypoints`, ni `nexus.bootstrap`, ni `nexus.settings`.
2. `forbidden` : `nexus.adapters` n'importe ni `nexus.entrypoints` ni `nexus.bootstrap`.
3. `independence` : les sous-paquets de `nexus.adapters` ne s'importent pas entre eux (un besoin transverse, comme le traçage, passe par un port injecté par `bootstrap`).
4. `layers` : `nexus.core.shared` n'importe aucune autre section du cœur.

Test de liste autorisée (`tests/unit/test_core_imports.py`) : parcourt le code du cœur avec `ast` et n'accepte que la bibliothèque standard (`sys.stdlib_module_names`), `pydantic` et `nexus.core`.

### Base locale

`compose.yaml` à la racine **(C)** : image `pgvector/pgvector` de la même version majeure que le projet Neon (17 par défaut, à vérifier à sa création), port publié sur `127.0.0.1` seulement, volume nommé, healthcheck. Deux bases : `nexus` (développement) et `nexus_test` (tests d'intégration), créées par un script d'initialisation. Moteur : **OrbStack** ; désinstaller Docker Desktop pour éviter deux moteurs sur le même socket.

### Variables d'environnement (`backend/.env.example`)

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | URL de l'application : le pooler de Neon en production (`statement_cache_size=0` imposé par le code) |
| `DATABASE_URL_DIRECT` | URL directe, pour Alembic seulement |
| `TEST_DATABASE_URL` | base `nexus_test` locale ou conteneur de service en CI |
| `GEMINI_API_KEY` | passerelle de modèles |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | traçage ; facultatives en local |

### Secrets

- En local : `backend/.env`, ignoré par git (`.env` et `.env.*` sauf `.env.example`).
- En CI : aucun secret pour les PR ; les tests externes lisent les secrets d'un environnement GitHub `external-tests`.
- En production (session Déploiement) : le batch lira les secrets d'un environnement GitHub `production`, l'API ceux de Secret Manager sur GCP.

### Tests

- **Unitaires** : le cœur avec de faux adaptateurs en mémoire ; aucun réseau, aucune base.
- **Intégration** : chaque méthode de dépôt, les gardes et les migrations, contre PostgreSQL + pgvector. Une fixture de session applique `alembic upgrade head` sur la base de test ; chaque test commence par `TRUNCATE … RESTART IDENTITY CASCADE` (un `TRUNCATE` ne déclenche pas les triggers d'`UPDATE`) **(C)**.
- **Externes** (`tests/external/`, marqueur `external`) :
  - **Neon** : sur une branche Neon `ci` dédiée, migrations par l'URL directe, puis requêtes répétées par le pooler sur plusieurs connexions avec `statement_cache_size=0`, sans erreur `prepared statement … already exists`.
  - **Gemini** : `gemini-embedding-2` avec `output_dimensionality=768`, pour un texte `document` et un texte `query` : vecteurs de longueur 768 et de norme proche de 1. En cas d'échec, repli sur `gemini-embedding-001` avec une normalisation couverte par un test (ADR-0004).

## Outillage du front-end **(C)**

| Sujet | Choix |
|---|---|
| Node | 24 LTS via `.nvmrc` ; pnpm par `packageManager` dans `package.json` |
| Framework | Next.js (dernière version stable), App Router, TypeScript `strict`, Tailwind |
| Lint et format | ESLint en configuration plate avec `eslint-config-next`, Prettier |
| Typage | `tsc --noEmit` |
| Tests | Vitest + Testing Library ; Playwright plus tard, pas dans le squelette |
| Client d'API | `openapi-typescript` (types) + `openapi-fetch` (client) : `openapi.json` exporté par le back-end, `schema.d.ts` généré, tous deux commités ; la CI vérifie qu'ils sont à jour |

Le flux SSE du chat ne se décrit pas bien en OpenAPI : son client sera écrit à la main, avec la spec du chat.

## CI (`.github/workflows/ci.yml`)

Déclenchée sur `pull_request` et sur `push` vers `main`, `permissions: contents: read`, une seule exécution par branche (`concurrency` avec annulation). Actions épinglées par SHA de commit, mises à jour par Dependabot **(C)**.

| Job | Étapes |
|---|---|
| `backend-lint` | `uv sync --locked`, `ruff check`, `ruff format --check`, `mypy`, `lint-imports` |
| `backend-test` | conteneur de service `pgvector/pgvector` ; `pytest` (unitaires + intégration, sans `external`) ; `alembic check` (modèles et migrations alignés) ; aller-retour `downgrade base` puis `upgrade head` |
| `frontend` | `pnpm install --frozen-lockfile`, lint, `prettier --check`, `tsc --noEmit`, `vitest run`, `next build` |
| `openapi` | exporte le schéma, régénère `schema.d.ts`, `git diff --exit-code` |
| `image` | `docker build` de `backend/` sans publication |
| `ci-ok` | dépend de tous les jobs ; **seule vérification obligatoire** de la protection de `main` |

Pas de filtre par chemin au MVP : une vérification obligatoire filtrée resterait en attente sur les PR qui ne la déclenchent pas **(C)**.

`pr-title.yml` vérifie que le titre de la PR suit Conventional Commits : avec la fusion en squash, il devient le message du commit sur `main` **(C)**. Il est aussi rendu obligatoire.

`external.yml` : `workflow_dispatch` et chaque lundi à 6 h UTC, environnement `external-tests`, `pytest -m external`. Réveiller Neon une fois par semaine coûte quelques minutes de calcul **(C)**.

`dependabot.yml` : `uv` (backend), `npm` (frontend, pnpm compris), `github-actions` et `docker`, une fois par semaine, mises à jour groupées **(C)**.

## Où s'exécute le batch **(C)**

Dans le **runner GitHub Actions**, qui lance l'image Docker publiée sur GHCR (`docker run … nexus-batch`) : même image que l'API, donc mêmes dépendances. Conséquences :
- Les secrets de production (`DATABASE_URL`, `GEMINI_API_KEY`, clés Langfuse) existent à deux endroits : l'environnement GitHub `production` pour le batch, Secret Manager pour l'API.
- Neon est joint par Internet, en TLS (`sslmode=require`), avec un mot de passe : l'offre gratuite ne filtre pas les adresses IP, et les runners n'ont pas d'adresse fixe.
- Workflow avec `concurrency` (pas de chevauchement de deux Exécutions horaires) et `timeout-minutes`.
- Un workflow planifié ne tourne que sur `main`, et GitHub le désactive après 60 jours sans activité sur le repo (D63).

L'alternative, un Cloud Run Job déclenché par Actions avec une fédération d'identité, garderait les secrets dans GCP seulement, mais demande plus de configuration. On pourra y passer sans changer d'image. Le workflow du batch et la publication sur GHCR relèvent de la session Déploiement : ils ne font pas partie du squelette.

## Repo public

- **Licence** : aucune. Le code est visible, tous droits réservés ; le README le dit. Les skills vendorés gardent leur `LICENSE` MIT, comme leur licence l'exige.
- **Fuites de secrets** : activer *secret scanning* et *push protection* dans les réglages du repo (gratuits pour un repo public), vérifiés par `gh api repos/{owner}/nexus` (`security_and_analysis`) ; alertes et mises à jour de sécurité Dependabot ; gitleaks en pre-commit.
- **Protection de `main`** (ruleset, sans contournement possible, propriétaire compris) : PR obligatoire, aucune approbation requise, fusion en squash seulement, pas de force-push ni de suppression ; vérifications obligatoires `ci-ok` et titre de PR, ajoutées quand la CI existe.

## Skills (`.claude/skills/`)

Vendorés depuis `mattpocock-skills` 1.2.3, licence MIT conservée :

| Skill | Usage dans Nexus |
|---|---|
| `grill-with-docs`, `grilling`, `domain-modeling` | cadrage avant une spec ; `grill-with-docs` lance les deux autres |
| `to-spec`, `to-tickets` | conversation → spec, spec → tickets (anciennement to-prd et to-issues) |
| `setup-matt-pocock-skills` | configure une fois le suivi des tickets (GitHub Issues) pour `to-tickets` |
| `tdd` | toute fonctionnalité du cœur |
| `diagnosing-bugs` | bug ou régression (anciennement diagnose) |
| `codebase-design` | dessin d'un port ou d'un module |
| `code-review` | revue d'une branche contre `AGENTS.md` et la spec |
| `writing-for-agents` | modifier un `AGENTS.md` ou un skill |
| `research` | vérifier un fait d'API ou de documentation (par exemple les dimensions de Gemini) |

`git-guardrails-claude-code` n'est pas vendoré : ses hooks vont directement dans `.claude/settings.json`. Ils bloquent `git push` vers `main`, `push --force`, `reset --hard`, `clean -f` et `branch -D`. Le plugin utilisateur est désactivé pour ce projet (`enabledPlugins`), pour ne pas voir chaque skill deux fois **(C)**.

## Contenu de la PR du squelette

1. Arborescence ci-dessus, paquets vides là où aucune règle n'existe encore.
2. `settings.py`, `bootstrap.py`, `GET /health` (qui vérifie la base), `nexus-batch` qui ouvre et clôt une Exécution vide.
3. Modèles ORM de tout `data-model.md`, première migration Alembic : schéma complet, vue `current_interest_version`, fonction de garde générique et ses triggers.
4. Gardes ORM (`before_update`, `do_orm_execute`) et leurs tests ; tests d'intégration des triggers : la purge d'un Article met `article_id` à NULL dans `entry` et `citation`, tout autre `UPDATE` est refusé (y compris sur `embedding`), un Briefing ne se met à jour que s'il est `failed`.
5. Contrats import-linter et test de liste autorisée.
6. Front Next.js minimal qui appelle `/health` par le client généré.
7. CI, Dependabot, pre-commit, `compose.yaml`, `.env.example`, Dockerfile.
8. Skills vendorés, hooks git.

Les `AGENTS.md` et `CLAUDE.md` sont déjà livrés par la PR de cadrage.

Hors squelette : Connecteurs, pipeline, Catalogue rempli, agent, authentification, déploiement, workflow du batch, Grafana.
