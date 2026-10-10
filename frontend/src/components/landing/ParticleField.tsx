import { useEffect, useRef } from "react";

interface ParticleFieldProps {
  density?: number;
  testId?: string;
}

interface Dot {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  gold: boolean;
}

const GOLD = "198, 161, 91";
const GREEN = "134, 197, 160";
const LINK_DIST = 120;
const MOUSE_DIST = 160;
// Half of the 8-neighbourhood (cell size == LINK_DIST): walking each dot
// against only these offsets visits every dot pair exactly once.
const FORWARD_CELLS: ReadonlyArray<readonly [number, number]> = [
  [0, 1],
  [1, -1],
  [1, 0],
  [1, 1],
];

export function ParticleField({ density = 110, testId = "landing-particles" }: ParticleFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el: HTMLCanvasElement | null = canvasRef.current;
    if (!el) return;
    const canvas: HTMLCanvasElement = el;
    const host: HTMLElement | null = canvas.parentElement;
    if (!host) return;
    const parent: HTMLElement = host;
    const context: CanvasRenderingContext2D | null = canvas.getContext("2d");
    if (!context) return;
    const ctx: CanvasRenderingContext2D = context;

    let dots: Dot[] = [];
    let w = 0;
    let h = 0;
    let raf = 0;
    let running = true;
    const mouse = { x: -9999, y: -9999, inside: false };

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function seed() {
      const area = Math.max(1, (w * h) / (1200 * 520));
      const count = Math.max(40, Math.min(180, Math.round(density * area)));
      dots = Array.from({ length: count }, (_, i) => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.45,
        vy: (Math.random() - 0.5) * 0.45,
        r: 1 + Math.random() * 1.6,
        gold: i % 5 < 3,
      }));
    }

    function resize() {
      const rect = parent.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = Math.max(1, rect.width);
      h = Math.max(1, rect.height);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      seed();
      if (reduced) draw();
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);

      // Spatial hash: bucket dots into LINK_DIST-sized cells so each dot is
      // only compared against its own cell and the four forward neighbours
      // (O(n) pair checks per frame instead of O(n^2) — 180 dots used to cost
      // ~16k distance checks on every animation frame, which is heavy on a
      // 390px phone). Same links are drawn as before.
      const cols = Math.max(1, Math.ceil(w / LINK_DIST));
      const rows = Math.max(1, Math.ceil(h / LINK_DIST));
      const grid: Dot[][] = Array.from({ length: cols * rows }, () => []);
      for (const d of dots) {
        const cx = Math.min(cols - 1, Math.max(0, Math.floor(d.x / LINK_DIST)));
        const cy = Math.min(rows - 1, Math.max(0, Math.floor(d.y / LINK_DIST)));
        grid[cy * cols + cx].push(d);
      }

      const link = (a: Dot, b: Dot) => {
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d = Math.hypot(dx, dy);
        if (d < LINK_DIST) {
          const alpha = (1 - d / LINK_DIST) * 0.28;
          ctx.strokeStyle = `rgba(${GOLD},${alpha.toFixed(3)})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      };

      for (let cy = 0; cy < rows; cy++) {
        for (let cx = 0; cx < cols; cx++) {
          const bucket = grid[cy * cols + cx];
          for (let i = 0; i < bucket.length; i++) {
            const a = bucket[i];
            for (let j = i + 1; j < bucket.length; j++) link(a, bucket[j]);
            for (let n = 0; n < FORWARD_CELLS.length; n++) {
              const nx = cx + FORWARD_CELLS[n][0];
              const ny = cy + FORWARD_CELLS[n][1];
              if (nx < 0 || ny < 0 || nx >= cols || ny >= rows) continue;
              const near = grid[ny * cols + nx];
              for (let j = 0; j < near.length; j++) link(a, near[j]);
            }
          }
        }
      }

      if (mouse.inside) {
        for (const a of dots) {
          const dx = a.x - mouse.x;
          const dy = a.y - mouse.y;
          const d = Math.hypot(dx, dy);
          if (d < MOUSE_DIST) {
            const alpha = (1 - d / MOUSE_DIST) * 0.55;
            ctx.strokeStyle = `rgba(${GOLD},${alpha.toFixed(3)})`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(mouse.x, mouse.y);
            ctx.stroke();
          }
        }
      }

      for (const d of dots) {
        let glow = 0;
        if (mouse.inside) {
          const md = Math.hypot(d.x - mouse.x, d.y - mouse.y);
          if (md < MOUSE_DIST) glow = 1 - md / MOUSE_DIST;
        }
        const base = d.gold ? GOLD : GREEN;
        ctx.fillStyle = `rgba(${base},${(0.55 + glow * 0.45).toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r + glow * 1.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    function step() {
      if (!running) return;
      for (const d of dots) {
        if (mouse.inside) {
          const dx = d.x - mouse.x;
          const dy = d.y - mouse.y;
          const dist = Math.hypot(dx, dy);
          if (dist < MOUSE_DIST && dist > 0.01) {
            const force = ((MOUSE_DIST - dist) / MOUSE_DIST) * 0.6;
            d.x += (dx / dist) * force;
            d.y += (dy / dist) * force;
          }
        }
        d.x += d.vx;
        d.y += d.vy;
        if (d.x < 0 || d.x > w) d.vx *= -1;
        if (d.y < 0 || d.y > h) d.vy *= -1;
        d.x = Math.max(0, Math.min(w, d.x));
        d.y = Math.max(0, Math.min(h, d.y));
      }
      draw();
      raf = requestAnimationFrame(step);
    }

    function onMove(e: PointerEvent) {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      mouse.inside = true;
    }

    function onLeave() {
      mouse.inside = false;
      mouse.x = -9999;
      mouse.y = -9999;
    }

    function onVisibility() {
      if (reduced) return;
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        raf = requestAnimationFrame(step);
      }
    }

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(parent);
    window.addEventListener("pointermove", onMove, { passive: true });
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);
    window.addEventListener("blur", onLeave);
    document.addEventListener("visibilitychange", onVisibility);

    if (!reduced) {
      running = true;
      raf = requestAnimationFrame(step);
    }

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("blur", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [density]);

  return (
    <canvas
      ref={canvasRef}
      className="landing-particles"
      data-testid={testId}
      aria-hidden="true"
    />
  );
}
