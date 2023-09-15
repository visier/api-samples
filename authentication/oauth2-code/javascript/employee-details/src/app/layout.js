import './globals.css'
import { Inter } from 'next/font/google'
import { ServerProvider } from '@/hooks/useServer'

const inter = Inter({ subsets: ['latin'] })

export const metadata = {
    title: 'Visier Sample app',
    description: 'Public Visier sample application with OAuth and API calls',
}

export default function RootLayout({ children }) {
    return (
        <html lang="en">
            <body className={inter.className}>
                <ServerProvider>
                    {children}
                </ServerProvider>
            </body>
        </html>
        )
}
    