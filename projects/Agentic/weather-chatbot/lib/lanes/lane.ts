/*
 * lib/lanes/lane.ts: what an open lane gives the chat: the tools the model sees, and how to close the lane once the
 * answer ends, however it ends.
 */
import "server-only";
import type { ToolSet } from "ai";
import type { LiveLaneId } from "@/lib/types";

/** An open lane. `close` runs once the answer ends; a REST lane has nothing to close. */
export type Lane = {
  id: LiveLaneId;
  tools: ToolSet;
  close: () => Promise<void>;
};
