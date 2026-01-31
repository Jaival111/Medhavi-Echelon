'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authAPI } from '@/lib/api';

export default function DashboardPage() {
    const router = useRouter();
    const [user, setUser] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchUser = async () => {
            try {
                const userData = await authAPI.getCurrentUser();
                setUser(userData);
            } catch (error) {
                router.push('/auth/login');
            } finally {
                setLoading(false);
            }
        };

        fetchUser();
    }, [router]);

    const handleLogout = async () => {
        try {
            await authAPI.logout();
            router.push('/auth/login');
        } catch (error) {
            console.error('Logout failed:', error);
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="text-xl text-gray-600">Loading...</div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50">
            <nav className="bg-white shadow-sm">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between h-16">
                        <div className="flex items-center">
                            <h1 className="text-xl font-bold text-gray-900">Medhavi Echelon</h1>
                        </div>
                        <div className="flex items-center">
                            <button
                                onClick={handleLogout}
                                className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition"
                            >
                                Logout
                            </button>
                        </div>
                    </div>
                </div>
            </nav>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="bg-white rounded-lg shadow p-6">
                    <h2 className="text-2xl font-bold text-gray-900 mb-4">Welcome to Dashboard</h2>
                    {user && (
                        <div className="space-y-2">
                            <p className="text-gray-700">
                                <span className="font-medium">Email:</span> {user.email}
                            </p>
                            <p className="text-gray-700">
                                <span className="font-medium">User ID:</span> {user.id}
                            </p>
                            <p className="text-gray-700">
                                <span className="font-medium">Status:</span>{' '}
                                <span className={user.is_active ? 'text-green-600' : 'text-red-600'}>
                                    {user.is_active ? 'Active' : 'Inactive'}
                                </span>
                            </p>
                            <p className="text-gray-700">
                                <span className="font-medium">Verified:</span>{' '}
                                <span className={user.is_verified ? 'text-green-600' : 'text-yellow-600'}>
                                    {user.is_verified ? 'Yes' : 'No'}
                                </span>
                            </p>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
