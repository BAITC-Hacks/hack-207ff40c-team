import { localPreferences, tabStorage } from '@/lib/browserStorage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

// Remove bearer tokens retained by older versions. Closing the tab now ends
// its local session; the server refresh cookie remains HttpOnly and Secure.
localPreferences.removeItem('auth-storage');

interface AuthState {
    token: string | null;
    sessionVersion: number;
    isAuthenticated: boolean;
    requiresRegistration: boolean;
    isInitialized: boolean;
    setToken: (token: string | null) => void;
    setRequiresRegistration: (requires: boolean) => void;
    setInitialized: (initialized: boolean) => void;
    logout: () => void;
}

export const useAuthStore = create<AuthState>()(
    persist(
        (set) => ({
            token: null,
            sessionVersion: 0,
            isAuthenticated: false,
            requiresRegistration: false,
            isInitialized: false,
            setToken: (token) => set(state => ({ token, isAuthenticated: !!token, sessionVersion: state.sessionVersion + 1 })),
            setRequiresRegistration: (requires) => set({ requiresRegistration: requires }),
            setInitialized: (initialized) => set({ isInitialized: initialized }),
            logout: () => {
                set(state => ({ token: null, isAuthenticated: false, sessionVersion: state.sessionVersion + 1 }));
                tabStorage.removeItem('auth-storage');
                // Optional: Call logout endpoint if needed, but side effects strictly in hooks/components usually better
            },
        }),
        {
            name: 'auth-storage',
            storage: createJSONStorage(() => tabStorage),
            partialize: (state) => ({ token: state.token }), // Only persist token
        }
    )
);
