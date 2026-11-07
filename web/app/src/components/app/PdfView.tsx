// A PDF page with boxes drawn where the checked values are printed. Box coordinates are PDF
// points from the bottom left, as the checker gives them. The wheel scrolls down the document,
// Ctrl + wheel or the buttons zoom, drag to move, and the page follows the selected finding.
import { useEffect, useRef, useState } from "react";
import type { Status } from "@/lib/types";

export interface Mark { id: string; status: Status; page: number; bbox: [number, number, number, number] }
type View = { x: number; y: number; w: number; h: number };

const COLOR: Record<Status, string> = { FAIL: "var(--fail)", UNKNOWN: "var(--unknown)", PASS: "var(--pass)" };

export function PdfView({ url, marks, selected, onSelect }: { url: string; marks: Mark[]; selected: string | null; onSelect: (id: string) => void }) {
  const [pageCount, setPageCount] = useState(0);
  const [page, setPage] = useState(marks[0]?.page ?? 1);
  const [image, setImage] = useState<{ src: string; w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState<View>({ x: 0, y: 0, w: 595, h: 842 });
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; view: View } | null>(null);
  const W = image?.w ?? 595, H = image?.h ?? 842;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        const doc = await pdfjs.getDocument(url).promise;
        const pdfPage = await doc.getPage(Math.min(page, doc.numPages));
        const size = pdfPage.getViewport({ scale: 1 }), viewport = pdfPage.getViewport({ scale: 2 });
        const canvas = document.createElement("canvas");
        canvas.width = viewport.width; canvas.height = viewport.height;
        const context = canvas.getContext("2d");
        if (!context) return;
        await pdfPage.render({ canvasContext: context, viewport }).promise;
        if (cancelled) return;
        setPageCount(doc.numPages);
        setImage({ src: canvas.toDataURL(), w: size.width, h: size.height });
        setView({ x: 0, y: 0, w: size.width, h: size.height });
        setFailed(false);
      } catch { if (!cancelled) setFailed(true); }
    })();
    return () => { cancelled = true; };
  }, [url, page]);

  // Show the selected finding: its page, zoomed in around it.
  const target = marks.find((m) => m.id === selected);
  useEffect(() => {
    if (!target) return;
    if (target.page !== page) { setPage(target.page); return; }
    if (!image) return;
    const [x0, y0, x1, y1] = target.bbox;
    const w = Math.max(W * 0.55, (x1 - x0) * 1.6);
    const h = w * (H / W);
    setView({ x: (x0 + x1) / 2 - w / 2, y: H - (y0 + y1) / 2 - h / 2, w, h });
  }, [selected, image?.src]); // eslint-disable-line react-hooks/exhaustive-deps

  const zoom = (factor: number) => setView((v) => {
    const w = Math.min(W * 2, Math.max(W * 0.15, v.w * factor)), k = w / v.w;
    return { x: v.x + v.w / 2 - (v.w * k) / 2, y: v.y + v.h / 2 - (v.h * k) / 2, w, h: v.h * k };
  });
  const pages = useRef({ page, pageCount });
  pages.current = { page, pageCount };
  const lastFlip = useRef(0);
  useEffect(() => {
    const element = svg.current;
    if (!element) return;
    // The wheel scrolls down the document and on to the next page at the edge; Ctrl + wheel (also a trackpad pinch) zooms.
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      if (event.ctrlKey) { zoom(event.deltaY > 0 ? 1.15 : 1 / 1.15); return; }
      const rect = element.getBoundingClientRect();
      const down = event.deltaY > 0;
      setView((v) => {
        const maxY = Math.max(0, H - v.h), y = v.y + event.deltaY * Math.max(v.w / rect.width, v.h / rect.height);
        const { page: current, pageCount: count } = pages.current;
        const atEdge = down ? y >= maxY : y <= 0;
        if (atEdge && Date.now() - lastFlip.current > 450) {
          const next = current + (down ? 1 : -1);
          if (next >= 1 && next <= count && Math.abs(event.deltaY) > 0) { lastFlip.current = Date.now(); setPage(next); }
        }
        return { ...v, y: Math.min(maxY, Math.max(0, y)) };
      });
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [W, H]); // eslint-disable-line react-hooks/exhaustive-deps

  const scale = () => { const r = svg.current?.getBoundingClientRect(); return r ? Math.max(view.w / r.width, view.h / r.height) : 1; };
  const onPage = marks.filter((m) => m.page === page);

  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="sheet-noprint flex items-center justify-between gap-2 border-b border-[var(--border)] px-2 py-1 text-xs">
      <span className="flex items-center gap-1">
        <button type="button" className="sheet-button h-6 px-2" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page">‹</button>
        <span className="sheet-mono">PAGE {page} / {pageCount || "–"}</span>
        <button type="button" className="sheet-button h-6 px-2" disabled={!pageCount || page >= pageCount} onClick={() => setPage(page + 1)} aria-label="Next page">›</button>
        {(() => { const others = marks.filter((m) => m.page !== page && m.status === "FAIL").length; return others ? <span className="ml-2 text-[var(--fail)]">{others} more issue{others > 1 ? "s" : ""} on other pages</span> : null; })()}
      </span>
      <span className="flex items-center gap-1">
        <button type="button" className="sheet-button h-6 px-2" onClick={() => zoom(1.25)} aria-label="Zoom out">−</button>
        <button type="button" className="sheet-button h-6 px-2" onClick={() => setView({ x: 0, y: 0, w: W, h: H })}>Fit</button>
        <button type="button" className="sheet-button h-6 px-2" onClick={() => zoom(0.8)} aria-label="Zoom in">+</button>
      </span>
    </div>
    {failed ? <p className="p-4 text-sm">The PDF could not be shown. The findings in the list are still valid.</p>
      : <svg ref={svg} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} preserveAspectRatio="xMidYMid meet" aria-label="Design document"
          className="block min-h-0 w-full flex-1 cursor-grab touch-none bg-[var(--background)] active:cursor-grabbing"
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, view }; e.currentTarget.setPointerCapture(e.pointerId); }}
          onPointerMove={(e) => { const d = drag.current; if (!d) return; const k = scale(); setView({ ...d.view, x: d.view.x - (e.clientX - d.x) * k, y: d.view.y - (e.clientY - d.y) * k }); }}
          onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
          {image && <image href={image.src} x={0} y={0} width={W} height={H} />}
          {onPage.map((mark) => {
            const [x0, y0, x1, y1] = mark.bbox, color = COLOR[mark.status], active = mark.id === selected;
            return <rect key={mark.id} x={x0} y={H - y1} width={x1 - x0} height={y1 - y0} rx={1.5} fill={color} fillOpacity={active ? 0.16 : 0.07}
              stroke={color} strokeWidth={active ? 2.5 : 1.25} vectorEffect="non-scaling-stroke" className="cursor-pointer"
              onPointerDown={(e) => e.stopPropagation()} onClick={() => onSelect(mark.id)}><title>{mark.status === "FAIL" ? "Issue" : mark.status === "PASS" ? "OK" : "To check"}</title></rect>;
          })}
        </svg>}
  </div>;
}
