/**
 * RoutingCard — shows how a complaint was (or would be) routed:
 * category, owning department, crisis flag, urgency, matched keywords.
 *
 * Works with both the /complaints/route-preview response and the
 * `routing` block returned inside a submitted complaint.
 *
 * Props:
 *   routing  — RouteResult object (or null)
 *   compact  — hide the keyword / alternatives detail
 */

const URGENCY_STYLES = {
  critical: 'bg-red-100 text-red-800 border-red-200',
  high: 'bg-orange-100 text-orange-800 border-orange-200',
  medium: 'bg-amber-100 text-amber-800 border-amber-200',
  low: 'bg-slate-100 text-slate-700 border-slate-200',
};

export default function RoutingCard({ routing, compact = false }) {
  if (!routing) return null;

  const {
    category,
    department,
    confidence,
    urgency,
    is_crisis: isCrisis,
    crisis_type: crisisType,
    crisis_department: crisisDept,
    matched_keywords: matched = [],
    urgency_signals: signals = [],
    alternatives = [],
  } = routing;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-3">
      {isCrisis && (
        <div className="flex items-start gap-2 rounded-md bg-red-600 px-3 py-2 text-white">
          <svg className="w-5 h-5 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
            <line x1="12" x2="12" y1="9" y2="13" /><line x1="12" x2="12.01" y1="17" y2="17" />
          </svg>
          <div className="text-sm">
            <p className="font-semibold">
              Emergency detected{crisisType ? ` — ${crisisType.replace(/_/g, ' ')}` : ''}
            </p>
            <p className="text-red-50">
              Fast-tracked to <strong>{crisisDept || department}</strong>.
            </p>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Routed to
        </span>
        <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-sm font-medium text-blue-700">
          {category}
        </span>
        <span className="text-gray-400">→</span>
        <span className="text-sm font-semibold text-gray-800">{department}</span>
        <span
          className={`ml-auto rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${
            URGENCY_STYLES[urgency] || URGENCY_STYLES.low
          }`}
        >
          {urgency} urgency
        </span>
      </div>

      {typeof confidence === 'number' && (
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span>Match confidence</span>
          <div className="h-1.5 flex-1 rounded-full bg-gray-100">
            <div
              className="h-1.5 rounded-full bg-blue-500"
              style={{ width: `${Math.round(confidence * 100)}%` }}
            />
          </div>
          <span>{Math.round(confidence * 100)}%</span>
        </div>
      )}

      {!compact && (matched.length > 0 || signals.length > 0) && (
        <div className="flex flex-wrap gap-1.5">
          {matched.slice(0, 8).map((k) => (
            <span key={k} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
              {k}
            </span>
          ))}
          {signals.map((k) => (
            <span key={k} className="rounded bg-orange-50 px-1.5 py-0.5 text-xs text-orange-700">
              ⚠ {k}
            </span>
          ))}
        </div>
      )}

      {!compact && alternatives.length > 0 && (
        <p className="text-xs text-gray-400">
          Other possible: {alternatives.map((a) => a.category).join(', ')}
        </p>
      )}
    </div>
  );
}
