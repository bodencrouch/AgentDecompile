import { lazy, Suspense, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { installWorkspaceFlush } from "./workspaceState";
import { chooseView, type AppView } from "./cockpit/viewRoute";

// The cockpit is the default view at /react/; every workstation view stays reachable
// at #workstation and through existing ?slug=…&view=… deep links.
const Cockpit = lazy(() => import("./cockpit/Cockpit").then(m => ({ default: m.Cockpit })));
const WorkstationApp = lazy(() => import("./workstation/WorkstationApp").then(m => ({ default: m.WorkstationApp })));

function Root() {
  const [view, setView] = useState<AppView>(() => chooseView(location.hash, location.search));
  useEffect(() => {
    const sync = () => setView(chooseView(location.hash, location.search));
    addEventListener("hashchange", sync);
    addEventListener("popstate", sync);
    return () => {
      removeEventListener("hashchange", sync);
      removeEventListener("popstate", sync);
    };
  }, []);
  useEffect(() => {
    if (view === "workstation") document.title = "AgentDecompile · Workstation";
  }, [view]);
  return <Suspense fallback={null}>{view === "cockpit" ? <Cockpit /> : <WorkstationApp />}</Suspense>;
}

installWorkspaceFlush();
createRoot(document.getElementById("root")!).render(<Root />);
