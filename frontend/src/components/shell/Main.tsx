import type { ReactNode } from "react";

interface MainProps {
  children: ReactNode;
}

export function Main({ children }: MainProps) {
  return (
    <main className="app-main" role="main">
      <div className="app-main__inner">{children}</div>
    </main>
  );
}