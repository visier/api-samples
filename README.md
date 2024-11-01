# Visier API samples
A collection of limited-scope sample applications and snippets using public Visier APIs.

## Structure
The samples are organized first by functional area, then by language, and then (optionally) by major library. For example, you can find the OAuth 2.0 three-legged authentication sample for Python using the [Visier Python Connector](https://github.com/visier/connector-python) under:
```
authentication
    oauth-code
        python
            connector
```

### Functional Areas
* [Authentication](authentication) provides samples showing the various methods by which users can authenticate against the Visier platform.
* [Data Intake](data-intake) provides samples showing how to use APIs to send data to your Visier tenant.

### Before You Begin
To send an API call to Visier, you must know your tenant's vanity name. To find your vanity name:
1. In Visier, in the global workspace, click **Settings > Single Sign-On** or **Partner Single Sign-On**.
2. Under **Single Sign-On** or **Bypass Users (Optional)**, find your service provider endpoint; for example, `https://jupiter.visier.com/VServer/auth`. In this example, `jupiter` is the vanity name.
