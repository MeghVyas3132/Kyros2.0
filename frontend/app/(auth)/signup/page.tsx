"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiRequest } from "@/lib/api";

const signupSchema = z
  .object({
    brand_name: z.string().min(2, "Brand name is required"),
    brand_slug: z.string().optional(),
    full_name: z.string().min(2, "Full name is required"),
    email: z.string().email(),
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_password: z.string().min(8),
    contact_phone: z.string().optional(),
    company_size: z.string().optional(),
    notes: z.string().max(1000).optional(),
  })
  .refine((values) => values.password === values.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords do not match",
  });

type SignupForm = z.infer<typeof signupSchema>;

export default function SignupPage() {
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const form = useForm<SignupForm>({
    resolver: zodResolver(signupSchema),
    defaultValues: {
      brand_name: "",
      brand_slug: "",
      full_name: "",
      email: "",
      password: "",
      confirm_password: "",
      contact_phone: "",
      company_size: "",
      notes: "",
    },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setLoading(true);
    setError(null);
    try {
      await apiRequest("/api/v1/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          brand_name: values.brand_name,
          brand_slug: values.brand_slug?.trim() || undefined,
          full_name: values.full_name,
          email: values.email,
          password: values.password,
          contact_phone: values.contact_phone?.trim() || undefined,
          company_size: values.company_size?.trim() || undefined,
          notes: values.notes?.trim() || undefined,
        }),
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  });

  if (submitted) {
    return (
      <div className="w-full max-w-md rounded-xl border border-slate-300 bg-white p-6 shadow-md">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-600">
          Submitted
        </p>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">Application received</h1>
        <p className="mt-3 text-sm text-slate-600">
          Thanks — your request is now in the review queue. A platform admin
          will reach out by email once your account is approved. You won&rsquo;t be
          able to log in until then.
        </p>
        <div className="mt-6">
          <Link
            href="/login"
            className="text-sm font-medium text-blue-600 hover:underline"
          >
            ← Back to login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md rounded-xl border border-slate-300 bg-white p-6 shadow-md">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Kyros</p>
      <h1 className="mt-2 text-xl font-semibold text-slate-900">Request access</h1>
      <p className="mt-1 text-sm text-slate-600">
        Tell us a bit about your brand. A platform admin will review and
        provision your workspace.
      </p>

      <form className="mt-6 space-y-3" onSubmit={onSubmit}>
        <div>
          <Input placeholder="Brand name" {...form.register("brand_name")} />
          {form.formState.errors.brand_name ? (
            <p className="mt-1 text-xs text-red-600">
              {form.formState.errors.brand_name.message}
            </p>
          ) : null}
        </div>
        <Input
          placeholder="Brand slug (optional, e.g. acme-fashion)"
          {...form.register("brand_slug")}
        />
        <div>
          <Input placeholder="Your full name" {...form.register("full_name")} />
          {form.formState.errors.full_name ? (
            <p className="mt-1 text-xs text-red-600">
              {form.formState.errors.full_name.message}
            </p>
          ) : null}
        </div>
        <div>
          <Input placeholder="Work email" {...form.register("email")} />
          {form.formState.errors.email ? (
            <p className="mt-1 text-xs text-red-600">
              {form.formState.errors.email.message}
            </p>
          ) : null}
        </div>
        <Input
          placeholder="Contact phone (optional)"
          {...form.register("contact_phone")}
        />
        <Input
          placeholder="Company size (e.g. 50-100 stores)"
          {...form.register("company_size")}
        />
        <div>
          <Input
            type="password"
            placeholder="Password (min 8 chars)"
            {...form.register("password")}
          />
          {form.formState.errors.password ? (
            <p className="mt-1 text-xs text-red-600">
              {form.formState.errors.password.message}
            </p>
          ) : null}
        </div>
        <div>
          <Input
            type="password"
            placeholder="Confirm password"
            {...form.register("confirm_password")}
          />
          {form.formState.errors.confirm_password ? (
            <p className="mt-1 text-xs text-red-600">
              {form.formState.errors.confirm_password.message}
            </p>
          ) : null}
        </div>
        <textarea
          {...form.register("notes")}
          placeholder="Anything you'd like the reviewer to know (optional)"
          className="block w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          rows={3}
        />
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "Submitting..." : "Submit application"}
        </Button>
      </form>

      <div className="mt-4 text-center text-sm text-slate-600">
        Already approved?{" "}
        <Link href="/login" className="font-medium text-blue-600 hover:underline">
          Sign in
        </Link>
      </div>
    </div>
  );
}
