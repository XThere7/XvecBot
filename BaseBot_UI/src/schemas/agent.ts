import { z } from "zod";
import {
  DEFAULT_LANGUAGE,
  DEFAULT_MODEL,
  DEFAULT_TEMPERATURE,
  MAX_DESCRIPTION_LENGTH,
  MAX_NAME_LENGTH,
} from "@/lib/constants";
import { LANGUAGES, MODELS } from "@/lib/reference-data";

const modelValues = MODELS.map((m) => m.value) as [string, ...string[]];
const languageValues = LANGUAGES as unknown as [string, ...string[]];

export const agentSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Give the agent a name.")
    .max(MAX_NAME_LENGTH, `Keep the name under ${MAX_NAME_LENGTH} characters.`),
  description: z
    .string()
    .max(MAX_DESCRIPTION_LENGTH, `Keep the description under ${MAX_DESCRIPTION_LENGTH} characters.`)
    .optional()
    .or(z.literal("")),
  system_prompt: z
    .string()
    .trim()
    .min(1, "Describe how the agent should behave."),
  welcome_message: z
    .string()
    .max(500, "The welcome message can be at most 500 characters.")
    .optional()
    .or(z.literal("")),
  model: z.enum(modelValues, {
    errorMap: () => ({ message: "Choose one of the listed models." }),
  }),
  // The backend soft-clamps; the UI clamps too so the two never disagree.
  temperature: z.number().min(0).max(1),
  language: z.enum(languageValues, {
    errorMap: () => ({ message: "Choose one of the listed languages." }),
  }),
  is_active: z.union([z.boolean(), z.literal(0), z.literal(1)]).optional(),
});

export type AgentValues = z.infer<typeof agentSchema>;

export const agentCreateSchema = agentSchema;

export const agentUpdateSchema = agentSchema.partial();

export const agentSchemaApi = z.object({
  id: z.string(),
  workspace_id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  system_prompt: z.string(),
  welcome_message: z.string().nullable(),
  model: z.string(),
  temperature: z.number(),
  language: z.string(),
  is_active: z.union([z.literal(0), z.literal(1)]),
  created_at: z.string(),
  updated_at: z.string(),
});

export const agentListSchema = z.array(agentSchemaApi);

export const AGENT_FORM_DEFAULTS: AgentValues = {
  name: "",
  description: "",
  system_prompt: "",
  welcome_message: "",
  model: DEFAULT_MODEL,
  temperature: DEFAULT_TEMPERATURE,
  language: DEFAULT_LANGUAGE,
};

export const AGENT_SYSTEM_PROMPT_PLACEHOLDER =
  "You are Acme Store's support assistant. Answer only from the knowledge base. If the answer is not in the documents, say so plainly.";

export function clampTemperature(value: number): number {
  if (Number.isNaN(value)) return DEFAULT_TEMPERATURE;
  return Math.min(1, Math.max(0, Math.round(value * 10) / 10));
}