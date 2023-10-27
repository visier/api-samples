# Direct Data Intake API
The Direct Data Intake API is suitable for Visier customers who have, at least in part, data to load into Visier that require no additional transformations. This is what makes this process 'direct'. In fact, the process is so streamlined that the column names in the source data files have to match the names of the properties to load in the target objects.

## Load Modes
When provisioning data to Visier using the Data Direct API, it's important to understand the three available modes that correespond to the relationship Direct Data loading has to other means of provisioning data in your tenant.

The following diagram outlines these modes:
![Three Direct Data Intake API Load Modes](/assets/images/load-options.png)
* The **Primary**, which is also the default mode is where all objects are loaded using the Direct Data API method.
* When in **Supplemental** mode, some - but crucially, not all - objects are loaded exclusively using the Direct Data API.
* The **Extension** mode is the most complex one where, potentially in addition to loading objects entirely using the Direct Data API and other objects using other methods, you need to load at least one object from **both** Direct Data API and others. There are caveats:
    * The object in question is primarily loaded through a mechanism _other than_ Direct Data API.
    * The various load processes, including Direct Data API, must not attempt to load _the same properties_ on the object in question.

### Examples
In order to help understand when which mode is applicable in which situations, it may be helpful to consider some example scenarios:
1. You are a new Visier customer and you are looking to integrate Visier into an existing data flow that is currently setup to extract from operational systems, cleanse and deduplicate before loading the data into a data warehouse. Since your source data has been transformed and is at the appropriate level of granularity, it is straight-forward to add simple column name mappings to match the load schema of the Analytic Objects in Visier. For this reason, you would like all Visier-relevant data to be loaded using the Direct Intake API. In this case, the Load Mode should be **Primary**.
2. You are an existing Visier customer with an established data provisioning process for loading the core Analytic Objects, such as `Employee`, `Employment_Start`, `Employee_Exit` etc. You have recently made the decision to expand your Visier platform capabilities by adding the Talent Aquisition module. Your operational TA application however is already providing data into an existing and extensible ETL process. To ensure you don't have to replicate the ETL-system configuration in the Visier system, you choose to load the TA data using the Direct Intake API. Because you are - through the API - loading objects that are distinct from the 'Essential' ones, you are in effect supplementing the primary data flow in Visier, the appropriate Load Mode is therefore **Supplemental**.
3. Similar to the previous example, you already have an established and running data provisioning process for the 'Essential' objects in Visier. Your Data Science team has however been able to train an ML model that can predict 'risk of exit' better than anything you've seen before and you would like those predictions as new properties on the `Employee` object. After adding the properties in question to the object, you can now integrate Visier in your data pipeline so that these predictions are written back to the specific set of properties on `Employee` (which continues to get the bulk of the data as per the original, primary data provisioning process in Visier). Since you are extending the `Employee` object, the Load Mode in this case is **Extension**, that is supplemental, with `Employee` added to the list of objects that should be extended.

## Samples
* [Extension Table](extension-table/jupyter/name-rank-sample.ipynb) provides a sample in the form of a Jupyter notebook showing how query, enrich and write data back to Visier.
