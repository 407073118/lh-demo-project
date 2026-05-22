import type { ReactNode } from "react";

type PanelProps = {
  children: ReactNode;
  className?: string;
};

export function Panel({ children, className }: PanelProps) {
  return <section className={className ? `panel ${className}` : "panel"}>{children}</section>;
}

export function PanelTitle({ children }: { children: ReactNode }) {
  return <h2 className="panel-title">{children}</h2>;
}
