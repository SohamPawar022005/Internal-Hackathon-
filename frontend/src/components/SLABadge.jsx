/**
 * SLABadge — shows whether a complaint is within or past its SLA deadline.
 *
 * Props:
 *   deadline: string (ISO date) — SLA deadline
 *   resolvedAt: string | null — when resolved (null if still open)
 *
 * TODO:
 *   - Compare deadline to now (or resolvedAt)
 *   - Green if within SLA, red if breached
 *   - Show "X days remaining" or "Breached by X days"
 */

export default function SLABadge({ deadline, resolvedAt = null }) {
  // TODO: implement SLA calculation logic
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
      SLA: {deadline ? 'Pending' : 'N/A'}
    </span>
  );
}
