# Visier OAuth Sample
The `Employee Details` is a sample application that showcases client application interaction with the Visier OAuth 2.0 API without an additional third-party OAuth libraries.
The sample authenticates with Visier using the authorization code flow (aka three-legged OAuth).

## Technical Summary
This application is built using [React](https://react.dev/) and [Next.js](https://nextjs.org/). Next.js is an opinionated choiceof framework and by no means necessary for SPAs powered by Visier's APIs. Next.js, by virtue of its consistent approach to routing for both client and the server, is particularly beneficial when calling APIs whoss server implementations will not pass CORS preflight checks.

The second reason the application is built with distinctly server-side components is that non-public configuration can be passed to the application through a simple environment file and the sensitive values therein are not transmitted to the client side components running in the browser.

This means that API calls such as getting members and executing queries cannot be made from components rendered on the client-side as CORS-adhering browsers will require preflight checks for API calls authenticated with (Bearer) tokens.

## Pre-requisites
In order to be able to successfully authenticate using Visier's OAuth APIs, a client application must have been registered and a client id as well as a coresponding secret obtained. The client must also have been registered with a redirect URI that exactly matches that of this application. When run with `yarn dev`, the application will listen for authorization codes on http://localhost:3000/oauth2/callback

## Client Environment
Upon startup, the application will looks for and attempt to load environment files. It is in the environment file, client application credentials are stored.

Before starting the application using `yarn dev`, create a file named `.env.development.local` providing actual values for the following variables:
```sh
VISIER_CLIENT_ID='client-id-from-registration'
VISIER_CLIENT_SECRET='client-secret-from-registration'
VISIER_HOST='api-fqdn-with-protocol'
VISIER_APIKEY='visier-provided-api-key'
```