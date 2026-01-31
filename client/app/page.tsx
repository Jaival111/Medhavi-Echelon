"use client"

import { useMemo, useState } from 'react'
import Link from 'next/link'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type ChatMessage = {
    role: 'user' | 'assistant'
    content: string
}

export default function Home() {
    const [input, setInput] = useState('')
    const [messages, setMessages] = useState<ChatMessage[]>([])
    const [loading, setLoading] = useState(false)

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

        const nextMessages = [...messages, { role: 'user', content: prompt.trim() }]
        setMessages(nextMessages)
        setInput('')
        setLoading(true)

        try {
            const response = await fetch(
                `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/chat`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        messages: nextMessages,
                        stream: false
                    })
                }
            )

            if (!response.ok) {
                throw new Error('Chat request failed')
            }

            const data = await response.json()
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: data?.message?.content || 'No response received.'
                }
            ])
        } catch (error) {
            setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: 'Sorry, I could not reach the server.' }
            ])
        } finally {
            setLoading(false)
        }
    }

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        sendMessage(input)
    }

    return (
        <div className="min-h-screen bg-black text-white">
            <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-8">
                <header className="flex items-center justify-between">
                    <div className="text-sm text-white/70">Medhavi Echelon</div>
                    <div className="flex items-center gap-2">
                        <button className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-xs text-white/90 hover:bg-white/10">
                            Deploy with Vercel
                        </button>
                        <Link
                            href="/auth/login"
                            className="rounded-md border border-white/15 bg-white/5 px-3 py-2 text-xs text-white/90 hover:bg-white/10"
                        >
                            Logout
                        </Link>
                    </div>
                </header>

                <main className="flex flex-1 flex-col items-center justify-center text-center">
                    <h1 className="text-3xl font-semibold sm:text-4xl">Hello there!</h1>
                    <p className="mt-2 text-white/60">How can I help you today?</p>

                    <div className="mt-10 grid w-full max-w-3xl grid-cols-1 gap-4 sm:grid-cols-2">
                        {suggestions.map((text) => (
                            <button
                                key={text}
                                onClick={() => sendMessage(text)}
                                className="rounded-full border border-white/10 bg-white/5 px-5 py-3 text-sm text-white/85 transition hover:border-white/20 hover:bg-white/10"
                            >
                                {text}
                            </button>
                        ))}
                    </div>

                    <div className="mt-8 w-full max-w-3xl rounded-2xl border border-white/10 bg-white/5 px-5 py-4">
                        <div className="max-h-72 space-y-4 overflow-y-auto text-left">
                            {messages.length === 0 && (
                                <div className="text-sm text-white/40">Your conversation will appear here.</div>
                            )}
                            {messages.map((message, index) => (
                                <div
                                    key={`${message.role}-${index}`}
                                    className={`rounded-xl px-4 py-3 text-sm ${message.role === 'user'
                                        ? 'bg-white/10 text-white'
                                        : 'bg-white/5 text-white/85'
                                        }`}
                                >
                                    <div className="mb-1 text-xs uppercase text-white/40">
                                        {message.role === 'user' ? 'You' : 'Assistant'}
                                    </div>
                                    <div className="prose prose-invert max-w-none text-sm">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                            {message.content}
                                        </ReactMarkdown>
                                    </div>
                                </div>
                            ))}
                            {loading && (
                                <div className="rounded-xl bg-white/5 px-4 py-3 text-sm text-white/60">
                                    Assistant is typing...
                                </div>
                            )}
                        </div>

                        <form onSubmit={handleSubmit} className="mt-5 flex items-center gap-3">
                            <div className="h-8 w-8 rounded-full bg-white/10" />
                            <input
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                className="flex-1 bg-transparent text-sm text-white/80 placeholder:text-white/30 focus:outline-none"
                                placeholder="Send a message..."
                            />
                            <button
                                type="submit"
                                disabled={loading || !input.trim()}
                                className="rounded-full bg-white/10 p-2 text-white/70 hover:bg-white/15 disabled:opacity-50"
                            >
                                ↑
                            </button>
                        </form>
                        <div className="mt-3 text-left text-xs text-white/40">Groq Chat</div>
                    </div>
                </main>
            </div>
        </div>
    )
}
