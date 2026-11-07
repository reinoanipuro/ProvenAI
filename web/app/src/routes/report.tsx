import { createFileRoute } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { api, DEMO_ID, qk } from '@/lib/api';
import { DailyReport } from '@/components/app/DailyReport';
import { useCheckedDrawings } from '@/lib/checkerSession';
import { useSettings } from '@/lib/settings';
export const Route = createFileRoute('/report')({ head: () => ({ meta: [ { title: 'Daily engineering report — ProvenAI' }, { name: 'description', content: 'Daily drawing checks, open nonconformities and information requests in a printable engineering report.' }, { property: 'og:title', content: 'Daily engineering report — ProvenAI' }, { property: 'og:description', content: 'Traceable compliance totals, redline crops and supervisor sign-off.' }, { property:'og:type', content:'website' }, { name:'twitter:card', content:'summary_large_image' } ] }), component: ReportPage });
function ReportPage() {
  const settings = useSettings(), checks = useCheckedDrawings();
  const id = checks.at(-1)?.inspection.id ?? DEMO_ID;
  const { data } = useQuery({ queryKey:['inspection',id,...qk.all()], queryFn:()=>api.inspection(id) });
  const { data:previous } = useQuery({ queryKey:['inspection',data?.previous_revision?.id,...qk.all()], queryFn:()=>api.inspection(data?.previous_revision?.id ?? ''), enabled:!!data?.previous_revision });
  return data ? <DailyReport insp={data} previous={previous} demo={settings.demo}/> : <p className="p-4 font-mono text-xs">READING REPORT DATA</p>;
}
