"use client"

import { useMemo, useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { authAPI, API_URL } from '@/lib/api'

type ChatMessage = {
    role: 'user' | 'assistant'
    content: string
}

type ChatHistory = {
    id: string
    title: string
    timestamp: number
    messages: ChatMessage[]
}

export default function Home() {
    const router = useRouter()
    const [input, setInput] = useState('')
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [loading, setLoading] = useState(false)
    const [chatHistory, setChatHistory] = useState<ChatHistory[]>([])
    const [currentChatId, setCurrentChatId] = useState<string | null>(null)
    const [sidebarOpen, setSidebarOpen] = useState(true)
    const [isAuthenticated, setIsAuthenticated] = useState(false)
    const [authChecking, setAuthChecking] = useState(true)

    // Check authentication on mount
    useEffect(() => {
        const checkAuth = async () => {
            try {
                await authAPI.getCurrentUser()
                setIsAuthenticated(true)
            } catch (error) {
                router.push('/auth/login')
            } finally {
                setAuthChecking(false)
            }
        }
        checkAuth()
    }, [router])

    // Load chat history from server
    useEffect(() => {
        if (!isAuthenticated) return

        const loadChatHistory = async () => {
            try {
                const response = await authAPI.getChatHistory()
                console.log('Chat history response:', response)
                if (response && response.chats && Array.isArray(response.chats)) {
                    console.log('Number of chats:', response.chats.length)
                    // Transform server chats to client format
                    const chats: ChatHistory[] = response.chats.map((chat: any) => ({
                        id: chat.id.toString ? chat.id.toString() : String(chat.id),
                        title: chat.name || 'Untitled',
                        timestamp: chat.created_at ? new Date(chat.created_at).getTime() : Date.now(),
                        messages: [] // Messages will be loaded on demand
                    }))
                    console.log('Loaded chats:', chats)
                    setChatHistory(chats)
                    return
                }
            } catch (error) {
                console.error('Failed to fetch chat history from server:', error)
            }

            // Fallback to localStorage if server fetch fails
            const saved = localStorage.getItem('chatHistory')
            if (saved) {
                try {
                    console.log('Using localStorage fallback')
                    setChatHistory(JSON.parse(saved))
                } catch {
                    // ignore parse errors
                }
            }
        }

        loadChatHistory()
    }, [isAuthenticated])

    // Save chat history to localStorage
    useEffect(() => {
        localStorage.setItem('chatHistory', JSON.stringify(chatHistory))
    }, [chatHistory])

    const refreshChatHistory = async () => {
        try {
            const response = await authAPI.getChatHistory()
            console.log('Refresh chat history response:', response)

            if (response && response.chats && Array.isArray(response.chats)) {
                console.log('Number of chats:', response.chats.length)
                const chats: ChatHistory[] = response.chats.map((chat: any) => {
                    console.log('Processing chat:', chat)
                    return {
                        id: chat.id.toString ? chat.id.toString() : String(chat.id),
                        title: chat.name || 'Untitled',
                        timestamp: chat.created_at ? new Date(chat.created_at).getTime() : Date.now(),
                        messages: []
                    }
                })
                console.log('Transformed chats:', chats)
                setChatHistory(chats)
            } else {
                console.warn('No chats in response or response is invalid:', response)
            }
        } catch (error) {
            console.error('Failed to refresh chat history:', error)
        }
    }

    const saveCurrentChat = () => {
        if (messages.length > 0 && currentChatId) {
            setChatHistory((prev) =>
                prev.map((chat) =>
                    chat.id === currentChatId
                        ? { ...chat, messages, timestamp: Date.now() }
                        : chat
                )
            )
        }
    }

    const startNewChat = () => {
        saveCurrentChat()
        setMessages([])
        setInput('')
        setCurrentChatId(null)
    }

    const loadChat = (chatId: string) => {
        saveCurrentChat()
        const loadChatData = async () => {
            try {
                const chatData = await authAPI.getChat(chatId)
                if (chatData.messages) {
                    const chatMessages: ChatMessage[] = chatData.messages.map((msg: any) => ({
                        role: msg.role as 'user' | 'assistant',
                        content: msg.content
                    }))
                    setMessages(chatMessages)
                    setCurrentChatId(chatId)
                }
            } catch (error) {
                console.error('Failed to load chat messages:', error)
                const chat = chatHistory.find((c) => c.id === chatId)
                if (chat) {
                    setMessages(chat.messages)
                    setCurrentChatId(chatId)
                }
            }
        }
        loadChatData()
    }

    const deleteChat = (chatId: string) => {
        // Delete from server
        authAPI.deleteChatAPI(chatId).catch((err) => console.error('Failed to delete chat:', err))

        // Remove from local state
        setChatHistory((prev) => prev.filter((c) => c.id !== chatId))
        if (currentChatId === chatId) {
            startNewChat()
        }
    }

    const suggestions = useMemo(
        () => [
            'What are the advantages of using Next.js?',
            "Write code to demonstrate Dijkstra's algorithm",
            'Help me write an essay about Silicon Valley',
            'What is the weather in San Francisco?'
        ],
        []
    )

    const sendMessage = async (prompt: string) => {
        if (!prompt.trim() || loading) return

        const nextMessages: ChatMessage[] = [...messages, { role: 'user', content: prompt.trim() }]
        setMessages(nextMessages)
        setInput('')
        setLoading(true)

        try {
            let responseData
            let chatId = currentChatId

            if (!chatId) {
                // Create new chat on first message
                const response = await fetch(
                    `${API_URL}/api/v1/chat/chats`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({
                            messages: nextMessages,
                            stream: false
                        })
                    }
                )

                if (!response.ok) {
                    let errorDetail = 'Chat request failed.'
                    try {
                        const errorData = await response.json()
                        errorDetail = errorData?.detail || errorDetail
                    } catch {
                        // ignore parse errors
                    }
                    throw new Error(errorDetail)
                }

                responseData = await response.json()
                chatId = responseData.id
                setCurrentChatId(chatId)

                // Refresh chat history from server to ensure consistency
                await refreshChatHistory()
            } else {
                // Add message to existing chat
                responseData = await authAPI.addMessage(chatId, {
                    messages: nextMessages,
                    stream: false
                })
            }

            // Parse response
            const assistantContent =
                responseData?.message?.content ||
                responseData?.messages?.slice?.(-1)?.[0]?.content ||
                'No response received.'
            const updatedMessages: ChatMessage[] = [
                ...nextMessages,
                {
                    role: 'assistant',
                    content: assistantContent
                }
            ]
            setMessages(updatedMessages)

            // Update chat history with new messages
            setChatHistory((prev) =>
                prev.map((chat) =>
                    chat.id === chatId
                        ? { ...chat, messages: updatedMessages, timestamp: Date.now() }
                        : chat
                )
            )
        } catch (error: any) {
            const errorMessage: ChatMessage[] = [
                ...nextMessages,
                { role: 'assistant', content: error?.message || 'Sorry, I could not reach the server.' }
            ]
            setMessages(errorMessage)
        } finally {
            setLoading(false)
        }
    }

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        sendMessage(input)
    }

    // Show loading while checking authentication
    if (authChecking) {
        return (
            <div className="min-h-screen bg-black text-white flex items-center justify-center">
                <div className="text-white/60">Loading...</div>
            </div>
        )
    }

    // Don't render if not authenticated (will redirect)
    if (!isAuthenticated) {
        return null
    }

    if (messages.length === 0) {
        return (
            <div className="min-h-screen bg-black text-white flex">
                {/* Sidebar */}
                <div className={`${sidebarOpen ? 'w-64' : 'w-20'} bg-black/50 border-r border-white/10 flex flex-col transition-all duration-300`}>
                    <div className="p-4 border-b border-white/10 flex items-center justify-between">
                        {sidebarOpen && <span className="text-sm font-semibold">Chat History</span>}
                        <button
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                            className="text-white/70 hover:text-white"
                        >
                            {sidebarOpen ? '✕' : '☰'}
                        </button>
                    </div>

                    {sidebarOpen && (
                        <>
                            <button
                                onClick={startNewChat}
                                className="mx-3 mt-4 w-[calc(100%-24px)] rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/90 hover:bg-white/10 transition"
                            >
                                + New Chat
                            </button>

                            <div className="flex-1 overflow-y-auto mt-4 space-y-1 px-2">
                                {chatHistory.map((chat) => (
                                    <div key={chat.id} className="flex items-center gap-2 group">
                                        <button
                                            onClick={() => loadChat(chat.id)}
                                            className={`flex-1 text-left px-3 py-2 rounded-lg text-xs truncate transition ${currentChatId === chat.id
                                                ? 'bg-white/10 text-white'
                                                : 'text-white/60 hover:bg-white/5'
                                                }`}
                                        >
                                            {chat.title}
                                        </button>
                                        <button
                                            onClick={() => deleteChat(chat.id)}
                                            className="opacity-0 group-hover:opacity-100 text-white/40 hover:text-red-400 px-2 transition"
                                        >
                                            🗑
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </div>

                {/* Main content */}
                <div className="flex-1 flex flex-col">
                    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-6 py-8">
                        <header className="flex items-center justify-between">
                            <div className="text-sm text-white/70">Medhavi Echelon</div>
                            <button
                                onClick={async () => {
                                    try {
                                        await authAPI.logout()
                                    } finally {
                                        setIsAuthenticated(false)
                                        router.push('/auth/login')
                                    }
                                }}
                                className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-xs text-white/90 hover:bg-white/10"
                            >
                                Logout
                            </button>
                        </header>

                        <main className="flex flex-1 flex-col items-center justify-center">
                            <h1 className="text-4xl font-semibold">Hello there!</h1>
                            <p className="mt-2 text-white/60">How can I help you today?</p>

                            <div className="mt-12 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
                                {suggestions.map((text) => (
                                    <button
                                        key={text}
                                        onClick={() => sendMessage(text)}
                                        className="rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-left text-sm text-white/80 transition hover:border-white/20 hover:bg-white/10"
                                    >
                                        {text}
                                    </button>
                                ))}
                            </div>
                        </main>

                        <div className="border-t border-white/10 py-4">
                            <form onSubmit={handleSubmit} className="flex items-end gap-3">
                                <button type="button" className="text-white/70 hover:text-white text-xl">
                                    +
                                </button>
                                <div className="flex-1 flex items-center gap-2 bg-white/5 border border-white/10 rounded-2xl px-4 py-2">
                                    <input
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        className="flex-1 bg-transparent text-sm text-white placeholder:text-white/30 focus:outline-none"
                                        placeholder="Ask anything"
                                    />
                                </div>
                                <button
                                    type="submit"
                                    disabled={loading || !input.trim()}
                                    className="rounded-full bg-white/10 p-2 text-white/70 hover:bg-white/15 hover:text-white disabled:opacity-50 transition"
                                >
                                    ↑
                                </button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-black text-white flex">
            {/* Sidebar */}
            <div className={`${sidebarOpen ? 'w-64' : 'w-20'} bg-black/50 border-r border-white/10 flex flex-col transition-all duration-300`}>
                <div className="p-4 border-b border-white/10 flex items-center justify-between">
                    {sidebarOpen && <span className="text-sm font-semibold">Chat History</span>}
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="text-white/70 hover:text-white"
                    >
                        {sidebarOpen ? '✕' : '☰'}
                    </button>
                </div>

                {sidebarOpen && (
                    <>
                        <button
                            onClick={startNewChat}
                            className="mx-3 mt-4 w-[calc(100%-24px)] rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/90 hover:bg-white/10 transition"
                        >
                            + New Chat
                        </button>

                        <div className="flex-1 overflow-y-auto mt-4 space-y-1 px-2">
                            {chatHistory.map((chat) => (
                                <div key={chat.id} className="flex items-center gap-2 group">
                                    <button
                                        onClick={() => loadChat(chat.id)}
                                        className={`flex-1 text-left px-3 py-2 rounded-lg text-xs truncate transition ${currentChatId === chat.id
                                            ? 'bg-white/10 text-white'
                                            : 'text-white/60 hover:bg-white/5'
                                            }`}
                                    >
                                        {chat.title}
                                    </button>
                                    <button
                                        onClick={() => deleteChat(chat.id)}
                                        className="opacity-0 group-hover:opacity-100 text-white/40 hover:text-red-400 px-2 transition"
                                    >
                                        🗑
                                    </button>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>

            {/* Main content */}
            <div className="flex-1 flex flex-col">
                <div className="mx-auto flex h-screen w-full max-w-3xl flex-col px-4">
                    <header className="flex items-center justify-between border-b border-white/10 py-4">
                        <div className="text-sm text-white/70">Medhavi Echelon</div>
                        <div className="text-xs text-white/50">Hi</div>
                        <button
                            onClick={async () => {
                                try {
                                    await authAPI.logout()
                                } finally {
                                    setIsAuthenticated(false)
                                    router.push('/auth/login')
                                }
                            }}
                            className="text-xs text-white/90 hover:text-white"
                        >
                            Logout
                        </button>
                    </header>

                    <div className="flex-1 overflow-y-auto py-6 space-y-6">
                        {messages.map((message, index) => (
                            <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                <div className={`max-w-2xl ${message.role === 'user' ? 'bg-white/10 text-white' : ''}`}>
                                    <div className={`px-4 py-3 rounded-lg ${message.role === 'user' ? 'bg-white/10 text-white' : 'text-white/85'}`}>
                                        <div className="prose prose-invert max-w-none text-sm">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {message.content}
                                            </ReactMarkdown>
                                        </div>
                                    </div>
                                    {message.role === 'assistant' && (
                                        <div className="mt-2 flex gap-2 px-4 text-white/40">
                                            <button className="hover:text-white/60">👍</button>
                                            <button className="hover:text-white/60">👎</button>
                                            <button className="hover:text-white/60">⋯</button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        {loading && (
                            <div className="flex justify-start">
                                <div className="text-white/60 text-sm">Assistant is typing...</div>
                            </div>
                        )}
                    </div>

                    <div className="border-t border-white/10 py-4">
                        <form onSubmit={handleSubmit} className="flex items-end gap-3">
                            <button type="button" className="text-white/70 hover:text-white text-xl">
                                +
                            </button>
                            <div className="flex-1 flex items-center gap-2 bg-white/5 border border-white/10 rounded-2xl px-4 py-2">
                                <input
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    className="flex-1 bg-transparent text-sm text-white placeholder:text-white/30 focus:outline-none"
                                    placeholder="Ask anything"
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={loading || !input.trim()}
                                className="rounded-full bg-white/10 p-2 text-white/70 hover:bg-white/15 hover:text-white disabled:opacity-50 transition"
                            >
                                ↑
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    )
}