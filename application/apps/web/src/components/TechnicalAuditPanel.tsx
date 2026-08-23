import type { AuditEvent } from "@/lib/types";

export function TechnicalAuditPanel({ events }: { events: AuditEvent[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-3">Tool</th>
            <th className="px-4 py-3">Input</th>
            <th className="px-4 py-3">Output</th>
            <th className="px-4 py-3">Duration</th>
            <th className="px-4 py-3">Timestamp</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {events.map((event, idx) => (
            <tr key={idx}>
              <td className="px-4 py-3 font-mono text-xs text-slate-800">{event.tool_name}</td>
              <td className="px-4 py-3 max-w-xs">
                <pre className="whitespace-pre-wrap break-words text-[11px] text-slate-500">
                  {JSON.stringify(event.input_summary, null, 1)}
                </pre>
              </td>
              <td className="px-4 py-3 max-w-xs">
                <pre className="whitespace-pre-wrap break-words text-[11px] text-slate-500">
                  {JSON.stringify(event.output_summary, null, 1)}
                </pre>
              </td>
              <td className="px-4 py-3 text-xs text-slate-500">
                {event.duration_ms != null ? `${event.duration_ms.toFixed(1)} ms` : "n/a"}
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(event.created_at).toLocaleTimeString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
