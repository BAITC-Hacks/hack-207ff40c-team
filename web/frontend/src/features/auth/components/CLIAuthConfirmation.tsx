import { useState, useEffect } from "react";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Button } from "@/components/ui/button";

export function CLIAuthConfirmation() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const { getAuthHeaders } = useAuth()
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [user, setUser] = useState<{ id: number; username: string } | null>(null)
    const [processing, setProcessing] = useState(false)

    const callbackUrl = searchParams.get('callback_url')
    const deviceName = searchParams.get('device_name') || 'CLI Device'
    const state = searchParams.get('state')
    let callbackDestination = ''
    try {
        const explicitLoopback = (callbackUrl || '').match(/^http:\/\/(?:127\.0\.0\.1|\[::1\]):([0-9]{1,5})\/callback$/)
        const callback = new URL(callbackUrl || '')
        if (explicitLoopback && Number(explicitLoopback[1]) > 0 && callback.protocol === 'http:' && ['127.0.0.1', '[::1]'].includes(callback.hostname)
            && callback.pathname === '/callback'
            && !callback.username && !callback.password && !callback.search && !callback.hash
            && /^[A-Za-z0-9_-]{43}$/.test(state || '')) callbackDestination = callbackUrl!
    } catch { /* Invalid links never reach the approval flow. */ }

    useEffect(() => {
        const checkSession = async () => {
            try {
                const res = await fetch('/api/v1/auth/cli/authorize', {
                    headers: getAuthHeaders(),
                })
                if (res.ok) {
                    const data = await res.json()
                    setUser(data.user)
                } else {
                    setError('You must be logged in to authorize the CLI.')
                }
            } catch {
                setError('Failed to verify session.')
            } finally {
                setLoading(false)
            }
        }

        if (!callbackDestination) {
            setError('Invalid request: start login from the CLI on this computer. A loopback callback and login nonce are required.')
            setLoading(false)
            return
        }

        checkSession()
    }, [callbackDestination, getAuthHeaders])

    const handleApprove = async () => {
        if (!callbackDestination) return;
        setProcessing(true)
        try {
            const res = await fetch('/api/v1/auth/cli/authorize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...getAuthHeaders(),
                },
                body: JSON.stringify({
                    callback_url: callbackDestination,
                    state,
                    device_name: deviceName,
                }),
            })

            if (res.ok) {
                const data = await res.json()
                // Redirect to the CLI callback URL
                const redirect = new URL(data.redirect_url)
                const expected = new URL(callbackDestination)
                if (redirect.origin !== expected.origin || redirect.pathname !== expected.pathname
                    || redirect.username || redirect.password || redirect.hash
                    || redirect.searchParams.get('state') !== state) throw new Error('Unexpected CLI callback.')
                window.location.href = redirect.href
            } else {
                setError('Failed to authorize CLI.')
                setProcessing(false)
            }
        } catch {
            setError('An error occurred.')
            setProcessing(false)
        }
    }

    const handleDeny = () => {
        navigate("/")
    }

    if (loading) {
        return (
            <Layout>
                <div className="flex items-center justify-center min-h-screen">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--brand-solid)]"></div>
                </div>
            </Layout>
        )
    }

    if (error) {
        return (
            <Layout>
                <div className="flex flex-col items-center justify-center min-h-[60vh] p-6">
                    <div className="bg-[var(--error)]/10 text-[var(--error)] p-4 rounded-[var(--radius-card)] mb-4">
                        {error}
                    </div>
                    <Button
                        variant="outline"
                        onClick={() => navigate("/")}
                    >
                        Go Home
                    </Button>
                </div>
            </Layout>
        )
    }

    return (
        <Layout>
            <div className="flex flex-col items-center justify-center min-h-[60vh] p-6">
                <div className="bg-[var(--bg-card)] shadow-[var(--shadow-card)] rounded-[var(--radius-card)] p-8 max-w-md w-full text-center border border-[var(--border-subtle)]">
                    <div className="w-16 h-16 bg-[var(--brand-solid)]/10 rounded-full flex items-center justify-center mx-auto mb-6">
                        <svg className="w-8 h-8 text-[var(--brand-solid)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
                    </div>

                    <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-2">
                        Authorize CLI Device?
                    </h1>

                    <p className="text-[var(--text-secondary)] mb-6">
                        <span className="font-bold">{deviceName}</span> wants to access your account <span className="font-bold">{user?.username}</span>.
                    </p>

                    <p className="text-sm break-all mb-6">Login returns only to this computer: <strong>{callbackDestination}</strong>. Approve only if you just started this login in your terminal.</p>
                    <div className="flex flex-col gap-3">
                        <Button
                            variant="brand"
                            onClick={handleApprove}
                            disabled={processing}
                            className="w-full"
                        >
                            {processing ? 'Authorizing...' : 'Approve'}
                        </Button>
                        <Button
                            variant="outline"
                            onClick={handleDeny}
                            disabled={processing}
                            className="w-full"
                        >
                            Deny
                        </Button>
                    </div>
                </div>
            </div>
        </Layout>
    )
}

