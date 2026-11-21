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
  source_url: z.string().nullable().optional(),
});

export const sourcesSchema = z.array(sourceSchema);

export const actionFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.enum([
    "short_text",
    "long_text",
    "email",
    "phone",
    "number",
    "select",
    "boolean",
    "date",
  ]),
  required: z.boolean(),
  max_length: z.number().optional(),
  options: z.array(z.string()).optional(),
  placeholder: z.string().optional(),
  help_text: z.string().optional(),
});

export const actionFormSchema = z.object({
  kind: z.literal("action_form"),
  action_id: z.string(),
  action_type: z.enum([
    "lead_capture",
    "data_collection",
    "custom_forms",
    "knowledge_support",
  ]),
  title: z.string(),
  description: z.string(),
  fields: z.array(actionFieldSchema),
  require_consent: z.boolean(),
  consent_text: z.string().nullable().optional(),
  submit_label: z.string(),
});

export const agentChatResponseSchema = z.object({
  conversation_id: z.string(),
  answer: z.string(),
  sources: sourcesSchema,
  model_used: z.string(),
  actions: z
    .array(
      z.object({
        type: z.string(),
        action_type: z.string().optional(),
        label: z.string().optional(),
        id: z.string().optional(),
        errors: z.array(z.string()).optional(),
        status: z.string().optional(),
      }),
    )
    .optional(),
  action_form: actionFormSchema.nullable().optional(),
});

export const publicAgentInfoSchema = z.object({
  name: z.string(),
  description: z.string().nullable(),
  language: z.string(),
  welcome_message: z.string(),
  icon_url: z.string().url().nullable(),
});

export const publicChatResponseSchema = z.object({
  answer: z.string(),
  sources: sourcesSchema,
  conversation_id: z.string(),
  actions: z
    .array(z.object({ type: z.string().nullable(), label: z.string().nullable() }))
    .optional(),
  action_form: actionFormSchema.nullable().optional(),
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