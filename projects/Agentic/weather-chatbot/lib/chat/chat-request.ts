/*
 * lib/chat/chat-request.ts: what POST /api/chat accepts, checked before any work: at most 20 messages, each of yours at
 * most 2,000 characters and the whole history at most 200,000, only the parts the page sends, tool calls with valid
 * input, a live lane, a real language tag, and messages in AI SDK's shape.
 */
import "server-only";
import { safeValidateUIMessages, type ToolSet } from "ai";
import { z } from "zod";
import { LIVE_LANE_IDS, MAX_HISTORY_CHARS, MAX_MESSAGE_CHARS, MAX_MESSAGES } from "@/lib/constants";
import { InputError } from "@/lib/errors";
import type { ChatMessage, LiveLaneId } from "@/lib/types";
import { OPEN_METEO_TOOLS } from "@/lib/weather/open-meteo-tools";

const MAX_CHAT_ID_CHARS = 100;
const MAX_LOCALE_CHARS = 35;

/** Whether a lane id is one that answers for real. */
function isLiveLaneId(laneId: string): laneId is LiveLaneId {
  return (LIVE_LANE_IDS as readonly string[]).includes(laneId);
}

/** Whether a string is a language tag, such as "en-US", as Intl reads it; anything else (words, new lines) isn't. */
function isLanguageTag(locale: string): boolean {
  try {
    return Intl.getCanonicalLocales(locale).length === 1;
  } catch {
    return false;
  }
}

// ① The body useChat sends: the chat's id and messages, plus what the page adds: the lane, and the browser's locale,
// which goes into the system prompt, so it must be a language tag and nothing else.
const ChatRequestSchema = z.object({
  id: z.string().min(1).max(MAX_CHAT_ID_CHARS),
  messages: z.array(z.unknown()).min(1).max(MAX_MESSAGES),
  laneId: z.string().refine(isLiveLaneId),
  locale: z.string().max(MAX_LOCALE_CHARS).refine(isLanguageTag).optional(),
});

// When a message was written: shown beside it, so a message without it still goes through.
const MetadataSchema = z.object({ createdAt: z.number(), isCutShort: z.boolean().optional() }).optional();

// Our tools' input schemas: a tool call in the history is checked as a new one would be.
const TOOL_INPUTS: ToolSet = Object.fromEntries(
  Object.values(OPEN_METEO_TOOLS).map((tool) => [tool.name, { inputSchema: tool.inputSchema }]),
);

// The parts the page sends back: your text, and the bot's text, steps and tool calls. Never files, or anything else.
const SENT_PART_TYPES: ReadonlySet<string> = new Set([
  "text",
  "step-start",
  ...Object.keys(OPEN_METEO_TOOLS).map((name) => `tool-${name}`),
]);

/** What to tell the user when the body's own fields break a rule, by the field that broke it. */
const RULE_BY_FIELD: Readonly<Record<string, string>> = {
  messages: `a chat can carry 1 to ${MAX_MESSAGES} messages.`,
  laneId: "that lane isn't live yet.",
  locale: "the browser's language isn't a language tag.",
};

export type ChatRequest = { messages: ChatMessage[]; laneId: LiveLaneId; locale: string | undefined };

/** The text of a message, its text parts joined. */
function toMessageText(message: ChatMessage): string {
  return message.parts.map((part) => (part.type === "text" ? part.text : "")).join("");
}

/** Checks a chat request's body; throws InputError, saying which rule it breaks. */
export async function parseChatRequest(body: unknown): Promise<ChatRequest> {
  // ② The body's own fields: the number of messages, the lane, the locale.
  const parsed = ChatRequestSchema.safeParse(body);
  if (!parsed.success) {
    const field = String(parsed.error.issues[0]?.path[0]);
    throw new InputError(RULE_BY_FIELD[field] ?? "the request isn't one the chat understands.");
  }
  // ③ The whole history's size: everything in it goes to the model.
  if (JSON.stringify(parsed.data.messages).length > MAX_HISTORY_CHARS) {
    throw new InputError("the chat is too long. Start a new chat.");
  }
  // ④ The messages themselves, in AI SDK's shape, with each tool call's input checked against its tool.
  const validated = await safeValidateUIMessages<ChatMessage>({
    messages: parsed.data.messages,
    metadataSchema: MetadataSchema,
    tools: TOOL_INPUTS,
  });
  if (!validated.success) {
    throw new InputError("its messages aren't in the shape the chat sends.");
  }
  const messages = validated.data;
  // ⑤ Only yours and the bot's, with only the parts the page sends, ending with yours.
  if (messages.some((message) => message.role !== "user" && message.role !== "assistant")) {
    throw new InputError("its messages can only be yours and the bot's.");
  }
  if (messages.some((message) => message.parts.some((part) => !SENT_PART_TYPES.has(part.type)))) {
    throw new InputError("its messages carry parts the chat doesn't send.");
  }
  if (messages.at(-1)?.role !== "user") {
    throw new InputError("the last message must be yours.");
  }
  // ⑥ None of yours is empty, or over 2,000 characters.
  const yours = messages.filter((message) => message.role === "user").map(toMessageText);
  if (yours.some((text) => text.length > MAX_MESSAGE_CHARS)) {
    throw new InputError(`a message can be at most ${MAX_MESSAGE_CHARS.toLocaleString("en-US")} characters.`);
  }
  if (yours.some((text) => text.trim() === "")) {
    throw new InputError("a message can't be empty.");
  }
  return { messages, laneId: parsed.data.laneId, locale: parsed.data.locale };
}
