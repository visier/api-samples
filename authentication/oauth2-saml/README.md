# Visier OAuth Sample
Sample that uses the `Saml2 Bearer` grant type to authenticate against the Visier platform. This sample shows how to obtain a JSON Web Token (JWT) from Visier after your Identity Provider (IdP) provides your application with a SAML assertion. You can then retrieve a JWT with a token request using the `Saml2 Bearer` grant type: `urn:ietf:params:oauth:grant-type:saml2-bearer`.

# Prerequisites
* Single sign-on with SAML IdP. For more information, see [Set Up Single Sign-On](https://docs.visier.com/developer/Studio/sign-in%20settings/single%20sign-on%20set%20up.htm).
* A confidential OAuth 2.0 client application. For more information, see [Register a Client Application](https://docs.visier.com/developer/Studio/sign-in%20settings/oauth2-setup.htm).
* A Visier account that has the appropriate profile and permission capabilities to make API calls. For more information, see [Permission Management](https://docs.visier.com/developer/Studio/permissions/permissions%20manage.htm).
* (Optional but recommended) TLS termination for the application.

# The Sample
This sample is a simple Node.js Express application that interfaces with the Visier platform. The sample proves that the resulting JWT is valid by calling the Data Model API (`GET /v1/data/model/metrics`). This sample focuses on the necessary API calls to get a valid JWT and doesn't represent a general pattern for how applications should be designed.

## Installation
Run `npm install`.

## Environment
This sample application requires that you define the following environment variables:
* `VISIER_HOST`: The base URL for API calls; for example, `https://vanity.api.visier.io`.
* `VISIER_CLIENT_ID`: A Visier-generated unique identifier for the registered OAuth 2.0 client.
* `VISIER_CLIENT_SECRET`: A Visier-generated secret to protect the registered OAuth 2.0 client.

## Run the sample
Run `node appljs`.

## Saml2 Bearer Grant Type
Your IdP must provide the endpoint `visier-jwt` with a SAML assertion for the calling user. In this sample, the endpoint constructs a URL-encoded form `POST` request to the VIsier `/v1/auth/oauth2/token` endpoint.
