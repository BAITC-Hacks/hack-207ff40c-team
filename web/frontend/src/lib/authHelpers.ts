import { useAuthStore } from '../features/auth/store/authStore';
import './authTypes';

let refreshInFlight: Promise<string | null> | null = null;

export function refreshToken(): Promise<string | null> {
    if (refreshInFlight) return refreshInFlight;
    const originalFetch = window.__scriberr_original_fetch || window.fetch.bind(window);
    const version = useAuthStore.getState().sessionVersion;
    refreshInFlight = (async () => {
        try {
            const response = await originalFetch('/api/v1/auth/refresh', { method: 'POST' });
            const data = response.ok ? await response.json() : null;
            const current = useAuthStore.getState();
            // A login/logout that happened while awaiting the network owns the session.
            if (current.sessionVersion !== version) return current.token;
            if (typeof data?.token !== 'string' || !data.token) return null;
            current.setToken(data.token);
            current.setRequiresRegistration(false);
            return data.token;
        } catch {
            const current = useAuthStore.getState();
            return current.sessionVersion !== version ? current.token : null;
        } finally { refreshInFlight = null; }
    })();
    return refreshInFlight;
}

export function logoutIfCurrent(version: number): void {
    const current = useAuthStore.getState();
    if (current.sessionVersion !== version) return;
    current.logout();
    navigateToHome();
}

function expiresSoon(token: string): boolean {
    try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        return typeof payload.exp !== 'number' || payload.exp <= Date.now() / 1000 + 300;
    } catch { return true; }
}

async function checkExpiry() {
    const state = useAuthStore.getState();
    if (state.token && expiresSoon(state.token) && !(await refreshToken())) {
        logoutIfCurrent(state.sessionVersion);
    }
}

let maintenanceUsers = 0;
let maintenanceTimer: ReturnType<typeof setInterval> | null = null;
export function retainAuthMaintenance(): () => void {
    if (maintenanceUsers++ === 0) {
        maintenanceTimer = setInterval(() => { void checkExpiry(); }, 60_000);
        void checkExpiry();
    }
    return () => {
        if (--maintenanceUsers === 0 && maintenanceTimer !== null) {
            clearInterval(maintenanceTimer);
            maintenanceTimer = null;
        }
    };
}

let initialization: Promise<void> | null = null;
export function initializeAuth(): Promise<void> {
    if (useAuthStore.getState().isInitialized) return Promise.resolve();
    if (initialization) return initialization;
    initialization = (async () => {
        try {
            const response = await fetch('/api/v1/auth/registration-status');
            if (response.ok) {
                const data = await response.json();
                useAuthStore.getState().setRequiresRegistration(typeof data.registration_enabled === 'boolean'
                    ? data.registration_enabled : !!data.requiresRegistration);
            }
        } catch { /* A transient connection failure does not destroy a session. */ }
        finally { useAuthStore.getState().setInitialized(true); initialization = null; }
    })();
    return initialization;
}

export function navigateToHome(): void {
    if (window.location.pathname !== "/") {
        window.history.pushState({ route: { path: 'home' } }, "", "/");
        window.dispatchEvent(new PopStateEvent('popstate', { state: { route: { path: 'home' } } }));
    }
}

export function parseRequestUrl(input: RequestInfo | URL): string {
    if (typeof input === 'string') return input;
    if (input instanceof URL) return input.href;
    return input.url;
}
