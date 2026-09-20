import type { ReactNode } from "react";

type BadgeProps = {
  children: ReactNode;
  variant?: "review" | "success" | "neutral" | "danger" | "warning" | "info";
  className?: string;
};

function Badge({ children, variant = "neutral", className = "" }: BadgeProps) {
  return (
    <span className={`status-badge ${variant} ${className}`.trim()}>
      <span className="status-dot" style={{ width: '6px', height: '6px' }} />
      {children}
    </span>
  );
}

export default Badge;
