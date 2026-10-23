# Modèle de données

État au 5 octobre 2026, dérivé de [`CONTEXT.md`](../CONTEXT.md) (vocabulaire et noms de code) et des ADR [0001](adr/0001-contenu-historise-par-copie.md) à [0005](adr/0005-coeur-metier-adaptateurs-et-instantanes-gardes.md). PostgreSQL (Neon) + pgvector, SQLAlchemy 2 async (ORM déclaratif) + Alembic.

## Conventions

- **Clés** : `id bigint GENERATED ALWAYS AS IDENTITY` partout.
- **Dates** : `timestamptz` en UTC. Seule exception : `briefing.briefing_date`, une `DATE` dans le jour local de l'Utilisateur.
- **Valeurs fermées** : colonne `text` + contrainte `CHECK` en base ; un `StrEnum` Python est la source de vérité dans le code.
- **Vecteurs** : `vector(768)`, produits par `gemini-embedding-2`. Chaque vecteur est accompagné de `embedding_model` (obligatoire) et de `embedding_kind` (`document` | `query`). On ne compare jamais deux vecteurs dont `embedding_model` diffère.
- **Copie plutôt que référence** pour tout contenu historisé (ADR-0001) : les liens vers `article` sont facultatifs et passent à `NULL` à la purge.
- **Rien de privé dans un objet commun** (ADR-0003) : les tables communes (`source`, `article`, `same_event_judgment`) ne portent aucune donnée d'interaction.
- **Relations ORM** : `lazy="raise"` partout ; sessions en `expire_on_commit=False`.
- **Persistance** (ADR-0005) : modèles ORM déclaratifs dans l'adaptateur, mappés explicitement vers des dataclasses `frozen` du cœur ; un `TypeDecorator` convertit les vecteurs en `tuple[float, ...]`, numpy n'atteint jamais le cœur. Écritures idempotentes par `INSERT … ON CONFLICT DO NOTHING`.
- **Tables gardées** (ADR-0005) : aucune mise à jour sur `entry`, `citation`, `interest_version`, `message`, `signal`, `same_event_judgment`, `relevance_score` et `briefing_composition`, sauf une clé étrangère qui passe à NULL lors d'une purge (`entry.article_id`, `citation.article_id`, `briefing_composition.execution_id`) ; `briefing` n'est mis à jour que s'il est `failed`. Garde ORM + trigger générique en base.
- **Nom des tables** : le nom de code de `CONTEXT.md`, sauf `app_user` (`USER` est un mot réservé de PostgreSQL).

## Tables

### Contenu commun

**`source`**
| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint | PK |
| `source_key` | text | **UNIQUE** ; clé naturelle (`reddit:python`, `rss:lemonde.fr/rss/une.xml`) construite après normalisation de l'URL (schéma, `www`, barre oblique finale, casse du domaine) |
| `connector` | text | CHECK (`rss`, `hackernews`, `reddit`) |
| `config` | jsonb | validé par un modèle Pydantic propre au Connecteur |
| `owner_user_id` | bigint NULL | FK `app_user` ; NULL = Source commune, renseigné = Source privée (compte connecté, hors MVP) |
| `is_active` | boolean | |
| `deactivation_reason` | text NULL | CHECK (`maintainer`, `repeated_failures`, `removed_from_catalog`) ; **CHECK (`is_active = (deactivation_reason IS NULL)`)** |
| `last_collected_at` | timestamptz NULL | sert de `since` au Connecteur |
| `http_etag` | text NULL | validateur `ETag` de la dernière réponse, renvoyé en requête conditionnelle |
| `http_last_modified` | text NULL | validateur `Last-Modified` de la dernière réponse |

**`article`**
| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint | PK |
| `source_id` | bigint | FK `source` ON DELETE RESTRICT |
| `canonical_url` | text | pour HN et Reddit : le lien externe |
| `discussion_url` | text NULL | page de commentaires HN ou Reddit |
| `linked_url` | text NULL | URL de la Page liée |
| `linked_page_status` | text | CHECK (`not_applicable`, `pending`, `fetched`, `reused`, `failed`, `timeout`, `too_large`, `blocked_by_robots`) |
| `excerpt` | text | plafonné à environ 3 000 caractères, sans HTML |
| `excerpt_origin` | text | CHECK (`source`, `linked_page`, `both`) |
| `title` | text | |
| `fingerprint` | text | empreinte du contenu, pour la déduplication au sein d'une Source |
| `published_at` | timestamptz | |
| `collected_at` | timestamptz | base de la Fenêtre du Briefing et de la purge |
| `nature` | text NULL | CHECK (`official`, `factual`, `rumor`, `opinion`, `unknown`) |
| `nature_confidence` | real NULL | |
| `summary` | text NULL | produit seulement si l'Article est pertinent pour au moins un Utilisateur |
| `embedding` | vector(768) NULL | `embedding_kind = document` ; NULL tant que la vectorisation n'a pas abouti |
| `embedding_model` | text NULL | renseigné si et seulement si `embedding` l'est (CHECK) |

