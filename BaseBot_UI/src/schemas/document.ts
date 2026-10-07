import { z } from "zod";
import { ALLOWED_FILE_EXTENSIONS } from "@/lib/constants";

export const docStatusSchema = z.enum(["uploaded", "processing", "ready", "failed"]);
export type DocStatus = z.infer<typeof docStatusSchema>;

export const fileTypeSchema = z.enum(["pdf", "txt", "docx"]);

export const workspaceDocumentSchema = z.object({
  id: z.string(),
  workspace_id: z.string(),
  filename: z.string(),
  file_type: fileTypeSchema,
  size_bytes: z.number(),
  status: docStatusSchema,
  chunk_count: z.number(),
  created_at: z.string(),
});

export const workspaceDocumentListSchema = z.array(workspaceDocumentSchema);

export const documentStatusSchema = z.object({
  doc_id: z.string(),
  filename: z.string(),
  status: docStatusSchema,
  chunk_count: z.number(),
});

export const trainResponseSchema = z.object({
  status: z.enum(["processing", "ready"]),
  message: z.string().optional(),
});

export function isAllowedExtension(filename: string): boolean {
  const dot = filename.lastIndexOf(".");
  if (dot === -1) return false;
  const ext = filename.slice(dot).toLowerCase();
  return (ALLOWED_FILE_EXTENSIONS as readonly string[]).includes(ext);
}

/** Client-side pre-flight. The upload route itself enforces no size cap. */
export function validateFile(
  file: File,
  maxSizeMb: number,
): { ok: true } | { ok: false; message: string } {
  if (!isAllowedExtension(file.name)) {
    return {
      ok: false,
      message: `Unsupported file type. Allowed: ${ALLOWED_FILE_EXTENSIONS.join(", ")}`,
    };
  }
  if (file.size > maxSizeMb * 1024 * 1024) {
    return {
      ok: false,
      message: `${file.name} is ${(file.size / (1024 * 1024)).toFixed(1)} MB. Files over ${maxSizeMb} MB may time out on slower connections.`,
    };
  }
  return { ok: true };
}