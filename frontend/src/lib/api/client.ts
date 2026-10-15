import createClient from "openapi-fetch";

import type { paths } from "./schema";

export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000",
  // Look `fetch` up on each call rather than once at import, so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
});
