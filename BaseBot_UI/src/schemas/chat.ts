import { z } from "zod";
import { MAX_MESSAGE_LENGTH } from "@/lib/constants";

export const chatMessageSchema = z
  .string()
  .trim()
  .min(1, "Type a message first.")
  .max(MAX_MESSAGE_LENGTH, `Messages can be at most ${MAX_MESSAGE_LENGTH} characters.`);

export const workspaceChatSchema = z.object({
  message: chatMessageSchema,
  conversation_history: z
    .array(z.object({ role: z.enum(["user", "assistant"]), content: z.string() }))
    .optional(),
});

export const agentChatSchema = z.object({
  message: chatMessageSchema,
  conversation_id: z.string().optional(),
});

export const sourceSchema = z.object({
  filename: z.string(),
  chunk_index: z.number(),
});

export const sourcesSchema = z.array(sourceSchema);

export const agentChatResponseSchema = z.object({
  conversation_id: z.string(),
  answer: z.string(),
  sources: sourcesSchema,
  model_used: z.string(),
});

export const workspaceChatResponseSchema = z.object({
  answer: z.string(),
  sources: sourcesSchema,
  conversation_history: z.array(
    z.object({ role: z.enum(["user", "assistant"]), content: z.string() }),
  ),
});

export const conversationSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  title: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const conversationListSchema = z.array(conversationSchema);

export const messageSchema = z.object({
  id: z.string(),
  conversation_id: z.string(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  sources: sourcesSchema.nullable(),
  created_at: z.string(),
});

export const conversationThreadSchema = z.object({
  conversation: conversationSchema,
  messages: z.array(messageSchema),
});