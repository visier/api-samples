# Visier OAuth Sample
The `Employee Details` is a sample application that showcases client application interaction with the Visier OAuth 2.0 API without any additional third-party OAuth libraries.
The sample uses the authorization code flow (three-legged OAuth) to authenticate with Visier.

## Technical Summary
This application is built using [React](https://react.dev/) and [Next.js](https://nextjs.org/). Next.js is an opinionated framework and isn't necessary for single-page applications powered by Visier APIs. Next.js has a consistent approach to routing for both client and the server, and is particularly beneficial when calling APIs whose server implementations will not pass CORS preflight checks.

The application is built with server-side components because it allows passing non-public configuration to the application through a simple environment file and its sensitive values are not transmitted to the client-side components running in the browser. This means that API calls, such as getting members and executing queries, cannot be made from components rendered on the client-side because CORS-adhering browsers will require preflight checks for API calls authenticated with Bearer tokens.

This means that API calls such as getting members and executing queries cannot be made from components rendered on the client-side as CORS-adhering browsers will require preflight checks for API calls authenticated with (Bearer) tokens.

## Prerequisites
To successfully authenticate using Visier's OAuth APIs, you must register a client application in Visier and obtain its Client ID and Client Secret. The registered client application must also have a redirect URI that exactly matches this Employee Details application. First install the dependencies by running `yarn install`. Executing `yarn dev` will run the application in development mode. In development mode, the application will listen for authorization codes on http://localhost:3000/oauth2/callback.

## Client Environment
The application-specific values are provided to the application through an environment file. 
Before starting the application using `yarn dev`, create a file named `.env.development.local` to provide actual values for the following variables:
```sh
VISIER_HOST=https://customer-specific.api.visier.io
VISIER_CLIENT_ID='client-id-from-registration'
VISIER_CLIENT_SECRET='client-secret-from-registration'
VISIER_APIKEY='visier-provided-api-key'
```