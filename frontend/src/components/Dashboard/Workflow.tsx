const steps = [
  {
    number: "01",
    title: "Ingest",
    description: "Material sources",
  },
  {
    number: "02",
    title: "Match",
    description: "AI candidate detection",
  },
  {
    number: "03",
    title: "Review",
    description: "Human validation",
  },
  {
    number: "04",
    title: "Harmonize",
    description: "Common material",
  },
  {
    number: "05",
    title: "Map",
    description: "CPSE → NMC",
  },
];

function Workflow() {
  return (
    <div className="workflow">
      {steps.map((step, index) => (
        <div key={step.number} className="workflow-group">
          <div
            className={`workflow-step ${
              index < 2 ? "active" : ""
            }`}
          >
            <span>{step.number}</span>
            <strong>{step.title}</strong>
            <small>{step.description}</small>
          </div>

          {index < steps.length - 1 && (
            <div className="workflow-line" />
          )}
        </div>
      ))}
    </div>
  );
}

export default Workflow;
