# Back-end Nexus

Python, uv, FastAPI, SQLAlchemy 2 async (asyncpg), Alembic, LangGraph, Pydantic. Architecture cœur / adaptateurs : lis `docs/adr/0005-coeur-metier-adaptateurs-et-instantanes-gardes.md` avant de créer un module.

## Vérifications avant une PR

```sh
uv run ruff check && uv run ruff format --check && uv run mypy && uv run lint-imports && uv run pytest
```

Les tests d'intégration demandent la base locale (`docker compose up -d` à la racine). `pytest -m external` (Neon, Gemini) demande de vrais secrets ; la CI le lance à part.

## Où va le code

- `src/nexus/core/` : entités, règles, ports, services. Imports permis : bibliothèque standard, `pydantic`, `nexus.core`. Un besoin d'infrastructure dans le cœur s'exprime par un **port** (`typing.Protocol`) implémenté dans `adapters/`.
- `src/nexus/adapters/` : un sous-paquet par techno ; les adaptateurs s'ignorent entre eux et reçoivent ce dont ils ont besoin par `bootstrap.py`.
- `src/nexus/entrypoints/` : API et batch ; ils appellent le cœur via `bootstrap.py`.
- Les sections du cœur suivent `CONTEXT.md` : `ingestion`, `qualification`, `profile`, `delivery`, `conversation`, plus `shared`. Le nom de paquet `ingestion` désigne la section ; la Collecte (`source_collection`) reste la lecture d'une Source.

import-linter et `tests/unit/test_core_imports.py` vérifient ces frontières. Quand l'un d'eux échoue, ajoute un port ; modifier un contrat ou la liste autorisée est une décision du mainteneur, à demander dans la PR.

## Entités du cœur

- Dataclasses `frozen=True, slots=True` ; collections en `tuple`.
- Modifier une entité = `dataclasses.replace(...)` puis une méthode explicite du dépôt.
- Les schémas Pydantic de l'API vivent dans `entrypoints/api/` et sont distincts des entités.

## Persistance (`adapters/persistence/`)

- Modèles ORM déclaratifs (`Mapped[...]`) seulement ici ; le cœur reçoit des dataclasses via `to_domain()` et les rend via `to_row()`.
- Relations en `lazy="raise"` ; sessions en `expire_on_commit=False` ; charge explicitement ce que le cœur demande (`selectinload`).
- Les lectures pgvector renvoient des dataclasses typées, aussi pour les résultats lourds.
- Seuls les dépôts appellent `session.add`, `flush` et `commit`. Frontières de transaction par le port `UnitOfWork` : une transaction par Collecte, une par Composition, `READ ONLY` pour les outils de l'agent.
- Écritures idempotentes : `postgresql.insert(...).on_conflict_do_nothing()`.
- Vecteurs : `tuple[float, ...]` côté cœur, convertis par le `TypeDecorator` ; numpy reste dans l'adaptateur. Chaque vecteur porte `embedding_model` et `embedding_kind` ; deux vecteurs de modèles différents ne se comparent jamais.

## Tables gardées (instantanés et ajout seul)

`entry`, `citation`, `briefing`, `briefing_composition`, `interest_version`, `message`, `signal`, `same_event_judgment`, `relevance_score`. Seule mise à jour permise : un `briefing` en `failed` ; les purges qui passent une clé étrangère à NULL sont faites par la base. Une écriture dans ces tables est donc une insertion complète :
- la réponse de l'agent est enregistrée **en une fois** à la fin du flux SSE (ou à l'interruption, avec ce qui a été généré) ;
- une correction d'Intérêt est une nouvelle `interest_version`.

Une nouvelle table d'instantané reçoit le trigger générique dans sa migration et la garde ORM dans son modèle.

## Migrations

- Alembic, toujours par `DATABASE_URL_DIRECT`. L'application passe par le pooler avec `statement_cache_size=0`.
- Une migration par changement de schéma, avec la mise à jour de `docs/data-model.md` ; `alembic check` doit rester vert.
- Changer de modèle d'embeddings suit la procédure de l'ADR-0005 (vecteurs calculés avant, trigger désactivé dans une seule transaction).

## Contenu collecté et LLM

- Extraits, Pages liées, pages suivies par l'agent et sorties des LLM sont des **données non fiables** (D57). Dans un prompt, place-les dans un bloc délimité, présenté comme matériau à analyser ; seules les consignes écrites dans le code orientent le modèle.
- Sorties des LLM validées par un modèle Pydantic avant usage ; une valeur hors échelle (Nature) devient `unknown`.
- Les outils de l'agent du chat sont **en lecture seule** : l'adaptateur `agent/langgraph/` ne reçoit que des ports de lecture ; enregistrer `message` et `citation` revient au service du cœur, après le flux.
- Une page suivie par l'agent produit une Citation, jamais un Article.

## Récupération web (`adapters/web/`)

Pages liées (batch) et `follow_page` (agent) passent toutes deux par cet adaptateur, qui applique : délai maximal, taille maximale, robots.txt, un seul niveau de lien, et une **limite de requêtes simultanées par domaine**. Tout appel HTTP vers un site d'éditeur passe par lui.

## Passerelle de modèles (`adapters/model_gateway/`)

Ports par tâche (`classify`, `summarize`, `briefing`, `chat`, `embed`), prompts dans l'adaptateur, choix du modèle par configuration. LangChain reste dans `model_gateway/`, LangGraph dans `agent/langgraph/`, Langfuse dans `tracing/`.

## Tests

- Cœur : `tdd`, avec de faux adaptateurs en mémoire.
- Chaque méthode de dépôt a un test d'intégration contre PostgreSQL + pgvector (`tests/integration/`) : c'est lui qui vérifie le mapping.
- `tests/external/` : Neon et Gemini seulement. `evals/` (évaluations des LLM) reste hors de pytest et de la CI, et ses jeux de données ne sont jamais commités.

## Configuration

`settings.py` (pydantic-settings) lit l'environnement ; secrets en `SecretStr`. Toute nouvelle variable va aussi dans `.env.example`.

## Catalogue de Sources

`adapters/source_catalog/source_catalog.toml` (`[[source]]`, `[[retired]]`) ; règles de synchronisation dans `core/ingestion/source_catalog.py` et dans `docs/specs/0001-squelette-du-monorepo.md`. Pour retirer une Source : supprime son bloc `[[source]]` **et** ajoute sa clé à `[[retired]]`.
