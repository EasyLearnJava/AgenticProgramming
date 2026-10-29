/*
 * vitest.evals.config.ts: the golden questions' settings: they ask a running deployment's /api/chat, so the real model
 * answers, one question at a time.
 */
import { defineConfig } from "vitest/config";

const EVAL_TIMEOUT_MS = 120_000;

export default defineConfig({
  resolve: { alias: { "@": import.meta.dirname } },
  test: {
    include: ["tests/evals/**/*.eval.ts"],
    environment: "node",
    testTimeout: EVAL_TIMEOUT_MS,
    fileParallelism: false,
  },
});
