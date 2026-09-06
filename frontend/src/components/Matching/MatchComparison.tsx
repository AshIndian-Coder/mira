import Badge from "../UI/Badge";
import Button from "../UI/Button";
import CriticalChecks from "./CriticalChecks";
import ScoreGrid from "./ScoreGrid";

function MaterialPanel({
  source,
  code,
  description,
}: {
  source: string;
  code: string;
  description: string;
}) {
  return (
    <div className="material-panel">
      <span className="source-label">{source}</span>

      <h3>{code}</h3>

      <p>{description}</p>

      <div className="attribute">
        <span>Material</span>
        <strong>SS304</strong>
      </div>

      <div className="attribute">
        <span>Size</span>
        <strong>2 inch / 50.8 mm</strong>
      </div>

      <div className="attribute">
        <span>Pressure</span>
        <strong>150 LB / Class 150</strong>
      </div>
    </div>
  );
}

function MatchComparison() {
  return (
    <div className="section-card comparison">
      <div className="section-header">
        <div>
          <span className="eyebrow">CANDIDATE COMPARISON</span>
          <h2>Potential Equivalent Materials</h2>
        </div>

        <Badge variant="review">REVIEW</Badge>
      </div>

      <div className="material-columns">
        <MaterialPanel
          source="CPSE A · IOCL"
          code="10003741"
          description="SS304 GATE VALVE 2 IN 150 LB FLG"
        />

        <MaterialPanel
          source="CPSE B · ONGC"
          code="VAL-00921"
          description="SS 304 GATE VALVE 50.8MM CLASS 150"
        />
      </div>

      <div className="score-section">
        <h3>AI Assessment</h3>
        <ScoreGrid />
      </div>

      <CriticalChecks />

      <div className="decision">
        <div>
          <span>Final score</span>
          <strong>94%</strong>
        </div>

        <div className="decision-actions">
          <Button>Reject</Button>
          <Button>Keep for Review</Button>
          <Button variant="primary">Approve Mapping</Button>
        </div>
      </div>
    </div>
  );
}

export default MatchComparison;
