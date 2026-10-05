# Cœur métier sans techno, persistance par ORM mappé et instantanés gardés sur trois couches

Le back-end est organisé en **cœur métier et adaptateurs** (architecture hexagonale, version pragmatique). Le cœur (`nexus.core`) contient les entités, les règles, les ports et les services, et n'importe que la bibliothèque standard et Pydantic. Les adaptateurs implémentent les ports : PostgreSQL, la passerelle de modèles (Gemini, Jev), les Connecteurs, la récupération des pages web, l'agent LangGraph, Langfuse. FastAPI et le batch sont des points d'entrée qui appellent le cœur. Les règles délicates (Fenêtre du Briefing, Règle de diversité, Candidats limités aux Abonnements) se testent ainsi sans base ni LLM, et changer de fournisseur reste un changement local. La persistance passe par **SQLAlchemy ORM en style déclaratif**, dans l'adaptateur, avec un **mapping explicite** vers des dataclasses `frozen` du cœur. L'immuabilité des instantanés (ADR-0001) et des tables en ajout seul est gardée sur trois couches : le type, l'ORM et la base.

## Garde-fous contre la sur-ingénierie

1. Des ports seulement aux frontières qui varient ou qui coûtent en test : persistance, passerelle de modèles, Connecteurs, pages web, agent, horloge, traçage, Catalogue de Sources.
2. Des ports de dépôt orientés cas d'usage (`find_candidates(...)`), écrits en SQL et pgvector, jamais un dépôt générique.
3. Pas de couche « application » distincte au MVP. Chaque section du cœur commence par trois fichiers (`entities.py`, `ports.py`, `services.py`), qu'on ne découpe que s'ils grossissent.

Pydantic est autorisé dans le cœur pour valider, jamais pour des entrées-sorties. Les schémas de l'API restent séparés des entités du cœur, pour ne jamais exposer un champ interne par accident.

## Les trois couches de garde

- **Le type** : les entités du cœur sont des dataclasses `frozen` dont les collections sont des tuples. « Remplacer » un Briefing en Échec revient à construire une nouvelle valeur, puis à l'écrire explicitement.
- **L'ORM** : un écouteur `before_update` (mapper) et un écouteur `do_orm_execute` (pour les `UPDATE` en masse) lèvent une erreur sur toute mise à jour d'une table gardée.
- **La base** : un trigger générique `BEFORE UPDATE` refuse toute mise à jour des tables gardées. Il compare la ligne entière en jsonb, donc les colonnes ajoutées plus tard sont protégées d'office. Seule exception : une colonne de clé étrangère qui passe d'une valeur à NULL, toutes les autres colonnes restant identiques, ce qu'exige la purge (`ON DELETE SET NULL` exécute un vrai `UPDATE`, qui déclenche les triggers utilisateur) :
  `OLD.<fk> IS NOT NULL AND NEW.<fk> IS NULL AND (to_jsonb(NEW) - '<fk>') = (to_jsonb(OLD) - '<fk>')`.
  Les colonnes `vector(768)` passent par leur sortie texte (pgvector ne définit aucune conversion vers jsonb), ce qui suffit à l'égalité.

| Table | Mise à jour autorisée |
|---|---|
| `entry`, `citation` | seulement `article_id` → NULL (purge des Articles) |
| `briefing` | seulement si `OLD.status = 'failed'` |
| `briefing_composition` | seulement `execution_id` → NULL (purge des Exécutions) |
| `interest_version`, `message`, `signal`, `same_event_judgment`, `relevance_score` | aucune |

`execution` et `source_collection` ne sont pas gardées : elles sont clôturées par une mise à jour. Les gardes ne bloquent pas les `DELETE` (purges, suppression d'un Utilisateur).

## Changement de modèle d'embeddings

L'ADR-0004 prévoit qu'un changement de modèle recalcule tous les vecteurs, y compris ceux des Entrées. Il n'y a pas d'exception permanente dans le trigger pour `embedding` et `embedding_model`. La procédure :
1. un script idempotent et reprenable calcule les nouveaux vecteurs dans une table temporaire, hors migration (quota, durée) ;
2. une migration, **en une seule transaction**, fait `ALTER TABLE … DISABLE TRIGGER`, puis `UPDATE … FROM` la table temporaire, puis `ENABLE TRIGGER`, et vérifie qu'il ne reste aucun vecteur de l'ancien modèle. Les DDL de PostgreSQL étant transactionnels, un échec réactive le trigger au `ROLLBACK`.

## Considered Options

- **Tout dans un même ensemble de paquets, sans frontière** (organisation par techno : `db/`, `ai/`, `api/`) : écarté, car les règles métier se mêlent aux SDK et ne se testent plus sans infrastructure.
- **SQLAlchemy Core sans ORM** (recommandé de peu pendant le cadrage, car rien n'y est implicite) : écarté, car l'ORM apporte des résultats vérifiés par mypy, une documentation abondante et la pratique courante en entreprise. L'immuabilité est protégée par des gardes plutôt que par le choix de l'outil.
- **ORM en mapping impératif** (entités du cœur mappées directement) : écarté, car SQLAlchemy doit écrire dans l'objet. Une dataclass `frozen` devient alors impossible, `__post_init__` est ignoré au chargement, et le flush écrit des objets du cœur sans appel explicite.
- **Liste de colonnes écrite à la main dans le trigger** : écarté, car une colonne ajoutée plus tard serait modifiable en silence.

## Consequences

- Environ 300 lignes de mapping (`to_domain` / `to_row`), mécaniques et couvertes par les tests d'intégration des dépôts. Ne pas les « simplifier » en exposant les modèles ORM au cœur.
- La règle est vérifiable : import-linter (le cœur n'importe ni adaptateur, ni point d'entrée ; les adaptateurs sont indépendants entre eux) et un test de liste autorisée des imports externes du cœur. Ajouter une dépendance au cœur est une décision visible dans une PR.
- Un seul `bootstrap.py` construit les adaptateurs pour les deux points d'entrée : une seule image Docker, deux commandes.
- Les gardes imposent des écritures en ajout seul, par exemple l'enregistrement en une fois de la réponse streamée de l'agent (voir `data-model.md`).
