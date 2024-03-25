# Visier OAuth Sample
This sample shows how to obtain a JWT from the Visier platform after your Identity Provider (IdP) has provided your application with a SAML assertion. This will be achieved by formulating a token request using the Saml2 Bearer grant type, `urn:ietf:params:oauth:grant-type:saml2-bearer`.

# Prerequisites
This is an advanced scenario and the specific steps are not outlined in this sample. Instead consult the administration guide for the specific steps. 

Areas that require configuration:
* Single Sign-On with SAML IdP
* Registration of confidential OAuth 2.0 client application
* Calling user must possess the appropriate capabilities and permissions in order to make the API calls.
Optional but recommended:
* TLS termination for the application

# The Sample
In order to focus on the specifics of the necessary API calls, this sample does not represent a general pattern for how applications should be designed. As such, the sample is a simple Node.js Express application that interfaces with the Visier platform and 'proves' that the resulting JWT is valid by calling a Model API (`GET` metrics).

## Installation
Run `npm install`.

## Environment
The sample application requires the following environment variables to be defined:
* `VISIER_HOST`: Protocol and fully qualified hostname. E.g. `https://vanity.api.visier.io`.
* `VISIER_APIKEY`: The API key required for all Visier Public API calls.
* `VISIER_CLIENT_ID`: The OAuth2 client ID.
* `VISIER_CLIENT_SECRET`: The OAuth2 client secret.

## Run the sample
Run `node appljs`.

## Saml2 Bearer grant type
At the heart of this sample is the endpoint `visier-jwt`, which the IdP must provide with a SAML assertion for the calling user. The sample endpoint constructs a URL-encoded form post request to the Visier `/v1/auth/oauth2/token` endpoint.
