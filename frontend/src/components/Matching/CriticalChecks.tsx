const checks = [
  ["Material grade", "MATCH"],
  ["Pressure rating", "MATCH"],
  ["Dimensions", "MATCH"],
];

function CriticalChecks() {
  return (
    <div className="critical-checks">
      <h3>Critical Checks</h3>

      {checks.map(([label, status]) => (
        <div className="check-row" key={label}>
          <span>✓</span>
          <span>{label}</span>
          <strong>{status}</strong>
        </div>
      ))}
    </div>
  );
}

export default CriticalChecks;
