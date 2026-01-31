import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_URL,
    withCredentials: true,
    headers: {
        'Content-Type': 'application/json',
    },
});

export interface LoginCredentials {
    email: string;
    password: string;
}

export interface RegisterData {
    email: string;
    password: string;
}

export interface SendOTPRequest {
    email: string;
}

export interface VerifyOTPRequest {
    otp: string;
    email: string;
    mode: 'login' | 'signup';
}

export interface AuthResponse {
    access_token?: string;
    token_type?: string;
}

export const authAPI = {
    // Login with email and password
    login: async (credentials: LoginCredentials): Promise<AuthResponse> => {
        const formData = new URLSearchParams();
        formData.append('username', credentials.email);
        formData.append('password', credentials.password);

        const response = await api.post('/auth/jwt/login', formData, {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        });
        return response.data;
    },

    // Register new user
    register: async (data: RegisterData) => {
        const response = await api.post('/auth/register', data);
        return response.data;
    },

    // Send OTP for login
    sendLoginOTP: async (data: { email: string; password: string }) => {
        const response = await api.post('/api/v1/2fa/login/send-otp', data);
        return response.data;
    },

    // Send OTP for signup
    sendSignupOTP: async (data: { email: string; password: string }) => {
        const response = await api.post('/api/v1/2fa/signup/send-otp', data);
        return response.data;
    },

    // Verify OTP
    verifyOTP: async (data: VerifyOTPRequest) => {
        const response = await api.post('/api/v1/2fa/verify', data);
        return response.data;
    },

    // Logout
    logout: async () => {
        const response = await api.post('/auth/jwt/logout');
        return response.data;
    },

    // Get current user
    getCurrentUser: async () => {
        const response = await api.get('/users/me');
        return response.data;
    },
};

export default api;
