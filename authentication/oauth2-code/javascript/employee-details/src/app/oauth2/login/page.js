"use client"
import { redirect } from 'next/navigation';
import { useEffect, useState } from 'react';

export default function Login() {
    const [url, setUrl] = useState("");

    useEffect(() => {
        async function callAuthorize() {
            const response = await fetch("/oauth2/authorize")
            if (response.ok) {
                const result = await response.json();
                const url = result.url;
                setUrl(url)
            }
        }

        callAuthorize();
        return () => {
            setUrl("");
        }
    }, [url]);

    if (url !== "") {
        redirect(url);
    } else {
        return (<p>Preparing to authenticate.</p>)
    }
}