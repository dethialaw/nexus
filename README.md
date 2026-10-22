# Nexus

Assistant de veille personnel : il collecte des contenus sur le web selon le Profil d'intérêts de l'utilisateur et lui livre chaque jour un Briefing fini, résumé et sourcé.

Projet en cours de construction : le squelette du monorepo est en place, les fonctionnalités arrivent.

## Organisation

| Dossier | Contenu |
|---|---|
| `backend/` | Python 3.14, uv, FastAPI, SQLAlchemy, Alembic |
| `frontend/` | Next.js (App Router), TypeScript, pnpm |
| `docs/` | ADR, modèle de données, specs |

Le vocabulaire du domaine est dans [`CONTEXT.md`](CONTEXT.md), les règles de contribution dans [`AGENTS.md`](AGENTS.md).

## Démarrage local

Prérequis : [uv](https://docs.astral.sh/uv/), Node 24 avec pnpm (via Corepack), un moteur Docker (OrbStack).

```sh
# Base PostgreSQL + pgvector (bases nexus et nexus_test)
docker compose up -d

# Back-end : API sur http://127.0.0.1:8000
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run nexus-api

# Front-end : http://localhost:3000
cd frontend
cp .env.example .env.local
corepack enable
pnpm install
pnpm dev
```

`uv run nexus-batch` lance une Exécution. Pour que la collecte ait quelque chose à lire, crée ton Utilisateur et abonne-le à des Sources du Catalogue (`uv run nexus-admin --help`) :

```sh
uv run nexus-admin user upsert --handle moi --timezone Africa/Dakar --briefing-hour 7
uv run nexus-admin subscribe moi rss:numerama.com/feed
```

Les vérifications à faire avant une PR sont dans `backend/AGENTS.md` et `frontend/AGENTS.md`.

## Licence

Aucune licence : le code est visible, mais tous droits réservés. Les skills de `.claude/skills/` gardent leur licence MIT d'origine.
