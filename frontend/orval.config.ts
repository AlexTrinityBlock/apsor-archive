import { defineConfig } from "orval";

const spec = process.env.VITE_OPENAPI_SPEC ?? "./openapi.json";

/**
 * Generates typed React Query hooks from the committed FastAPI schema.
 *
 * `openapi.json` is exported by `backend/script/export_openapi.py`. To regenerate
 * from a running backend, set VITE_OPENAPI_SPEC to its `/openapi.json` URL:
 *
 *   VITE_OPENAPI_SPEC=http://127.0.0.1:8000/openapi.json bun run api:generate:live
 *
 * The generated client is committed so a fresh clone and the production image
 * build without a backend available. `make api-check` catches contract drift.
 */
export default defineConfig({
  "apsor-archive": {
    input: {
      target: spec,
    },
    output: {
      // tags-split turns this directory into one file per OpenAPI tag.
      target: "./src/app/generated-apis-types/",
      schemas: "./src/app/generated-apis-types/schemas",
      mode: "tags-split",
      client: "react-query",
      httpClient: "fetch",
      mock: false,
      clean: true,
      override: {
        mutator: {
          path: "./src/apis/fetch-client.ts",
          name: "apiFetch",
        },
        fetch: {
          // Hooks resolve to the response payload instead of a { status, data }
          // union, keeping page-level callsites compact.
          includeHttpResponseReturnType: false,
        },
      },
    },
  },
});
