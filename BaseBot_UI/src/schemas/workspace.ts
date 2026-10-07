import { z } from "zod";
import { DEFAULT_SYSTEM_PROMPT, MAX_DESCRIPTION_LENGTH, MAX_NAME_LENGTH } from "@/lib/constants";

export const workspaceSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Give the workspace a name.")
    .max(MAX_NAME_LENGTH, `Keep the name under ${MAX_NAME_LENGTH} characters.`),
  description: z
    .string()
    .max(MAX_DESCRIPTION_LENGTH, `Keep the description under ${MAX_DESCRIPTION_LENGTH} characters.`)
    .optional()
    .or(z.literal("")),
  system_prompt: z.string().max(4000).optional().or(z.literal("")),
});

export type WorkspaceValues = z.infer<typeof workspaceSchema>;

export const workspaceUpdateSchema = workspaceSchema.partial();

export const workspaceSchemaApi = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  system_prompt: z.string(),
  owner_id: z.string(),
  created_at: z.string(),
});

export const workspaceListSchema = z.array(workspaceSchemaApi);

export const WORKSPACE_FORM_DEFAULTS: WorkspaceValues = {
  name: "",
  description: "",
  system_prompt: DEFAULT_SYSTEM_PROMPT,
};