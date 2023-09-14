"use client"

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function Callback() {
    const router = useRouter();
    const searchParams = useSearchParams()
    const code = searchParams.get("code");
    const { setAuth, accessToken } = useAuth();

    useEffect(() => {
        if (accessToken === null && code !== undefined) {
            async function callToken() {
                const response = await fetch("/oauth2/token?code=" + code);
                if (response.ok) {
                    const jwt = await response.json();
                    setAuth(jwt.access_token, jwt.token_type)
                }
            }

            callToken();
        }
    }, [accessToken]);


    if (accessToken !== null) {
        router.replace("/")
    } else {
        return (<p>Preparing to authenticate.</p>)
    }
}