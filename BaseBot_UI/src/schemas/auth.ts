import { z } from "zod";
import { MAX_EMAIL_LENGTH, MIN_PASSWORD_LENGTH } from "@/lib/constants";

export const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Enter your email address.")
    .max(MAX_EMAIL_LENGTH, "That email address is too long.")
    .email("Enter a valid email address."),
  // No minimum length on login — this is not the password being created.
  password: z.string().min(1, "Enter your password."),
});

export type LoginValues = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  email: z
    .string()
    .min(1, "Enter your email address.")
    .max(MAX_EMAIL_LENGTH, "That email address is too long.")
    .email("Enter a valid email address."),
  password: z
    .string()
    .min(MIN_PASSWORD_LENGTH, `Use at least ${MIN_PASSWORD_LENGTH} characters.`),
  // Visual only — there is no backend field for terms.
  acceptTerms: z.literal(true, {
    errorMap: () => ({ message: "Accept the terms to create an account." }),
  }),
});

export type RegisterValues = z.infer<typeof registerSchema>;

export const tokenResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.string(),
  user_id: z.string().min(1),
});