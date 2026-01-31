'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { authAPI } from '@/lib/api';

export default function VerifyOTPPage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const email = searchParams.get('email') || '';
    const mode = (searchParams.get('mode') || 'login') as 'login' | 'signup';
    const [otp, setOtp] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!email) {
            router.replace('/auth/login');
        }
    }, [email, router]);

    const handleVerifyOTP = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            await authAPI.verifyOTP({ otp, email, mode });
            router.push('/');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Invalid OTP. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-green-50 to-emerald-100 px-4">
            <div className="max-w-md w-full bg-white rounded-lg shadow-xl p-8">
                <div className="text-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-900">Enter OTP</h1>
                    <p className="text-gray-600 mt-2">We sent a 6-digit code to</p>
                    <p className="text-gray-700 font-medium mt-1">{email}</p>
                </div>

                <form onSubmit={handleVerifyOTP} className="space-y-6">
                    {error && (
                        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                            {error}
                        </div>
                    )}

                    <div>
                        <label htmlFor="otp" className="block text-sm font-medium text-gray-700 mb-2">
                            One-Time Password
                        </label>
                        <input
                            id="otp"
                            type="text"
                            value={otp}
                            onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                            required
                            maxLength={6}
                            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent transition text-gray-900 text-center text-2xl tracking-widest"
                            placeholder="000000"
                        />
                    </div>

                    <button
                        type="submit"
                        disabled={loading || otp.length !== 6}
                        className="w-full bg-green-600 text-white py-3 rounded-lg font-medium hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {loading ? 'Verifying...' : 'Verify OTP'}
                    </button>
                </form>
            </div>
        </div>
    );
}
