import { useAuthStore } from '../features/auth/store/authStore';
import { refreshToken, logoutIfCurrent, parseRequestUrl } from './authHelpers';
import './authTypes';

export function setupAuthInterceptor(): void {
    if (window.__scriberr_original_fetch) {
        return;
    }

    const originalFetch = window.fetch.bind(window);
    window.__scriberr_original_fetch = originalFetch;

    const wrappedFetch: typeof window.fetch = async (input, init) => {
        const url = new URL(parseRequestUrl(input), window.location.href);
        // Station pairing and external services own their authentication.
        // Never leak a Scriberr JWT or refresh/logout on their 401 responses.
        if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/v1/')) {
            return originalFetch(input, init);
        }
        const isAuthEndpoint = url.pathname.startsWith('/api/v1/auth/');

        const state = useAuthStore.getState();
        const token = state.token;

        let requestInit = init || {};
        if (token && !isAuthEndpoint) {
            const headers = new Headers(requestInit.headers || (input instanceof Request ? input.headers : undefined));
            if (!headers.has('Authorization')) {
                headers.set('Authorization', `Bearer ${token}`);
                requestInit = { ...requestInit, headers };
            }
        }

        let response = await originalFetch(input, requestInit);

        if (response.status === 401 && !isAuthEndpoint) {
            const current = useAuthStore.getState();
            // Another request may already have refreshed while this 401 was in flight.
            const newToken = current.sessionVersion !== state.sessionVersion
                ? current.token : await refreshToken();
            const retryVersion = useAuthStore.getState().sessionVersion;

            if (newToken) {
                const retryHeaders = new Headers(requestInit.headers);
                retryHeaders.set('Authorization', `Bearer ${newToken}`);
                const retryInit = { ...requestInit, headers: retryHeaders };

                response = await originalFetch(input, retryInit);
                if (response.status !== 401) return response;
            }

            logoutIfCurrent(newToken ? retryVersion : state.sessionVersion);
        }

        return response;
    };

    window.fetch = wrappedFetch;
}
