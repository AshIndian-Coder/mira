import { NavLink } from "react-router-dom";
import {
  BarChart3,
  ClipboardCheck,
  Database,
  FileSearch,
  GitBranch,
  History,
  LayoutDashboard,
  Link2,
  Settings,
  Users,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

const navigation = [
  {
    label: "Overview",
    path: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    label: "Materials",
    path: "/materials",
    icon: Database,
  },
  {
    label: "Match Review",
    path: "/match-review",
    icon: ClipboardCheck,
  },
  {
    label: "Common Materials",
    path: "/common-materials",
    icon: FileSearch,
  },
  {
    label: "Mappings",
    path: "/mappings",
    icon: Link2,
  },
  {
    label: "ERP Integration",
    path: "/erp-integration",
    icon: GitBranch,
  },
  {
    label: "Analytics",
    path: "/analytics",
    icon: BarChart3,
  },
  {
    label: "Audit Trail",
    path: "/audit-trail",
    icon: History,
  },
];

function Sidebar() {
  const { isAdmin } = useAuth();

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">M</div>

        <div>
          <strong>MIRA</strong>
          <span>Material Intelligence</span>
        </div>
      </div>

      <nav className="navigation">
        <span className="nav-heading">WORKSPACE</span>

        {navigation.map(({ label, path, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              `nav-item ${isActive ? "active" : ""}`
            }
          >
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}

        {isAdmin && (
          <>
            <span className="nav-heading" style={{ marginTop: "12px" }}>
              ADMINISTRATION
            </span>
            <NavLink
              to="/users"
              className={({ isActive }) =>
                `nav-item ${isActive ? "active" : ""}`
              }
            >
              <Users size={18} />
              <span>User Directory</span>
            </NavLink>
          </>
        )}
      </nav>

      <div className="sidebar-bottom">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `nav-item ${isActive ? "active" : ""}`
          }
        >
          <Settings size={18} />
          <span>Settings</span>
        </NavLink>

        <div className="environment">
          <span className="environment-dot" />

          <div>
            <strong>Prototype Environment</strong>
            <small>Integration ready</small>
          </div>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
