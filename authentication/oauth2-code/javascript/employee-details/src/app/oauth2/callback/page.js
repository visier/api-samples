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

"use client"
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import useCredsStore from '@/store/credsStore';

export default function Callback() {
    // router for query args navigation back to the main page
    const router = useRouter();
    const searchParams = useSearchParams();

    // code state to prevent multiple token calls
    const code = searchParams.get("code");
    const [isAuthenticated, setIsAuthenticated] = useState(false);

    const [setJWT, setConfig] = useCredsStore(s => [s.setJWT, s.setConfig]);
    

    useEffect(() => {
        if (!isAuthenticated) {
            async function callToken() {
                const response = await fetch("/oauth2/token?code=" + code);
                if (response.ok) {
                    const responseBody = await response.json();

                    setJWT(responseBody.jwt);
                    setConfig(responseBody.config)
                    
                    setIsAuthenticated(true);
                }
            }

            callToken();
        }
    }, [isAuthenticated]);

    useEffect(() => {
        if (isAuthenticated) {
            router.replace("/")
        }
    }, [isAuthenticated]);


    return (<p>Redirecting...</p>)
}