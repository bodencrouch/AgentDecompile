import { createRoot } from "react-dom/client";
import { App } from "./App";
import { installWorkspaceFlush } from "./workspaceState";
import "./style.css";

installWorkspaceFlush();
createRoot(document.getElementById("root")!).render(<App />);
