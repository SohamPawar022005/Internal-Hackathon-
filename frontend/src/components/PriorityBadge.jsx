/**
 * PriorityBadge — displays the priority level as a color-coded badge.
 *
 * Props:
 *   level: 'critical' | 'high' | 'medium' | 'low'
 *
 * TODO:
 *   - Map level to color: critical=red, high=orange, medium=yellow, low=green
 *   - Render as a pill/badge with icon from lucide-react
 */

const COLORS = {
  critical: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-green-100 text-green-800',
};

export default function PriorityBadge({ level = 'medium' }) {
  const colorClass = COLORS[level] || COLORS.medium;
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClass}`}>
      {level.toUpperCase()}
    </span>
  );
}
