import { Navigate, Route, Routes } from "react-router-dom";

import Dashboard from "../pages/Dashboard/Dashboard";
import Materials from "../pages/Materials/Materials";
import MatchReview from "../pages/MatchReview/MatchReview";
import CommonMaterials from "../pages/CommonMaterials/CommonMaterials";
import Mappings from "../pages/Mappings/Mappings";
import ERPIntegration from "../pages/ERPIntegration/ERPIntegration";
import Analytics from "../pages/Analytics/Analytics";
import AuditTrail from "../pages/AuditTrail/AuditTrail";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/materials" element={<Materials />} />
      <Route path="/match-review" element={<MatchReview />} />
      <Route path="/common-materials" element={<CommonMaterials />} />
      <Route path="/mappings" element={<Mappings />} />
      <Route path="/erp-integration" element={<ERPIntegration />} />
      <Route path="/analytics" element={<Analytics />} />
      <Route path="/audit-trail" element={<AuditTrail />} />
      <Route
        path="/settings"
        element={
          <div className="page">
            <div className="page-header">
              <div>
                <span className="eyebrow">SYSTEM CONFIGURATION</span>
                <h1>Settings</h1>
                <p>Configure workspace and integration preferences.</p>
              </div>
            </div>

            <div className="placeholder">
              <h2>Settings</h2>
              <p>This workspace will be built in the next step.</p>
            </div>
          </div>
        }
      />
    </Routes>
  );
}

export default AppRoutes;
