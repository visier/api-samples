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

import axios from 'axios';

/**
 * General wrapper for making Visier Public API calls.
 * 
 * @param {*} req Request definition containing the Visier API request details
 * @returns The response payload from the Visier API
 */
export async function POST(req) {
    const delegateRequestBody = await req.json();
    const instance = makeInstance(delegateRequestBody);
    let responsePromise;

    switch (delegateRequestBody.method) {
        case 'POST':
            responsePromise = instance.post(delegateRequestBody.url, delegateRequestBody.body).then(makeSuccesResponse).catch(makeErrorResponse)
            break;

        case 'GET':
        default:
            responsePromise = instance.get(delegateRequestBody.url).then(makeSuccesResponse).catch(makeErrorResponse)
            break;
    }

    return responsePromise;
}

/**
 * Make an axios instance from the provided request details.
 * 
 * @param {*} req 
 */
const makeInstance = req => {
    const config = req.config;
    const configWithAuth = {
        ...config,
        headers: {
            ...config.headers,
            Authorization: req.auth
        }
    }
    return axios.create(configWithAuth);
}

const makeSuccesResponse = response => {
    return new Response(JSON.stringify(response.data), { status: response.status})
};

const makeErrorResponse = error => {
    return new Response(error, { status: error.status })
}