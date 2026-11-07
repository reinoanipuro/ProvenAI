// A PDF viewer that works like Acrobat: every page in one scrolling column, fitted to the width of its panel.
// The wheel scrolls, Ctrl + wheel (or a trackpad pinch) zooms, dragging moves the page, and a selected finding
// scrolls into view. Box coordinates are PDF points from the bottom left, as the checker gives them.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { Status } from "@/lib/types";

export interface Mark { id: string; status: Status; page: number; bbox: [number, number, number, number] }
type Zoom = "width" | "page" | number;
interface Size { w: number; h: number }

const COLOR: Record<Status, string> = { FAIL: "var(--fail)", UNKNOWN: "var(--unknown)", PASS: "var(--pass)" };
const LABEL: Record<Status, string> = { FAIL: "Issue", UNKNOWN: "To check", PASS: "OK" };
const PAD = 16, GAP = 12, SCROLLBAR = 16, MIN_SCALE = 0.25, MAX_SCALE = 5;
const LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];
const clamp = (value: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));

export function PdfView({ url, marks, selected, onSelect }: { url: string; marks: Mark[]; selected: string | null; onSelect: (id: string) => void }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [sizes, setSizes] = useState<Size[]>([]);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState<Zoom>("width");
  const [box, setBox] = useState<Size>({ w: 0, h: 0 });
  const [page, setPage] = useState(1);
  const [typed, setTyped] = useState<string | null>(null);
  const [grabbing, setGrabbing] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const anchor = useRef<number | null>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const scrolledTo = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    setPdf(null); setSizes([]); setFailed(false); setPage(1);
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        const opened = await pdfjs.getDocument(url).promise;
        if (cancelled) { void opened.destroy(); return; }
        loaded = opened;
        const dimensions = await Promise.all(Array.from({ length: opened.numPages }, async (_, index) => {
          const viewport = (await opened.getPage(index + 1)).getViewport({ scale: 1 });
          return { w: viewport.width, h: viewport.height };
        }));
        if (cancelled) return;
        setSizes(dimensions);
        setPdf(opened);
      } catch { if (!cancelled) setFailed(true); }
    })();
    return () => { cancelled = true; void loaded?.destroy(); };
  }, [url]);

  useEffect(() => {
    const element = scroller.current;
    if (!element) return;
    const measure = () => setBox({ w: element.clientWidth, h: element.clientHeight });
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    measure();
    return () => observer.disconnect();
  }, [failed]);

  const widest = sizes.length ? Math.max(...sizes.map((size) => size.w)) : 595;
  const current = sizes[page - 1];
  const fitWidth = box.w ? (box.w - 2 * PAD - SCROLLBAR) / widest : 1;
  const fitPage = current && box.h ? Math.min(fitWidth, (box.h - 2 * PAD) / current.h) : fitWidth;
  const scale = clamp(zoom === "width" ? fitWidth : zoom === "page" ? fitPage : zoom);
  const tops = useMemo(() => {
    let y = PAD;
    return sizes.map((size) => { const top = y; y += size.h * scale + GAP; return top; });
  }, [sizes, scale]);

  // Zooming keeps the middle of the view where it was.
  function zoomTo(next: number) {
    const element = scroller.current;
    if (element && element.scrollHeight) anchor.current = (element.scrollTop + element.clientHeight / 2) / element.scrollHeight;
    setZoom(clamp(next));
  }
  useLayoutEffect(() => {
    const element = scroller.current;
    if (element && anchor.current !== null) {
      element.scrollTop = anchor.current * element.scrollHeight - element.clientHeight / 2;
      anchor.current = null;
    }
  }, [scale]);

  const latest = useRef({ scale, zoomTo });
  latest.current = { scale, zoomTo };
  useEffect(() => {
    const element = scroller.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      latest.current.zoomTo(latest.current.scale * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [failed]);

  const frame = useRef(0);
  function onScroll() {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const element = scroller.current;
      if (!element || !tops.length) return;
      const line = element.scrollTop + element.clientHeight / 3;
      let index = 0;
      tops.forEach((top, i) => { if (top <= line) index = i; });
      setPage(index + 1);
    });
  }
  function goTo(number: number) {
    const target = Math.min(Math.max(1, number), Math.max(1, sizes.length));
    scroller.current?.scrollTo({ top: (tops[target - 1] ?? PAD) - PAD, behavior: "smooth" });
    setPage(target);
  }

  // Scroll a selected finding into view, once per selection.
  useEffect(() => {
    if (!selected) { scrolledTo.current = null; return; }
    const container = scroller.current;
    if (!pdf || !container || scrolledTo.current === selected) return;
    const element = container.querySelector<HTMLElement>(`[data-mark="${CSS.escape(selected)}"]`);
    if (!element) return;
    scrolledTo.current = selected;
    const inner = element.getBoundingClientRect(), outer = container.getBoundingClientRect();
    container.scrollTo({
      top: container.scrollTop + (inner.top - outer.top) - container.clientHeight / 3,
      left: container.scrollLeft + (inner.left - outer.left) - container.clientWidth / 2 + inner.width / 2,
      behavior: "smooth",
    });
  }, [selected, pdf, marks]);

  const percent = Math.round(scale * 100);
  const zoomValue = zoom === "width" || zoom === "page" ? zoom : String(zoom);
  const custom = typeof zoom === "number" && !LEVELS.includes(zoom);
  const zoomIn = () => zoomTo(LEVELS.find((level) => level > scale * 1.01) ?? MAX_SCALE);
  const zoomOut = () => zoomTo([...LEVELS].reverse().find((level) => level < scale * 0.99) ?? MIN_SCALE);

  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="pdf-toolbar sheet-noprint">
      <span className="flex items-center gap-1">
        <button type="button" className="sheet-button h-6 px-2" disabled={page <= 1} onClick={() => goTo(page - 1)} aria-label="Previous page">‹</button>
        <input className="pdf-page-input sheet-mono" aria-label="Page number" inputMode="numeric" value={typed ?? String(page)}
          onFocus={(e) => { setTyped(String(page)); e.currentTarget.select(); }} onBlur={() => setTyped(null)} onChange={(e) => setTyped(e.target.value.replace(/\D/g, ""))}
          onKeyDown={(e) => { if (e.key === "Enter") { goTo(Number(typed) || page); e.currentTarget.blur(); } }} />
        <span className="sheet-mono">/ {sizes.length || "–"}</span>
        <button type="button" className="sheet-button h-6 px-2" disabled={!sizes.length || page >= sizes.length} onClick={() => goTo(page + 1)} aria-label="Next page">›</button>
      </span>
      <span className="flex items-center gap-1">
        <button type="button" className="sheet-button h-6 px-2" disabled={scale <= MIN_SCALE} onClick={zoomOut} aria-label="Zoom out">−</button>
        <select className="pdf-zoom sheet-mono" aria-label="Zoom" value={custom ? "custom" : zoomValue}
          onChange={(e) => { const value = e.target.value; if (value === "width" || value === "page") setZoom(value); else if (value !== "custom") zoomTo(Number(value)); }}>
          <option value="width">Fit width · {percent}%</option>
          <option value="page">Fit page · {percent}%</option>
          {custom && <option value="custom">{percent}%</option>}
          {LEVELS.map((level) => <option key={level} value={String(level)}>{Math.round(level * 100)}%</option>)}
        </select>
        <button type="button" className="sheet-button h-6 px-2" disabled={scale >= MAX_SCALE} onClick={zoomIn} aria-label="Zoom in">+</button>
      </span>
    </div>
    {failed ? <p className="p-4 text-sm">The PDF could not be shown. The findings in the list are still valid.</p>
      : <div ref={scroller} className="pdf-scroller" data-grabbing={grabbing || undefined} tabIndex={0} aria-label="Design document" onScroll={onScroll}
          onPointerDown={(e) => {
            if (e.button !== 0 || (e.target as HTMLElement).closest("[data-mark]")) return;
            const element = e.currentTarget;
            drag.current = { x: e.clientX, y: e.clientY, left: element.scrollLeft, top: element.scrollTop };
            element.setPointerCapture(e.pointerId);
            setGrabbing(true);
          }}
          onPointerMove={(e) => {
            const start = drag.current;
            if (!start) return;
            e.currentTarget.scrollLeft = start.left - (e.clientX - start.x);
            e.currentTarget.scrollTop = start.top - (e.clientY - start.y);
          }}
          onPointerUp={() => { drag.current = null; setGrabbing(false); }} onPointerCancel={() => { drag.current = null; setGrabbing(false); }}>
          {!pdf && <p className="sheet-label p-4">Loading the document …</p>}
          <div className="pdf-pages" style={{ padding: PAD, paddingBottom: PAD - GAP }}>
            {pdf && sizes.map((size, index) => <PdfPage key={index} pdf={pdf} number={index + 1} size={size} scale={scale}
              marks={marks.filter((mark) => mark.page === index + 1)} selected={selected} onSelect={onSelect} />)}
          </div>
        </div>}
  </div>;
}

