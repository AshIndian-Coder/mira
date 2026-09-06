import MatchList from "../../components/Matching/MatchList";
import MatchComparison from "../../components/Matching/MatchComparison";

function MatchReview() {
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <span className="eyebrow">
            AI-ASSISTED VALIDATION
          </span>

          <h1>Match Review</h1>

          <p>
            Review candidate material equivalences before
            harmonization.
          </p>
        </div>

        <span className="review-count">326 pending</span>
      </div>

      <div className="review-layout">
        <MatchList />
        <MatchComparison />
      </div>
    </div>
  );
}

export default MatchReview;
