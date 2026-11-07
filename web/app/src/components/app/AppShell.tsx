import { useRouterState } from "@tanstack/react-router";
import { CheckerHeader } from "./CheckerHeader";
import { useEffect, type ReactNode } from "react";



export function workspaceCommand(command: string) { window.dispatchEvent(new CustomEvent("checker-command", { detail: command })); }
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: state => state.location.pathname });
  const workspace = pathname === "/" || /^\/inspections\/[^/]+$/.test(pathname) && pathname !== "/inspections/new";
  useEffect(() => { document.documentElement.classList.remove("dark"); }, []);
  return <div className="checker-app">
    {!workspace && <CheckerHeader title="PROVENAI"/>}
    <main>{children}</main>
  </div>;
}
export function PageHeader({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return <header className="document-header"><div><h1>{title}</h1>{sub && <p className="text-sm">{sub}</p>}</div>{actions && <div className="flex items-center gap-2 no-print">{actions}</div>}</header>;
}
