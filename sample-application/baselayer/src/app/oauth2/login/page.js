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
import { redirect } from 'next/navigation';
import React, { useEffect, useState } from 'react';

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