# Authentication
Visier recommends that customers and partners authenticate against the Visier platform using the OAuth 2.0 protocol. Visier supports the following two grant types:
* `authorization_code` This is the grant type for so called 'three-legged' OAuth and it requires registering a callback URI the authorizing server will call with an authentication code. That code is then used when requesting the bearer token. This is the recommended way of authenticating against Visier as it is the most secure and does not require providing the client application with a password.
* `password` This grant type enables so call 'two-legged' OAuth and it work by the client providing both the client ID along with its secret along with the username and password of the user to actually log on with. The `password` grant type support is provided for backwards compatibility only and should only be used where it is not possible to use `authorization_code`.

## Environment
The Authentication samples require an initialized environment. Exactly which parameters are required will depend on the grant type.

Common for all samples however is that it is recommended that the non-sensitive parameter values are assigned in an environement file that is 'sourced' into the shell environment.

In Unix-style shells and an environment file called `.env`, the environment is sourced in simply executing:
```sh
source .env
```

## Samples
* [Authorization Code](oauth2-code)
* [Password](oauth2-password)