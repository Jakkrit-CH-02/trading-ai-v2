import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const RoleSchema = z.enum(["admin", "operator", "viewer"]);
export type Role = z.infer<typeof RoleSchema>;

export const AuthUserSchema = z.object({
  id: z.string(),
  username: z.string(),
  role: RoleSchema,
  created_at: z.number().int(),
});
export type AuthUser = z.infer<typeof AuthUserSchema>;

export const LoginResponseSchema = z.object({
  token: z.string(),
  user: AuthUserSchema,
});
export type LoginResponse = z.infer<typeof LoginResponseSchema>;

function unwrap<T>(env: ApiEnvelope<T>): T {
  if (env.error || env.data == null) {
    throw new Error(env.error?.message ?? "empty response");
  }
  return env.data;
}

export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const { data } = await api.post<ApiEnvelope<unknown>>("/api/auth/login", {
    username,
    password,
  });
  return LoginResponseSchema.parse(unwrap(data));
}

export async function getMe(): Promise<AuthUser> {
  const { data } = await api.get<ApiEnvelope<unknown>>("/api/auth/me");
  return AuthUserSchema.parse(unwrap(data));
}

export async function logout(): Promise<void> {
  await api.post("/api/auth/logout");
}

export async function register(
  username: string,
  password: string,
  role: Role,
): Promise<AuthUser> {
  const { data } = await api.post<ApiEnvelope<unknown>>("/api/auth/register", {
    username,
    password,
    role,
  });
  return AuthUserSchema.parse(unwrap(data));
}
