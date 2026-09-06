import { Database } from "lucide-react";

type PlaceholderProps = {
  title: string;
  description?: string;
};

function Placeholder({
  title,
  description = "This workspace will be built in the next step.",
}: PlaceholderProps) {
  return (
    <div className="placeholder">
      <Database size={28} />
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

export default Placeholder;
