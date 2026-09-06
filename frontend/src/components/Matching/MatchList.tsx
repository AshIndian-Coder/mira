const matches = [
  {
    source: "IOCL · 10003741",
    description: "SS304 GATE VALVE 2 IN 150 LB FLG",
    score: "94%",
  },
  {
    source: "ONGC · VAL-00921",
    description: "SS 304 GATE VALVE 50.8MM CLASS 150",
    score: "91%",
  },
  {
    source: "BPCL · BV-004821",
    description: 'STAINLESS STEEL GATE VALVE 2"',
    score: "87%",
  },
];

function MatchList() {
  return (
    <div className="section-card match-list">
      <div className="section-header">
        <div>
          <h2>Candidate Matches</h2>
          <p>Sorted by review priority.</p>
        </div>
      </div>

      {matches.map((match, index) => (
        <div
          key={match.source}
          className={`match-item ${
            index === 0 ? "selected" : ""
          }`}
        >
          <div>
            <strong>{match.source}</strong>
            <span>{match.description}</span>
          </div>

          <b>{match.score}</b>
        </div>
      ))}
    </div>
  );
}

export default MatchList;
