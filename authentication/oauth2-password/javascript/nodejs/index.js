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

import axios from "axios";

/**
 * See the environment variable template file for details on how to set these values.
 */
const apikey = process.env.VISIER_APIKEY
const vhost = process.env.VISIER_HOST
const clienId = process.env.VISIER_CLIENT_ID
const clientSecret = process.env.VISIER_CLIENT_SECRET
const username = process.env.VISIER_USERNAME
const password = process.env.VISIER_PASSWORD
const grantType = "password"

/**
 * Attempt to authenticate using a password grant for a given client.
 * 
 * Though it returns the JWT if successful, this function also installs
 * an axios request interceptor to set the Authorization header with the 
 * returned Bearer token.
 * 
 * @param {*} instance The axios instance with baseURL and apikey set
 * @returns A promise of a JWT
 */
const authenticate = async instance => {
    const url = "/v1/auth/oauth2/token"
    const body = {
        grant_type: grantType,
        client_id: clienId,
        scope: "read",
        username,
        password
    }
    const config = {
        headers: {
            "Content-Type": "application/x-www-form-urlencoded"
        },
        auth: {
            username: clienId,
            password: clientSecret
        },
    }
    return instance.post(url, body, config).then(response => {
        const jwt = response.data
        const tokenType = jwt.token_type
        const accessToken = jwt.access_token

        // Request interceptor without retry logic.
        instance.interceptors.request.use(config => {
            config.headers.Authorization = `${tokenType} ${accessToken}`
            return config
        })
        return jwt
    })

}

/**
 * Simple Model API call to show thow subsequent calls on the axios instance.
 * 
 * @param {*} instance The axios instance with configured headers.
 * @returns The payload from the API, which in this case are the members for a specific dimension.
 */
const sampleApiCall = async instance => {
    const members = instance.get("/v1/data/model/analytic-objects/Employee/dimensions/Gender/members")
        .then(r => r.data)
        .catch(console.error)
    return members
}

try {
    const instance = axios.create({
        baseURL: vhost,
        headers: {
            apikey: apikey
        }
    })

    await authenticate(instance)
    const r = await sampleApiCall(instance)
    console.log(r)
} catch (err) {
    console.error("Unable to call Visier API with password grant authentication. Details: " + err)
}