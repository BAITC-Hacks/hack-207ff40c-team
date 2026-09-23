import { useEffect, useCallback } from 'react';
import { useAuthStore } from '../store/authStore';
import { initializeAuth, retainAuthMaintenance, navigateToHome } from '../../../lib/authHelpers';
import '../../../lib/authTypes';
import { localStationMode } from '../../../lib/stationMode';

export function useAuth() {
    const {
        token,
        requiresRegistration,
        isInitialized,
        setToken,
        setRequiresRegistration,
        logout: storeLogout
    } = useAuthStore();

    const isAuthenticated = localStationMode || !!token;

    const getAuthHeaders = useCallback((): Record<string, string> => {
        if (localStationMode) return {};
        if (token) {
            return { Authorization: `Bearer ${token}` };
        }
        return {};
    }, [token]);

    const logout = useCallback(() => {
        storeLogout();
        if (localStationMode) {
            window.location.assign('/meeting-intelligence');
            return;
        }
        fetch("/api/v1/auth/logout", {
            method: "POST",
            headers: {
                "Authorization": token ? `Bearer ${token}` : "",
            },
        }).catch(() => { });

        navigateToHome();
    }, [token, storeLogout]);


    const login = useCallback((newToken: string) => {
        setToken(newToken);
        setRequiresRegistration(false);
    }, [setToken, setRequiresRegistration]);

    useEffect(() => {
        if (localStationMode) return;
        void initializeAuth();
        return retainAuthMaintenance();
    }, []);

    return {
        token,
        isAuthenticated,
        requiresRegistration: localStationMode ? false : requiresRegistration,
        isInitialized: localStationMode ? true : isInitialized,
        login,
        logout,
        getAuthHeaders
    };
}
