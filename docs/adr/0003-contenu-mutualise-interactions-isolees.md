# Contenu mutualisé, interactions isolées

Les Sources communes et leurs Articles (avec résumés, Nature et embeddings) sont partagés entre tous les Utilisateurs : une Source n'est collectée et traitée qu'une fois, ce qui compte avec un quota de stockage gratuit. Tout ce qui révèle les centres d'intérêt de quelqu'un (Profil, Scores de pertinence, Briefings, Signaux, Conversations) reste propre à chaque Utilisateur, et rien de privé n'entre jamais dans un objet commun : la Source issue d'un compte connecté appartient à son seul propriétaire, comme les Articles qu'elle produit.

## Considered Options

- **Tout par Utilisateur** (chaque Utilisateur a ses propres Sources et Articles) : écarté, car une même Source serait collectée, résumée et vectorisée autant de fois qu'elle a d'abonnés, ce que le quota de stockage et le budget LLM ne permettent pas.
- **Mutualiser aussi les interactions** (Signaux, Conversations ou popularité interne partagés pour améliorer la sélection) : écarté, car ces données révèlent les centres d'intérêt de chacun et finiraient par influencer ce que voient les autres.
- **Contenu mutualisé, interactions isolées** (retenu).

## Consequences

- Les Candidats d'un Utilisateur sont restreints aux Sources auxquelles il est abonné : sinon les Abonnements des autres influenceraient ce qu'il voit, ce qui fuiterait indirectement leurs intérêts. « Aussi couvert par » en est plus pauvre, c'est assumé.
- Aucune fonctionnalité ne s'appuie sur l'activité des autres Utilisateurs (« les autres lecteurs ont aussi aimé ») ; la popularité, par exemple pour une future Entrée d'exploration, vient uniquement des signaux de la Source (points HN, votes Reddit).
