export function isLocalAppResource(value: string | URL, baseUrl: string): boolean {
  const url = new URL(value.toString(), baseUrl);
  return url.origin === new URL(baseUrl).origin || url.protocol === "blob:" || url.protocol === "data:";
}

/**
 * Defense in depth for clinical content: application-initiated fetch requests
 * may access only this PWA's own origin (plus in-memory blob/data resources).
 */
export function installSameOriginFetchGuard(): void {
  const nativeFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const target = input instanceof Request ? input.url : input.toString();
    if (!isLocalAppResource(target, window.location.href)) {
      return Promise.reject(new Error("プライバシー保護のため外部通信を拒否しました。"));
    }
    return nativeFetch(input, init);
  };
}
