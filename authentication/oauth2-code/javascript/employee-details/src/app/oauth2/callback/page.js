"use client"

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useServer } from "@/hooks/useServer";
import axios from "axios";

export default function Callback() {
    const router = useRouter();
    const searchParams = useSearchParams()
    const code = searchParams.get("code");
    const { instance, setServerInstance } = useServer();
    const [usedCode, setUsedCode] = useState();

    useEffect(() => {
        if (instance === null && code !== usedCode) {
            async function callToken() {
                const response = await fetch("/oauth2/token?code=" + code);
                if (response.ok) {
                    const responseBody = await response.json();

                    // This instance definition (with baseURL in config) will trigger a preflight check.
                    const instance = axios.create(responseBody.config);
                    const { access_token, token_type } = responseBody.jwt;
                    instance.interceptors.request.use(config => {
                        config.headers.Authorization = `${token_type} ${access_token}`
                        return config
                    })
                    setUsedCode(code);
                    setServerInstance(instance);
                }
            }

            callToken();
            return () => {
                setServerInstance(null);
            }
        }
    }, [instance, usedCode]);

    useEffect(() => {
        if (instance !== null) {
            router.replace("/")
        }
    }, [instance]);


    return (<p>Redirecting...</p>)
}