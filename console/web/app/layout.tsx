import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "oneEdge Console",
  description: "Zero-trust fleet operations"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100">
        <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
          <header className="flex items-center justify-between">
            <h1 className="text-3xl font-semibold text-slate-100">oneEdge Console</h1>
            <nav className="space-x-4 text-sm text-slate-400">
              <a href="/" className="hover:text-primary">Overview</a>
              <a href="/devices" className="hover:text-primary">Devices</a>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
