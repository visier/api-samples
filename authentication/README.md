# Authentication
Visier recommends that customers and partners use OAuth 2.0 to authenticate against the Visier platform. Visier supports the following grant types:
* `authorization_code`: This grant type enables three-legged OAuth. The `authorization_code` grant type requires a registered callback URI that the authorizing server will call with an authentication code. That authentication code is then used to request the bearer token. We recommend this authentication method because it is the most secure and doesn't require providing the client application with a password.
* `password`: This grant type enables two-legged OAuth. The `password` grant type requires a client ID, client secret, username, and password to log in with. Visier provides the `password` grant type for backwards compatibility and only recommends using `password` where it is not possible to use `authorization_code`.

## Environment
The Authentication samples require an initialized environment. The required parameters depend on the grant type. For all samples, we recommend that non-sensitive parameter values are assigned in an environement file that is 'sourced' into the shell environment.

In Unix-style shells and an environment file called `.env`, the environment is sourced by executing:
```sh
source .env
```

## Samples
* [Authorization Code](oauth2-code)
* [Password](oauth2-password)
