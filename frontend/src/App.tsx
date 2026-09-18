import type { ReactNode } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import "./app.css";
import AnimatedBackground from "./components/AnimatedBackground";
import AccountMenu from "./components/AccountMenu";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Investigate from "./pages/Investigate";
import History from "./pages/History";
import Sandbox from "./pages/Sandbox";
import { RequireAuth, useAuth } from "./auth";

function NavBar() {
  return (
    <header className="top-nav">
      <span className="typewriter top-nav-title">ECHOTRACE</span>
      <nav className="top-nav-links">
        <NavLink to="/app" className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}>
          Investigate
        </NavLink>
        <NavLink to="/history" className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}>
          History
        </NavLink>
        <NavLink to="/sandbox" className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}>
          Sandbox
        </NavLink>
      </nav>
      <AccountMenu />
    </header>
  );
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell-v2">
      <NavBar />
      <main className="app-main">{children}</main>
    </div>
  );
}

export default function App() {
  const { loggedIn } = useAuth();

  return (
    <>
      <AnimatedBackground />
      <Routes>
        <Route path="/login" element={loggedIn ? <Navigate to="/app" replace /> : <Login />} />
        <Route path="/register" element={loggedIn ? <Navigate to="/app" replace /> : <Register />} />
        <Route
          path="/app"
          element={
            <RequireAuth>
              <AppShell>
                <Investigate />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/history"
          element={
            <RequireAuth>
              <AppShell>
                <History />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route
          path="/sandbox"
          element={
            <RequireAuth>
              <AppShell>
                <Sandbox />
              </AppShell>
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to={loggedIn ? "/app" : "/login"} replace />} />
      </Routes>
    </>
  );
}
