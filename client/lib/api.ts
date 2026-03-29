import axios from 'axios';

export const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

const api = axios.create({
    baseURL: typeof window === 'undefined' ? API_URL : '',
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

    // Send OTP for login (uses auth login endpoint)
    sendLoginOTP: async (data: { email: string; password: string }) => {
        const formData = new URLSearchParams();
        formData.append('username', data.email);
        formData.append('password', data.password);

        const response = await api.post('/auth/jwt/login', formData, {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        });
        return response.data;
    },

    // Send OTP for signup (register first, then request login OTP)
    sendSignupOTP: async (data: { email: string; password: string }) => {
        await api.post('/auth/register', data);
        const formData = new URLSearchParams();
        formData.append('username', data.email);
        formData.append('password', data.password);

        const response = await api.post('/auth/jwt/login', formData, {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        });
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

    // Get user chat history
    getChatHistory: async () => {
        const response = await api.get('/api/v1/chat/chats');
        return response.data;
    },

    // Get a specific chat with messages
    getChat: async (chatId: string) => {
        const response = await api.get(`/api/v1/chats/${chatId}`);
        return response.data;
    },

    // Add message to existing chat
    addMessage: async (chatId: string, data: { messages: Array<{ role: string; content: string }>; stream?: boolean; model?: string; temperature?: number; max_tokens?: number }) => {
        const response = await api.post(`/api/v1/chat/${chatId}`, data);
        return response.data;
    },

    // Update chat (rename)
    updateChat: async (chatId: string, name: string) => {
        const response = await api.patch(`/api/v1/chats/${chatId}`, { name });
        return response.data;
    },

    // Delete chat via API
    deleteChatAPI: async (chatId: string) => {
        const response = await api.delete(`/api/v1/chats/${chatId}`);
        return response.data;
    },

    // Get chat messages only
    getChatMessages: async (chatId: string) => {
        const response = await api.get(`/api/v1/chats/${chatId}/messages`);
        return response.data;
    },

    // List available models
    listModels: async () => {
        const response = await api.get('/api/v1/chat/models');
        return response.data;
    },

    // Security check
    securityCheck: async (prompt: string) => {
        const response = await api.post('/api/v1/security-check', { prompt });
        return response.data;
    },
};

export default api;
