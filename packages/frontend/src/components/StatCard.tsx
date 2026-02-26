/**
 * Stat card — displays a single metric with label and optional trend.
 */

interface StatCardProps {
  label: string;
  value: string | number;
  detail?: string;
  color?: string;
}

export function StatCard({ label, value, detail, color }: StatCardProps) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={color ? { color } : undefined}>
        {value}
      </div>
      {detail && <div className="stat-detail">{detail}</div>}
    </div>
  );
}
