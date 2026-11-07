import { useEffect, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";

export function AppShell({ children }: { children: ReactNode }) {
  useEffect(() => { document.documentElement.classList.remove("dark"); }, []);
  return <div className="min-h-screen">
    <TopBar />
    <main className="mx-auto w-full max-w-7xl px-4 py-5">{children}</main>
  </div>;
}

function TopBar() {
  return <header className="sheet-noprint border-b border-[var(--foreground)] bg-[var(--card)]">
    <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-2">
      <Link to="/" className="flex items-center gap-2"><img src="/logo.png" alt="" className="h-7 w-7" /><span className="sheet-title text-[17px]">ProvenAI</span></Link>
      <nav className="flex gap-5 text-[13px] uppercase tracking-wide [font-family:var(--font-label)]">
        <Link to="/" className="hover:underline">New check</Link>
        <Link to="/history" className="hover:underline">Earlier checks</Link>
        <Link to="/settings" className="hover:underline">Settings</Link>
      </nav>
    </div>
  </header>;
}

/** The ruled title of a page, as on a drawing sheet. */
export function PageTitle({ label, title, children }: { label: string; title: ReactNode; children?: ReactNode }) {
  return <header className="sheet-rule flex flex-wrap items-end justify-between gap-4 py-3">
    <div className="min-w-0"><p className="sheet-label">{label}</p><h1 className="sheet-title break-words">{title}</h1></div>
    {children}
  </header>;
}
