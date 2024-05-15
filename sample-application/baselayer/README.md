# Visier Baselayer Sample Application
The `Baselayer` is a sample application that showcases client application interaction with the Visier OAuth 2.0 API without any additional third-party OAuth libraries. It also showcases several API calls to the Visier API built on top of a Next.js application. You must login to your account first. 

## Technical Summary
This application is built using [React](https://react.dev/) and [Next.js](https://nextjs.org/). 

It is built of 4 smaller React components, each of which showcases a Visier Alpine API. All of these live together as part of the main React app.
- Most of the API explores the capabilities of the [Data Model and Data Query API](https://docs.visier.com/developer/apis/data-model-query/data-model-query-api.htm#:~:text=Use%20the%20Data%20Model%20API,in%20Visier%20unless%20otherwise%20specified.)
- We also have built in a data intake widget to showcase the [Data Intake API](https://docs.visier.com/developer/Tutorials/data-file-upload/upload-data-files-solution.htm). 

Next.js routes the API calls through the `pages/api/execute.js` which utilizes `axios` in order to make API calls. Each API call is routed through this workflow before returning the data back. Each component also sets up its own API call within the component itself as well.


## Prerequisites
There are a few pre-requisites before Baselayer will work out of the box.
- You must register a client application in Visier and obtain its `Client ID` and `Client Secret`. 
- You must have a Visier `API Key`. 
- You must have completed the [Extend the Analytic Model: Create a Subject](https://docs.visier.com/developer/Tutorials/analytic-model/extend-analytic-model-subject.htm) tutorial successfully and set up expense report subjects.
- In development mode, the application will listen for authorization codes on http://localhost:3000/oauth2/callback. The registered client application must also have a redirect URI that exactly matches this application. 

You must also have `node` installed.

## Client Environment
The application-specific values are provided to the application through an environment file. 
Before starting the application, create a file named `.env.development.local` to provide actual values for the following variables:
```sh
VISIER_HOST=https://customer-specific.api.visier.io
VISIER_CLIENT_ID='client-id-from-registration'
VISIER_CLIENT_SECRET='client-secret-from-registration'
VISIER_APIKEY='visier-provided-api-key'
```

## Installation and Running
First install the dependencies by running `yarn install` in your command line application of choice, such as Terminal. Executing `yarn dev` will run the application in development mode. Afterwards, navigate to `localhost:3000` in order to login, authenticate, and begin sending API calls. 


