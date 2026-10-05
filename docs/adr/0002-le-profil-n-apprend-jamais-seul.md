# Le Profil d'intérêts n'apprend jamais tout seul

Les Signaux (Ouverture, Pas intéressé) sont enregistrés mais ne modifient jamais le Profil d'intérêts. Seule une action explicite de l'Utilisateur le change, chaque fois tracée dans le Journal du Profil avec son origine. Nexus existe pour rendre la personnalisation transparente et corrigeable : un ajustement automatique des poids d'après les clics recréerait l'opacité, et la boucle d'engagement, des algorithmes qu'on fuit.

## Considered Options

- **Ajustement automatique des poids** (l'approche habituelle des systèmes de recommandation) : écarté, car l'Utilisateur ne saurait plus pourquoi son Profil a changé.
- **Signaux enregistrés + corrections explicites** (retenu) : au MVP, « Pas intéressé » propose un raccourci (« Baisser l'Intérêt PSG ? » / « Non, juste cet article ») ; plus tard, des Suggestions calculées à partir des Signaux, toujours soumises à validation.

## Consequences

- Ne pas ajouter de « boucle d'apprentissage » sur les Signaux qui écrirait dans le Profil : c'est un choix délibéré, pas un oubli.
