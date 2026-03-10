"use client";

import useSWR from "swr";

import { apiRequest } from "@/lib/api";
import { User } from "@/types";

export function useAuth() {
  return useSWR<User>("/api/v1/auth/me", (path: string) => apiRequest<User>(path));
}
