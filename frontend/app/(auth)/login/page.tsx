"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiRequest, setAuthTokens } from "@/lib/api";
import { LoginResponse } from "@/types";

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

type LoginForm = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const form = useForm<LoginForm>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<LoginResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(values),
      });
      setAuthTokens(response.access_token, response.refresh_token);
      localStorage.setItem("kyros_user", JSON.stringify(response.user));
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  });

  return (
    <div className="w-full max-w-md rounded-xl border border-slate-300 bg-white p-6 shadow-md">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Kyros</p>
      <h1 className="mt-2 text-xl font-semibold text-slate-900">Planner Login</h1>
      <p className="mt-1 text-sm text-slate-600">Sign in with your pilot account credentials.</p>

      <form className="mt-6 space-y-3" onSubmit={onSubmit}>
        <Input placeholder="Email" {...form.register("email")} />
        <Input type="password" placeholder="Password" {...form.register("password")} />
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "Signing in..." : "Sign In"}
        </Button>
      </form>
    </div>
  );
}
