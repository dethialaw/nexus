# Front-end Nexus

Next.js (App Router), TypeScript `strict`, Tailwind, pnpm. Déployé sur Vercel.

## Vérifications avant une PR

```sh
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build
```

## Client d'API

- Les types et le client viennent de `src/lib/api/` (`openapi-typescript` + `openapi-fetch`), générés depuis l'OpenAPI du back-end. Un type d'API manquant se règle côté back-end, puis par `pnpm gen:api` ; la CI refuse un client périmé.
- Exception : le flux SSE du chat, dont le client est écrit à la main.

## Contenu collecté

Titres, résumés, Synthèses, Citations et réponses de l'agent sont des données non fiables : rends-les comme texte React. Les liens externes portent `rel="noopener noreferrer nofollow"`.

## Affichage, d'après `CONTEXT.md`

- Chaque information garde sa Nature visible (Officiel, Factuel, Rumeur, Opinion, Inconnu).
- « Aussi couvert par » indique une couverture, jamais une confirmation : formule-le ainsi.
- Une Entrée montre l'Intérêt qui l'explique.
- Un Briefing vide dit pourquoi : journée calme (Normal), Collecte partielle (Sources en échec nommées) ou Échec.

## Variables d'environnement

Seules les variables `NEXT_PUBLIC_*` atteignent le navigateur : elles ne contiennent que des valeurs publiques (URL de l'API). Toute variable va aussi dans `.env.example`.
