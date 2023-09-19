import axios from 'axios';
import { NextResponse } from 'next/server';

const clientId = process.env.VISIER_CLIENT_ID
const clientSecret = process.env.VISIER_CLIENT_SECRET
const host = process.env.VISIER_HOST
const apiKey = process.env.VISIER_APIKEY

export async function GET(request) {
    const isDefined = id => id !== undefined && id !== ""

    if (isDefined(clientSecret)) {
        const code = request.nextUrl.searchParams.get("code");
        if (!isDefined(code)) {
            return new Response({ message: "Missing OAuth 2.0 authorization code" }, { status: 401 });
        }

        const body = {
            grant_type: "authorization_code",
            client_id: clientId,
            scope: "read",
            code
        }

        const instance = axios.create({
            baseURL: host,
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                apikey: apiKey
            },
            auth: {
                username: clientId,
                password: encodeURI(clientSecret)
            }
        });
        
        const tokenResponse = await instance.post("/v1/auth/oauth2/token", body);
        // Build a response that the client can use to initialize axios base config as well as well
        // as request interceptors.
        const response = {
            config: {
                baseURL: host,
                headers: {
                    apikey: apiKey
                }
            },
            jwt: tokenResponse.data
        }
        return NextResponse.json(response)
    }
    console.error("Missing Client Secret");
    return new Response({ message: "Missing OAuth 2.0 credentials" }, { status: 401 });
}