Contraintes : **UNIQUE (`source_id`, `canonical_url`)** ; **UNIQUE (`source_id`, `fingerprint`)** ; index sur `collected_at`. `pending` : Page liée pas encore récupérée.

**`purged_article`** (Trace de purge) : table commune, sans donnée d'Utilisateur (ADR-0003). Elle empêche un Article purgé de revenir.
| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint | PK |
| `source_id` | bigint | FK `source` ON DELETE RESTRICT |
| `canonical_url` | text | |
| `fingerprint` | text | |
| `purged_at` | timestamptz | base de la suppression des Traces après 365 jours |

Index sur (`source_id`, `canonical_url`), sur (`source_id`, `fingerprint`) et sur `purged_at`.

**Rattrapage (pipeline idempotent)** : à chaque Exécution, le pipeline complète les Articles encore en rétention auxquels il manque un embedding, une Nature ou un résumé (ce dernier seulement si l'Article remplit la condition de pertinence). Une étape qui échoue (quota, fournisseur indisponible) laisse la colonne à NULL au lieu de faire échouer la Collecte. Un Article sans embedding ne peut pas être scoré, donc il n'est pas Candidat tant qu'il n'a pas été complété.

**`same_event_judgment`** : aucun `user_id`, c'est une propriété du contenu.
| Colonne | Type | Notes |
|---|---|---|
| `article_a_id`, `article_b_id` | bigint | PK composite ; CHECK `article_a_id < article_b_id` ; FK `article` ON DELETE CASCADE |
| `same_event` | boolean | |
| `probability` | real | |
| `model` | text | |
| `judged_at` | timestamptz | |

### Profil

**`app_user`** : `id`, `handle` (identifiant non personnel, **UNIQUE**, CHECK `^[a-z0-9_-]{3,32}$`), `timezone` (nom IANA), `briefing_hour` (heure locale, smallint), `created_at`.

**`subscription`** : PK (`user_id`, `source_id`) ; `user_id` en ON DELETE CASCADE, `source_id` en RESTRICT ; `created_at`.

**`interest`** : `id`, `user_id` (FK, CASCADE), `created_at`, `deleted_at NULL`. Il ne porte que l'identité.

**`interest_version`** : le Journal du Profil, en ajout seul.
| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint | PK |
| `interest_id` | bigint | FK `interest` ON DELETE CASCADE |
| `version_no` | integer | **UNIQUE (`interest_id`, `version_no`)** |
| `change_type` | text | CHECK (`created`, `updated`, `deleted`) |
| `origin` | text | CHECK (`direct`, `onboarding`, `not_interested`) |
| `label`, `description` | text | |
| `weight` | real | CHECK `weight > 0 AND weight <= 1` (pas d'Intérêt négatif au MVP) |
| `embedding` | vector(768) | `embedding_kind = query` |
| `embedding_model` | text | |
| `created_at` | timestamptz | |

**Vue `current_interest_version`** : la dernière version de chaque Intérêt dont `deleted_at IS NULL`.

**`relevance_score`**
| Colonne | Type | Notes |
|---|---|---|
| `user_id` | bigint | FK `app_user` ON DELETE CASCADE ; dénormalisé pour les requêtes |
| `article_id` | bigint | FK `article` ON DELETE CASCADE |
| `interest_version_id` | bigint | FK `interest_version` ON DELETE CASCADE ; une version n'est jamais supprimée isolément (le Journal est en ajout seul), donc ce cas ne survient qu'avec la suppression de l'Utilisateur |
| `similarity` | real | similarité brute, conservée pour le calibrage |
| `score` | real | similarité pondérée |

PK (`user_id`, `article_id`, `interest_version_id`). La Pertinence globale (le maximum) est calculée par requête et n'est pas stockée.

### Exécution et livraison

**`execution`** : `id`, `started_at`, `finished_at`, `result` CHECK (`success`, `partial`, `failed`), `failure_cause` CHECK (`technical`, `collection`) NULL, `error_detail` NULL, `anomalies` jsonb (défaut `[]`) : avertissements qui ne font pas échouer l'Exécution, par exemple `[{"kind": "catalog_sync_blocked", "detail": …}]` ou `feed_moved` (flux déplacé par une redirection permanente, avec l'ancienne et la nouvelle URL).

**`source_collection`** : `id`, `execution_id` (FK, CASCADE), `source_id` (FK), `result` CHECK (`success`, `failed`), `article_count`, `unreadable_count` (défaut 0 : éléments du flux ignorés car sans titre ou sans lien), `error_detail`, `started_at`, `finished_at`.

**`briefing_composition`** : `id`, `execution_id` (FK, **ON DELETE SET NULL**), `user_id` (FK, CASCADE), `briefing_date`, `result` CHECK (`normal`, `partial`, `failed`), `failure_cause` NULL, `error_detail` NULL, `created_at`.

**`briefing`**
| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint | PK |
| `user_id` | bigint | FK ON DELETE CASCADE |
| `briefing_date` | date | jour local |
| `status` | text | CHECK (`normal`, `partial`, `failed`) |
| `synthesis` | text NULL | |
| `failed_source_names` | jsonb | copie des noms des Sources abonnées en échec |
| `composition_id` | bigint | FK `briefing_composition` : la Composition qui a produit l'état courant |
| `created_at`, `updated_at` | timestamptz | |

Contrainte : **UNIQUE (`user_id`, `briefing_date`)**. Seul un Briefing `failed` est mis à jour, sur place.

**`entry`**
| Colonne | Type | Notes |
|---|---|---|
| `id` | bigint | PK |
| `briefing_id` | bigint | FK ON DELETE CASCADE |
| `user_id` | bigint | dénormalisé |
| `article_id` | bigint NULL | FK `article` **ON DELETE SET NULL** |
| `rank` | smallint | **UNIQUE (`briefing_id`, `rank`)** |
| `title`, `summary`, `url`, `source_name`, `nature` | copies | |
| `embedding` | vector(768) | copie ; `embedding_kind = document` |
| `embedding_model` | text | |
| `interest_id`, `interest_version_id` | bigint | Intérêt explicatif et sa version |
| `interest_label` | text | copie |
| `also_covered_by` | jsonb | `[{source_name, url}]` |

Contrainte : **UNIQUE partiel (`user_id`, `article_id`) WHERE `article_id IS NOT NULL`**.

**`signal`** : `id`, `entry_id` (FK, CASCADE), `user_id` (dénormalisé), `kind` CHECK (`opened`, `not_interested`), `created_at`. Contrainte **UNIQUE (`entry_id`, `kind`)** : l'Engagement compte les Entrées ouvertes, pas les clics.

### Conversation

**`conversation`** : `id`, `user_id` (FK, CASCADE), `created_at`.

**`message`** : `id`, `conversation_id` (FK, CASCADE), `role` CHECK (`user`, `assistant`), `content`, `created_at`. En ajout seul : la réponse de l'agent, streamée en SSE, est enregistrée en une fois à la fin du flux (ou à l'interruption, avec ce qui a été généré), jamais créée vide puis complétée.

