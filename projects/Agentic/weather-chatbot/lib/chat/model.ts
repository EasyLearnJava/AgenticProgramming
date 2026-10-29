/*
 * lib/chat/model.ts: the chat model: Gemini, through @ai-sdk/google, with the key from GOOGLE_API_KEY. The one file to
 * change for another model, or for Vercel AI Gateway.
 */
import "server-only";
import { createGoogleGenerativeAI } from "@ai-sdk/google";
import type { LanguageModel } from "ai";
import { type Config, config } from "@/lib/config";
import { ConfigError } from "@/lib/errors";

/**
 * The model the chat uses. Without a key it throws ConfigError, so the page can say the chat isn't set up: the Gemini
 * provider itself would only fail at the first call, and would look for another variable, GOOGLE_GENERATIVE_AI_API_KEY.
 */
export function getChatModel(chat: Config["chat"] = config.chat): LanguageModel {
  if (chat.googleApiKey === undefined) {
    throw new ConfigError("GOOGLE_API_KEY isn't set.");
  }
  return createGoogleGenerativeAI({ apiKey: chat.googleApiKey })(chat.model);
}
