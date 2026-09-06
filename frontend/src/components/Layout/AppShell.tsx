import type { ReactNode } from "react";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <Sidebar />

      <main className="main-content">
        <Topbar />
        {children}
      </main>
    </div>
  );
}

export default AppShell;
