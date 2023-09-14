"use client"
import Employee from './employee/page';
import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';

export default function Home() {
    const { isAuthenticated, accessToken } = useAuth();
    return (
        <>
            {isAuthenticated() ? <Employee /> : (
                <>
                    <h3>Three-legged OAuth 2.0 authentication sample</h3>
                    <Link href="/oauth2/login">
                        Log in to Visier - {accessToken}
                    </Link>
                </>
            )}
        </>
    );
}
