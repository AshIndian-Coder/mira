import type { ReactNode } from "react";

type BadgeProps = {
  children: ReactNode;
  variant?: "review" | "success" | "neutral" | "danger" | "warning" | "info";
  className?: string;
};

function Badge({ children, variant = "neutral", className = "" }: BadgeProps) {
  return (
    <span
      className={`status-badge ${variant} ${className}`.trim()}
      style={{
        display: "inline-flex",
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        whiteSpace: "nowrap",
        flexShrink: 0,
        gap: "5px",
      }}
    >
      <span
        className="status-dot"
        style={{
          width: "6px",
          height: "6px",
          minWidth: "6px",
          minHeight: "6px",
          borderRadius: "50%",
          display: "inline-block",
          flexShrink: 0,
          margin: 0,
          padding: 0,
        }}
      />
      <span className="status-text" style={{ display: "inline", whiteSpace: "nowrap" }}>
        {children}
      </span>
    </span>
  );
}

export default Badge;
