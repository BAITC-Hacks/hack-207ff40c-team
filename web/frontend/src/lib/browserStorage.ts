// Storage may be denied by browser policy even when the property exists. Keep
// the tab usable (and logout reliable) without persisting secrets elsewhere.
export function safeStorage(kind: 'localStorage' | 'sessionStorage') {
    const memory = new Map<string, string>();
    let unavailable = false;
    return {
        getItem(key: string): string | null {
            if (!unavailable) {
                try { return window[kind].getItem(key); } catch { unavailable = true; }
            }
            return memory.get(key) ?? null;
        },
        setItem(key: string, value: string): void {
            memory.set(key, value);
            if (!unavailable) {
                try { window[kind].setItem(key, value); } catch { unavailable = true; }
            }
        },
        removeItem(key: string): void {
            memory.delete(key);
            if (!unavailable) {
                try { window[kind].removeItem(key); } catch { unavailable = true; }
            }
        },
    };
}
export const localPreferences = safeStorage('localStorage');
export const tabStorage = safeStorage('sessionStorage');
