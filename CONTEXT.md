# Nexus

Assistant de veille personnel : il collecte des contenus sur le web selon le profil d'intérêts de l'utilisateur et lui livre chaque jour une sélection finie, résumée et sourcée.

Le domaine se dit en français, le code s'écrit en anglais : chaque terme indique son nom de code (`_Code_`), à utiliser tel quel pour les classes, tables et variables.

## Language

### Ingestion

De la Source à l'Article : Connecteurs, Sources, Collectes et Exécutions. Le titre de cette section n'est pas un terme ; son nom de code (`ingestion`) désigne la section dans le code, tandis que la Collecte reste la lecture d'une Source.

**Connecteur**:
Un type de provenance que Nexus sait lire (RSS, Hacker News, Reddit, plus tard X).
_Code_: `connector`
_Avoid_: plugin, intégration

**Source**:
Une instance configurée d'un Connecteur (le flux RSS du Monde, r/python), active ou inactive, qui mémorise sa date de dernière collecte. Commune à tous les Utilisateurs, sauf la Source issue d'un compte connecté, qui est privée à son propriétaire. Une Source sans Abonnement n'est pas collectée ; seuls le mainteneur, ou le système après plusieurs Collectes échouées d'affilée (avec alerte au mainteneur), la rendent inactive.
_Code_: `source`
_Avoid_: flux, fil, compte

**Abonnement**:
Le lien par lequel un Utilisateur suit une Source.
_Code_: `subscription`
_Avoid_: suivi, follow

**Catalogue de Sources**:
La liste des Sources communes proposées à l'Utilisateur pour s'abonner, entretenue par le mainteneur de Nexus, avec la liste des Sources qu'il en a retirées.
_Code_: `source_catalog`
_Avoid_: annuaire, registre

**Article brut**:
Ce que renvoie un Connecteur, tel quel, avant normalisation.
_Code_: `raw_article`
_Avoid_: item, RawItem, contenu

**Article**:
Une publication unique, issue d'une seule Source, normalisée et dédupliquée ; commune à tous les Utilisateurs et conservée seulement pendant la Fenêtre de rétention.
_Code_: `article`
_Avoid_: item, élément, contenu, post

**Page liée**:
La page web vers laquelle pointe un Article (le lien d'un post HN ou Reddit, ou la page de l'article lui-même pour un Article RSS), récupérée une seule fois et sur un seul niveau pour en compléter l'Extrait.
_Code_: `linked_page`
_Avoid_: lien externe, cible

**Extrait**:
Le texte normalisé et plafonné conservé pour un Article, tiré de la Source et, s'il y en a une, de sa Page liée. Comme tout contenu collecté, c'est une donnée, jamais une instruction.
_Code_: `excerpt`
_Avoid_: contenu, corps, texte intégral

**Fenêtre de rétention**:
La durée (30 jours) pendant laquelle un Article est conservé avant d'être purgé.
_Code_: `retention_window`
_Avoid_: TTL, durée de vie

**Trace de purge**:
Ce qui reste d'un Article après sa purge : de quoi le reconnaître, sans aucun contenu, conservé un an pour qu'un élément encore présent dans le flux de sa Source ne soit jamais collecté de nouveau.
_Code_: `purged_article`
_Avoid_: tombstone, archive

**Exécution**:
Un lancement du batch, avec son heure, son résultat et, en cas d'échec, sa cause (technique ou collecte). Elle est conservée même quand le Briefing qu'elle a raté est remplacé.
_Code_: `execution`
_Avoid_: run, job, tâche

**Collecte**:
La lecture d'une Source au cours d'une Exécution, réussie ou échouée.
_Code_: `source_collection`
_Avoid_: fetch, synchronisation

**Histoire** _(hors MVP)_:
Une entité durable regroupant plusieurs Articles traitant du même événement.
_Code_: `story`
_Avoid_: sujet, cluster

### Qualification

**Nature**:
Le caractère d'un Article, choisi dans une échelle fermée : Officiel, Factuel, Rumeur, Opinion ou Inconnu, avec une confiance associée.
_Code_: `nature`
_Avoid_: type, catégorie

**Officiel**:
Émis par l'entité concernée elle-même (communiqué, compte officiel d'un club ou d'un ministère).
_Code_: `official`

