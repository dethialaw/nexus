# Modèle d'embeddings dans le cloud, figé et recalculable

Tous les vecteurs (Articles, Intérêts, questions du chat, Entrées) sont produits par `gemini-embedding-2` en 768 dimensions, sans modèle local : la machine de développement (M1, 8 Go) ne fait pas partie de l'infrastructure. Le modèle est multilingue (contenus en français et en anglais), stable, couvert par l'offre gratuite, normalise lui-même les vecteurs tronqués, et c'est le plus récent de la gamme, donc celui dont le retrait est le plus lointain. Chaque vecteur porte son `embedding_model` et son `embedding_kind` (document ou requête), et deux vecteurs dont le modèle diffère ne sont jamais comparés.

## Considered Options

- **Modèle local via Ollama** : écarté, Nexus ne doit pas dépendre de la machine de son auteur.
- **`gemini-embedding-001`** : écarté, il n'apparaît plus dans la grille tarifaire et exige une normalisation manuelle pour toute dimension autre que 3072, source de bug silencieux. Repli possible, avec normalisation couverte par un test.
- **1536 ou 3072 dimensions** : écarté, le stockage (Articles, Entrées et leurs index) est contraint par le quota de 0,5 Go.

## Consequences

- Le fournisseur peut retirer le modèle. Les Articles se recalculent d'eux-mêmes en 30 jours de rétention ; la Mémoire longue reste recalculable car chaque Entrée copie son titre et son résumé (ADR-0001). Changer de modèle = migration explicite de tous les vecteurs, jamais un mélange.
- La dimension 768 est inscrite dans le type des colonnes `vector(768)` : la changer est une migration de schéma.
- Avant toute ouverture à des Utilisateurs de l'EEE, tous les appels Gemini passent sur l'offre payante (conditions de l'API) ; au tarif actuel de 0,20 $ par million de tokens, le coût reste de l'ordre de quelques dollars par mois.
