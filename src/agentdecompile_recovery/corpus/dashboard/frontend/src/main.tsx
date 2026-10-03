import { createRoot } from "react-dom/client";
import { WorkstationApp } from "./workstation/WorkstationApp";
import { SpectatorView } from "./workstation/SpectatorView";
import { SPECTATOR_TOKEN_KEY } from "./contracts";
import { installWorkspaceFlush } from "./workspaceState";

// A spectator token arrives once, in the URL (shared out-of-band by the
// operator). It is moved into sessionStorage and stripped from the URL
// immediately, before anything else runs, so it never reappears in
// history, a bookmark, or a shared link (R46).
function resolveSpectatorToken(): string {
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get("spectate");
  if (fromUrl) {
    sessionStorage.setItem(SPECTATOR_TOKEN_KEY, fromUrl);
    params.delete("spectate");
    const rest = params.toString();
    history.replaceState({}, "", location.pathname + (rest ? `?${rest}` : "") + location.hash);
  }
  return sessionStorage.getItem(SPECTATOR_TOKEN_KEY) || "";
}

installWorkspaceFlush();
const spectating = Boolean(resolveSpectatorToken());
createRoot(document.getElementById("root")!).render(spectating ? <SpectatorView /> : <WorkstationApp />);
