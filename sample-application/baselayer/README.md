# Visier Baselayer Sample Application
Baselayer is a Visier sample application that showcases:
* Client application interaction with Visier's OAuth 2.0 client without any third-party OAuth libraries.
* API calls to Visier's public APIs built on top of a Next.js application.

Baselayer is built with [React](https://react.dev/) and [Next.js](https://nextjs.org/). It consists of 4 smaller React components, each showcasing a Visier API. All React components live together in the main React app. The React components use Visier's [Data Model and Data Query API](https://docs.visier.com/developer/apis/data-model-query/data-model-query-api.htm). Next.js routes API calls through `pages/api/execute.js`, which utilizes `axios` to make API calls. Each API call routes through this workflow before returning the data. Each component sets up its own API call within the component itself.

Baselayer also has a data intake widget to showcase Visier's [Direct Data Intake API](https://docs.visier.com/developer/Tutorials/direct-data-intake/send-data-to-visier.htm).

To use Baselayer, you must authenticate with OAuth 2.0 in Visier.

# Prerequisites
* Register a client application in Visier. For more information, see [Register a Client Application](https://docs.visier.com/developer/Studio/sign-in%20settings/oauth2-setup.htm).
  * Obtain the client application's `Client ID` and `Client secret`.
  * Set the client application's `Redirect URI` to http://localhost:3000/oauth2/callback. In development mode, Baselayer listens for authorization codes at this URL.
* Retrieve your Visier API key. For more information, see [Generate an API Key](https://docs.visier.com/developer/Studio/solution%20settings/api-key-generate.htm).
* Create Expense Report objects and load data in Visier. For more information, see [Create a Subject to Analyze Expense Report Data](https://docs.visier.com/developer/Tutorials/analytic-model/extend-analytic-model-subject.htm).
* Install `node`.

# Environment
Before you start the application, create a file named `.env.development.local` to define the following variables:
* `VISIER_HOST`: The base URL for API calls; for example, `https://vanity.api.visier.io`.
* `VISIER_APIKEY`: The API key required for all Visier API calls.
* `VISIER_CLIENT_ID`: A Visier-generated unique identifier for the registered OAuth 2.0 client.
* `VISIER_CLIENT_SECRET`: A Visier-generated secret to protect the registered OAuth 2.0 client.

## Installation
Run `yarn install` in a command line application of your choice, such as Terminal.

## Run the Sample
Execute `yarn dev` to run Baselayer in development mode. Next, navigate to `localhost:3000` to login, authenticate, and begin sending API calls. 


