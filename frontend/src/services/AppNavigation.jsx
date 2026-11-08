import { createContext } from "react";

// Shared sidebar actions use App's history/owner handling on every page.
export const AppNavigation = createContext({ onMonitoring: null, onDashboard: null });
