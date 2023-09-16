import axios from 'axios';

export async function POST(req) {
    const delegateRequestBody = await req.json();
    const instance = makeInstance(delegateRequestBody);
    let responsePromise;

    switch (delegateRequestBody.method) {
        case 'GET':
        default:
            console.log(delegateRequestBody.url)
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
    console.error("Error", error)
    return new Response(error, { status: error.status })
}