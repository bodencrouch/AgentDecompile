import {
  unavailableProviderResult,
  type ProviderCapability,
  type ProviderResult,
} from "../analysis/contracts";

export type AnalysisProvider = {
  capability: ProviderCapability;
  dispose?: () => void | Promise<void>;
};

export class ProviderRegistry {
  private readonly providers = new Map<string, AnalysisProvider>();

  register(provider: AnalysisProvider): void {
    if (!provider.capability.id) {
      throw new Error("Provider capability requires an id");
    }
    if (this.providers.has(provider.capability.id)) {
      throw new Error(`Provider capability already registered: ${provider.capability.id}`);
    }
    this.providers.set(provider.capability.id, provider);
  }

  get(id: string): AnalysisProvider | undefined {
    return this.providers.get(id);
  }

  capabilities(): ProviderCapability[] {
    return [...this.providers.values()].map(({ capability }) => ({ ...capability }));
  }

  capability(id: string): ProviderCapability {
    const provider = this.providers.get(id);
    return provider
      ? { ...provider.capability }
      : {
          id,
          label: id,
          status: "unavailable",
          reason: "This provider is not registered in the current runtime",
        };
  }

  unavailable<T>(id: string, resultId: string, revisionId: string): ProviderResult<T> {
    const capability = this.capability(id);
    if (capability.status === "available") {
      return {
        id: resultId,
        provider: id,
        status: "pending",
        capability,
        revisionId,
        createdAt: new Date().toISOString(),
        freshness: { state: "unknown", version: revisionId, reason: "Provider has not returned a result" },
      };
    }
    return unavailableProviderResult<T>(
      resultId,
      id,
      revisionId,
      capability.reason ?? `Provider is ${capability.status}`,
      capability,
    );
  }

  async dispose(): Promise<void> {
    const providers = [...this.providers.values()];
    this.providers.clear();
    await Promise.all(providers.map((provider) => provider.dispose?.()));
  }
}
