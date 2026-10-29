# Spec 0002 : ingestion RSS

État au 16 octobre 2026, issu de la séance de cadrage. S'appuie sur [`CONTEXT.md`](../../CONTEXT.md), les ADR [0001](../adr/0001-contenu-historise-par-copie.md) à [0005](../adr/0005-coeur-metier-adaptateurs-et-instantanes-gardes.md) et [`data-model.md`](../data-model.md), qui priment en cas de conflit. Elle suit la [spec 0001](0001-squelette-du-monorepo.md) (squelette).

## Problème

Le squelette ouvre et clôt une Exécution vide : la base ne reçoit aucun Article, et rien en aval (qualification, Scores de pertinence, Briefing, chat) ne peut être construit ni évalué sur du vrai contenu. Le mainteneur n'a aucun moyen de s'abonner à une Source, de vérifier un flux avant de l'ajouter au Catalogue, ni d'être prévenu quand la collecte tombe en panne.

## Solution

Chaque Exécution collecte les flux RSS des Sources actives auxquelles au moins un Utilisateur est abonné, et enregistre des Articles normalisés et dédupliqués, avec leur Extrait. Le cycle de vie de l'Article est complet dès cette tranche : purge après la Fenêtre de rétention, Trace de purge pour qu'il ne revienne jamais. La collecte est polie envers les éditeurs (User-Agent identifiant, requêtes conditionnelles, une requête à la fois par domaine) et défensive envers leur contenu (HTTPS seulement, analyse XML filtrée). Une commande d'administration crée l'Utilisateur mainteneur, gère ses Abonnements et vérifie un flux. Le batch rend un résumé lisible et un code de sortie qui permettront au futur workflow d'alerter le mainteneur.

L'Article n'est pas encore enrichi : ni embedding, ni Nature, ni résumé, ni Page liée récupérée. Les colonnes correspondantes restent à NULL (ou `pending`), et le rattrapage prévu par `data-model.md` les complétera dans la spec suivante.

## User stories

### Utilisateur et Abonnements

1. En tant que mainteneur, je veux créer mon Utilisateur avec un handle, un fuseau horaire et une heure de Briefing, pour que Nexus collecte pour moi.
2. En tant que mainteneur, je veux que relancer la création avec le même handle mette à jour fuseau et heure sans créer de doublon, pour pouvoir rejouer mes commandes sans risque.
3. En tant que mainteneur, je veux un handle non personnel plutôt qu'une adresse e-mail, pour que la base ne contienne pas de donnée personnelle inutile.
4. En tant que mainteneur, je veux m'abonner à une Source par son `source_key`, pour choisir ce qui est collecté pour moi.
5. En tant que mainteneur, je veux qu'un abonnement à un `source_key` inconnu soit refusé avec un message clair, pour ne pas croire suivre une Source qui n'existe pas.
6. En tant que mainteneur, je veux pouvoir m'abonner à une Source inactive, avec un avertissement, pour que l'Abonnement prenne effet si elle est réactivée.
7. En tant que mainteneur, je veux qu'un abonnement déjà existant ou un désabonnement absent ne fasse rien, pour que les commandes soient idempotentes.
8. En tant que mainteneur, je veux que les commandes d'Abonnement soient additives, pour qu'un oubli dans une liste ne me désabonne jamais en silence.
9. En tant que mainteneur, je veux réactiver une Source désactivée après des échecs répétés, pour la remettre en collecte une fois la panne de l'éditeur passée.

### Catalogue de Sources

