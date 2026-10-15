import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // frontend/AGENTS.md is maintained by hand: `next dev` must not rewrite it.
  agentRules: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
