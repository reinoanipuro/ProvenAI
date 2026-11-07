import { useEffect, useRef, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { CheckerHeader } from './CheckerHeader';
import { CheckerWorkspace } from './CheckerWorkspace';
import { DrawingViewer } from './DrawingViewer';
import { api, DEMO_ID } from '@/lib/api';
import reference from '@/assets/rcrv-deck01-cabins.png.asset.json';

export function DrawingStart({ calibrate }: { calibrate: boolean }) {
  const [loaded,setLoaded] = useState(false), [loading,setLoading] = useState(false), [lines,setLines] = useState<string[]>([]), [over,setOver] = useState(false);
  const [file,setFile] = useState<{name:string;url:string}|null>(null), [message,setMessage] = useState('');
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => { if(file) URL.revokeObjectURL(file.url); }, [file]);
  useEffect(() => { const listener = (event: Event) => { if((event as CustomEvent<string>).detail==='load') { setLoaded(false); setFile(null); } }; window.addEventListener('checker-command',listener); return()=>window.removeEventListener('checker-command',listener); }, []);
  async function loadTest() {
    if(loading) return; setLoading(true); setMessage('');
    try {
      const start = Date.now();
      const inspection = await api.inspection(DEMO_ID);
      setLines(['Reading 6096-070-001 GA rev J, page 10 · test fixture … ok']);
      const image = new Image(); image.src = reference.url; await image.decode();
      await new Promise(resolve=>window.setTimeout(resolve,Math.max(0,500-(Date.now()-start))));
      setLines(previous=>[...previous, 'Scale 1/8" = 1\'-0" · drawing metadata … ok']);
      await new Promise(resolve=>window.setTimeout(resolve,500));
      setLines(previous=>[...previous, `${inspection.elements.filter(e=>e.type==='door').length} doors, ${inspection.elements.filter(e=>e.type==='cabin').length} spaces loaded · illustrative demo evidence … ok`]);
      await new Promise(resolve=>window.setTimeout(resolve,500)); setLoaded(true);
    } catch { setMessage('Test drawing could not be loaded. Try again.'); } finally { setLoading(false); }
  }
  function openFile(files: FileList | null) {
    const next = files?.[0]; if(!next) return;
    if(next.name.toLowerCase().endsWith('.pdf')) { setFile({name:next.name,url:URL.createObjectURL(next)}); setMessage('PDF preview only. Evidence extraction requires the connected inspection service; no test findings are applied to your file.'); }
    else if(/\.(ifc|json)$/i.test(next.name)) setMessage('IFC and design JSON extraction require the connected inspection service. Open a new inspection to send this file. Demo mode does not extract uploaded files.');
    else setMessage('Choose a PDF, IFC or design JSON file.');
  }
  if(loaded) return <CheckerWorkspace id={DEMO_ID} calibrate={calibrate} loadLines={lines}/>;
  return <div className="drawing-start no-print">
    <input hidden ref={input} type="file" accept=".pdf,.ifc,.json" onChange={e=>{openFile(e.target.files);e.target.value='';}}/>
    <CheckerHeader loaded={!!file} title={file?.name} running={loading} onLoad={loadTest}/>
    <section className={`empty-sheet ${over?'drag-over':''}`} aria-label="Drawing drop zone" onDragOver={e=>{e.preventDefault();setOver(true);}} onDragLeave={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))setOver(false);}} onDrop={e=>{e.preventDefault();setOver(false);openFile(e.dataTransfer.files);}}>
      {file ? <><header className="canvas-heading">DRAWING · {file.name}<Button variant="ghost" onClick={()=>setFile(null)}>CLOSE</Button></header><DrawingViewer compact elements={[]} results={[]} selectedElementId={null} onSelectElement={()=>{}} pdfUrl={file.url} fileName={file.name}/><div className="file-preview-message">{message} <Button asChild variant="outline"><Link to="/inspections/new">NEW INSPECTION</Link></Button></div></> : <>
      <div className="empty-sheet-copy"><h1>NO DRAWING LOADED</h1><p>Drop a general arrangement drawing here (PDF, IFC or design JSON)</p><div><Button variant="ghost" onClick={()=>input.current?.click()} aria-label="Browse drawing files">OPEN FILE</Button></div>{message && <p role="status">{message} <Link to="/inspections/new">New inspection</Link></p>}</div>
      {loading && <aside className="loading-margin"><h2>CHECKER'S NOTES</h2>{lines.map(line=><p key={line}>{line}</p>)}</aside>}
      <table className="drawing-title-block" aria-label="Empty drawing title block"><tbody>{['VESSEL','DRAWING','REV'].map(label=><tr key={label}><td>{label}</td><td>—</td></tr>)}</tbody></table>
      </>}
    </section>
  </div>;
}
