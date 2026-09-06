import StatCard from "../../components/Dashboard/StatCard";
import Workflow from "../../components/Dashboard/Workflow";

function Dashboard() {
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <span className="eyebrow">
            NATIONAL MATERIAL GOVERNANCE
          </span>

          <h1>Overview</h1>

          <p>
            Monitor material harmonization across participating
            CPSEs.
          </p>
        </div>
      </div>

      <div className="stats-grid">
        <StatCard
          label="Total Materials"
          value="43,301"
          description="Across connected sources"
        />

        <StatCard
          label="Matches Identified"
          value="8,742"
          description="Candidate relationships"
        />

        <StatCard
          label="Pending Review"
          value="326"
          description="Require human validation"
        />

        <StatCard
          label="Harmonized"
          value="6,184"
          description="Approved mappings"
        />
      </div>

      <div className="section-card">
        <div className="section-header">
          <div>
            <h2>Harmonization Workflow</h2>
            <p>
              Current state of the material standardization
              pipeline.
            </p>
          </div>
        </div>

        <Workflow />
      </div>
    </div>
  );
}

export default Dashboard;
