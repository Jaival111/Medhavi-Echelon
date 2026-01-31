'use client';

import Link from 'next/link';

export default function DemoHomePage() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-blue-100 px-4">
            <div className="max-w-xl w-full bg-white rounded-lg shadow-xl p-10 text-center">
                <h1 className="text-3xl font-bold text-gray-900">Demo Home</h1>
                <p className="text-gray-600 mt-2">You have successfully verified your OTP.</p>

                <div className="mt-6">
                    <Link
                        href="/auth/login"
                        className="inline-flex items-center justify-center bg-indigo-600 text-white px-5 py-3 rounded-lg font-medium hover:bg-indigo-700 transition"
                    >
                        Back to Login
                    </Link>
                </div>
            </div>
        </div>
    );
}
