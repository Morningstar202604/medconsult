import { useEffect, useState } from "react";
import { clearAuth, getUser, Me, setAuth } from "./api";
import Login from "./pages/Login";
import Layout from "./components/Layout";

function parseHash(): string {
  const h = window.location.hash.replace(/^#\/?/, "");
  return h.split("?")[0] || "dashboard";
}

export default function App() {
  const [user, setUser] = useState<Me | null>(getUser());
  const [page, setPage] = useState<string>(parseHash());

  useEffect(() => {
    const onHash = () => setPage(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (!user) {
    return (
      <Login
        onLogin={(token, u) => {
          setAuth(token, u);
          setUser(u);
          window.location.hash = "#/dashboard";
        }}
      />
    );
  }

  const logout = () => {
    clearAuth();
    setUser(null);
    window.location.hash = "#/login";
  };

  return <Layout user={user} page={page} onNavigate={(p) => (window.location.hash = "#/" + p)} onLogout={logout} />;
}
