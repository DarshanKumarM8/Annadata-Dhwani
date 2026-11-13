// Owner: Darshan. Each route file belongs to one person (TASK_DIVISION.md §3, C1).
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Login from "./routes/Login";
import Buyer from "./routes/Buyer"; // Nahyan
import Sim from "./routes/Sim"; // Hitesh
import Agent from "./routes/Agent"; // Anirudh
import Ops from "./routes/Ops"; // Anirudh
import { API_BASE } from "./lib/api";

const links = [
  ["/buyer", "Buyer"],
  ["/sim", "Phone simulator"],
  ["/agent", "FPO agent"],
  ["/ops", "Ops"],
  ["/login", "Login"],
] as const;

export default function App() {
  return (
    <div className="flex min-h-full flex-col">
      <nav className="flex flex-wrap items-center gap-1 bg-green-800 px-4 py-2 text-sm text-white">
        <span className="mr-4 font-semibold">अन्नदाता ध्वनि · Annadata Dhwani</span>
        {links.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `rounded px-3 py-1 ${isActive ? "bg-green-950" : "hover:bg-green-700"}`
            }
          >
            {label}
          </NavLink>
        ))}
        <span className="ml-auto text-xs text-green-200">API: {API_BASE}</span>
      </nav>
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Navigate to="/buyer" replace />} />
          <Route path="/login" element={<Login />} />
          <Route path="/buyer" element={<Buyer />} />
          <Route path="/sim" element={<Sim />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/ops" element={<Ops />} />
          <Route path="*" element={<p className="p-6">Not found</p>} />
        </Routes>
      </main>
    </div>
  );
}
