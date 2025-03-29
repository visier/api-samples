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
  let delegateRequestBody = req.body;
  const instance = makeInstance(delegateRequestBody);
  let responsePromise;

  try {
    switch (delegateRequestBody.method) {
      case 'POST':
        return await instance.post(delegateRequestBody.url, { query: delegateRequestBody.query });
      case 'GET':
        return await instance.get(delegateRequestBody.url);
      case 'PUT':
        return await instance.put(delegateRequestBody.url, delegateRequestBody.data);
      default:
        return await instance.get(delegateRequestBody.url);
    }
  } catch (error) {
    if (error.response) {
      // The request was made and the server responded with a status code
      // that falls out of the range of 2xx
      console.error("Data", error.response.data);
    } else if (error.request) {
      // The request was made but no response was received
      console.error("No response received", error.request);
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error("Error", error.message);
    }
    return { message: error.message };
  }

  // Handle response and errors in the route handler
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
  return new Response(JSON.stringify(response.data), { status: response.status })
};

const makeErrorResponse = error => {
  return new Response(error, { status: error.status })
}
