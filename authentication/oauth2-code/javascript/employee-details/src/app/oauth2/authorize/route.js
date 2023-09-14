import { NextResponse } from 'next/server';

const clientId = process.env.VISIER_CLIENT_ID
const host = process.env.VISIER_HOST
const apiKey = process.env.VISIER_APIKEY

export async function GET(request) {
    const isDefined = id => id !== undefined && id !== ""

    if (isDefined(clientId) && isDefined(host) && isDefined(apiKey)) {
        const url = `${host}/v1/auth/oauth2/authorize?client_id=${clientId}&response_type=code&apikey=${apiKey}`
        return NextResponse.json({ url });
    }
    console.error("Missing either Client ID, host or API Key");
    return new Response({ message: "Missing OAuth 2.0 credentials" }, { status: 401 })
}