import "@testing-library/jest-dom/vitest";

// jsdom implements neither IntersectionObserver nor matchMedia. Both are used
// for presentation only (scroll-spy on the rail, reduced-motion detection), so
// a stub keeps the behavioural assertions honest without pulling in a browser.
if (!("IntersectionObserver" in globalThis)) {
  class StubIntersectionObserver implements IntersectionObserver {
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds: ReadonlyArray<number> = [];
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
  }
  Object.defineProperty(globalThis, "IntersectionObserver", {
    writable: true,
    configurable: true,
    value: StubIntersectionObserver,
  });
}

if (!globalThis.matchMedia) {
  Object.defineProperty(globalThis, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => false,
    }),
  });
}
