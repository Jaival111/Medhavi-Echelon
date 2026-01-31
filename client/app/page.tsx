import Link from 'next/link'

export default function Home() {
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
                        {[
                            'What are the advantages of using Next.js?',
                            "Write code to demonstrate Dijkstra's algorithm",
                            'Help me write an essay about Silicon Valley',
                            'What is the weather in San Francisco?'
                        ].map((text) => (
                            <button
                                key={text}
                                className="rounded-full border border-white/10 bg-white/5 px-5 py-3 text-sm text-white/85 transition hover:border-white/20 hover:bg-white/10"
                            >
                                {text}
                            </button>
                        ))}
                    </div>

                    <div className="mt-8 w-full max-w-3xl rounded-2xl border border-white/10 bg-white/5 px-5 py-4">
                        <div className="flex items-center gap-3">
                            <div className="h-8 w-8 rounded-full bg-white/10" />
                            <input
                                className="flex-1 bg-transparent text-sm text-white/80 placeholder:text-white/30 focus:outline-none"
                                placeholder="Send a message..."
                            />
                            <button className="rounded-full bg-white/10 p-2 text-white/70 hover:bg-white/15">
                                ↑
                            </button>
                        </div>
                        <div className="mt-3 text-left text-xs text-white/40">Gemini 2.5 Flash Lite</div>
                    </div>
                </main>
            </div>
        </div>
    )
}
