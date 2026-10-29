/*
 * vitest.config.ts: the unit tests' settings: where they live, and the same @/ alias as the app.
 */
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      // ① The same @/ alias as tsconfig.json.
      "@": import.meta.dirname,
      // ② The server-only package throws outside Next.js's server build, so tests get an empty stand-in.
      "server-only": path.join(import.meta.dirname, "tests/stubs/server-only.ts"),
    },
  },
  test: {
    // ③ The unit tests, in tests/unit/, run in Node.
    include: ["tests/unit/**/*.test.ts"],
    environment: "node",
  },
});
