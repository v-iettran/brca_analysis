import { exportUrl } from "@/lib/api";

export function ExportButtons({ runId }: { runId: string }) {
  return (
    <div className="flex items-center rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
      <a
        href={exportUrl(runId, "pdf")}
        className="rounded-md bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-700"
        title="Download print-ready clinician report"
      >
        PDF
      </a>
      <a
        href={exportUrl(runId, "json")}
        className="rounded-md px-2.5 py-1.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
        title="Export complete JSON audit"
      >
        JSON
      </a>
      <a
        href={exportUrl(runId, "csv")}
        className="rounded-md px-2.5 py-1.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
        title="Export drug evidence as CSV"
      >
        CSV
      </a>
    </div>
  );
}
