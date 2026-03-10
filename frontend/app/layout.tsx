import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Kyros",
  description: "Allocation intelligence for fashion retail",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
