"use client"
import { useAuth } from "@/hooks/useAuth"

export default function Employee() {
    const { accessToken, tokenType } = useAuth();

    return (<p>Show the Employee info. Make calls using {tokenType} {accessToken}</p>)
}