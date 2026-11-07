import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { Result, ShipElement } from "@/lib/types";
import { revisionCloud } from "@/lib/redlineGeometry";
import { drawingSize, findingOverlay, normalizedPoint } from "@/lib/drawingOverlays";
import referenceDrawing from "@/assets/rcrv-deck01-cabins.png.asset.json";
import { statusColorVar, statusRank } from "./Status";

type VB = { x: number; y: number; w: number; h: number };
type Box = { x: number; y: number; w: number; h: number };

export function DrawingViewer({ elements, results, selectedElementId, onSelectElement, pdfUrl, fileName, selectedResult, onWhy, markerLimit, calibrate = false, onCursor, onZoom, compact = false, hoveredResultId, onHoverResult }: {
  elements: ShipElement[]; results: Result[]; selectedElementId: string | null; onSelectElement: (id: string, resultId?: string) => void;
  pdfUrl: string | null; fileName?: string | undefined;
  selectedResult?: Result | null; onWhy?: () => void; markerLimit?: number | undefined; calibrate?: boolean; compact?: boolean; onCursor?: (p: { x: number; y: number } | null) => void; onZoom?: (percent: number) => void;
  hoveredResultId?: string | null; onHoverResult?: (id: string | null) => void;
}) {
  const pages = useMemo(() => [...new Set(elements.map((e) => e.page))].sort((a, b) => a - b), [elements]);
  const [page, setPage] = useState(pages[0] ?? 1);
  const [pdfPages, setPdfPages] = useState<number[]>([]);
  const [img, setImg] = useState<{ src: string; w: number; h: number } | null>(null);
  const reference = !pdfUrl;
  const W = img?.w ?? drawingSize.width, H = img?.h ?? drawingSize.height;
  const fit: VB = { x: 0, y: 0, w: W, h: H };
  const [vb, setVb] = useState<VB>(fit);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; vb: VB; moved: boolean } | null>(null);
  const wheelHandler = useRef<(e: WheelEvent) => void>(() => {});

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const resize = () => setSize({ w: svg.clientWidth, h: svg.clientHeight });
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(svg);
    const wheel = (e: WheelEvent) => { e.preventDefault(); wheelHandler.current(e); };
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => { observer.disconnect(); svg.removeEventListener("wheel", wheel); };
  }, []);

  useEffect(() => {
    if (!pdfUrl) { setImg(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const worker = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
        pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
        const doc = await pdfjs.getDocument(pdfUrl).promise;
        if (!cancelled) setPdfPages(Array.from({ length: doc.numPages }, (_, i) => i + 1));
        const p = await doc.getPage(page);
        const vp1 = p.getViewport({ scale: 1 }), vp = p.getViewport({ scale: 2 });
        const canvas = document.createElement("canvas");
        canvas.width = vp.width; canvas.height = vp.height;
        const context = canvas.getContext("2d");
        if (!context) return;
        await p.render({ canvasContext: context, viewport: vp }).promise;
        if (!cancelled) { setImg({ src: canvas.toDataURL(), w: vp1.width, h: vp1.height }); setVb({ x: 0, y: 0, w: vp1.width, h: vp1.height }); }
      } catch { if (!cancelled) setImg(null); }
    })();
    return () => { cancelled = true; };
  }, [pdfUrl, page]);

  function boxFor(r: Result): Box | null {
    if (reference) {
      const b = findingOverlay(r.id, r.element_id);
      return b ? { x: b.x0 * W, y: b.y0 * H, w: (b.x1 - b.x0) * W, h: (b.y1 - b.y0) * H } : null;
    }
    const el = elements.find((e) => e.id === r.element_id);
    if (!el || el.page !== page) return null;
    const [x0, y0, x1, y1] = el.bbox;
    return { x: x0, y: H - y1, w: x1 - x0, h: y1 - y0 };
  }


  useEffect(() => {
    if (!selectedResult) return;
    const el = elements.find((e) => e.id === selectedElementId);
    if (!reference && el && el.page !== page) { setPage(el.page); return; }
    const b = boxFor(selectedResult);
    if (!b) return;
    const aspect = size.w / Math.max(size.h, 1);
    const w = Math.max(W * 0.4, b.w * 3.2, b.h * 1.5 * aspect);
    const h = w / aspect;
    setVb({ x: b.x + b.w / 2 - w * 0.28, y: b.y + b.h / 2 - h * (compact ? 0.22 : 0.54), w, h });
  }, [selectedResult?.id, img?.src, size.w, size.h, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const svgPoint = (clientX: number, clientY: number) => {
    const matrix = svgRef.current?.getScreenCTM();
    if (!matrix) return null;
    return new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
  };
  const zoom = (factor: number, anchor?: { x: number; y: number }) => setVb((v) => {
    const w = Math.min(W * 2, Math.max(W * 0.12, v.w * factor));
    const k = w / v.w;
    const p = anchor ?? { x: v.x + v.w / 2, y: v.y + v.h / 2 };
    return { x: p.x - (p.x - v.x) * k, y: p.y - (p.y - v.y) * k, w, h: v.h * k };
  });
  useEffect(() => { onZoom?.(Math.round(W / vb.w * 100)); }, [W, vb.w, onZoom]);
  useEffect(() => {
    const command = (event: Event) => {
      const action = (event as CustomEvent<string>).detail;
      if (action === "fit") setVb(fit);
      if (action === "zoom-in") zoom(1 / 1.3);
      if (action === "zoom-out") zoom(1.3);
    };
    window.addEventListener("checker-command", command);
    return () => window.removeEventListener("checker-command", command);
  }, [W, H]);
  wheelHandler.current = (e) => {
    const p = svgPoint(e.clientX, e.clientY);
    if (!p) return;
    const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? size.h : 1);
    zoom(Math.exp(Math.max(-300, Math.min(300, dy)) * 0.0015), p);
  };
  const onDown = (e: React.PointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, vb, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const p = svgPoint(e.clientX, e.clientY);
    onCursor?.(p ? normalizedPoint(p.x, p.y, W, H) : null);
    const d = drag.current;
    if (!d) return;
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) d.moved = true;
    if (!d.moved) return;
    const k = Math.max(d.vb.w / Math.max(size.w, 1), d.vb.h / Math.max(size.h, 1));
    setVb({ ...d.vb, x: d.vb.x - (e.clientX - d.x) * k, y: d.vb.y - (e.clientY - d.y) * k });
  };
  const onUp = (e: React.PointerEvent<SVGSVGElement>) => {
    if (calibrate && !drag.current?.moved) {
      const p = svgPoint(e.clientX, e.clientY);
      if (p) setPoint(normalizedPoint(p.x, p.y, W, H));
    }
    drag.current = null;
  };

  const markers = [...results].filter((r) => boxFor(r))
    .sort((a, b) => statusRank[a.status] - statusRank[b.status]).slice(0, markerLimit);
  const unit = Math.max(vb.w / Math.max(size.w, 1), vb.h / Math.max(size.h, 1));
  const allProblems = [...results].filter(r => r.status !== "PASS").sort((a,b) => statusRank[a.status] - statusRank[b.status]);
  const visibleBox = { x: vb.x-(Math.max(0,size.w/Math.max(size.h,1)*vb.h-vb.w)/2), y:vb.y-(Math.max(0,size.h/Math.max(size.w,1)*vb.w-vb.h)/2), w:Math.max(vb.w,size.w/Math.max(size.h,1)*vb.h), h:Math.max(vb.h,size.h/Math.max(size.w,1)*vb.w) };
  const offscreen = markers.filter(r => { const b=boxFor(r); return b && (b.x+b.w<visibleBox.x || b.x>visibleBox.x+visibleBox.w || b.y+b.h<visibleBox.y || b.y>visibleBox.y+visibleBox.h); });
  return <div className="drawing-sheet flex h-full min-h-0 flex-col overflow-hidden bg-card">
    {!compact && <div className="flex h-8 shrink-0 items-center justify-between border-b px-2">
      <span className="font-mono text-xs">{reference ? "RCRV · DECK 01 · GA 6096-070-001" : fileName ?? "Drawing"}</span>
      <div className="flex">{!reference && <select value={page} onChange={e => setPage(+e.target.value)} className="border bg-background font-mono text-xs" aria-label="Page">{(pdfPages.length ? pdfPages : pages).map(p => <option key={p} value={p}>Page {p}</option>)}</select>}
      <Button variant="ghost" onClick={() => zoom(1.3)} aria-label="Zoom out">−</Button><Button variant="ghost" onClick={() => setVb(fit)}>Fit</Button><Button variant="ghost" onClick={() => zoom(1/1.3)} aria-label="Zoom in">+</Button></div>
    </div>}
    <svg ref={svgRef} aria-label="Inspection drawing" viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} className="block min-h-0 w-full flex-1 cursor-grab touch-none bg-canvas active:cursor-grabbing"
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={() => { drag.current = null; }} preserveAspectRatio="xMidYMid meet">
      {reference ? <image className="drawing-image" opacity={markers.length ? .55 : 1} href={referenceDrawing.url} x={0} y={0} width={W} height={H} /> : img && <image opacity={markers.length ? .55 : 1} href={img.src} x={0} y={0} width={W} height={H} />}
      {[...markers].sort((a,b) => (a.status === "UNKNOWN" ? -1 : 1) - (b.status === "UNKNOWN" ? -1 : 1)).map((r) => {
        const b = boxFor(r);
        if (!b) return null;
        const color = statusColorVar[r.status];
        const number = allProblems.findIndex(p => p.id === r.id) + 1;
        const duplicates = markers.slice(0, markers.indexOf(r)).filter(p => JSON.stringify(boxFor(p)) === JSON.stringify(b)).length;
        const bx = b.x + b.w + (30 + duplicates * 32) * unit;
        const by = b.y + b.h * .25 + duplicates * 28 * unit;
        return <g key={r.id} data-element={r.element_id} data-finding={r.id} data-marker={r.status} className={`cursor-pointer ${hoveredResultId===r.id?'cloud-hovered':''}`} onMouseEnter={()=>onHoverResult?.(r.id)} onMouseLeave={()=>onHoverResult?.(null)}
          onPointerDown={(e) => { if (!calibrate) e.stopPropagation(); }}
          onClick={(e) => { if (!calibrate) { e.stopPropagation(); onSelectElement(r.element_id, r.id); onWhy?.(); } }}>
          {r.status==='PASS' ? <rect x={b.x} y={b.y} width={b.w} height={b.h} fill="none" stroke={color} strokeWidth={hoveredResultId===r.id?2:1} vectorEffect="non-scaling-stroke"/> : <path className="redline-cloud" d={revisionCloud(b, 18 * unit)} pathLength={1} fill={r.status==='FAIL'?'var(--redline-fill)':'none'} stroke={color} strokeWidth={hoveredResultId===r.id?5:3} strokeDasharray={r.status === "UNKNOWN" ? "0.012 0.008" : undefined} vectorEffect="non-scaling-stroke" />}
          <line x1={b.x + b.w} y1={b.y + b.h / 2} x2={bx} y2={by} stroke={color} strokeWidth={1} vectorEffect="non-scaling-stroke" />
          <circle cx={bx} cy={by} r={(r.status==='PASS'?9:13) * unit} fill="var(--card)" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
          <text x={bx} y={by + 4 * unit} textAnchor="middle" fontSize={13 * unit} fontWeight={600} fontFamily="var(--font-mono)" fill={color}>{r.status==='PASS'?'✓':r.status === "UNKNOWN" ? "?" : number}</text>
        </g>;
      })}
      {calibrate && point && <g pointerEvents="none"><path d={`M ${point.x * W - 8 * unit} ${point.y * H} h ${16 * unit} M ${point.x * W} ${point.y * H - 8 * unit} v ${16 * unit}`} stroke="var(--foreground)" vectorEffect="non-scaling-stroke" /></g>}
    </svg>
    {offscreen.map((r,i)=>{ const b=boxFor(r); if(!b)return null; const left=b.x<visibleBox.x, right=b.x>visibleBox.x+visibleBox.w; return <Button key={r.id} variant="ghost" className={`edge-marker ${left?'edge-left':right?'edge-right':b.y<visibleBox.y?'edge-top':'edge-bottom'}`} style={{'--edge-index':i} as React.CSSProperties} aria-label={`Show off-screen note ${allProblems.findIndex(p=>p.id===r.id)+1}`} onClick={()=>onSelectElement(r.element_id,r.id)}>{left?'←':right?'→':b.y<visibleBox.y?'↑':'↓'} {r.status==='PASS'?'✓':allProblems.findIndex(p=>p.id===r.id)+1}</Button>; })}
    {markers.length>0 && <svg className="drawing-minimap" aria-label="Drawing overview minimap" viewBox={`0 0 ${W} ${H}`} onClick={e=>{ const rect=e.currentTarget.getBoundingClientRect(); const x=(e.clientX-rect.left)/rect.width*W,y=(e.clientY-rect.top)/rect.height*H; setVb(v=>({...v,x:x-v.w/2,y:y-v.h/2})); }}><image href={reference?referenceDrawing.url:img?.src} width={W} height={H}/>{markers.map(r=>{const b=boxFor(r);return b?<circle key={r.id} cx={b.x+b.w/2} cy={b.y+b.h/2} r={22} fill={statusColorVar[r.status]} onClick={e=>{e.stopPropagation();onSelectElement(r.element_id,r.id);}}/>:null;})}<rect x={visibleBox.x} y={visibleBox.y} width={visibleBox.w} height={visibleBox.h} fill="none" stroke="var(--foreground)" strokeWidth={2} vectorEffect="non-scaling-stroke"/></svg>}
    {calibrate && <output aria-label="Calibration coordinates" className="calibration-coordinates">{point ? `x ${point.x.toFixed(4)} · y ${point.y.toFixed(4)}` : "Calibration · x — · y —"}</output>}
    {reference && <table className="drawing-title-block" aria-label="Drawing title block"><tbody>
      <tr><td>VESSEL</td><td>RCRV</td></tr>
      <tr><td>DRAWING</td><td>GA 6096-070-001</td></tr>
      <tr><td>REV</td><td>J</td></tr>
      <tr><td>SCALE</td><td>1/8&quot; = 1&apos;-0&quot;</td></tr>
      <tr><td>CHECKED BY</td><td>ProvenAI · DEMO</td></tr>
    </tbody></table>}
  </div>;
}
