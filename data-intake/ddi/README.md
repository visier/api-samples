# Direct Data Intake API
The Direct Data Intake API is suitable for Visier customers who have, at least in part, data to load into Visier that require no additional transformations. This is what makes this process 'direct'. In fact, the process is so streamlined that the column names in the source data files have match the names of the properties to load in the target objects.

## Load Modes
When provisioning data to Visier using the Data Direct API, it's important to understand the three available modes that correespond to the relationship Direct Data loading has to other means of provisioning data in you tenant.

The following diagram outlines these modes:
![Three Direct Data Intake API Load Modes](/assets/images/load-options.png)
* The **Primary**, which is also the default mode is where all objects are loaded using the Direct Data API method.
* When in **Supplemental** mode, some - but crucially, not all - objects are loaded exclusively using the Direct Data API.
* The **Extension** mode is the most complex one where, potentially in addition to loading objects entirely using the Direct Data API and other objects using other methods, you need to load at least one object from **both** Direct Data API and others. There are caveats:
    * The object in question is primarily loaded through a mechanism _other than_ Direct Data API.
    * The various load processes, including Direct Data API, must not attempt to load _the same properties_ on the object in question.

## Samples
* [Extension Table](extension-table/jupyter/name-rank-sample.ipynb) provides a sample in the form of a Jupyter notebook showing how query, enrich and write data back to Visier.