**Factuel**:
Compte rendu journalistique de faits vérifiables.
_Code_: `factual`

**Rumeur**:
Information présentée comme non confirmée.
_Code_: `rumor`

**Opinion**:
Point de vue ou analyse de l'auteur.
_Code_: `opinion`
_Avoid_: analyse, tribune

**Inconnu**:
Nature retenue quand la qualification n'est pas assez sûre.
_Code_: `unknown`

**Jugement « même événement »**:
La réponse, avec sa probabilité, à la question « ces deux Articles traitent-ils du même événement ? ». C'est une propriété du contenu : établie une seule fois par paire d'Articles, commune à tous les Utilisateurs.
_Code_: `same_event_judgment`
_Avoid_: doublon, similarité

### Profil

**Utilisateur**:
La personne pour qui Nexus fait la veille, rattachée à un fuseau horaire ; tout ce qui révèle ses centres d'intérêt (Profil, Scores de pertinence, Briefings, Signaux, Conversations) lui est propre et n'est jamais mutualisé.
_Code_: `user`
_Avoid_: compte, client

**Profil d'intérêts**:
L'ensemble des Intérêts d'un utilisateur, toujours consultable et corrigeable par lui.
_Code_: `interest_profile`
_Avoid_: préférences, persona, profil déclaré

**Journal du Profil**:
L'historique daté de chaque création, modification ou suppression d'Intérêt, avec son origine (action directe, onboarding, « via pas intéressé »…), qui permet de reconstituer le Profil d'intérêts à n'importe quelle date et de savoir pourquoi il a changé. Chacune de ses lignes est une version d'Intérêt.
_Code_: `interest_version` (une ligne du Journal)
_Avoid_: historique, audit

**Intérêt**:
Un libellé libre, précisé par une description et pondéré, qui décrit une chose que l'utilisateur veut suivre (« Ballon d'Or », « Python async »). Il garde son identité quand l'Utilisateur le modifie ; chaque modification en crée une nouvelle version dans le Journal du Profil. Nexus ne décide jamais qu'un Intérêt modifié en est devenu un autre.
_Code_: `interest`
_Avoid_: thème, sujet, tag, catégorie

**Score de pertinence**:
Le degré de correspondance entre un Article et une version d'Intérêt pondérée ; il est conservé pour chaque Intérêt afin de justifier pourquoi un Article est montré.
_Code_: `relevance_score`
_Avoid_: score, note

**Pertinence globale**:
Le plus élevé des Scores de pertinence d'un Article pour un Utilisateur ; l'Intérêt qui l'atteint est celui qui explique la présence de l'Article.
_Code_: `overall_relevance`
_Avoid_: score final, score total

**Signal**:
Une réaction enregistrée de l'Utilisateur à une Entrée, qui ne modifie jamais le Profil d'intérêts à elle seule. Au MVP : Ouverture ou Pas intéressé.
_Code_: `signal` (`opened`, `not_interested`)
_Avoid_: feedback, clic, événement

**Pas intéressé**:
Le Signal par lequel l'Utilisateur rejette une Entrée ; il peut viser l'Article seul ou, sur confirmation explicite, conduire à baisser l'Intérêt qui l'explique.
_Code_: `not_interested`
_Avoid_: dislike, masquer

**Engagement**:
Ce que les Signaux révèlent des intérêts réels d'un Utilisateur, mesuré par version d'Intérêt (ouvertures rapportées aux Entrées attribuées) et affiché seulement au-delà d'un nombre minimal d'Entrées.
_Code_: `engagement`
_Avoid_: profil d'engagement, taux de clic

**Exposition** _(hors MVP)_:
Ce à quoi un Utilisateur est exposé sur ses comptes connectés.
_Code_: `exposure`
_Avoid_: profil d'exposition

**Miroir**:
La vue qui compare le Profil d'intérêts à l'Engagement, puis plus tard à l'Exposition.
_Code_: `mirror`
_Avoid_: profil comparé

**Suggestion** _(hors MVP)_:
Une proposition de modification du Profil d'intérêts, tirée des Signaux, que l'Utilisateur accepte ou refuse.
_Code_: `suggestion`
_Avoid_: recommandation

### Livraison

