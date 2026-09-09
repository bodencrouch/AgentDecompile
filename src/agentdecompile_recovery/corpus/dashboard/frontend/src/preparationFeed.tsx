import { createContext, useContext, type ReactNode } from "react";
import { usePreparationRuns, type PreparationFeed } from "./usePreparationRuns";

const PreparationFeedContext = createContext<PreparationFeed | null>(null);

export function PreparationFeedProvider({ children }: { children: ReactNode }) {
  const feed = usePreparationRuns();
  return <PreparationFeedContext.Provider value={feed}>{children}</PreparationFeedContext.Provider>;
}

export function usePreparationFeed(): PreparationFeed {
  const feed = useContext(PreparationFeedContext);
  if (!feed) throw new Error("usePreparationFeed requires PreparationFeedProvider");
  return feed;
}
