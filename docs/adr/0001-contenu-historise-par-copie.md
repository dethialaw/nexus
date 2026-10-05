# Tout contenu historisé est un instantané par copie

Les Articles sont purgés à la fin de la fenêtre de rétention, imposée par le quota de stockage gratuit. Les Briefings et les Conversations, eux, sont conservés indéfiniment. Plutôt que de faire référence aux Articles, chaque Entrée de Briefing, sa mention « Aussi couvert par » et chaque Citation de Conversation **copient** ce qu'il faut afficher : titre, résumé, lien, nom de la Source et, pour l'Entrée, l'embedding de l'Article. Un instantané ne doit dépendre de rien qui puisse changer ou disparaître.

## Considered Options

- **La purge épargne les Articles cités** : écarté, car le stockage commun grossirait indéfiniment avec l'historique de chaque Utilisateur et la purge deviendrait conditionnelle.
- **Copie** (retenu) : duplication assumée, d'environ 11 Mo par an et par Utilisateur pour les embeddings.

## Consequences

- La duplication entre Article et Entrée est voulue : ne pas la « normaliser ».
- Les Briefings passés constituent la Mémoire longue, interrogeable par similarité par l'agent au-delà de la fenêtre de rétention.