**`citation`** : `id`, `message_id` (FK, CASCADE), `position`, `kind` CHECK (`article`, `followed_page`), `title`, `url`, `source_name` (nom de la Source ou du site), `article_id` NULL (FK, SET NULL).

## Règles de suppression

| Événement | Effet |
|---|---|
| Purge quotidienne : Article collecté il y a plus de 30 jours | supprime `relevance_score` et `same_event_judgment` (CASCADE) ; `entry.article_id` et `citation.article_id` passent à NULL |
| Purge : Exécution de plus de 90 jours | supprime ses `source_collection` (CASCADE) ; `briefing_composition.execution_id` passe à NULL (les Compositions restent) |
| Source retirée du Catalogue (inscrite dans `[[retired]]`) | jamais supprimée : si elle est active, `is_active = false`, `deactivation_reason = removed_from_catalog` ; si elle est déjà inactive, elle garde sa raison d'origine |
| Suppression d'un Intérêt | `interest.deleted_at` + ligne `interest_version` de type `deleted` ; rien n'est effacé |
| Suppression d'un Utilisateur (`app_user`) | CASCADE sur toutes ses données personnelles, y compris `relevance_score` (voir Points ouverts pour ses Sources privées) |

## Décisions

### Tour 1
1. **Journal du Profil = `interest` (identité) + `interest_version` (ajout seul) + vue de la version courante** : l'Engagement par version (D42) sans la complexité de l'event sourcing pur.
2. **Unicité de l'Article sur (`source_id`, `canonical_url`)** : un Article appartient à une Source (D38) ; la déduplication entre Sources relève de la Règle de diversité.
3. **Page liée récupérée par le batch, sur un seul niveau** (délai, taille, robots.txt, pages payantes acceptées en l'état) : un post HN sans sa page n'a qu'un titre, donc un score sans valeur.
4. **Extrait plafonné (environ 3 000 caractères), jamais d'Article brut stocké** : assez pour le chat, compatible avec le quota.
5. **Tous les Scores conservés, purgés en cascade avec l'Article** : le calibrage a besoin de la distribution complète.
6. **Exécution → Collectes + Compositions ; un Briefing en Échec est mis à jour sur place** : l'unicité n'est jamais violée et l'Exécution ratée reste tracée.
7. **`entry.article_id` facultatif, SET NULL, avec `user_id` dénormalisé** : permet la contrainte d'unicité partielle (D26) sans bloquer la purge.

### Tour 2
8. **`gemini-embedding-2` en 768 dimensions, tout dans le cloud** (ADR-0004) : multilingue, stable, retrait le plus lointain, normalisation automatique.
9. **Un seul vecteur `document` par Article ; `query` pour les Intérêts et les questions** : on ne double pas le stockage, et Jev tranche la comparaison entre Articles.
10. **Jugement « même événement » stocké, sans `user_id`, une fois par paire** : propriété du contenu (ADR-0003), jeu de calibrage, et futur socle des Histoires.
11. **Pages liées récupérées pour tous les Articles, en parallèle, avec réutilisation des Extraits déjà en base** : un seuil de moins à calibrer, une requête de moins vers l'éditeur.
12. **Code en anglais, noms de code dans `CONTEXT.md`, noms spécifiques** (`source_collection`, `briefing_composition`) : le code parle comme le glossaire.
13. **Pages suivies par l'agent : jamais d'Article, seulement une Citation** : c'est une interaction (ADR-0003).
14. **Gemini gratuit au MVP** (règles « données payantes » applicables dans l'EEE), **payant pour tous les appels avant l'entourage** : conditions de l'API.

### Tour 3
15. **SQLAlchemy async partout (`asyncpg`), `lazy="raise"`, `statement_cache_size=0` sur le pooler ; migrations Alembic par l'URL directe** : un seul style, et le piège PgBouncer est neutralisé.
16. **`bigint identity`, `timestamptz` UTC, `briefing_date` en DATE locale, fuseau IANA** : économie de stockage et sémantique claire du « jour ».
17. **`text` + CHECK + `StrEnum`** : ajouter une valeur reste une migration triviale.
18. **Pas d'index vectoriel au MVP** : la recherche exacte est rapide sur environ 15 000 lignes, sans perte due au filtrage après coup ni surcoût de stockage.
19. **`source_key` unique, construit sur une URL normalisée ; Catalogue synchronisé sans suppression** : pas de doublons, et aucune référence qui pointe vers du vide.
20. **Purge quotidienne sur `collected_at` (30 jours) ; Exécutions purgées après 90 jours, Compositions conservées** : cohérence avec la Fenêtre du Briefing ; la surveillance n'est pas de la mémoire.

### Corrections avant la première migration
21. **Table `app_user`** : `USER` est un mot réservé de PostgreSQL.
22. **`article.embedding` facultatif + rattrapage à chaque Exécution** : une panne du fournisseur d'embeddings ou de LLM ne fait perdre aucun Article ; le pipeline est idempotent.
23. **`relevance_score.user_id` et `interest_version_id` en clés étrangères CASCADE** : aucune donnée orpheline à la suppression d'un Utilisateur.
24. **CHECK (`is_active = (deactivation_reason IS NULL)`) sur `source`** : une Source inactive dit toujours pourquoi, et une Source active n'a pas de raison de désactivation.

### Tour 4 : cadrage du squelette
25. **Cœur métier / adaptateurs, persistance par ORM déclaratif + mapping vers des dataclasses `frozen`** (ADR-0005) : le cœur se teste sans infrastructure, et l'immuabilité est garantie par le type.
26. **Gardes d'immuabilité sur trois couches** (type, ORM, trigger générique comparant la ligne en jsonb) sur les tables d'instantanés et en ajout seul ; seule exception, une clé étrangère qui passe à NULL lors d'une purge (ADR-0005) : sinon la purge des Articles échouerait.
27. **`execution.anomalies` (jsonb)** : un avertissement (synchronisation du Catalogue bloquée) n'est pas un échec, mais doit rester visible dans la base, donc dans Grafana.
28. **Synchronisation du Catalogue de Sources au début de chaque Exécution**, limitée aux Sources communes : `[[retired]]` désactive explicitement (seulement les Sources actives) ; une Source commune active absente des deux listes est une disparition inexpliquée ; au-delà de `max(3, 20 % des Sources communes actives)` disparitions, ou si le catalogue est vide, rien n'est appliqué et l'anomalie est inscrite. Une Source revenue au catalogue n'est réactivée que si sa raison est `removed_from_catalog`.

## Points ouverts

### Chantier zéro
- Test d'intégration contre Neon qui valide la configuration du pooler (`asyncpg`, `statement_cache_size=0`) ; migrations par l'URL directe. Prévu dans [`specs/0001-squelette-du-monorepo.md`](specs/0001-squelette-du-monorepo.md).
- Vérifier que `gemini-embedding-2` accepte bien 768 dimensions pour le texte ; sinon repli sur `001` avec une normalisation couverte par un test. Prévu dans la même spec.

### Grafana (session Déploiement)
- **Ne pas empêcher la mise en veille de Neon** : le quota de calcul (100 CU-heures par mois) suppose que la base s'endort ; des requêtes de tableau de bord ou d'alerte trop fréquentes la garderaient éveillée.
- **Rôle PostgreSQL en lecture seule, limité à des vues agrégées**, sans accès aux Signaux ni aux Conversations (ADR-0003).
- **Proposition, à confirmer** : une règle d'alerte Grafana sur `execution.anomalies` et sur les Exécutions `failed` sert de canal d'alerte au mainteneur.

### Avant l'ouverture à l'entourage
- Volume de `relevance_score` : passer probablement à « tout garder 7 jours, puis seulement le score de l'Intérêt explicatif ».
- Tous les appels Gemini sur l'offre payante.
- Identifiant public (non énumérable) pour les ressources exposées par l'API, si besoin.
- Authentification.
- Suppression d'un Utilisateur propriétaire de Sources privées : sort de ces Sources et de leurs Articles (actuellement `RESTRICT`).
- Conditions d'utilisation des flux RSS de chaque éditeur du Catalogue : beaucoup les réservent à un usage personnel.

### Avant toute ouverture publique
- Droits voisins des éditeurs de presse (stockage d'Extraits et de résumés).

### À trancher plus tard
- Évaluer Jev (TypeSafe AI) pour la tâche `classify` (Nature avec sa probabilité, Jugement « même événement ») : simple choix de configuration de la passerelle.
- Seuils à calibrer : similarité du pré-filtre de diversité, pertinence pour déclencher le résumé, confiance pour Inconnu, minimum d'Entrées pour l'Engagement et pour la Synthèse.
- Heure par défaut du Briefing ; nombre N de Collectes échouées avant désactivation ; canal d'alerte (proposition : Grafana, voir plus haut).
- **Clé de `same_event_judgment`** : (`article_a_id`, `article_b_id`) et la garde interdisent de juger une même paire avec deux modèles ; avec `ON CONFLICT DO NOTHING`, le second jugement serait même ignoré sans erreur. Pour évaluer Jev contre Gemini, ajouter `model` à la clé.
- **Forme de l'agent du chat** : graphe fixe (comprendre → récupérer → vérifier/reformuler → répondre) ou agent libre qui choisit ses outils (`follow_page` suppose au moins un choix d'outil par le LLM). L'ADR-0005 convient aux deux ; à trancher avec la spec du chat.
- **Historique renvoyé au LLM** : sans checkpointer, l'historique est relu dans `message` à chaque question ; fixer une limite (N derniers messages ou résumé) avec la spec du chat.
- Index vectoriel (HNSW) le jour où la latence l'exige.
- Popularité dans la Source (points, votes) sur `article`, pour la future Entrée d'exploration.
