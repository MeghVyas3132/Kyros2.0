"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiRequest, setAuthTokens } from "@/lib/api";
import { LoginResponse } from "@/types";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

const bootstrapSchema = z
  .object({
    brand_name: z.string().min(2, "Brand name is required"),
    brand_slug: z.string().optional(),
    full_name: z.string().min(2, "Full name is required"),
    email: z.string().email(),
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_password: z.string().min(8),
  })
  .refine((values) => values.password === values.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords do not match",
  });

type LoginForm = z.infer<typeof loginSchema>;
type BootstrapForm = z.infer<typeof bootstrapSchema>;

interface BootstrapStatus {
  bootstrap_required: boolean;
  user_count: number;
}

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [bootstrapRequired, setBootstrapRequired] = useState<boolean>(false);
  const [checkingBootstrap, setCheckingBootstrap] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void apiRequest<BootstrapStatus>("/api/v1/auth/bootstrap/status", {
      timeoutMs: 8000,
      retryCount: 0,
    })
      .then((response) => {
        if (!cancelled) {
          setBootstrapRequired(Boolean(response.bootstrap_required));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBootstrapRequired(false);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCheckingBootstrap(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const form = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const bootstrapForm = useForm<BootstrapForm>({
    resolver: zodResolver(bootstrapSchema),
    defaultValues: {
      brand_name: "",
      brand_slug: "",
      full_name: "",
      email: "",
      password: "",
      confirm_password: "",
    },
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

  const onBootstrap = bootstrapForm.handleSubmit(async (values) => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiRequest<LoginResponse>("/api/v1/auth/bootstrap", {
        method: "POST",
        body: JSON.stringify({
          brand_name: values.brand_name,
          brand_slug: values.brand_slug?.trim() || undefined,
          full_name: values.full_name,
          email: values.email,
          password: values.password,
          initial_config: {},
        }),
      });
      setAuthTokens(response.access_token, response.refresh_token);
      localStorage.setItem("kyros_user", JSON.stringify(response.user));
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workspace setup failed");
    } finally {
      setLoading(false);
    }
  });

  if (checkingBootstrap) {
    return (
      <div className="w-full max-w-md rounded-xl border border-slate-300 bg-white p-6 shadow-md">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Kyros</p>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">Checking workspace…</h1>
      </div>
    );
  }

  if (bootstrapRequired) {
    return (
      <div className="w-full max-w-md rounded-xl border border-slate-300 bg-white p-6 shadow-md">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Kyros</p>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">Initialize Workspace</h1>
        <p className="mt-1 text-sm text-slate-600">
          No users found. Create your first admin account and brand.
        </p>

        <form className="mt-6 space-y-3" onSubmit={onBootstrap}>
          <Input placeholder="Brand name" {...bootstrapForm.register("brand_name")} />
          <Input placeholder="Brand slug (optional)" {...bootstrapForm.register("brand_slug")} />
          <Input placeholder="Your full name" {...bootstrapForm.register("full_name")} />
          <Input placeholder="Admin email" {...bootstrapForm.register("email")} />
          <Input type="password" placeholder="Password" {...bootstrapForm.register("password")} />
          <Input
            type="password"
            placeholder="Confirm password"
            {...bootstrapForm.register("confirm_password")}
          />
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <Button type="submit" disabled={loading} className="w-full">
            {loading ? "Creating..." : "Create Admin & Continue"}
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md rounded-xl border border-slate-300 bg-white p-6 shadow-md">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Kyros</p>
      <h1 className="mt-2 text-xl font-semibold text-slate-900">Planner Login</h1>
      <p className="mt-1 text-sm text-slate-600">Sign in with your workspace credentials.</p>

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
