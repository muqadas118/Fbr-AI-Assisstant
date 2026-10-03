import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import type { ReactNode } from "react";

interface MainProps {
  children: ReactNode;
}

/**
 * Remounts the page inner on every route change so the CSS page-enter
 * animation (fade-rise) replays for each navigation. Scroll resets to
 * top as well, matching the animation.
 */
export function Main({ children }: MainProps) {
  const { pathname } = useLocation();

  useEffect(() => {
    const main = document.querySelector<HTMLElement>(".app-main");
    // jsdom/test environments do not implement scrollTo.
    if (main && typeof main.scrollTo === "function") {
      main.scrollTo({ top: 0 });
    } else if (main) {
      main.scrollTop = 0;
    }
  }, [pathname]);

  return (
    <main className="app-main" role="main">
      <div className="app-main__inner" key={pathname} data-page={pathname}>
        {children}
      </div>
    </main>
  );
}
