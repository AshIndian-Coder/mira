const scores = [
  ["Text similarity", "94%"],
  ["Semantic similarity", "91%"],
  ["Specification similarity", "100%"],
  ["Grade similarity", "100%"],
];

function ScoreGrid() {
  return (
    <div className="score-grid">
      {scores.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

export default ScoreGrid;
