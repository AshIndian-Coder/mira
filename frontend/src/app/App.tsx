import { BrowserRouter } from "react-router-dom";
import AppShell from "../components/Layout/AppShell";
import AppRoutes from "./routes";

function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <AppRoutes />
      </AppShell>
    </BrowserRouter>
  );
}

export default App;