10. En tant que mainteneur, je veux que le Catalogue initial contienne dix flux larges sur trois thèmes, pour juger les premiers Briefings sur du contenu qui m'intéresse, mes intérêts précis restant dans mes Intérêts en base.
11. En tant que mainteneur, je veux que la synchronisation du Catalogue ait lieu au début de chaque Exécution, pour qu'un ajout au Catalogue soit pris en compte à l'heure suivante.
12. En tant que mainteneur, je veux qu'un changement de config d'une Source déjà en base (par exemple un motif d'exclusion) soit appliqué par la synchronisation, pour que le Catalogue reste la référence des Sources communes.
13. En tant que mainteneur, je veux qu'une config invalide dans le Catalogue bloque toute la synchronisation, pour qu'elle ne soit ni appliquée à moitié ni ignorée en silence.
14. En tant que mainteneur, je veux qu'une config identique une fois validée et normalisée ne soit pas réécrite, pour ne pas voir une mise à jour à chaque Exécution.
15. En tant que mainteneur, je veux voir dans le résumé les configs mises à jour, pour savoir ce que la synchronisation a changé.
16. En tant que mainteneur, je veux exclure d'une Source les éléments dont l'URL contient un motif (les fiches de RMC Sport), pour que des pages encyclopédiques ne soient pas prises pour de l'actualité.
17. En tant que mainteneur, je veux qu'un flux entièrement exclu donne une Collecte réussie, pour qu'un filtre ne déclenche jamais une désactivation.
18. En tant que mainteneur, je veux vérifier un flux par son URL avant de l'ajouter au Catalogue, sans rien écrire en base, pour connaître le nombre d'éléments lisibles, les dates, les validateurs HTTP et les anomalies.
19. En tant que mainteneur, je veux que cette vérification applique exactement les protections de la Collecte, pour qu'un flux qui passe la vérification passe aussi la Collecte.
20. En tant que mainteneur, je veux qu'une adresse `http://` soit refusée dans le Catalogue, pour qu'aucun contenu modifiable en route n'entre dans Nexus.

### Exécution

21. En tant que mainteneur, je veux qu'une seule Exécution tourne à la fois, pour que deux batchs ne collectent ni n'écrivent les mêmes Articles en même temps.
22. En tant que mainteneur, je veux qu'une Exécution qui trouve le verrou pris sorte proprement avec le code 0 et le dise dans le résumé, pour qu'un chevauchement occasionnel ne soit pas traité comme une panne.
23. En tant que mainteneur, je veux qu'une Exécution soit `success` quand toutes les Collectes ont réussi, `partial` quand certaines ont échoué, et `failed` quand toutes ont échoué ou qu'une erreur technique l'a interrompue, pour distinguer une panne d'un éditeur d'une panne de Nexus.
24. En tant que mainteneur, je veux une anomalie quand aucune Source n'est à collecter, pour distinguer un batch sain d'un batch qui ne fait rien.
25. En tant que mainteneur, je veux qu'une synchronisation bloquée laisse les Collectes se faire, pour qu'une erreur dans le Catalogue n'arrête pas la veille.
26. En tant que mainteneur, je veux que la purge s'exécute même quand les Collectes échouent, pour que la base ne grossisse jamais faute de purge.
27. En tant que mainteneur, je veux un résumé de chaque Exécution (résultat, Collectes, Articles insérés, éléments illisibles et exclus, anomalies, configs mises à jour, version d'expat), pour comprendre ce qui s'est passé sans ouvrir la base.
28. En tant que mainteneur, je veux que le batch sorte avec un code non nul quand l'Exécution est `failed`, qu'une Source vient d'être désactivée ou que la synchronisation est bloquée, pour que le futur workflow m'alerte.

### Collecte

29. En tant qu'Utilisateur, je veux que seules les Sources actives auxquelles je suis abonné soient collectées, pour que Nexus ne lise que ce que je suis.
30. En tant que mainteneur, je veux que les Collectes se fassent en parallèle, pour que l'Exécution reste courte.
31. En tant qu'éditeur d'un site lu par Nexus, je veux recevoir une seule requête à la fois de Nexus, pour que la veille ne charge pas mon serveur.
32. En tant qu'éditeur, je veux que Nexus s'identifie par un User-Agent qui pointe vers son repo, pour savoir qui me lit et comment le joindre.
33. En tant qu'éditeur, je veux que Nexus envoie mes validateurs (ETag, Last-Modified), pour répondre 304 sans renvoyer un flux inchangé.
34. En tant que mainteneur, je veux qu'une réponse 304 soit une Collecte réussie sans Article, pour qu'un flux inchangé ne compte jamais comme une panne.
35. En tant que mainteneur, je veux qu'un flux vide ou sans nouveauté soit une Collecte réussie, pour ne pas désactiver une Source calme.
36. En tant que mainteneur, je veux qu'une erreur réseau, un délai dépassé, une réponse non 2xx (429 et 503 compris) ou un flux illisible fassent échouer la Collecte, pour que les pannes soient comptées.
37. En tant que mainteneur, je veux qu'un flux dont les éléments sont tous illisibles fasse échouer la Collecte, pour qu'un changement de format soit traité comme une panne et non comme un flux vide.
38. En tant que mainteneur, je veux qu'un élément illisible dans un flux par ailleurs valide soit ignoré et compté, pour qu'un élément mal formé ne fasse pas perdre les autres.
39. En tant que mainteneur, je veux qu'une Source soit désactivée après 24 Collectes échouées d'affilée, avec une anomalie, pour qu'une Source morte ne soit pas relue indéfiniment sans que je le sache.
40. En tant que mainteneur, je veux qu'un flux déplacé de façon permanente (301) soit suivi et signalé par une anomalie, pour mettre à jour le Catalogue.
41. En tant que mainteneur, je veux qu'une redirection de HTTPS vers HTTP fasse échouer la Collecte, pour qu'un serveur ne puisse pas contourner la règle du HTTPS.
42. En tant que mainteneur, je veux qu'une Collecte, ses Articles, la date de dernière collecte et les validateurs HTTP soient enregistrés ensemble ou pas du tout, pour qu'une Collecte interrompue ne laisse pas d'état incohérent.

### Sécurité de l'analyse

43. En tant que mainteneur, je veux qu'un flux contenant une déclaration DOCTYPE ou ENTITY, quelle que soit sa casse et où qu'elle soit, soit refusé avant l'analyse, pour qu'aucune attaque XXE ni billion laughs n'atteigne l'analyseur.
44. En tant que mainteneur, je veux qu'un flux encodé en UTF-16 ou UTF-32 soit refusé, pour qu'une déclaration encodée n'échappe pas au filtre préalable.
45. En tant que mainteneur, je veux que ces refus fassent échouer la Collecte avec une cause explicite, pour savoir pourquoi un flux est rejeté.
46. En tant que mainteneur, je veux que la taille d'une réponse soit plafonnée, pour qu'un flux démesuré ne sature pas la mémoire.

### Article

47. En tant qu'Utilisateur, je veux qu'un même article n'apparaisse qu'une fois par Source, même rejoué ou republié sous une autre URL, pour ne pas lire deux fois la même chose.
48. En tant qu'Utilisateur, je veux que les liens des Articles soient débarrassés des paramètres de suivi et des fragments, mais restent cliquables, pour ouvrir la bonne page sans pistage inutile.
49. En tant que mainteneur, je veux que les liens relatifs d'un flux soient résolus par rapport à l'URL du flux, pour que chaque Article ait une URL absolue.
50. En tant qu'Utilisateur, je veux qu'un Extrait soit du texte sans HTML, entités décodées, tiré du contenu le plus complet du flux et plafonné, pour que les étapes suivantes travaillent sur du texte propre.
51. En tant qu'Utilisateur, je veux qu'un élément sans titre ou sans lien soit ignoré plutôt que complété, pour ne jamais lire un titre que l'éditeur n'a pas écrit.
52. En tant que mainteneur, je veux qu'un élément publié il y a plus de 30 jours ne soit pas inséré, pour qu'un flux ancien ne remplisse pas la base à la première Collecte.
53. En tant que mainteneur, je veux qu'une date absente ou illisible soit remplacée par la date de collecte, et qu'une date plus de 15 minutes dans le futur y soit ramenée, pour que chaque Article ait une date plausible.
54. En tant qu'Utilisateur, je veux qu'un Article purgé ne revienne jamais, même sans date et toujours présent dans le flux, pour ne pas le revoir chaque mois dans mon Briefing.

### Purge

55. En tant que mainteneur, je veux que les Articles collectés depuis plus de 30 jours soient purgés à chaque Exécution, en laissant une Trace de purge, pour respecter la Fenêtre de rétention.
56. En tant que mainteneur, je veux que les Traces de purge soient conservées 365 jours puis purgées, pour que la protection contre le retour d'un Article ne grossisse pas sans fin.
57. En tant que mainteneur, je veux que les Exécutions soient purgées après 90 jours, pour que la surveillance ne devienne pas de la mémoire.

## Décisions d'implémentation

### Ports du cœur

- **`HttpFetcher`** : chaque appel déclare son **usage** (flux, Page liée, page de l'agent) et l'adaptateur en déduit ses protections. Il reçoit les validateurs à envoyer et rend le statut, le corps, les nouveaux validateurs, l'URL finale et la présence d'une redirection permanente. Il est implémenté dans l'adaptateur de récupération web et injecté par la racine de composition dans le Connecteur, puisque les adaptateurs ne s'importent pas entre eux.
- **Connecteur** : lit les octets d'un flux et rend des Articles bruts (champs tels que le flux les donne) et le décompte des éléments illisibles, ou un refus avec sa cause. Le Connecteur RSS est le premier ; il appelle `HttpFetcher` avec l'usage « flux ».
- **Verrou d'Exécution** : un port pris au démarrage et relâché à la fin. Son adaptateur tient un verrou consultatif de session PostgreSQL sur une **connexion directe** dédiée, jamais par le pooler : en mode transaction, PgBouncer change de connexion serveur entre deux transactions, et un verrou de session n'y tient pas.
- **Dépôts** : Sources (lecture des Sources à collecter, synchronisation, validateurs, désactivation), Abonnements, Utilisateurs, Articles (insertion idempotente, purge), Traces de purge, Collectes, Exécutions.

### Exécution

Ordre : verrou, synchronisation du Catalogue, Collectes, purge, clôture.

- **Verrou pris** : aucune Exécution n'est créée ; le batch sort avec le code 0 et le résumé indique « Exécution précédente encore en cours ».
- **Résultat** :
  - `success` : toutes les Collectes ont réussi, y compris quand il n'y en a aucune ;
  - `partial` : au moins une Collecte a échoué et au moins une a réussi ;
  - `failed` + `collection` : toutes les Collectes ont échoué, et il y en avait au moins une ;
  - `failed` + `technical` : une exception hors Collecte ; l'Exécution est close en `failed` si c'est encore possible.
- **Anomalies** (`execution.anomalies`), qui ne changent pas le résultat :
  - `catalog_sync_blocked` (existante) ;
  - `no_source_to_collect` : aucune Source active n'a d'Abonnement ;
  - `source_deactivated` : une Source vient d'être désactivée pour échecs répétés ;
  - `feed_moved` : un flux a répondu par une redirection permanente, avec l'ancienne et la nouvelle URL.
- **Purge** : s'exécute même si les Collectes ont échoué.
- **Résumé** : écrit dans `$GITHUB_STEP_SUMMARY` quand la variable existe, et dans le journal sinon. Il donne le résultat, chaque Collecte (Source nommée par son `source_key`, Articles insérés, éléments illisibles, éléments exclus, erreur), les anomalies, les configs mises à jour par la synchronisation (information, pas anomalie) et la version d'expat. Une Exécution échouée techniquement affiche aussi la cause et l'erreur.
- **Code de sortie** : non nul si l'Exécution est `failed`, si une Source a été désactivée ou si la synchronisation est bloquée ; 0 dans tous les autres cas, `partial`, `feed_moved` et `no_source_to_collect` compris.

### Synchronisation du Catalogue

Les quatre règles de la spec 0001 restent valables. S'y ajoutent :

- Chaque bloc `[[source]]` est validé par le modèle de config de son Connecteur **avant** toute écriture. Une config invalide bloque toute la synchronisation (`catalog_sync_blocked`) : rien n'est appliqué.
- La synchronisation **met à jour `config`** d'une Source commune existante quand la config validée et normalisée diffère de celle en base. La comparaison porte sur les configs validées, pas sur le texte du TOML. La mise à jour vaut aussi pour une Source inactive, sans la réactiver, et reste soumise au seuil de blocage.
- Un changement de config n'est pas rétroactif : un motif d'exclusion ajouté ne retire pas les Articles déjà collectés.

### Config d'une Source RSS

- `feed_url` : **HTTPS obligatoire**, `http://` refusé à la validation.
- `exclude_url_patterns` (facultatif) : liste de sous-chaînes, sensibles à la casse, cherchées dans la `canonical_url` normalisée. Pas d'expressions régulières. Le `source_key` dépend seulement de `feed_url`.

### Collecte

- **Sources collectées** : les Sources actives qui ont au moins un Abonnement.
- **Parallélisme** : 8 Collectes à la fois au plus ; une seule requête à la fois par domaine. Pool de connexions SQLAlchemy dimensionné à 10 (8 Collectes, l'Exécution et une de marge).
- **Limites** : 30 s et 5 Mo par flux.
- **Requêtes conditionnelles** : les validateurs de la Source sont envoyés ; une réponse 304 est une Collecte réussie avec 0 Article. Les validateurs sont mis à jour à chaque réponse 200 et effacés si le serveur cesse de les envoyer.
- **Échec** : erreur réseau, délai dépassé, réponse non 2xx après redirections (429 et 503 compris, sans nouvel essai dans l'Exécution), redirection de HTTPS vers HTTP, refus du filtre préalable, flux illisible, ou flux dont les éléments sont tous illisibles.
- **Réussite** : flux vide, flux sans nouveauté, 304, flux dont tous les éléments sont exclus. Un élément exclu n'est jamais un élément illisible.
- **Transaction** : une par Collecte. La Collecte, ses Articles, `last_collected_at` et les validateurs sont enregistrés ensemble ou pas du tout. `last_collected_at` n'est mis à jour qu'en cas de réussite et ne sert pas de filtre.
- **Échecs répétés** : après 24 Collectes échouées d'affilée, comptées depuis l'historique des Collectes, la Source est désactivée (`repeated_failures`) et l'anomalie `source_deactivated` est inscrite. Seul `nexus-admin source reactivate` la rallume ; la synchronisation du Catalogue ne réactive que `removed_from_catalog`.

### Récupération web (`HttpFetcher`)

- User-Agent qui identifie Nexus et pointe vers le repo.
- HTTPS seulement ; toute redirection de HTTPS vers HTTP est refusée.
- robots.txt appliqué selon l'usage déclaré : à tout **sauf aux flux**.
- Une requête à la fois par domaine.
- Délai et taille maximale sont des **paramètres de l'adaptateur**, réglés par la configuration en production et à quelques millisecondes et kilo-octets dans les tests.

### Lecture d'un flux

**Filtre préalable**, sur les octets, avant toute analyse XML :
- refus de tout encodage qui n'est pas compatible avec l'ASCII, détecté par les premiers octets (BOM, `<?` en UTF-16 ou UTF-32, `<?xm` en EBCDIC) ou par l'encodage déclaré. Seuls passent l'ASCII, l'UTF-8, l'ISO-8859-* et le Windows-125x, ou l'absence de déclaration. Raison : feedparser décode le document avant de l'analyser, et une déclaration écrite dans un autre encodage échapperait à la recherche sur les octets. L'encodage déclaré est lu comme le fait feedparser, dans toute instruction `<?…?>` en tête du document ;
- refus de tout document contenant `<!DOCTYPE` ou `<!ENTITY`, sans tenir compte de la casse (l'analyseur tolérant de feedparser n'y est pas sensible), n'importe où, y compris dans un commentaire.

Le refus est une Collecte échouée avec une cause explicite. Aucun des flux vérifiés au cadrage n'a de DOCTYPE. Raison : feedparser ne résout jamais les entités externes, mais son propre filtre de DOCTYPE se contourne par un simple commentaire placé avant ; il ne reste alors contre le billion laughs que la limite d'amplification d'expat, qui dépend de la version liée à Python et coûte déjà environ une seconde et 100 Mo par flux avant d'interrompre l'analyse.

**Analyse** : feedparser lit les **octets** reçus par `HttpFetcher`, jamais une URL. RSS 2.0 et Atom.

**Élément lisible** : il a un titre et un lien. Le lien est le `link`, s'il mène à une URL `http` ou `https` une fois résolu par rapport à l'URL du flux ; à défaut, le `guid` s'il est une URL `http` ou `https`. Un élément sans titre ou sans lien est illisible : un lien `javascript:`, `data:` ou `ftp:` ne compte pas, car l'Article serait affiché comme un lien cliquable.

### Article brut → Article (normalisation dans le cœur)

- **`canonical_url`** :
  - lien relatif résolu par rapport à l'URL du flux ;
  - fragment retiré ;
  - paramètres de suivi retirés, d'après une liste fermée : `utm_*`, `xtor`, `fbclid`, `gclid`, `at_medium`, `at_campaign`… ;
  - schéma, `www` et casse du chemin conservés : l'URL est affichée et cliquée. Ce n'est pas la normalisation du `source_key`.
- **Exclusion** : un élément dont la `canonical_url` contient un motif de `exclude_url_patterns` est compté comme exclu et n'est pas inséré.
- **Extrait** :
  - HTML retiré ;
  - entités HTML décodées, y compris échappées deux fois ;
  - `content:encoded` (ou le contenu Atom) préféré à la description quand il est plus long ;
  - plafonné à environ 3 000 caractères ;
  - `excerpt_origin` = `source`.
- **Dates** :
  - `published_at` absente ou illisible : `collected_at` ;
  - plus de 15 minutes dans le futur : ramenée à `collected_at`.
- **Ancienneté** : un élément publié il y a plus de 30 jours (la Fenêtre de rétention) n'est pas inséré.
- **Empreinte** : SHA-256 du titre normalisé (minuscules, espaces réduits, ponctuation retirée), suivi des 500 premiers caractères normalisés de l'Extrait.
- **Page liée** : `linked_url` = `canonical_url`, `linked_page_status` = `pending`.
- **Déduplication** : un élément n'est pas inséré si (`source_id`, `canonical_url`) ou (`source_id`, `fingerprint`) existe déjà, ou si sa `canonical_url` ou son empreinte figure dans une Trace de purge de la même Source. Les éléments d'un flux ne sont jamais supposés triés par date.

### Purge

À chaque Exécution, même en échec de Collecte :

- les Articles dont `collected_at` a plus de 30 jours sont supprimés ; chacun laisse une **Trace de purge** (`source_id`, `canonical_url`, `fingerprint`, `purged_at`), sans contenu ;
- les Traces de purge de plus de 365 jours sont supprimées ;
- les Exécutions de plus de 90 jours sont supprimées, avec leurs Collectes ; les Compositions sont conservées (déjà prévu par `data-model.md`).

### Schéma

Deux migrations, chacune avec la mise à jour de `data-model.md` dans la même PR. La première :

- `source` : `http_etag` et `http_last_modified`, texte, facultatifs ;
- `app_user` : `handle`, texte, **UNIQUE**, au format `^[a-z0-9_-]{3,32}$` ;
- `article` : l'index (`source_id`, `fingerprint`) devient une contrainte **UNIQUE**, pour que l'écriture idempotente soit garantie par la base ;
- `article.linked_page_status` : nouvelle valeur `pending` ;
- nouvelle table `purged_article` : `id`, `source_id` (FK `source`), `canonical_url`, `fingerprint`, `purged_at`, avec index sur (`source_id`, `canonical_url`), sur (`source_id`, `fingerprint`) et sur `purged_at`. Table commune, sans donnée d'Utilisateur (ADR-0003).

La seconde, ajoutée avec l'analyse défensive (#14) : `source_collection.unreadable_count`, entier, défaut 0, pour que le décompte des éléments illisibles soit enregistré avec la Collecte.

### Administration (`nexus-admin`)

Nouveau point d'entrée en ligne de commande, déclaré comme script du paquet. Toutes ses sous-commandes sont idempotentes :

- **`user upsert --handle … --timezone … --briefing-hour …`** : fuseau validé comme nom IANA, heure entre 0 et 23 ;
- **`subscribe <handle> <source_key>`** : refuse un `source_key` inconnu ; accepte une Source inactive avec un avertissement ;
- **`unsubscribe <handle> <source_key>`** : ne fait rien si l'Abonnement n'existe pas ; refuse, comme `subscribe`, un handle ou un `source_key` inconnu, pour qu'une faute de frappe donne une erreur explicite plutôt qu'un succès silencieux ;
- **`source reactivate <source_key>`** ;
- **`source check <url>`** : télécharge le flux par `HttpFetcher` (usage « flux », mêmes protections) et l'analyse comme une Collecte. Il affiche les éléments lisibles, illisibles et exclus, les dates, les validateurs HTTP, les anomalies (`feed_moved`…) et la cause d'un refus. Il **n'ouvre aucune connexion à la base** : il est en lecture seule par construction.

### Catalogue initial

Dix flux, tous vérifiés le 16 octobre 2026 : HTTPS, XML valide, sans redirection, dates et liens absolus sur chaque élément.

| Thème | Source | URL | Remarque |
|---|---|---|---|
| Football | BBC Sport Football | `https://feeds.bbci.co.uk/sport/football/rss.xml` | sans validateurs ; éléments jusqu'à 2,5 mois |
| | RMC Sport Football | `https://rmcsport.bfmtv.com/rss/football/` | `exclude_url_patterns = ["_DN-"]` (fiches encyclopédiques re-datées) ; vidéos conservées |
| | Foot Mercato | `https://www.footmercato.net/flux-rss` | sans validateurs ; transferts |
| Tech | Numerama | `https://www.numerama.com/feed/` | |
| | The Verge | `https://www.theverge.com/rss/index.xml` | Atom ; ETag envoyé mais ignoré |
| | Ars Technica | `https://arstechnica.com/feed/` | |
| | Hacker News (hnrss) | `https://hnrss.org/frontpage` | dépendance temporaire, retirée à l'arrivée du Connecteur Hacker News |
| Sénégal | APS | `https://aps.sn/feed/` | flux général ; entités échappées deux fois |
| | Seneweb | `https://www.seneweb.com/feed` | préféré à Dakaractu (flux plus propre et plus fiable) |
| | RFI Afrique | `https://www.rfi.fr/fr/afrique/rss` | éléments non triés |

L'Équipe (protection anti-robots, contournée seulement par un endpoint non annoncé) et Maxifoot (HTTP seulement) ont été écartés : on ne contourne jamais une protection anti-robots, on remplace la Source.

### Invariants reportés dans `backend/AGENTS.md`

Pour qu'ils s'appliquent à tout futur Connecteur, et pas seulement à cette spec :
- HTTPS seulement et refus des redirections de HTTPS vers HTTP ;
- filtre préalable de tout XML collecté (encodage, DOCTYPE, ENTITY) ;
- robots.txt selon l'usage déclaré à `HttpFetcher` ;
- ne jamais contourner une protection anti-robots : on remplace la Source.

## Décisions de test

Un bon test vérifie un comportement observable par la couture (Articles enregistrés, Exécution et Collectes, code de sortie, résumé, requêtes émises), jamais la façon dont le code y parvient. Tous les flux de test sont **synthétiques**, écrits à la main : aucun contenu d'éditeur n'est commité dans ce repo public.

### Couture 1 : lecture d'un flux (unitaire, tableau de cas)

Le Connecteur RSS composé avec la normalisation du cœur : octets d'un flux et date de collecte en entrée ; Articles prêts à l'insertion, décomptes (illisibles, exclus) ou refus en sortie. Cas :
- RSS 2.0 et Atom ;
- `content:encoded` plus long que la description ;
- entités échappées deux fois ;
- liens relatifs ; paramètres de suivi et fragment ; `guid` sans lien ;
- éléments sans titre, sans lien, tous illisibles ;
- éléments exclus, ou tous exclus ;
- dates absentes, illisibles, dans le futur, plus vieilles que 30 jours ; éléments non triés ;
- filtre préalable : DOCTYPE et ENTITY en majuscules, en minuscules et dans un commentaire ; UTF-16 et UTF-32 par BOM et par déclaration ;
- XXE et billion laughs sur un flux **bien formé** et sur un flux **mal formé**, qui bascule sur l'analyseur tolérant.

### Couture 2 : `run_execution` (unitaire)

Couture existante (`test_pipeline`). Les tests assemblent le vrai Connecteur RSS, un faux `HttpFetcher` qui rend un flux synthétique, un statut et des en-têtes choisis, des dépôts en mémoire, `FakeClock`, un faux verrou et un Catalogue construit dans le test. Règles d'orchestration :
- **Résultats et anomalies** :
  - résultats `success`, `partial` et `failed` ;
  - `no_source_to_collect` ;
  - synchronisation bloquée sans arrêt des Collectes ;
  - `feed_moved`.
- **Sources collectées** : seulement les Sources actives qui ont un Abonnement.
- **Réussites sans Article** : une réponse 304 est une réussite ; une Collecte dont tous les éléments sont exclus est une réussite.
- **Déduplication** :
  - Collecte rejouée sur le même flux, sans doublon ;
  - republication sous une autre URL, écartée par l'empreinte ;
  - élément présent dans la Trace de purge, non réinséré, même sans date.
- **Désactivation** :
  - 23 échecs puis une réussite : rien ne se passe ;
  - 24 échecs : désactivation et anomalie.
- **Purge** :
  - s'exécute malgré des Collectes en échec ;
  - laisse une Trace ;
  - les Traces de plus de 365 jours et les Exécutions de plus de 90 jours disparaissent.
- **Configuration du Catalogue** :
  - mise à jour d'une config modifiée ;
  - config identique non réécrite ;
  - config invalide qui bloque la synchronisation ;
  - Source inactive mise à jour sans réactivation.
- **Validateurs HTTP** : envoyés, mis à jour, effacés.

### Couture 3 : adaptateur `HttpFetcher` (unitaire)

Derrière un transport HTTP simulé, sans réseau, avec délai et taille maximale injectés en millisecondes et kilo-octets :
- **HTTPS** : refus de `http://` et d'une redirection de HTTPS vers HTTP ;
- **limites** : délai dépassé, réponse trop grande ;
- **politesse** :
  - une requête à la fois par domaine ;
  - envoi des validateurs et du User-Agent ;
  - robots.txt appliqué à une Page liée et ignoré pour un flux ;
- **redirections** : 301 signalée, 302 non signalée.

### Couture 4 : dépôts et verrou (intégration contre PostgreSQL)

Comme les tests de dépôt existants :
- **dépôts** : chaque nouvelle méthode ;
- **contraintes** : les deux UNIQUE de `article` avec l'écriture idempotente, `purged_article`, la valeur `pending` et `app_user.handle` ;
- **migration** : son aller-retour (déjà en CI) ;
- **verrou** : sa logique contre le PostgreSQL de la CI, sans pooler. Une seconde connexion trouve le verrou pris ; il se libère à la fin, ou quand la connexion tombe.

Le test externe contre Neon (hors CI des PR) vérifie en plus que le verrou est pris par la **connexion directe**.

### Couture 5 : points d'entrée (intégration)

Comme les tests de points d'entrée existants :
- **`nexus-batch`** :
  - code de sortie non nul pour une Exécution `failed`, une Source désactivée ou une synchronisation bloquée ;
  - code 0 pour une Exécution `partial` ;
  - verrou pris : code 0 et ligne dans le résumé ;
  - contenu du résumé, version d'expat comprise.
- **`nexus-admin`** :
  - idempotence de `user upsert`, `subscribe` et `unsubscribe` ;
  - refus d'un `source_key` inconnu, par `subscribe` comme par `unsubscribe` ;
  - avertissement pour une Source inactive ;
  - `source reactivate` ;
  - `source check`, qui fonctionne sans aucune configuration de base de données.

## Hors périmètre

- **Enrichissement** : embeddings, Nature, résumé, Jugement « même événement », passerelle de modèles. C'est la spec suivante, avec le rattrapage.
- **Pages liées** : leur récupération (`pending` reste en l'état), robots.txt pour la page d'un Article RSS, et le sort du HTTP pour les Pages liées. À trancher dans la spec de l'enrichissement.
- **Autres Connecteurs** : Hacker News et Reddit.
- **Report automatique des Abonnements** quand un flux est déplacé : le mainteneur se réabonne à la main (voir Notes).
- **Déploiement** : workflow planifié du batch, publication de l'image, secrets de production, Grafana.
- **Authentification**, API et front pour les Abonnements.
- **Scores de pertinence, Compositions, Briefings.**

## Notes

- **Pour la spec Déploiement** :
  - ajouter un groupe de concurrence GitHub Actions au workflow du batch, en première barrière avant le verrou PostgreSQL ;
  - brancher l'alerte sur le code de sortie et le résumé définis ici.
- **Points ouverts « Avant l'ouverture à l'entourage »** (`data-model.md`) :
  - conditions d'utilisation des flux de chaque éditeur (déjà ajouté) ;
  - report des Abonnements quand un flux est déplacé, par exemple une entrée de Catalogue `replaces = "<ancien source_key>"`.
- **Glossaire mis à jour au cadrage** : la Page liée couvre la page d'un Article RSS ; nouveau terme **Trace de purge** (`purged_article`).
- **Aucun ADR** : aucune décision n'est à la fois difficile à défaire, surprenante et issue d'un vrai arbitrage.
- **Vérifications du cadrage** :
  - flux téléchargés le 16 octobre 2026 ;
  - feedparser 6.0.14 testé contre XXE et billion laughs ;
  - le Python 3.14 du projet embarque expat 2.9.0, mais l'expat de l'image Docker n'a pas été vérifié, d'où sa version dans le résumé.