function PdfPage({ pdf, number, size, scale, marks, selected, onSelect }: {
  pdf: PDFDocumentProxy; number: number; size: Size; scale: number; marks: Mark[]; selected: string | null; onSelect: (id: string) => void;
}) {
  const holder = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = holder.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(!!entry?.isIntersecting), { rootMargin: "900px 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Draw only pages near the view, off screen first, so zooming does not flash a blank page.
  useEffect(() => {
    if (!visible) return;
    let dead = false;
    let task: { cancel: () => void } | null = null;
    const timer = window.setTimeout(async () => {
      try {
        const page = await pdf.getPage(number);
        const viewport = page.getViewport({ scale: scale * Math.min(window.devicePixelRatio || 1, 2) });
        const offscreen = window.document.createElement("canvas");
        offscreen.width = Math.floor(viewport.width);
        offscreen.height = Math.floor(viewport.height);
        const context = offscreen.getContext("2d");
        if (!context || dead) return;
        const render = page.render({ canvasContext: context, viewport });
        task = render;
        await render.promise;
        const target = canvas.current;
        if (dead || !target) return;
        target.width = offscreen.width;
        target.height = offscreen.height;
        target.getContext("2d")?.drawImage(offscreen, 0, 0);
      } catch { /* a newer draw replaced this one, or the page could not be drawn */ }
    }, 120);
    return () => { dead = true; window.clearTimeout(timer); task?.cancel(); };
  }, [pdf, number, scale, visible]);

  return <div ref={holder} className="pdf-page" style={{ width: size.w * scale, height: size.h * scale, marginBottom: GAP }}>
    <canvas ref={canvas} className="pdf-canvas" />
    {marks.map((mark) => {
      const [x0, y0, x1, y1] = mark.bbox;
      return <button key={mark.id} type="button" data-mark={mark.id} data-active={mark.id === selected || undefined} className="pdf-mark"
        title={LABEL[mark.status]} aria-label={`${LABEL[mark.status]} on page ${number}`} onClick={() => onSelect(mark.id)}
        style={{
          left: `${(x0 / size.w) * 100}%`, top: `${((size.h - y1) / size.h) * 100}%`,
          width: `${((x1 - x0) / size.w) * 100}%`, height: `${((y1 - y0) / size.h) * 100}%`, ["--mark" as string]: COLOR[mark.status],
        }} />;
    })}
  </div>;
}
