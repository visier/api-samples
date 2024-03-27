const express = require('express');
const bodyParser = require('body-parser');
const axios = require('axios');

const app = express();
const port = process.env.PORT || 3000;

if (!(process.env.VISIER_HOST && process.env.VISIER_APIKEY && process.env.VISIER_CLIENT_ID && process.env.VISIER_CLIENT_SECRET)) {
    console.error("Define VISIER_HOST, VISIER_APIKEY, VISIER_CLIENT_ID, and VISIER_CLIENT_SECRET environment variables.");
    process.exit(1);
}

app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());

// Endpoint called by the client Identity Provider (IdP) to exchange the SAMLResponse for a JWT
app.post('/visier-jwt', async (req, res) => {
    try {
        const { SAMLResponse } = req.body;

        // Construct OAuth token request
        const tokenEndpoint = `${process.env.VISIER_HOST}/v1/auth/oauth2/token`;
        const grantType = 'urn:ietf:params:oauth:grant-type:saml2-bearer';

        const options = {
            method: 'post',
            url: tokenEndpoint,
            data: {
                grant_type: grantType,
                assertion: SAMLResponse,
                client_id: process.env.VISIER_CLIENT_ID,
                client_secret: process.env.VISIER_CLIENT_SECRET,
            },
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                apikey: process.env.VISIER_APIKEY,
            },
        }
        // Issue the OAuth token request
        const response = await axios(options);

        // Extract JWT from the response
        const access_token = response.data.access_token;

        // Call an API using the JWT for authentication to provde that the JWT is valid
        const endpointUrl = `${process.env.VISIER_HOST}/v1/data/model/metrics/employeeCount`
        const headers = {
          apikey: process.env.VISIER_APIKEY,
          Authorization: 'Bearer ' + access_token
        }
        const metricResponse = await axios.get(endpointUrl, { headers });
        const metric = metricResponse.data

        res.status(200).json({ metric });
      } catch (error) {
        console.error('Error requesting JWT:', error.message);
        res.status(500).json({ error: 'Internal server error', message: error.message });
      }
});

app.listen(port, () => {
    console.log(`Server running at http://localhost:${port}`);
});
