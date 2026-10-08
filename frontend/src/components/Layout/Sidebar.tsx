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
import type { UserRole } from "../../lib/api";

interface NavItem {
  label: string;
  path: string;
  icon: typeof LayoutDashboard;
  /** Omit to allow every authenticated role. */
  roles?: UserRole[];
}

const navigation: NavItem[] = [
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
    // view_audit is admin, data_steward and auditor only — reviewers excluded.
    roles: ["admin", "data_steward", "auditor"],
  },
];

function Sidebar() {
  const { isAdmin, hasRole } = useAuth();

  const visibleNavigation = navigation.filter(
    (item) => !item.roles || hasRole(item.roles),
  );

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

        {visibleNavigation.map(({ label, path, icon: Icon }) => (
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
