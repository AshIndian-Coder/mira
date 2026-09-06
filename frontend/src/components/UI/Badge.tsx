import type { ReactNode } from "react";

type BadgeProps = {
  children: ReactNode;
  variant?: "review" | "success" | "neutral";
};

function Badge({ children, variant = "neutral" }: BadgeProps) {
  return (
    <span className={`status-badge ${variant}`}>
      {children}
    </span>
  );
}

export default Badge;
