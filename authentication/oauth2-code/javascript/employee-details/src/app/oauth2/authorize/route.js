// Copyright 2023 Visier Solutions Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { NextResponse } from 'next/server';
const clientId = process.env.VISIER_CLIENT_ID
const host = process.env.VISIER_HOST
const apiKey = process.env.VISIER_APIKEY

export async function GET() {
    const isDefined = id => id !== undefined && id !== ""

    if (isDefined(clientId) && isDefined(host) && isDefined(apiKey)) {
        const url = `${host}/v1/auth/oauth2/authorize?client_id=${clientId}&response_type=code&apikey=${apiKey}`
        return NextResponse.json({ url });
    }
    console.error("Missing either Client ID, host or API Key");
    return new Response({ message: "Missing OAuth 2.0 credentials" }, { status: 401 })
}