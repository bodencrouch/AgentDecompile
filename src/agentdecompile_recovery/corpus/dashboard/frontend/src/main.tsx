import { createRoot } from "react-dom/client";
import { WorkstationApp } from "./workstation/WorkstationApp";
import { installWorkspaceFlush } from "./workspaceState";

installWorkspaceFlush();
createRoot(document.getElementById("root")!).render(<WorkstationApp />);