**Briefing**:
L'instantané fini (de 0 à 15 Entrées, sans minimum à atteindre) livré une fois par jour local de l'Utilisateur, qui ne dépend d'aucune donnée pouvant changer ou disparaître. Il est définitif dès sa création, sauf en Échec, où il peut être remplacé le même jour.
_Code_: `briefing`
_Avoid_: digest, fil, newsletter

**Composition**:
La construction du Briefing d'un Utilisateur au cours d'une Exécution, réussie ou échouée, avec sa cause ; elle est conservée même quand le Briefing est remplacé.
_Code_: `briefing_composition`
_Avoid_: génération, build

**État du Briefing**:
Distingue un Briefing vide parce que la journée était calme d'un Briefing vide parce que la collecte a échoué : Normal, Collecte partielle ou Échec.
_Code_: `briefing_status` (`normal`, `partial`, `failed`)
_Avoid_: statut

**Collecte partielle**:
État d'un Briefing composé alors que certaines Sources de l'Utilisateur ont échoué ; il nomme ces Sources, et seulement celles auxquelles l'Utilisateur est abonné.
_Code_: `partial`

**Échec**:
État d'un Briefing qui n'a pas pu être composé, pour une cause technique ou parce qu'aucune Source n'a répondu ; il ne contient aucune Entrée.
_Code_: `failed`

**Candidat**:
Un Article pouvant entrer dans le Briefing ou les réponses d'un Utilisateur : il provient d'une Source à laquelle l'Utilisateur est abonné au moment du calcul. Pour le Briefing, il doit en plus appartenir à la Fenêtre du Briefing.
_Code_: `candidate`

**Fenêtre du Briefing**:
Les Articles collectés depuis le dernier Briefing qui n'est pas en Échec (sur trois jours au plus) et publiés depuis moins de 48 heures. Un Article non retenu dans sa fenêtre ne revient jamais dans un Briefing ultérieur.
_Code_: `briefing_window`
_Avoid_: période, file d'attente

**Synthèse**:
Le court texte d'ouverture d'un Briefing, tiré uniquement de ses Entrées, qui conserve la Nature de chaque information reprise ; absent quand le Briefing a trop peu d'Entrées.
_Code_: `synthesis`
_Avoid_: résumé, intro, chapô

**Entrée**:
Une ligne du Briefing : la copie de ce qu'il faut retenir d'un Article (titre, résumé, lien, nom de la Source, Nature, embedding). Un Article ne donne lieu qu'à une seule Entrée par Utilisateur, tous Briefings confondus. Elle copie aussi le libellé de l'Intérêt qui l'explique et garde la version de cet Intérêt. Chaque Entrée vaut impression, dénominateur des Signaux, et garde son rang dans le Briefing ; les Entrées sont groupées par Intérêt explicatif.
_Code_: `entry`
_Avoid_: élément, item, impression

**Aussi couvert par**:
La liste copiée dans une Entrée des autres Sources dont les Articles ont été écartés par la Règle de diversité. Elle indique une couverture, jamais une confirmation.
_Code_: `also_covered_by`
_Avoid_: confirmé par, sources concordantes

**Règle de diversité**:
La décision ponctuelle, prise à la Composition, de ne garder que le plus pertinent de deux Candidats traitant du même événement d'après leur Jugement « même événement ». Elle ne crée aucune entité durable, contrairement à l'Histoire.
_Code_: `diversity_rule`

**Entrée d'exploration** _(hors MVP)_:
Une Entrée étiquetée comme telle, choisie hors du Profil d'intérêts pour sa popularité dans sa Source (points, votes), jamais d'après l'activité des autres Utilisateurs.
_Code_: `exploration_entry`

### Conversation

**Conversation**:
Un échange de questions et de réponses entre un Utilisateur et l'agent, conservé dans son historique.
_Code_: `conversation`
_Avoid_: chat, session, discussion

**Citation**:
La copie (titre, lien, nom de la Source ou du site) d'un Article ou d'une page suivie par l'agent, sur lequel s'appuie une réponse de Conversation. Une page suivie par l'agent ne devient jamais un Article.
_Code_: `citation`
_Avoid_: référence, source

**Mémoire longue**:
L'ensemble des Briefings passés d'un Utilisateur, seul souvenir de ce qui a existé au-delà de la Fenêtre de rétention ; l'agent l'interroge par similarité.
_Code_: `long_term_memory`
